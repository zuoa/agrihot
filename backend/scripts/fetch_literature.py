"""Manually run one OpenAlex literature poll + scoring/cards.
Usage: python -m scripts.fetch_literature
"""
import asyncio
import json
import logging

from app.database import ensure_schema
from app.services.literature_scheduler import run_once


async def main() -> None:
    await ensure_schema()
    stats = await run_once()
    print(json.dumps(
        {k: v for k, v in stats.items() if k != "created_ids"},
        ensure_ascii=False, indent=2,
    ))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
