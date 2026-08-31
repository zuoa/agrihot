"""Re-split existing tags that were stored as concatenated keyword blobs.

Usage: python -m scripts.retag           # apply
       python -m scripts.retag --dry-run # print diffs only

Idempotent: already-normalized tags are left unchanged. Orphan Tag rows
(no remaining items) are deleted after reassignment.
Startup also runs this automatically when blob tags are detected.
"""
from __future__ import annotations

import asyncio
import sys

from app.database import SessionLocal, engine
from app.models import Base
from app.services.ingest_service import retag_all_items


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        stats = await retag_all_items(session, dry_run=dry_run)
        for item_id, old, new in stats["diffs"]:
            print(f"  [{item_id}] {old} → {new}")
        if not dry_run:
            await session.commit()

        mode = "dry-run" if dry_run else "applied"
        extra = f"，删除孤儿 {stats['orphans']}" if not dry_run else ""
        print(
            f"完成（{mode}）：{stats['items']} 条中 {stats['changed']} 条标签被切开；"
            f"标签 {stats['tags_before']} → {stats['tags_after']}{extra}"
        )


if __name__ == "__main__":
    asyncio.run(main())
