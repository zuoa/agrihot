"""Public SEO endpoints: robots.txt, sitemap.xml."""
from fastapi import APIRouter

from ...services import read_cache, seo_service

router = APIRouter(tags=["seo"], include_in_schema=False)


@router.get("/robots.txt")
async def robots():
    return seo_service.robots_txt()


@router.get("/sitemap.xml")
async def sitemap():
    return await read_cache.get(("sitemap",), seo_service.sitemap_xml, ttl=300)
