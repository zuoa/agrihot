"""Classify all content writers while keeping imports independent of model setup."""
from types import SimpleNamespace

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value


def register_taxonomy_hooks():
    from ..models import Item, ItemClassification, ItemTopic, Tag, item_tags

    @event.listens_for(Session, "before_flush")
    def classify_changes(session, flush_context, instances):
        from .taxonomy_service import INPUT_FIELDS, _upsert_nodes, apply_result, classify, input_hash

        changed = [obj for obj in session.new | session.dirty if isinstance(obj, Item)
                   and (obj in session.new or any(inspect(obj).attrs[f].history.has_changes() for f in INPUT_FIELDS))]
        for item in changed:
            key = item.id if item.id else id(item)
            if key in session.info.get("taxonomy_suppressed", set()) or (item.classification and item.classification.locked):
                continue
            evidence_item = item
            if item not in session.new:
                fields = ["title", "summary", "summary_zh", "content"]
                current = session.connection().execute(select(*(getattr(Item, f) for f in fields))
                    .where(Item.id == item.id).with_for_update()).mappings().one()
                locked = session.connection().execute(select(ItemClassification.locked).where(ItemClassification.item_id == item.id)).scalar()
                if locked:
                    continue
                fresh_meta = session.execute(select(ItemClassification).where(ItemClassification.item_id == item.id)
                    .execution_options(populate_existing=True)).scalar_one_or_none()
                fresh_links = list(session.execute(select(ItemTopic).where(ItemTopic.item_id == item.id)
                    .execution_options(populate_existing=True)).scalars())
                set_committed_value(item, "classification", fresh_meta)
                set_committed_value(item, "topic_links", fresh_links)
                values = {f: getattr(item, f) if inspect(item).attrs[f].history.has_changes() else current[f] for f in fields}
                if inspect(item).attrs.tags.history.has_changes():
                    values["tags"] = item.tags
                else:
                    names = session.connection().execute(select(Tag.name).join(item_tags, item_tags.c.tag_id == Tag.id).where(item_tags.c.item_id == item.id)).scalars()
                    values["tags"] = [SimpleNamespace(name=n) for n in names]
                evidence_item = SimpleNamespace(**values)
            if not session.info.get("taxonomy_seeded"):
                _upsert_nodes(session.connection())
                session.info["taxonomy_seeded"] = True
            if item in session.new:
                item.topic_links = []
                item.classification = None
            apply_result(session, item, classify(evidence_item))
            item.classification.input_hash = input_hash(evidence_item)

    @event.listens_for(Session, "after_flush_postexec")
    def clear_suppression(session, flush_context):
        session.info.pop("taxonomy_suppressed", None)

    @event.listens_for(Session, "after_commit")
    @event.listens_for(Session, "after_rollback")
    def clear_state(session):
        session.info.pop("taxonomy_seeded", None)
        session.info.pop("taxonomy_suppressed", None)
