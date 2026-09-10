"""Public SEO endpoints: robots.txt, sitemap.xml."""
from fastapi import APIRouter, Depends
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
