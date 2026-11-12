"""Bounded, resumable reading-aid backfill; never changes scores or selection."""
import json
from datetime import timedelta

from sqlalchemy import and_, case, exists, or_, select

from ..config import settings
from ..models import Item, PipelineState, Special, SpecialItem, utcnow
from . import editorial_service as editorial, scoring_service


async def backfill(factory, *, batch_id="editorial-v1", limit=20, dry_run=False, report=None):
    if not 1 <= limit <= 1000:
        raise ValueError("limit 必须在 1–1000 之间")
    key = f"editorial_backfill:{batch_id}"
    async with factory() as session:
        saved = await session.get(PipelineState, key)
        state = json.loads(saved.value) if saved else {"cursor": 0, "failed_ids": [], "since": (utcnow() - timedelta(days=30)).isoformat()}
        from datetime import datetime
        scope = or_(and_(Item.is_selected.is_(True), Item.created_at >= datetime.fromisoformat(state["since"])),
                    exists(select(SpecialItem.item_id).join(Special, Special.id == SpecialItem.special_id)
                           .where(SpecialItem.item_id == Item.id, Special.status == "published")))
        ids = list((await session.scalars(select(Item.id).where(scope, or_(Item.id > state["cursor"], Item.id.in_(state["failed_ids"])))
                                         .order_by(case((Item.id > state["cursor"], 0), else_=1), Item.id).limit(limit))).all())
    stats = {"total": len(ids), "generated": 0, "skipped": 0, "failed": 0, "dry_run": dry_run, "batch_id": batch_id}
    if not dry_run and not settings.deepseek_api_key:
        raise ValueError("DEEPSEEK_API_KEY 未配置，无法补全关注点与来源")
    for item_id in ids:
        error = None
        usage = {}
        async with factory() as session:
            item = await session.get(Item, item_id)
            if item is None:
                stats["skipped"] += 1
                continue
            expected = editorial.fingerprint(item)
            meta = item.editorial_meta or {}
            complete = meta.get("version") == editorial.VERSION and meta.get("input_hash") == expected
            locked = meta.get("attention_locked") and meta.get("provenance_locked")
            await session.commit()  # release DB connection before network
            if complete or locked or dry_run:
                stats["skipped"] += 1
            else:
                try:
                    raw = await scoring_service._call_deepseek(item)
                    usage = scoring_service.last_usage.get() or {}
                    data = json.loads(raw) if raw else None
                    if not isinstance(data, dict) or "attention_point" not in data or "source_provenance" not in data:
                        raise ValueError("模型未返回完整阅读辅助字段")
                    await session.refresh(item, with_for_update={"of": Item})
                    if editorial.apply_model(item, data, expected_hash=expected):
                        await session.commit()
                        stats["generated"] += 1
                    else:
                        raise ValueError("文章在生成期间发生变化，等待重试")
                except (ValueError, TypeError) as exc:
                    await session.rollback()
                    error = str(exc)
                    stats["failed"] += 1
        if not dry_run:
            state["cursor"] = max(state["cursor"], item_id)
            failed = set(state["failed_ids"])
            failed.add(item_id) if error else failed.discard(item_id)
            state["failed_ids"] = sorted(failed)
            async with factory() as session:
                record = await session.get(PipelineState, key)
                if record is None:
                    record = PipelineState(key=key, value="")
                    session.add(record)
                record.value = json.dumps(state)
                record.updated_at = utcnow()
                await session.commit()
        if report:
            await report("editorial", f"文章 {item_id}：{error or ('预览' if dry_run else '已处理')}",
                         level="warning" if error else "info", item_id=item_id, **stats, **usage)
    stats["cursor"] = state["cursor"]
    return stats
