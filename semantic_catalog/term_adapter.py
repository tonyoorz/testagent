import os
import re
from collections import OrderedDict
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

_GENERIC_ASCII_COLUMN_ALIASES = {
    "id",
    "name",
    "status",
    "year",
    "spec",
    "raw",
    "json",
    "program",
    "team",
}

_ZH_MEANING_ALIAS_SKIP_TERMS = {
    "字段",
    "数据",
    "用于",
    "表示",
    "主要",
    "原始",
    "完整",
    "格式",
    "时间",
    "状态",
}

_NON_GROUPABLE_DIMENSIONS = {
    "id",
    "defect_id",
    "mr_id",
    "test_id",
    "raw_json",
    "year",
    "spec",
    "creation_time",
    "last_modified",
    "started",
    "finished",
    "fetched_at",
    "version_stamp",
}

_UNIFIED_INTENT_CACHE_MAXSIZE = 128
_UNIFIED_INTENT_ADAPTER_CACHE: "OrderedDict[Tuple[str, str, str, bool], Dict[str, Any]]" = OrderedDict()


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


def _collect_meaning_aliases(meaning: Any) -> List[str]:
    text = str(meaning or "").strip()
    if not text:
        return []

    primary = re.split(r"[（(,，;；。:：]", text, maxsplit=1)[0].strip()
    if not primary:
        return []

    candidates: List[str] = [primary]
    for sep in ["/", "、", "|"]:
        if sep in primary:
            candidates.extend([part.strip() for part in primary.split(sep) if part.strip()])

    out: List[str] = []
    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        lowered = candidate.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        if candidate.isascii() and len(candidate) <= 2:
            continue
        if any(skip in candidate for skip in _ZH_MEANING_ALIAS_SKIP_TERMS):
            continue
        out.append(candidate)
    return out


def _collect_optimized_column_aliases(datasets: Sequence[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    pairs: List[Tuple[str, str, str]] = []
    for ds in datasets:
        ds_id = str(ds.get("id") or "").strip()
        optimized = ds.get("optimized_table") if isinstance(ds.get("optimized_table"), dict) else {}
        columns = optimized.get("columns") if isinstance(optimized.get("columns"), list) else []

        for col in columns:
            if not isinstance(col, dict):
                continue
            canonical = str(col.get("name") or "").strip()
            if not canonical:
                continue

            alias_candidates: List[str] = [
                canonical,
                canonical.replace("_", " "),
                canonical.replace("_", "-"),
            ]

            octane_source = str(col.get("octane_source") or "").strip()
            if octane_source:
                source_base = octane_source.split(".")[0].strip()
                if source_base:
                    alias_candidates.append(source_base)

            alias_candidates.extend(_collect_meaning_aliases(col.get("meaning")))

            dedup_aliases: List[str] = []
            seen = set()
            for alias in alias_candidates:
                text = str(alias or "").strip()
                if not text:
                    continue
                lowered = text.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                dedup_aliases.append(text)

            for alias in dedup_aliases:
                alias_lower = alias.lower()
                if alias_lower.isascii() and len(alias_lower) <= 2:
                    continue
                if alias_lower in _GENERIC_ASCII_COLUMN_ALIASES:
                    continue
                pairs.append((alias_lower, canonical, ds_id))

    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return pairs


def _collect_semantic_aliases(datasets: Sequence[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    combined = _collect_dimension_aliases(datasets)
    combined.extend(_collect_optimized_column_aliases(datasets))

    dedup: List[Tuple[str, str, str]] = []
    seen = set()
    for alias_lower, canonical, ds_id in combined:
        key = (alias_lower, canonical, ds_id)
        if key in seen:
            continue
        seen.add(key)
        dedup.append((alias_lower, canonical, ds_id))
    dedup.sort(key=lambda x: len(x[0]), reverse=True)
    return dedup


def _pick_preferred_dimension(matched_dimensions: Sequence[str], asks_feature_breakdown: bool) -> str:
    dims = [str(d).strip() for d in (matched_dimensions or []) if str(d).strip()]
    if not dims:
        return "top_aida" if asks_feature_breakdown else ""

    feature_priority = ["top_aida", "aida_english", "aida", "product_area", "service", "module", "domain"]
    for candidate in feature_priority:
        if candidate in dims:
            return candidate

    if asks_feature_breakdown:
        return "top_aida"

    general_priority = [
        "project",
        "tproject",
        "team",
        "run_team",
        "status_phase",
        "status",
        "phase",
        "severity",
        "problem_severity",
        "blocking_reason",
        "solution_cluster",
        "release",
        "software_version",
        "execution_sw_version",
        "test_phase",
        "testing_tool_type",
        "target_ecu_conf",
        "set_field",
        "lead_model",
        "assigned_ecu",
        "tester",
        "run_by",
        "owner",
        "author",
    ]
    for candidate in general_priority:
        if candidate in dims:
            return candidate

    for candidate in dims:
        c = candidate.lower()
        if c in _NON_GROUPABLE_DIMENSIONS:
            continue
        if c.endswith("_id"):
            continue
        return candidate
    return ""


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

        scope_team = str(hints.get("scope_team") or "").strip()
        if scope_team and not str(merged.get("scope_team") or "").strip():
            merged["scope_team"] = scope_team

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


def _dedup_text_list(values: Sequence[Any], limit: int = 8) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _infer_query_family(question_lower: str, merged_hints: Dict[str, Any]) -> str:
    if bool(merged_hints.get("wants_test_coverage")):
        return "test_coverage"
    if any(term in question_lower for term in ["测试", "测试用例", "execution status", "pass rate", "覆盖率"]):
        return "test_coverage"
    if bool(merged_hints.get("wants_aida_dist")) or bool(merged_hints.get("wants_feature_breakdown")):
        return "defect_distribution"
    if bool(merged_hints.get("wants_matrix")) or bool(merged_hints.get("wants_matrix_severity")):
        return "matrix"
    if bool(merged_hints.get("wants_trend")):
        return "trend"
    return "detail"


def _infer_table_hint(question_lower: str, query_family: str, table_name: str) -> str:
    explicit_table = str(table_name or "").strip()
    if explicit_table:
        return explicit_table
    if query_family == "test_coverage":
        return "octane_manual_runs"
    if any(term in question_lower for term in ["history", "历史", "状态变更", "变更记录", "流转"]):
        return "octane_defect_histories"
    return "octane_defects"


def _get_cached_adapter_output(
    question: str,
    table_name: str,
    db_path: Optional[str],
    prefer_db: bool,
) -> Dict[str, Any]:
    cache_key = (
        str(question or "").strip(),
        str(table_name or "").strip(),
        str(db_path or ""),
        bool(prefer_db),
    )
    cached = _UNIFIED_INTENT_ADAPTER_CACHE.get(cache_key)
    if isinstance(cached, dict):
        _UNIFIED_INTENT_ADAPTER_CACHE.move_to_end(cache_key)
        return cached

    adapter_out = adapt_question_with_semantic_terms(
        question,
        table_name=table_name,
        db_path=db_path,
        prefer_db=prefer_db,
    )
    if not isinstance(adapter_out, dict):
        adapter_out = {}

    _UNIFIED_INTENT_ADAPTER_CACHE[cache_key] = adapter_out
    _UNIFIED_INTENT_ADAPTER_CACHE.move_to_end(cache_key)
    while len(_UNIFIED_INTENT_ADAPTER_CACHE) > _UNIFIED_INTENT_CACHE_MAXSIZE:
        _UNIFIED_INTENT_ADAPTER_CACHE.popitem(last=False)
    return adapter_out


def _clear_unified_intent_adapter_cache() -> None:
    _UNIFIED_INTENT_ADAPTER_CACHE.clear()


def build_unified_query_intent(
    question: str,
    columns: Optional[Sequence[str]] = None,
    *,
    table_name: str = "",
    semantic_hints: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
    prefer_db: Optional[bool] = None,
) -> Dict[str, Any]:
    q = str(question or "").strip()
    q_lower = q.lower()
    input_hints = semantic_hints if isinstance(semantic_hints, dict) else {}

    if prefer_db is None:
        prefer_db = bool(db_path)

    adapter_out = _get_cached_adapter_output(
        q,
        table_name=table_name,
        db_path=db_path,
        prefer_db=bool(prefer_db),
    )
    adapted_hints = adapter_out.get("semantic_hints") if isinstance(adapter_out.get("semantic_hints"), dict) else {}
    merged_hints = merge_semantic_hints(adapted_hints, input_hints)

    merged_entity_tokens: List[Any] = []
    for source in [input_hints.get("entity_tokens"), adapted_hints.get("entity_tokens"), merged_hints.get("entity_tokens")]:
        if isinstance(source, list):
            merged_entity_tokens.extend(source)

    month_number = merged_hints.get("month_number")
    if not (isinstance(month_number, int) and 1 <= month_number <= 12):
        month_number = _extract_month_number(q)

    query_family = _infer_query_family(q_lower, merged_hints)
    table_hint = _infer_table_hint(q_lower, query_family, table_name)

    semantic_constraints: Dict[str, Any] = {}
    for key in [
        "wants_feature_breakdown",
        "wants_aida_dist",
        "wants_showstopper",
        "wants_showstopper_candidate",
        "wants_distribution",
        "wants_matrix",
        "wants_matrix_severity",
        "wants_trend",
        "wants_test_coverage",
        "wants_tester",
        "wants_detail",
        "wants_topissue",
        "wants_efficiency",
        "wants_recommendation",
        "wants_analysis",
    ]:
        if bool(merged_hints.get(key)):
            semantic_constraints[key] = True

    preferred_dimension = str(merged_hints.get("preferred_dimension") or "").strip()
    if preferred_dimension:
        semantic_constraints["preferred_dimension"] = preferred_dimension

    mapped_dimensions = merged_hints.get("mapped_dimensions")
    if isinstance(mapped_dimensions, list):
        normalized_dims = _dedup_text_list(mapped_dimensions, limit=16)
        if normalized_dims:
            semantic_constraints["mapped_dimensions"] = normalized_dims

    if isinstance(month_number, int) and 1 <= month_number <= 12:
        semantic_constraints["month_number"] = month_number

    entity_filters = _dedup_text_list(merged_entity_tokens, limit=8)
    time_scope: Dict[str, Any] = {}
    if isinstance(month_number, int) and 1 <= month_number <= 12:
        time_scope["month_number"] = month_number

    provenance: List[Dict[str, Any]] = []
    adapter_provenance = adapter_out.get("provenance")
    if isinstance(adapter_provenance, list):
        for row in adapter_provenance:
            if isinstance(row, dict):
                provenance.append(dict(row))
    if semantic_constraints or entity_filters:
        provenance.append({"type": "unified_intent", "source": "term_adapter"})

    signal_count = 0
    signal_count += 1 if semantic_constraints else 0
    signal_count += 1 if entity_filters else 0
    signal_count += 1 if time_scope else 0
    signal_count += 1 if query_family != "detail" else 0
    confidence = min(1.0, 0.25 + 0.15 * signal_count)

    return {
        "query_family": query_family,
        "table_hint": table_hint,
        "time_scope": time_scope,
        "entity_filters": entity_filters,
        "semantic_constraints": semantic_constraints,
        "confidence": float(confidence),
        "provenance": provenance[:40],
        "columns": [str(c).strip() for c in (columns or []) if str(c).strip()],
    }


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
    alias_rows = _collect_semantic_aliases(selected_datasets)
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

    preferred_dimension = _pick_preferred_dimension(matched_dimensions, asks_feature_breakdown)

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
