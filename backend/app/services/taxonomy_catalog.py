"""Versioned editorial vocabulary. No database or network dependencies."""
from functools import lru_cache
from pathlib import Path
import re

import yaml


@lru_cache(maxsize=1)
def catalog() -> dict:
    data = yaml.safe_load((Path(__file__).parents[1] / "taxonomy.yaml").read_text(encoding="utf-8"))
    nodes = data["topics"]
    codes = {n["code"] for n in nodes}
    slugs = {n["slug"] for n in nodes}
    if len(codes) != len(nodes) or len(slugs) != len(nodes):
        raise ValueError("主题 code 和 slug 必须唯一")
    parents = {n["code"]: n.get("parent_code") for n in nodes}
    for node in nodes:
        parent = node.get("parent_code")
        if parent and (parent not in parents or parents[parent]):
            raise ValueError("主题只允许两级，父级必须存在")
    aliases = data.get("aliases", {})
    if any(name == target or target in aliases for name, target in aliases.items()):
        raise ValueError("别名必须直接指向规范词，不能形成链或循环")
    return data


def canonical_name(name: str) -> str:
    return catalog().get("aliases", {}).get(name, name)


def equivalent_names(name: str) -> list[str]:
    canonical = canonical_name(name)
    return [canonical, *(a for a, target in catalog().get("aliases", {}).items() if target == canonical)]


def tag_properties(name: str) -> tuple[str, str]:
    data = catalog()
    if name in data["hidden_tags"]:
        return "keyword", "hidden"
    if name in data["technologies"]:
        return "technology", "active"
    if name in data["regions"]:
        return "region", "active"
    if name in data["aliases"].values() or re.search(r"农科院|农业科学院|研究所$|大学$", name):
        return "organization", "active" if name in data["aliases"].values() else "candidate"
    known = any(name in n.get("terms", []) for n in data["topics"])
    return "keyword", "active" if known else "candidate"


def text_matches(term: str, text: str) -> bool:
    """Latin tokens need word boundaries: 'rice' must not match 'price'."""
    if re.search(r"[\u4e00-\u9fff]", term):
        if term == "葡萄":
            text = text.replace("葡萄糖", "")
        return term in text
    return re.search(r"(?<![a-z0-9])" + re.escape(term.casefold()) + r"(?![a-z0-9])", text.casefold()) is not None
