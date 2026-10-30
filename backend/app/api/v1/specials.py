"""Public special reads and authenticated editorial controls."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from ...database import get_session
from ...models import Item, Special, SpecialItem, SpecialVersion, utcnow
from ...security import require_admin
from ...special_schemas import MergeIn, SpecialPatch
from ...services import job_runner, special_service as service
from .public import _list_load_options, _to_item_out

router = APIRouter(prefix="/api/v1", tags=["specials"])


@router.get("/specials/featured")
async def featured(session: AsyncSession = Depends(get_session)):
    rows = await service.public_specials(session, featured=True)
    return {"specials": [service.brief(s, v) for s, v in rows[:3]]}


@router.get("/specials")
async def list_specials(
    page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=50),
    kind: str | None = Query(None, pattern="^(event|research)$"),
    status: str | None = Query(None, pattern="^(published|archived)$"),
    q: str | None = Query(None, max_length=100), item_id: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    rows = await service.public_specials(session, item_id=item_id, kind=kind, status=status, q=q)
    return {"total": len(rows), "page": page, "page_size": page_size,
            "specials": [service.brief(s, v) for s, v in rows[(page - 1) * page_size:page * page_size]]}


@router.get("/specials/{special_id}")
async def detail(
    special_id: int, page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=50),
    category: str | None = Query(None, max_length=20), session: AsyncSession = Depends(get_session),
):
    special = await session.get(Special, special_id)
    if special and special.status == "merged" and special.merged_into:
        seen = {special.id}
        target = await session.get(Special, special.merged_into)
        while target and target.status == "merged" and target.id not in seen:
            seen.add(target.id)
            target = await session.get(Special, target.merged_into)
        if not target or target.id in seen or target.status not in {"published", "archived"}:
            raise HTTPException(404, "目标专题尚未发布或已下架")
        return {"redirect_to": target.id}
    if not special or special.status not in {"published", "archived"}:
        raise HTTPException(404, "专题不存在或已下架")
    version = (await service.valid_versions(session, [special])).get(special.id)
    if not version:
        raise HTTPException(404, "专题来源正在重新核验")
    await session.refresh(version, attribute_names=["document", "sources"])
    internal = [s for s in version.sources if s["kind"] == "internal"]
    ids = [s["item_id"] for s in internal]
    items = (await session.scalars(select(Item).options(*_list_load_options(True)).where(Item.id.in_(ids)))).all()
    by_id = {i.id: i for i in items}
    # Core evidence first; latest articles first within each group.
    internal = sorted([s for s in internal if s["role"] == "core"], key=lambda s: s["published_at"] or "", reverse=True) + sorted(
        [s for s in internal if s["role"] != "core"], key=lambda s: s["published_at"] or "", reverse=True)
    filtered = [s for s in internal if not category or by_id[s["item_id"]].category == category]
    selected = filtered[(page - 1) * page_size:page * page_size]
    revisions = (await session.scalars(select(SpecialVersion).options(load_only(
        SpecialVersion.id, SpecialVersion.created_at, SpecialVersion.changes,
    )).where(SpecialVersion.special_id == special_id)
                                      .order_by(SpecialVersion.id.desc()).limit(20))).all()
    return {**service.brief(special, version), "version_id": version.id, "document": version.document,
            "sources": [{k: value for k, value in s.items() if k not in {"text", "hash"}} for s in version.sources],
            "articles": [{"role": s["role"], "reason": s["reason"], "item": _to_item_out(by_id[s["item_id"]], compact=True)} for s in selected],
            "total": len(filtered), "page": page, "page_size": page_size,
            "categories": sorted({i.category for i in items}),
            "updates": [{"date": v.created_at, "changes": v.changes} for v in revisions if v.id <= version.id],
            "changes": version.changes,
            "topics": list({link.topic_code: {"name": link.topic.name, "slug": link.topic.slug} for item in items
                            for link in item.topic_links if link.topic}.values())}


admin = APIRouter(prefix="/admin/specials", dependencies=[Depends(require_admin)], include_in_schema=False)


@admin.get("")
async def admin_list(page: int = Query(1, ge=1), session: AsyncSession = Depends(get_session)):
    rows = list((await session.scalars(select(Special).order_by(Special.id.desc()))).all())
    valid = await service.valid_versions(session, rows)
    return {"total": len(rows), "specials": [{"id": s.id, "title": s.title, "kind": s.kind, "status": s.status,
                                              "pinned": s.pinned, "locked_fields": s.locked_fields,
                                              "checked_at": s.checked_at, "content_updated_at": s.content_updated_at,
                                              "last_error": s.last_error, "external_status": s.external_status,
                                              "evidence_valid": s.id in valid} for s in rows[(page - 1) * 20:page * 20]]}


@admin.post("/generate")
async def generate():
    accepted = await job_runner.spawn("specials_generate")
    return {"accepted": accepted}


@admin.get("/{special_id}")
async def admin_detail(special_id: int, session: AsyncSession = Depends(get_session)):
    special = await session.get(Special, special_id)
    if not special:
        raise HTTPException(404, "专题不存在")
    versions = (await session.scalars(select(SpecialVersion).where(SpecialVersion.special_id == special_id).order_by(SpecialVersion.id.desc()).limit(20))).all()
    links = (await session.scalars(select(SpecialItem).where(SpecialItem.special_id == special_id))).all()
    return {"id": special.id, "title": special.title, "scope": special.scope, "kind": special.kind,
            "status": special.status, "pinned": special.pinned, "locked_fields": special.locked_fields,
            "external_status": special.external_status, "last_error": special.last_error,
            "document": versions[0].document if versions else None,
            "items": [{"item_id": l.item_id, "role": l.role, "reason": l.reason, "evidence_group": l.evidence_group} for l in links],
            "versions": [{"id": v.id, "date": v.created_at, "changes": v.changes} for v in versions],
            "sources": [{k: value for k, value in s.items() if k not in {"text", "hash"}} for s in versions[0].sources] if versions else []}


@admin.patch("/{special_id}")
async def edit(special_id: int, payload: SpecialPatch, session: AsyncSession = Depends(get_session)):
    special = await session.get(Special, special_id)
    if not special or special.status == "merged":
        raise HTTPException(404, "专题不存在或已合并")
    values = payload.model_dump(exclude_none=True)
    valid = await service.valid_versions(session, [special])
    if values.get("status") in {"published", "archived"} and special_id not in valid:
        raise HTTPException(422, "没有引用有效的发布版本，请先重新生成")
    if payload.document:
        if special_id not in valid:
            raise HTTPException(422, "来源已变更，请先重新生成")
        version = valid[special_id]
        await session.refresh(version, attribute_names=["document", "sources"])
        document = payload.document.model_dump()
        try:
            service.validate_evidence(document, version.sources)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        session.add(SpecialVersion(special_id=special_id, input_hash=service.digest(document), sources=version.sources,
                                   signatures=version.signatures, preview=service.preview(document, version.sources),
                                   document=document, changes="人工修订综合内容"))
        special.content_updated_at = utcnow()
    if payload.items:
        ids = {i.item_id for i in payload.items}
        exists = set((await session.scalars(select(Item.id).where(Item.id.in_(ids)))).all())
        if exists != ids:
            raise HTTPException(422, "关联文章不存在")
        await session.execute(delete(SpecialItem).where(SpecialItem.special_id == special_id))
        for item in payload.items:
            session.add(SpecialItem(special_id=special_id, **item.model_dump()))
    locks = set(payload.locked_fields if payload.locked_fields is not None else special.locked_fields)
    for field in ("title", "scope", "items", "document"):
        if field in values:
            locks.add(field)
    special.locked_fields = sorted(locks)
    for key in ("title", "scope", "status", "pinned"):
        if key in values:
            setattr(special, key, values[key])
    await session.commit()
    return {"ok": True}


@admin.post("/{special_id}/regenerate")
async def regenerate(special_id: int, session: AsyncSession = Depends(get_session)):
    special = await session.get(Special, special_id)
    if not special or special.status in {"withdrawn", "merged"}:
        raise HTTPException(404, "专题不存在或已下架")
    return {"accepted": await job_runner.spawn("specials_generate", {"special_id": special_id})}


@admin.post("/{special_id}/merge")
async def merge(special_id: int, payload: MergeIn, session: AsyncSession = Depends(get_session)):
    source, target = await session.get(Special, special_id), await session.get(Special, payload.target_id)
    if not source or not target or source.id == target.id or source.kind != target.kind or source.status == "merged" or target.status in {"merged", "withdrawn"}:
        raise HTTPException(422, "请选择同类型且未合并或下架的目标专题")
    links = (await session.scalars(select(SpecialItem).where(SpecialItem.special_id.in_([source.id, target.id])))).all()
    existing = {l.item_id for l in links if l.special_id == target.id}
    for link in links:
        if link.special_id == source.id and link.item_id not in existing:
            session.add(SpecialItem(special_id=target.id, item_id=link.item_id, role=link.role, reason=link.reason, evidence_group=link.evidence_group))
            existing.add(link.item_id)
    source.status, source.merged_into = "merged", target.id
    await session.commit()
    return {"ok": True, "target_id": target.id}


router.include_router(admin)
