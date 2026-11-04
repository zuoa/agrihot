"""python -m scripts.editorial_backfill --dry-run --limit 20"""
import argparse
import asyncio
import json

from app.database import SessionLocal
from app.services.editorial_backfill import backfill


async def main():
    parser = argparse.ArgumentParser(description="补全近30天精选及当前专题文章的关注点与来源，不改评分")
    parser.add_argument("--batch-id", default="editorial-v1")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true", help="只预览，不调用模型、不写入数据库")
    args = parser.parse_args()

    async def report(stage, message, **details):
        print(message)

    result = await backfill(SessionLocal, **vars(args), report=report)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
