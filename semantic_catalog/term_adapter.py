import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from semantic_catalog.runtime import SemanticCatalog


_DISABLED_VALUES = {"0", "false", "no", "off"}
_FEATURE_DIMENSION_HINTS = {
    "aida",
    "aidas",
    "aida_english",
    "top_aida",
    "product_area",
    "module",
    "domain",
    "service",
}


def is_semantic_catalog_enabled() -> bool:
    raw = str(os.getenv("AGENT_SEMANTIC_CATALOG_ENABLED", "1") or "1").strip().lower()
    return raw not in _DISABLED_VALUES


def _is_db_semantic_enabled() -> bool:
    raw = str(os.getenv("AGENT_DB_SEMANTIC_ENABLED", "1") or "1").strip().lower()
    return raw not in _DISABLED_VALUES


def _extract_month_number(question: str) -> Optional[int]:
    q = str(question or "")

    zh_match = re.search(r"(?<!\d)(1[0-2]|0?[1-9])\s*月", q)
    if zh_match:
        try:
            month = int(zh_match.group(1))
            if 1 <= month <= 12:
                return month
        except Exception:
            pass

    lower = q.lower()
    month_map = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    for name, month in month_map.items():
        if re.search(rf"\b{name}\b", lower):
            return month
    return None


def _contains_phrase(text_lower: str, phrase: str) -> bool:
    p = str(phrase or "").strip().lower()
    if not p:
        return False
    if p.isascii() and re.fullmatch(r"[a-z0-9_\-\s]+", p):
        return re.search(rf"(?<![a-z0-9_]){re.escape(p)}(?![a-z0-9_])", text_lower) is not None
    return p in text_lower


def _select_datasets(catalog: Dict[str, Any], table_name: str = "") -> List[Dict[str, Any]]:
    datasets = [d for d in (catalog.get("datasets") or []) if isinstance(d, dict)]
    if not datasets:
        return []

    table = str(table_name or "").strip().lower()
    if not table:
        return datasets

    selected: List[Dict[str, Any]] = []
    for ds in datasets:
        ds_id = str(ds.get("id") or "").strip().lower()
        aliases = [str(a or "").strip().lower() for a in (ds.get("aliases") or []) if str(a or "").strip()]
        if table == ds_id or table in aliases:
            selected.append(ds)
    return selected or datasets


def _collect_dimension_aliases(datasets: Sequence[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    pairs: List[Tuple[str, str, str]] = []
    for ds in datasets:
        ds_id = str(ds.get("id") or "").strip()
        dimensions = ds.get("core_dimensions") or []
        if not isinstance(dimensions, list):
            continue
        for dim in dimensions:
            if not isinstance(dim, dict):
                continue
            canonical = str(dim.get("name") or "").strip()
            if not canonical:
                continue
            aliases = [canonical]
            aliases.extend([str(a or "").strip() for a in (dim.get("aliases") or []) if str(a or "").strip()])
            for alias in aliases:
                alias_lower = alias.lower()
                if not alias_lower:
                    continue
                # Avoid very short ASCII aliases like "id" that produce noisy matches.
                if alias_lower.isascii() and len(alias_lower) <= 2:
                    continue
                pairs.append((alias_lower, canonical, ds_id))

    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return pairs


def _collect_rule_terms(catalog: Dict[str, Any]) -> List[Tuple[str, str]]:
    terms: List[Tuple[str, str]] = []
    for rule in (catalog.get("business_rules") or []):
        if not isinstance(rule, dict):
            continue
        rule_id = str(rule.get("id") or "").strip()
        if not rule_id:
            continue
        candidates = []
        candidates.extend([str(t or "").strip() for t in (rule.get("trigger_terms") or []) if str(t or "").strip()])
        candidates.extend([str(t or "").strip() for t in (rule.get("aliases") or []) if str(t or "").strip()])
        for term in candidates:
            t_lower = term.lower()
            if not t_lower:
                continue
            if t_lower.isascii() and len(t_lower) <= 2:
                continue
            terms.append((t_lower, rule_id))

    terms.sort(key=lambda x: len(x[0]), reverse=True)
    return terms


def merge_semantic_hints(*hints_list: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for hints in hints_list:
        if not isinstance(hints, dict):
            continue

        for key in ["wants_feature_breakdown", "wants_aida_dist", "wants_showstopper", "wants_showstopper_candidate"]:
            if bool(hints.get(key)):
                merged[key] = True

        if merged.get("month_number") is None:
            month = hints.get("month_number")
            if isinstance(month, int) and 1 <= month <= 12:
                merged["month_number"] = month

        preferred_dimension = str(hints.get("preferred_dimension") or "").strip()
        if preferred_dimension and not str(merged.get("preferred_dimension") or "").strip():
            merged["preferred_dimension"] = preferred_dimension

        for list_key in ["mapped_dimensions", "matched_rule_ids", "entity_tokens"]:
            values = hints.get(list_key)
            if not isinstance(values, list):
                continue
            acc = merged.setdefault(list_key, [])
            if not isinstance(acc, list):
                acc = []
                merged[list_key] = acc
            for value in values:
                text = str(value or "").strip()
                if text and text not in acc:
                    acc.append(text)

    return merged


def adapt_question_with_semantic_terms(
    question: str,
    *,
    table_name: str = "",
    db_path: Optional[str] = None,
    prefer_db: Optional[bool] = None,
) -> Dict[str, Any]:
    q = str(question or "").strip()
    out: Dict[str, Any] = {
        "original_question": q,
        "normalized_question": q,
        "semantic_hints": {},
        "mapped_dimensions": [],
        "matched_rule_ids": [],
        "provenance": [],
    }
    if not q:
        return out

    if not is_semantic_catalog_enabled():
        return out

    if prefer_db is None:
        prefer_db = bool(db_path)

    catalog: Dict[str, Any] = {}
    try:
        catalog = SemanticCatalog(db_path=db_path, prefer_db=bool(prefer_db)).load_catalog()
    except Exception as exc:
        out["error"] = f"semantic_catalog_load_failed: {exc}"
        return out

    selected_datasets = _select_datasets(catalog, table_name=table_name)
    alias_rows = _collect_dimension_aliases(selected_datasets)
    rule_rows = _collect_rule_terms(catalog)

    q_lower = q.lower()
    matched_dimensions: List[str] = []
    matched_rule_ids: List[str] = []
    provenance: List[Dict[str, str]] = []

    for alias, canonical, dataset_id in alias_rows:
        if _contains_phrase(q_lower, alias):
            if canonical not in matched_dimensions:
                matched_dimensions.append(canonical)
            provenance.append({
                "type": "dimension_alias",
                "alias": alias,
                "canonical": canonical,
                "dataset": dataset_id,
            })

    for term, rule_id in rule_rows:
        if _contains_phrase(q_lower, term):
            if rule_id not in matched_rule_ids:
                matched_rule_ids.append(rule_id)
            provenance.append({
                "type": "business_rule",
                "term": term,
                "rule_id": rule_id,
            })

    asks_feature_breakdown = any(token in q_lower for token in ["功能", "哪些功能", "模块", "feature", "features", "module", "service", "aida"])
    asks_showstopper = any(token in q_lower for token in ["showstopper", "show stopper", "候选", "candidate"])

    preferred_dimension = ""
    for candidate in ["top_aida", "aida_english", "aida", "product_area", "service", "module", "domain"]:
        if candidate in matched_dimensions:
            preferred_dimension = candidate
            break

    if not preferred_dimension and asks_feature_breakdown:
        preferred_dimension = "top_aida"

    hints = {
        "wants_feature_breakdown": bool(asks_feature_breakdown or (set(matched_dimensions) & _FEATURE_DIMENSION_HINTS)),
        "wants_aida_dist": bool(asks_feature_breakdown or (set(matched_dimensions) & _FEATURE_DIMENSION_HINTS)),
        "wants_showstopper": bool(asks_showstopper or ("br_defect_critical_classification_default" in matched_rule_ids)),
        "wants_showstopper_candidate": bool(("candidate" in q_lower) or ("候选" in q_lower)),
        "month_number": _extract_month_number(q),
        "preferred_dimension": preferred_dimension,
        "mapped_dimensions": matched_dimensions,
        "matched_rule_ids": matched_rule_ids,
    }

    normalized_tokens: List[str] = []
    if hints["wants_aida_dist"] and "aida" not in q_lower:
        normalized_tokens.append("aida")
    if hints["wants_showstopper"] and "showstopper" not in q_lower:
        normalized_tokens.append("showstopper")
    if hints["wants_showstopper_candidate"] and "candidate" not in q_lower:
        normalized_tokens.append("candidate")
    if isinstance(hints.get("month_number"), int):
        normalized_tokens.append(f"month={int(hints['month_number']):02d}")
    if preferred_dimension:
        normalized_tokens.append(f"dimension={preferred_dimension}")

    normalized_question = q
    if normalized_tokens:
        normalized_question = f"{q}\n\nsemantic_terms: {' '.join(sorted(set(normalized_tokens)))}"

    out.update(
        {
            "normalized_question": normalized_question,
            "semantic_hints": hints,
            "mapped_dimensions": matched_dimensions,
            "matched_rule_ids": matched_rule_ids,
            "provenance": provenance[:40],
            "db_semantic_enabled": _is_db_semantic_enabled(),
        }
    )
    return out
