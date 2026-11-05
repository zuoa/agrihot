"""DB definition overlay and deletion markers for packaged collection sources."""
import hashlib
import json
from dataclasses import asdict

from sqlalchemy import select

from ..models import PipelineState, utcnow
from ..source_schemas import SourceDefinitionIn
from .source_adapters import Source

CONFIG_PREFIX = "source_definition:"


def fingerprint(source: Source) -> str:
    data = asdict(source)
    for key in ("id", "enabled", "managed"):
        data.pop(key, None)
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def from_definition(source_id: str, definition: SourceDefinitionIn) -> Source:
    return Source(id=source_id, managed=True, **definition.model_dump())


async def definitions(session) -> dict:
    rows = (await session.execute(select(PipelineState.key, PipelineState.value, PipelineState.updated_at).where(
        PipelineState.key.startswith(CONFIG_PREFIX),
    ))).all()
    return {row.key[len(CONFIG_PREFIX):]: {"data": json.loads(row.value), "updated_at": row.updated_at} for row in rows}


async def merged_sources(session, defaults: list[Source]) -> list[Source]:
    result = {source.id: source for source in defaults}
    for source_id, record in (await definitions(session)).items():
        data = record["data"]
        if data.get("deleted"):
            result.pop(source_id, None)
        else:
            result[source_id] = from_definition(source_id, SourceDefinitionIn.model_validate(data))
    return list(result.values())


async def store_definition(session, source_id: str, data: dict) -> None:
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    statement = insert(PipelineState).values(key=CONFIG_PREFIX + source_id,
                                            value=json.dumps(data, ensure_ascii=False), updated_at=utcnow())
    await session.execute(statement.on_conflict_do_update(index_elements=[PipelineState.key], set_={
        "value": statement.excluded.value, "updated_at": statement.excluded.updated_at,
    }, where=PipelineState.value != statement.excluded.value))
