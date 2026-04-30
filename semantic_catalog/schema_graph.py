"""
SchemaGraph — 数据知识图谱

从 schema_graph.json 加载字段定义、关系、状态机、口径规则，
为 Agent 提供结构化的业务语义。

用法:
    from semantic_catalog.schema_graph import SchemaGraph

    graph = SchemaGraph()           # 自动加载 JSON
    field = graph.get_field("ecu")  # 字段定义
    rels = graph.get_relationships("ecu")  # 关联字段
    sm = graph.get_state_machine("status_phase")  # 状态机
    cal = graph.get_calibration("severity")  # 口径规则
    ctx = graph.field_context_for_prompt("status_phase")  # prompt 上下文
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 默认 JSON 路径：与本模块同目录
_DEFAULT_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema_graph.json")


class SchemaGraph:
    """数据知识图谱 — 字段关系 + 状态机 + 口径规则。"""

    def __init__(self, json_path: Optional[str] = None):
        self._json_path = json_path or _DEFAULT_JSON_PATH
        self._data: Dict[str, Any] = {}
        self._loaded = False
        self._alias_to_field: Dict[str, str] = {}
        self._load()

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """加载 schema_graph.json；文件不存在则 graceful fallback。"""
        if not os.path.exists(self._json_path):
            logger.debug(f"schema_graph.json not found: {self._json_path}")
            return
        try:
            with open(self._json_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            self._loaded = True
            self._build_alias_index()
            logger.debug(f"SchemaGraph loaded from {self._json_path}")
        except Exception as e:
            logger.warning(f"SchemaGraph load failed: {e}")
            self._data = {}

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ------------------------------------------------------------------
    # Alias 索引
    # ------------------------------------------------------------------

    def _build_alias_index(self) -> None:
        """预建 alias→field_name 索引，将 O(n) 查询优化为 O(1)。"""
        self._alias_to_field = {}
        for name, defn in self._data.get("field_definitions", {}).items():
            self._alias_to_field[name.lower().strip()] = name
            for alias in defn.get("aliases", []):
                self._alias_to_field[str(alias).lower().strip()] = name

    # ------------------------------------------------------------------
    # 字段定义
    # ------------------------------------------------------------------

    def get_field(self, field_name: str) -> Optional[Dict[str, Any]]:
        """获取字段定义。支持按 name 或 alias 查找（O(1) 索引）。"""
        fields = self._data.get("field_definitions", {})
        # 精确匹配
        if field_name in fields:
            return dict(fields[field_name])
        # alias 索引匹配
        resolved = self._alias_to_field.get(field_name.lower().strip())
        if resolved and resolved in fields:
            return dict(fields[resolved])
        return None

    def get_all_field_names(self) -> List[str]:
        """返回所有已定义字段名。"""
        return list(self._data.get("field_definitions", {}).keys())

    def get_fields_by_dataset(self, dataset_id: str) -> List[Dict[str, Any]]:
        """返回属于指定数据集的所有字段定义。"""
        results = []
        for name, defn in self._data.get("field_definitions", {}).items():
            if dataset_id in defn.get("datasets", []):
                entry = dict(defn)
                entry["name"] = name
                results.append(entry)
        return results

    # ------------------------------------------------------------------
    # 关系
    # ------------------------------------------------------------------

    def get_relationships(self, field_name: str) -> List[Dict[str, Any]]:
        """获取与指定字段相关的所有关系。"""
        relationships = self._data.get("relationships", [])
        results = []
        fn_lower = field_name.lower().strip()
        for rel in relationships:
            source = str(rel.get("source", "")).lower()
            target = str(rel.get("target", "")).lower()
            if fn_lower in (source, target):
                results.append(dict(rel))
        return results

    def get_all_relationships(self) -> List[Dict[str, Any]]:
        """返回所有关系定义。"""
        return list(self._data.get("relationships", []))

    # ------------------------------------------------------------------
    # 状态机
    # ------------------------------------------------------------------

    def get_state_machine(self, field_name: str) -> Optional[Dict[str, Any]]:
        """获取字段对应的状态机定义。"""
        state_machines = self._data.get("state_machines", {})
        fn_lower = field_name.lower().strip()
        resolved = self._alias_to_field.get(fn_lower, field_name.lower().strip())
        # state_machine key 通常是字段名本身，优先精确匹配
        if fn_lower in state_machines:
            return dict(state_machines[fn_lower])
        # alias 索引匹配
        if resolved in state_machines:
            return dict(state_machines[resolved])
        return None

    def get_all_state_machines(self) -> Dict[str, Dict[str, Any]]:
        """返回所有状态机定义。"""
        return {k: dict(v) for k, v in self._data.get("state_machines", {}).items()}

    # ------------------------------------------------------------------
    # 口径规则
    # ------------------------------------------------------------------

    def get_calibration(self, field_name: str) -> List[Dict[str, Any]]:
        """获取适用于指定字段的口径规则。"""
        calibrations = self._data.get("calibration_rules", [])
        results = []
        fn_lower = field_name.lower().strip()
        for cal in calibrations:
            applies_to = [str(a).lower().strip() for a in cal.get("applies_to", [])]
            if fn_lower in applies_to:
                results.append(dict(cal))
        return results

    def get_all_calibrations(self) -> List[Dict[str, Any]]:
        """返回所有口径规则。"""
        return list(self._data.get("calibration_rules", []))

    def find_calibrations_by_trigger(self, question: str) -> List[Dict[str, Any]]:
        """根据问题文本匹配相关的口径规则。"""
        calibrations = self._data.get("calibration_rules", [])
        q_lower = question.lower()
        results = []
        for cal in calibrations:
            triggers = [str(t).lower().strip() for t in cal.get("trigger_terms", [])]
            if any(t in q_lower for t in triggers):
                results.append(dict(cal))
        return results

    # ------------------------------------------------------------------
    # Prompt 上下文生成
    # ------------------------------------------------------------------

    def field_context_for_prompt(self, field_name: str) -> str:
        """为指定字段生成完整的 prompt 上下文字符串。"""
        parts: List[str] = []

        # 字段定义
        field_def = self.get_field(field_name)
        if field_def:
            parts.append(f"字段: {field_name}")
            parts.append(f"  含义: {field_def.get('meaning', '')}")
            if field_def.get("aliases"):
                parts.append(f"  别名: {', '.join(field_def['aliases'])}")
            if field_def.get("data_quality_warning"):
                parts.append(f"  ⚠️ {field_def['data_quality_warning']}")
            if field_def.get("data_processing"):
                parts.append(f"  数据处理: {field_def['data_processing']}")

        # 关系
        rels = self.get_relationships(field_name)
        if rels:
            rel_strs = []
            for r in rels:
                other = r["target"] if r["source"].lower() == field_name.lower() else r["source"]
                rel_strs.append(f"{other}({r.get('type', '')}: {r.get('description', '')})")
            parts.append("  关联字段: " + "; ".join(rel_strs))

        # 状态机
        sm = self.get_state_machine(field_name)
        if sm:
            states = [s["name"] for s in sm.get("states", [])]
            parts.append(f"  状态: {' → '.join(states)}")
            groups = sm.get("category_groups", {})
            if groups:
                for gk, gv in groups.items():
                    parts.append(f"    {gv.get('label', gk)}: {', '.join(gv.get('states', []))}")
            derived = sm.get("derived_metrics", [])
            if derived:
                for m in derived:
                    parts.append(f"    {m['name']}: {m.get('formula', '')} ({m.get('note', '')})")

        # 口径规则
        cals = self.get_calibration(field_name)
        for cal in cals:
            parts.append(f"  口径[{cal.get('name', '')}]:")
            for rule in cal.get("rules", []):
                parts.append(f"    - {rule}")
            for guard in cal.get("sql_guardrails", []):
                parts.append(f"    ⚠️ {guard}")

        return "\n".join(parts) if parts else ""

    def calibration_context_for_prompt(self, question: str) -> str:
        """根据问题生成口径规则上下文。"""
        cals = self.find_calibrations_by_trigger(question)
        if not cals:
            return ""

        parts: List[str] = ["【口径规则提醒】"]
        for cal in cals:
            parts.append(f"- {cal.get('name', '')}: {cal.get('description', '')}")
            for rule in cal.get("rules", []):
                parts.append(f"  规则: {rule}")
            for guard in cal.get("sql_guardrails", []):
                parts.append(f"  SQL注意: {guard}")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # 健康检查
    # ------------------------------------------------------------------

    def validate(self) -> List[str]:
        """校验 JSON 数据一致性，返回警告列表（空=无问题）。

        检查项：
        - relationships 的 source/target 是否都在 field_definitions 中
        - state_machines 的 key 是否与 field_definitions 对应
        - calibration_rules 的 applies_to 是否引用了已定义字段
        """
        warnings: List[str] = []
        if not self._loaded:
            return ["SchemaGraph not loaded"]

        fields = set(self._data.get("field_definitions", {}).keys())
        # alias 也算有效引用
        all_valid = fields | set(self._alias_to_field.keys())

        # relationships
        for rel in self._data.get("relationships", []):
            src = rel.get("source", "")
            tgt = rel.get("target", "")
            if src not in all_valid:
                warnings.append(f"Relationship '{rel.get('id', '?')}' source '{src}' not in field_definitions")
            if tgt not in all_valid:
                warnings.append(f"Relationship '{rel.get('id', '?')}' target '{tgt}' not in field_definitions")

        # state_machines
        for sm_key in self._data.get("state_machines", {}):
            if sm_key not in all_valid:
                warnings.append(f"State machine '{sm_key}' not in field_definitions")

        # calibration_rules
        for cal in self._data.get("calibration_rules", []):
            for applies in cal.get("applies_to", []):
                if applies not in all_valid:
                    warnings.append(f"Calibration '{cal.get('id', '?')}' applies_to '{applies}' not in field_definitions")

        return warnings
