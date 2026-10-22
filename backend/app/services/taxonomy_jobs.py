"""Resumable classification batches, previews and conditional rollback."""
import json
import uuid
from collections import Counter

from sqlalchemy import func, select

from ..models import ClassificationChange, Item, PipelineState
from .taxonomy_catalog import catalog
from .taxonomy_service import apply_result, classify, classify_one, definitions, snapshot


async def backfill(factory, *, dry_run=False, batch_id=None, batch_size=100, after_id=0,
                   limit=None, use_model=False, force=False, progress=None):
    if not 1 <= batch_size <= 500:
        raise ValueError("batch_size 应为 1–500")
    if use_model and not dry_run:
        from ..config import settings
        if not settings.deepseek_api_key:
            raise ValueError("未配置 DEEPSEEK_API_KEY，不能启用模型补判")
    batch_id = batch_id or ("taxonomy-" + uuid.uuid4().hex)
    state_key = "taxonomy:" + batch_id
    counts = Counter()
    previews = []
    async with factory() as session:
        checkpoint = await session.get(PipelineState, state_key)
        state = json.loads(checkpoint.value) if checkpoint else {}
        if state and state["version"] != catalog()["version"]:
            raise ValueError("规则版本已变化，请使用新的 batch_id")
        if state and bool(state.get("use_model")) != bool(use_model):
            raise ValueError("恢复批次时 use_model 必须与原批次一致")
        upper_id = state.get("upper_id") or (await session.execute(select(func.max(Item.id)))).scalar() or 0
        cursor = max(after_id, state.get("last_id", 0))
        counts.update(state.get("counts", {}))
        remaining = (await session.execute(select(func.count(Item.id)).where(Item.id > cursor, Item.id <= upper_id))).scalar_one()
        if limit is not None:
            remaining = min(remaining, limit)
    processed = 0
    while cursor < upper_id and (limit is None or processed < limit):
        async with factory() as session:
            size = min(batch_size, limit - processed) if limit is not None else batch_size
            ids = list((await session.execute(select(Item.id).where(Item.id > cursor, Item.id <= upper_id).order_by(Item.id).limit(size))).scalars())
        if not ids:
            break
        for item_id in ids:
            async with factory() as session:
                # One article per transaction keeps the admin editor responsive.
                item = (await session.execute(select(Item).where(Item.id == item_id).with_for_update())).scalar_one_or_none()
                if item is None:
                    counts["missing"] += 1
                elif item.classification and item.classification.locked:
                    counts["locked"] += 1
                elif dry_run:
                    result = classify(item)
                    counts[result["status"]] += 1
                    if len(previews) < 30:
                        previews.append({"id": item.id, "title": item.title, **result})
                else:
                    changed = await classify_one(session, item, batch_id=batch_id, use_model=use_model, force=force)
                    counts["changed" if changed else "unchanged"] += 1
                    counts[item.classification.status] += 1
                cursor, processed = item_id, processed + 1
                if not dry_run:
                    row = await session.get(PipelineState, state_key)
                    if row is None:
                        row = PipelineState(key=state_key)
                        session.add(row)
                    row.value = json.dumps({"version": catalog()["version"], "use_model": use_model, "upper_id": upper_id,
                                            "last_id": cursor, "counts": dict(counts)}, ensure_ascii=False)
                    await session.commit()
                else:
                    await session.rollback()
            if progress:
                await progress(processed, remaining)
    return {"batch_id": batch_id, "version": catalog()["version"], "dry_run": dry_run,
            "last_id": cursor, "upper_id": upper_id, "processed": processed, **dict(counts), "previews": previews}


async def rollback(factory, batch_id):
    restored = skipped = 0
    async with factory() as session:
        ids = list((await session.execute(select(ClassificationChange.id).where(ClassificationChange.batch_id == batch_id)
                   .order_by(ClassificationChange.id.desc()))).scalars())
    for change_id in ids:
        async with factory() as session:
            change = await session.get(ClassificationChange, change_id)
            item = (await session.execute(select(Item).where(Item.id == change.item_id).with_for_update())).scalar_one_or_none()
            if not item or (item.classification and item.classification.locked) or snapshot(item) != change.after:
                skipped += 1
                continue
            before = change.before
            if any(code not in definitions() for code, _ in before["links"]):
                skipped += 1
                continue
            meta = before["classification"]
            result = {"primary": next((code for code, primary in before["links"] if primary), None),
                      "secondary": [code for code, primary in before["links"] if not primary],
                      "status": meta["status"] if meta else "unclassified", "evidence": meta["evidence"] if meta else {}}
            await session.run_sync(lambda s: apply_result(s, item, result))
            if meta:
                for key, value in meta.items():
                    setattr(item.classification, key, value)
            else:
                await session.delete(item.classification)
                item.classification = None
            session.add(ClassificationChange(batch_id="rollback:" + batch_id, item_id=item.id, before=change.after, after=before))
            await session.commit()
            restored += 1
    return {"batch_id": batch_id, "restored": restored, "skipped": skipped}
