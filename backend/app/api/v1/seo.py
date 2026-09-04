"""Public SEO endpoints: robots.txt, sitemap.xml, crawler HTML."""
from datetime import date as date_type

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_session
from ...services import seo_service

router = APIRouter(tags=["seo"], include_in_schema=False)


@router.get("/robots.txt")
async def robots():
    return seo_service.robots_txt()


@router.get("/sitemap.xml")
async def sitemap(session: AsyncSession = Depends(get_session)):
    return await seo_service.sitemap_xml(session)


@router.get("/seo")
@router.get("/seo/")
async def seo_home(
    category: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    return await seo_service.page_home(session, category)


@router.get("/seo/feed")
async def seo_feed(
    category: str | None = None,
    direction: str | None = None,
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    session: AsyncSession = Depends(get_session),
):
    return await seo_service.page_feed(
        session, category=category, direction=direction, q=q, page=page
    )


@router.get("/seo/dailies")
async def seo_dailies(session: AsyncSession = Depends(get_session)):
    return await seo_service.page_dailies(session)


@router.get("/seo/dailies/{day}")
async def seo_daily(day: date_type, session: AsyncSession = Depends(get_session)):
    return await seo_service.page_daily(session, day)


@router.get("/seo/items/{item_id}")
async def seo_item(item_id: int, session: AsyncSession = Depends(get_session)):
    return await seo_service.page_item(session, item_id)


@router.get("/seo/tags")
async def seo_tags(session: AsyncSession = Depends(get_session)):
    return await seo_service.page_tags(session)


@router.get("/seo/tags/{name}")
async def seo_tag(name: str, session: AsyncSession = Depends(get_session)):
    return await seo_service.page_tag(session, name)


@router.get("/seo/about")
async def seo_about():
    return seo_service.page_about()


@router.get("/seo/agent")
async def seo_agent():
    return seo_service.page_agent()


@router.get("/seo/{rest:path}")
async def seo_fallback(rest: str):
    path = "/" + rest if rest else "/"
    return seo_service.page_not_found(path)
