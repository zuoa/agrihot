"""Backfill AI scores for items that have none (score IS NULL).
Usage: python -m scripts.rescore          # all unscored items
       python -m scripts.rescore --all    # re-score everything
Requires DEEPSEEK_API_KEY.
"""
import asyncio
import sys

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal, engine
from app.models import Base, Item
from app.services import scoring_service


async def main() -> None:
    if not settings.deepseek_api_key:
        print("DEEPSEEK_API_KEY 未配置，退出")
        return
    rescore_all = "--all" in sys.argv

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        stmt = select(Item).order_by(Item.id)
        if not rescore_all:
            stmt = stmt.where(Item.score.is_(None))
        items = (await session.execute(stmt)).scalars().all()
        print(f"待评分 {len(items)} 条")
        days = set()
        for item in items:
            total = await scoring_service.score_item(session, item)
            days.add(item.created_at.replace(hour=0, minute=0, second=0, microsecond=0))
            mark = f"{total} 分" if total is not None else "评分失败"
            print(f"  [{item.id}] {item.title[:36]} ... {mark}")
        for day in days:  # 重算每天 Top-N 精选名单
            await scoring_service.refresh_day_selection(session, day)
        await session.commit()
        selected = sum(1 for i in items if i.is_selected)
        print(f"完成：{selected} 条进入精选")


if __name__ == "__main__":
    asyncio.run(main())
