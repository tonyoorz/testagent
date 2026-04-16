"""Shared helpers used by multiple tool modules.

Extracted from intelligent_agent.py during the tool refactoring.
"""

import json
import logging
import os
from copy import deepcopy
from functools import lru_cache
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Dimension resolution
# ---------------------------------------------------------------------------

def semantic_core_dimensions(dataset: str) -> List[Dict[str, Any]]:
    """Load core dimensions for a dataset from semantic catalog."""
    try:
        from semantic_catalog.runtime import SemanticCatalog

        catalog = SemanticCatalog().load_catalog() or {}
        dkey = str(dataset or "").strip().lower()
        for ds in (catalog.get("datasets") or []):
            aliases = [str(a).strip().lower() for a in (ds.get("aliases") or [])]
            if str(ds.get("id", "")).strip().lower() == dkey or dkey in aliases:
                dims = ds.get("core_dimensions") or []
                return [d for d in dims if isinstance(d, dict)]
    except Exception:
        return []
    return []


def resolve_dimension_to_column(dataset: str, dim_or_alias: str, dataframe_columns: List[str]) -> Optional[str]:
    """Resolve a dimension name/alias to an actual column name in the DataFrame."""
    if not dim_or_alias:
        return None
    cols = [str(c) for c in (dataframe_columns or [])]
    col_set = set(cols)
    raw = str(dim_or_alias).strip()
    if raw in col_set:
        return raw
    key = raw.lower()
    for d in semantic_core_dimensions(str(dataset or "").strip().lower()):
        name = str(d.get("name", "")).strip()
        if not name:
            continue
        aliases = [str(a).strip() for a in (d.get("aliases") or []) if a is not None and str(a).strip()]
        alias_l = [a.lower() for a in aliases]
        if key == name.lower() or key in alias_l:
            if name in col_set:
                return name
            for a in aliases:
                if a in col_set:
                    return a
    if key in col_set:
        return key
    for c in cols:
        if c.lower() == key:
            return c
    return None


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------

def coerce_float(value: Any, default: float) -> float:
    try:
        result = float(value)
        if np.isfinite(result):
            return result
    except Exception:
        pass
    return default


def coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            return True
        if raw in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


# ---------------------------------------------------------------------------
# Anomaly rule evaluation
# ---------------------------------------------------------------------------

_DEFAULT_ANOMALY_RULE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "wow_spike_300pct": {
        "enabled": True,
        "threshold_pct": 300.0,
    },
    "sparse_signal_suppression": {
        "enabled": True,
        "min_baseline": 3.0,
        "min_current": 3.0,
    },
    "risk_concentration_shift": {
        "enabled": False,
        "share_shift_threshold_pct": 20.0,
    },
}


@lru_cache(maxsize=1)
def load_anomaly_rule_configs() -> Dict[str, Dict[str, Any]]:
    configs = deepcopy(_DEFAULT_ANOMALY_RULE_CONFIGS)
    path = os.path.join(PROJECT_ROOT, "semantic_catalog", "business_rules.json")

    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception:
        return configs

    rules = payload.get("business_rules") if isinstance(payload, dict) else []
    if not isinstance(rules, list):
        return configs

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        cfg = rule.get("config")
        if not isinstance(cfg, dict):
            continue
        rule_key = str(cfg.get("rule_key") or "").strip().lower()
        if rule_key not in configs:
            continue

        merged = deepcopy(configs[rule_key])
        merged.update(cfg)
        merged["enabled"] = coerce_bool(cfg.get("enabled"), bool(merged.get("enabled", True)))

        if rule_key == "wow_spike_300pct":
            merged["threshold_pct"] = coerce_float(cfg.get("threshold_pct"), float(configs[rule_key]["threshold_pct"]))
        elif rule_key == "sparse_signal_suppression":
            merged["min_baseline"] = coerce_float(cfg.get("min_baseline"), float(configs[rule_key]["min_baseline"]))
            merged["min_current"] = coerce_float(cfg.get("min_current"), float(configs[rule_key]["min_current"]))
        elif rule_key == "risk_concentration_shift":
            merged["share_shift_threshold_pct"] = coerce_float(
                cfg.get("share_shift_threshold_pct"),
                float(configs[rule_key]["share_shift_threshold_pct"]),
            )

        configs[rule_key] = merged

    return configs


def clear_anomaly_rule_config_cache() -> None:
    load_anomaly_rule_configs.cache_clear()


def extract_risk_share_pct(row: Dict[str, Any]) -> Optional[float]:
    if not isinstance(row, dict):
        return None

    for key in [
        "top_share_pct", "dominant_share_pct", "share_pct",
        "risk_share_pct", "top_share", "share",
    ]:
        raw = row.get(key)
        try:
            value = float(raw)
        except Exception:
            continue
        if not np.isfinite(value):
            continue
        if 0.0 <= value <= 1.0:
            return value * 100.0
        return value

    top_bucket = row.get("top_risk_bucket")
    for key in ["risk_distribution", "risk_bucket_distribution", "bucket_distribution"]:
        dist = row.get(key)
        if not isinstance(dist, dict) or not dist:
            continue

        numeric_items: Dict[str, float] = {}
        total = 0.0
        for bucket_name, raw_value in dist.items():
            try:
                bucket_value = float(raw_value)
            except Exception:
                continue
            if not np.isfinite(bucket_value) or bucket_value < 0:
                continue
            numeric_items[str(bucket_name)] = bucket_value
            total += bucket_value

        if total <= 0:
            continue

        if isinstance(top_bucket, str) and top_bucket in numeric_items:
            return (numeric_items[top_bucket] / total) * 100.0

        return (max(numeric_items.values()) / total) * 100.0

    return None


def evaluate_anomaly_rules(trend_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Evaluate configurable anomaly rules against trend points."""
    if not isinstance(trend_data, list) or len(trend_data) < 2:
        return []

    configs = load_anomaly_rule_configs()
    wow_cfg = configs.get("wow_spike_300pct", {})
    sparse_cfg = configs.get("sparse_signal_suppression", {})
    risk_cfg = configs.get("risk_concentration_shift", {})

    wow_enabled = bool(wow_cfg.get("enabled", True))
    wow_threshold_pct = coerce_float(wow_cfg.get("threshold_pct"), 300.0)

    sparse_enabled = bool(sparse_cfg.get("enabled", True))
    sparse_baseline = coerce_float(sparse_cfg.get("min_baseline"), 3.0)
    sparse_current = coerce_float(sparse_cfg.get("min_current"), 3.0)

    risk_enabled = bool(risk_cfg.get("enabled", False))
    risk_share_shift_threshold = coerce_float(risk_cfg.get("share_shift_threshold_pct"), 20.0)

    findings: List[Dict[str, Any]] = []

    for idx in range(1, len(trend_data)):
        prev_row = trend_data[idx - 1] if isinstance(trend_data[idx - 1], dict) else {}
        curr_row = trend_data[idx] if isinstance(trend_data[idx], dict) else {}

        try:
            prev_value = float(prev_row.get("value"))
            curr_value = float(curr_row.get("value"))
        except Exception:
            continue

        if not np.isfinite(prev_value) or not np.isfinite(curr_value):
            continue

        sparse_blocked = bool(
            sparse_enabled and (prev_value < sparse_baseline or curr_value < sparse_current)
        )

        if wow_enabled and (not sparse_blocked) and prev_value > 0:
            change_pct = ((curr_value - prev_value) / prev_value) * 100.0
            if change_pct >= wow_threshold_pct:
                findings.append({
                    "rule_id": "wow_spike_300pct",
                    "severity": "high",
                    "index": idx,
                    "group": curr_row.get("group"),
                    "value": curr_value,
                    "previous_group": prev_row.get("group"),
                    "previous_value": prev_value,
                    "change_pct": round(change_pct, 2),
                })

        if risk_enabled:
            prev_share_pct = extract_risk_share_pct(prev_row)
            curr_share_pct = extract_risk_share_pct(curr_row)

            if prev_share_pct is not None and curr_share_pct is not None:
                share_shift_pct = abs(curr_share_pct - prev_share_pct)
                if share_shift_pct >= risk_share_shift_threshold:
                    findings.append({
                        "rule_id": "risk_concentration_shift",
                        "severity": "medium",
                        "index": idx,
                        "group": curr_row.get("group"),
                        "previous_group": prev_row.get("group"),
                        "top_risk_bucket": curr_row.get("top_risk_bucket"),
                        "previous_top_risk_bucket": prev_row.get("top_risk_bucket"),
                        "top_share_pct": round(curr_share_pct, 2),
                        "previous_top_share_pct": round(prev_share_pct, 2),
                        "share_shift_pct": round(share_shift_pct, 2),
                    })

    return findings
