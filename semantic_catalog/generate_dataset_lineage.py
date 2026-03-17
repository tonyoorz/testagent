import ast
import json
import os
from typing import Any, Dict, Optional, Tuple


def _extract_mapping_dicts(py_path: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    with open(py_path, "r", encoding="utf-8") as f:
        src = f.read()
    mod = ast.parse(src, filename=py_path)

    field_mappings: Optional[Dict[str, str]] = None
    list_field_mappings: Optional[Dict[str, str]] = None

    for node in ast.walk(mod):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            continue
        t = node.targets[0]
        if not isinstance(t, ast.Name):
            continue
        if t.id not in {"field_mappings", "list_field_mappings"}:
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        try:
            value = ast.literal_eval(node.value)
        except Exception:
            continue
        if not isinstance(value, dict):
            continue
        normalized = {}
        for k, v in value.items():
            if isinstance(k, str) and isinstance(v, str):
                normalized[k] = v
        if t.id == "field_mappings":
            field_mappings = normalized
        else:
            list_field_mappings = normalized

    return field_mappings or {}, list_field_mappings or {}


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _dump_json(path: str, obj: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main() -> None:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    dp_path = os.path.join(base_dir, "data_processor.py")
    datasets_path = os.path.join(base_dir, "semantic_catalog", "datasets.json")

    field_mappings, list_field_mappings = _extract_mapping_dicts(dp_path)
    if not field_mappings and not list_field_mappings:
        raise SystemExit("未能从 data_processor.py 提取 field_mappings/list_field_mappings")

    datasets = _load_json(datasets_path)
    items = datasets.get("datasets") or []
    updated = False
    for it in items:
        if not isinstance(it, dict):
            continue
        if str(it.get("id")) != "octane_defects":
            continue
        it["field_lineage"] = dict(sorted(field_mappings.items(), key=lambda x: x[0]))
        it["list_field_lineage"] = dict(sorted(list_field_mappings.items(), key=lambda x: x[0]))
        updated = True
        break

    if not updated:
        raise SystemExit("datasets.json 中未找到 id=octane_defects")

    _dump_json(datasets_path, datasets)
    print("已更新 semantic_catalog/datasets.json: octane_defects.field_lineage/list_field_lineage")


if __name__ == "__main__":
    main()

