"""Resume or rebuild Agent search indexes: python -m scripts.reindex [--force] [--run]."""
import argparse
import asyncio
import json

from app.database import SessionLocal, ensure_schema
from app.services.search_index_service import enqueue_backfill, process_one, status


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="recheck hashes and retry failed items; unchanged successful embeddings are reused")
    parser.add_argument("--run", action="store_true", help="process the pending queue once, then exit")
    args = parser.parse_args()
    await ensure_schema()
    async with SessionLocal() as session:
        print(f"Queued: {await enqueue_backfill(session, force=args.force)}")
    if args.run:
        while await process_one():
            pass
    async with SessionLocal() as session:
        print(json.dumps(await status(session), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
