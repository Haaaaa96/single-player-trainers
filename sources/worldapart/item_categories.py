"""Shared display names for the game's item-type metadata; no ID mapping."""
from collections.abc import Mapping

ALL_CATEGORIES = "全部分类"
UNKNOWN_CATEGORY = "未知分类"


def category_name(definition):
    """Use reviewed localized type names, or an already-formatted row label.

    Missing display metadata does not alter item quantity limits or eligibility.
    Both inventory and the full acquisition catalogue use this same fallback.
    """
    if not isinstance(definition, Mapping):
        return UNKNOWN_CATEGORY
    names = definition.get("type_names")
    if isinstance(names, Mapping):
        for language in ("zh-Hans", "en-US"):
            value = names.get(language)
            if isinstance(value, str) and value.strip():
                return value.strip()
    value = definition.get("type_name")
    return value.strip() if isinstance(value, str) and value.strip() else UNKNOWN_CATEGORY
