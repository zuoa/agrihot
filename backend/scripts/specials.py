"""Preview/generate specials: --dry-run discovers without writes; --id refreshes one."""
import argparse
import asyncio
import json

from app.database import SessionLocal
from app.services import runtime_settings
from app.services.special_service import run_once


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--id", type=int)
    args = parser.parse_args()
    async with SessionLocal() as session:
        await runtime_settings.load(session)
    result = await run_once(special_id=args.id, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
