from typing import Any, Dict, List, Optional, Tuple

from .runtime import SemanticCatalog


def _is_str_list(v: Any) -> bool:
    if v is None:
        return True
    if not isinstance(v, list):
        return False
    return all(isinstance(x, str) for x in v)


def validate_catalog(base_dir: Optional[str] = None) -> Dict[str, Any]:
    catalog = SemanticCatalog(base_dir=base_dir).load_catalog()
    errors: List[str] = []
    warnings: List[str] = []

    datasets = catalog.get("datasets") or []
    metrics = catalog.get("metrics") or []
    charts = catalog.get("charts") or []

    if not isinstance(datasets, list):
        errors.append("datasets.json: datasets 必须是 list")
        datasets = []
    if not isinstance(metrics, list):
        errors.append("metrics.json: metrics 必须是 list")
        metrics = []
    if not isinstance(charts, list):
        errors.append("charts.json: charts 必须是 list")
        charts = []

    def _unique_id(items: List[Dict[str, Any]], kind: str) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
        seen = {}
        for it in items:
            if not isinstance(it, dict):
                errors.append(f"{kind}: 条目必须是 object")
                continue
            _id = it.get("id")
            if not isinstance(_id, str) or not _id.strip():
                errors.append(f"{kind}: 存在缺少 id 的条目")
                continue
            if _id in seen:
                errors.append(f"{kind}: id 重复: {_id}")
            seen[_id] = it
        return list(seen.keys()), seen

    _, ds_map = _unique_id(datasets, "datasets")
    metric_ids, metric_map = _unique_id(metrics, "metrics")
    _, chart_map = _unique_id(charts, "charts")

    for ds_id, ds in ds_map.items():
        if "aliases" in ds and not _is_str_list(ds.get("aliases")):
            errors.append(f"datasets[{ds_id}].aliases 必须是 string[]")
        for dim in (ds.get("core_dimensions") or []):
            if not isinstance(dim, dict):
                continue
            if "aliases" in dim and not _is_str_list(dim.get("aliases")):
                errors.append(f"datasets[{ds_id}].core_dimensions.aliases 必须是 string[]")

    for chart_id, ch in chart_map.items():
        dash = ch.get("dashboard")
        if not isinstance(dash, str) or not dash.strip():
            errors.append(f"charts[{chart_id}].dashboard 缺失或非法")
        src = ch.get("data_source")
        if isinstance(src, str) and src.startswith("datasets."):
            ref = src.split(".", 1)[1].strip()
            if ref and ref not in ds_map:
                errors.append(f"charts[{chart_id}].data_source 引用不存在的数据集: {ref}")
        if "aliases" in ch and not _is_str_list(ch.get("aliases")):
            errors.append(f"charts[{chart_id}].aliases 必须是 string[]")

    for mid, m in metric_map.items():
        if "aliases" in m and not _is_str_list(m.get("aliases")):
            errors.append(f"metrics[{mid}].aliases 必须是 string[]")
        alias_of = m.get("alias_of")
        if isinstance(alias_of, str) and alias_of.strip():
            if alias_of not in metric_ids:
                warnings.append(f"metrics[{mid}].alias_of 指向未知指标: {alias_of}")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def main() -> int:
    report = validate_catalog()
    if report.get("warnings"):
        for w in report["warnings"]:
            print("WARN:", w)
    if report.get("errors"):
        for e in report["errors"]:
            print("ERROR:", e)
        return 1
    print("OK: semantic catalog validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
