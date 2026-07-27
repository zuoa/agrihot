"""Create / rotate API keys. Usage:
    python -m scripts.create_api_key <name>          # generates a random key
    python -m scripts.create_api_key <name> --key <raw-key>
The raw key is printed ONCE; only its sha256 is stored.
"""
import argparse
import asyncio
import secrets

from sqlalchemy import select

from app.database import SessionLocal, engine
from app.models import ApiKey, Base, hash_api_key


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="key owner, e.g. crawler-policy-bot")
    parser.add_argument("--key", help="use this raw key instead of a random one")
    args = parser.parse_args()

    raw = args.key or f"agri_{secrets.token_urlsafe(32)}"

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        existing = (
            await session.execute(
                select(ApiKey).where(ApiKey.key_hash == hash_api_key(raw))
            )
        ).scalar_one_or_none()
        if existing:
            print(f"key already exists (owner: {existing.name})")
            return
        session.add(ApiKey(key_hash=hash_api_key(raw), name=args.name))
        await session.commit()

    print("API Key created (store it safely, it cannot be retrieved later):")
    print(f"  name: {args.name}")
    print(f"  key:  {raw}")


if __name__ == "__main__":
    asyncio.run(main())
