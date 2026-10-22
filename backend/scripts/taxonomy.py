"""python -m scripts.taxonomy sync|backfill|rollback. Never changes scoring."""
import argparse
import asyncio
import json
from pathlib import Path

from app.database import SessionLocal, ensure_schema
from app.services.taxonomy_jobs import backfill, rollback
from app.services.taxonomy_service import sync_catalog


async def run(args):
    if args.command == "sync":
        await ensure_schema()
        async with SessionLocal() as session:
            await sync_catalog(session)
            await session.commit()
        result = {"status": "synced"}
    elif args.command == "backfill":
        result = await backfill(SessionLocal, dry_run=args.dry_run, batch_id=args.batch_id,
                                batch_size=args.batch_size, after_id=args.after_id, limit=args.limit,
                                use_model=args.use_model, force=args.force)
    else:
        result = await rollback(SessionLocal, args.batch_id)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(output + "\n", encoding="utf-8")
    print(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync", help="迁移结构并同步字典；不回填历史文章")
    fill = sub.add_parser("backfill", help="独立回填分类，支持断点续跑")
    fill.add_argument("--dry-run", action="store_true", help="仅预览规则结果，不调用模型、不写分类或断点")
    fill.add_argument("--batch-id", help="恢复批次时传原 batch_id")
    fill.add_argument("--batch-size", type=int, default=100)
    fill.add_argument("--after-id", type=int, default=0)
    fill.add_argument("--limit", type=int)
    fill.add_argument("--use-model", action="store_true", help="仅对规则待复核结果调用 DeepSeek（产生 API 用量）")
    fill.add_argument("--force", action="store_true", help="重算相同版本；仍保护人工锁定")
    undo = sub.add_parser("rollback", help="撤回指定批次，跳过之后有改动的文章")
    undo.add_argument("batch_id")
    for command in (sync, fill, undo):
        command.add_argument("--report", help="保存 JSON 报告")
    args = parser.parse_args()
    if args.command == "backfill" and (args.after_id < 0 or (args.limit is not None and args.limit < 1)):
        parser.error("after-id 必须非负，limit 必须大于 0")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
