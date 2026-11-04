"""Collect fixed sources; --dry-run previews live candidates without any DB writes."""
import argparse
import asyncio
import json
import logging

from app.database import ensure_schema
from app.services import job_runner, runtime_settings, watchlist_service
from app.services.source_service import run_once
from app.database import SessionLocal


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source-id")
    parser.add_argument("--limit", type=int, default=5, help="Preview candidates per source (1–50)")
    args = parser.parse_args()
    if not 1 <= args.limit <= 50:
        parser.error("--limit must be between 1 and 50")
    if args.dry_run:
        stats = await run_once(dry_run=True, source_id=args.source_id, preview_limit=args.limit)
    else:
        await ensure_schema()
        async with SessionLocal() as session:
            await runtime_settings.load(session)
            await watchlist_service.load_from_db(session)
        result = await job_runner.run("sources_fetch", {"source_id": args.source_id})
        stats = result.get("stats") or result
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if stats.get("errors") or stats.get("status") == "error":
        raise SystemExit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
