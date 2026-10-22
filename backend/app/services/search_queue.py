"""ORM change hooks shared by the web app and maintenance scripts."""
from sqlalchemy import delete, event, inspect
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

_CONTENT_FIELDS = {"title", "summary", "summary_zh", "content", "tags", "search_phrases"}


def register_queue_hooks():
    # Called after model declarations, without importing the engine or worker.
    from ..models import Item, PaperMeta, SearchChunk, SearchJob, utcnow

    @event.listens_for(Session, "before_flush")
    def collect_changes(session, flush_context, instances):
        changed = session.info.setdefault("search_changed", set())
        deleted = session.info.setdefault("search_deleted", set())
        for obj in session.new | session.dirty:
            if isinstance(obj, Item) and (obj in session.new or any(inspect(obj).attrs[f].history.has_changes() for f in _CONTENT_FIELDS)):
                changed.add(obj)
            elif isinstance(obj, PaperMeta) and obj.item_id:
                changed.add(obj.item_id)
        for obj in session.deleted:
            if isinstance(obj, Item):
                deleted.add(obj.id)
                session.connection().execute(delete(SearchChunk).where(SearchChunk.item_id == obj.id))
                session.connection().execute(delete(SearchJob).where(SearchJob.item_id == obj.id))

    @event.listens_for(Session, "after_flush_postexec")
    def queue_changes(session, flush_context):
        deleted = session.info.pop("search_deleted", set())
        ids = {o if isinstance(o, int) else o.id for o in session.info.pop("search_changed", set())} - deleted
        if not ids:
            return
        connection = session.connection()
        insert = pg_insert if connection.dialect.name == "postgresql" else sqlite_insert
        for item_id in ids:
            stmt = insert(SearchJob).values(item_id=item_id, status="pending", revision=1, updated_at=utcnow())
            connection.execute(stmt.on_conflict_do_update(index_elements=[SearchJob.item_id], set_={
                "status": "pending", "revision": SearchJob.revision + 1, "attempts": 0,
                "retry_at": None, "error": None, "updated_at": utcnow(),
            }))

    @event.listens_for(Session, "after_rollback")
    def discard_changes(session):
        session.info.pop("search_changed", None)
        session.info.pop("search_deleted", None)
