#!/usr/bin/env python3
"""
长期优化项目 1：实现业务知识图谱

目标：构建业务知识图谱，增强查询理解
预期效果：准确率 +5-8%
时间：2周

实施步骤：
1. 提取业务实体和关系
2. 构建知识图谱数据结构
3. 实现查询解析器
4. 集成到 Prompt 构建器
5. 测试和优化

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-29
"""

import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
import json
import sqlite3
import logging

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# 业务实体定义
# ============================================================================

@dataclass
class BusinessEntity:
    """业务实体"""
    name: str
    display_name: str
    table_name: str
    description: str
    type: str  # "table", "column", "enum"
    attributes: Dict[str, Any] = field(default_factory=dict)
    relationships: List[str] = field(default_factory=list)


@dataclass
class BusinessRelation:
    """业务关系"""
    name: str
    from_entity: str
    to_entity: str
    relation_type: str  # "1:N", "N:N", "1:1", "has"
    foreign_key: Optional[str] = None
    description: str = ""  # 添加默认值


@dataclass
class BusinessRule:
    """业务规则"""
    name: str
    description: str = ""
    rule_type: str = "business"  # "constraint", "business", "calculation"
    condition: str = ""
    action: str = ""


@dataclass
class BusinessTerm:
    """业务术语"""
    term: str
    definition: str
    synonyms: List[str] = field(default_factory=list)
    category: str = ""
    examples: List[str] = field(default_factory=list)


# ============================================================================
# 业务知识图谱
# ============================================================================

class BusinessKnowledgeGraph:
    """业务知识图谱"""

    def __init__(self):
        """初始化业务知识图谱"""
        self.entities = {}
        self.relations = {}
        self.rules = {}
        self.terms = {}

        # 初始化默认知识
        self._init_default_knowledge()

    def _init_default_knowledge(self):
        """初始化默认业务知识"""
        # 添加实体
        self._add_default_entities()
        # 添加关系
        self._add_default_relations()
        # 添加规则
        self._add_default_rules()
        # 添加术语
        self._add_default_terms()

    def _add_default_entities(self):
        """添加默认实体"""
        # 缺陷表
        defect_entity = BusinessEntity(
            name="defect",
            display_name="缺陷",
            table_name="defects",
            description="产品或系统中的问题、错误或不符合需求的地方",
            type="table",
            attributes={
                "id": {"type": "INTEGER", "description": "缺陷 ID", "primary_key": True},
                "severity": {"type": "TEXT", "description": "严重度", "enum": ["Critical", "Major", "Medium", "Minor"]},
                "status": {"type": "TEXT", "description": "状态", "enum": ["New", "Open", "In Progress", "Fixed", "Closed"]},
                "project": {"type": "TEXT", "description": "项目名称"},
                "module": {"type": "TEXT", "description": "模块名称"},
                "component": {"type": "TEXT", "description": "组件名称"},
                "creation_time": {"type": "DATETIME", "description": "创建时间"},
                "pingpong": {"type": "INTEGER", "description": "重开次数"},
                "build_number": {"type": "TEXT", "description": "构建号"}
            },
            relationships=["test_run", "project", "module", "component"]
        )
        self.entities["defect"] = defect_entity

        # 测试表
        test_entity = BusinessEntity(
            name="test",
            display_name="测试",
            table_name="test_runs",
            description="测试用例的执行记录",
            type="table",
            attributes={
                "id": {"type": "INTEGER", "description": "测试 ID", "primary_key": True},
                "test_name": {"type": "TEXT", "description": "测试名称"},
                "status": {"type": "TEXT", "description": "测试状态", "enum": ["Passed", "Failed", "Blocked", "No Run"]},
                "result": {"type": "TEXT", "description": "测试结果"},
                "start_time": {"type": "DATETIME", "description": "开始时间"},
                "end_time": {"type": "DATETIME", "description": "结束时间"},
                "duration": {"type": "INTEGER", "description": "执行时长（秒）"},
                "build_number": {"type": "TEXT", "description": "构建号"},
                "tester": {"type": "TEXT", "description": "测试人员"}
            },
            relationships=["defect", "project", "module"]
        )
        self.entities["test"] = test_entity

        # 项目实体（概念）
        project_entity = BusinessEntity(
            name="project",
            display_name="项目",
            table_name="defects",  # 使用 defects 表
            description="最高级别的项目分类，如 AIDA、HUD",
            type="table",
            attributes={
                "project": {"type": "TEXT", "description": "项目名称", "unique": True}
            },
            relationships=["defect", "test", "module", "component"]
        )
        self.entities["project"] = project_entity

        # 模块实体
        module_entity = BusinessEntity(
            name="module",
            display_name="模块",
            table_name="defects",
            description="项目下的功能模块，如 Display、Camera",
            type="column",
            attributes={
                "module": {"type": "TEXT", "description": "模块名称"}
            },
            relationships=["project", "component", "defect", "test"]
        )
        self.entities["module"] = module_entity

        # 组件实体
        component_entity = BusinessEntity(
            name="component",
            display_name="组件",
            table_name="test_coverage",
            description="模块下的具体组件",
            type="column",
            attributes={
                "component": {"type": "TEXT", "description": "组件名称"}
            },
            relationships=["module", "test"]
        )
        self.entities["component"] = component_entity

        # 严重度枚举
        severity_entity = BusinessEntity(
            name="severity",
            display_name="严重度",
            table_name="defects",
            description="缺陷的严重程度",
            type="enum",
            attributes={
                "Critical": {"value": "Critical", "level": 4, "description": "致命：系统崩溃、数据丢失、安全漏洞"},
                "Major": {"value": "Major", "level": 3, "description": "严重：主要功能不可用、性能严重下降"},
                "Medium": {"value": "Medium", "level": 2, "description": "中等：功能受限、性能下降"},
                "Minor": {"value": "Minor", "level": 1, "description": "轻微：界面问题、拼写错误、体验问题"}
            },
            relationships=["defect", "test"]
        )
        self.entities["severity"] = severity_entity

    def _add_default_relations(self):
        """添加默认关系"""
        # 缺陷 -> 测试
        defect_test_relation = BusinessRelation(
            name="defect_test",
            from_entity="defect",
            to_entity="test",
            relation_type="1:N",
            foreign_key="build_number",
            description="一个缺陷可能关联多个测试执行"
        )
        self.relations["defect_test"] = defect_test_relation

        # 缺陷 -> 项目
        defect_project_relation = BusinessRelation(
            name="defect_project",
            from_entity="defect",
            to_entity="project",
            relation_type="N:1",
            foreign_key="project",
            description="每个缺陷属于一个项目"
        )
        self.relations["defect_project"] = defect_project_relation

        # 项目 -> 模块
        project_module_relation = BusinessRelation(
            name="project_module",
            from_entity="project",
            to_entity="module",
            relation_type="1:N",
            foreign_key="project",
            description="一个项目包含多个模块"
        )
        self.relations["project_module"] = project_module_relation

        # 模块 -> 组件
        module_component_relation = BusinessRelation(
            name="module_component",
            from_entity="module",
            to_entity="component",
            relation_type="1:N",
            foreign_key="module",
            description="一个模块包含多个组件"
        )
        self.relations["module_component"] = module_component_relation

    def _add_default_rules(self):
        """添加默认业务规则"""
        # 高优先级规则
        high_priority_rule = BusinessRule(
            name="high_priority_defect",
            description="高优先级缺陷定义",
            rule_type="business",
            condition="severity = 'Critical' OR (severity = 'Major' AND pingpong > 3)",
            action="标记为高优先级，需要立即处理"
        )
        self.rules["high_priority_defect"] = high_priority_rule

        # 长期未修复规则
        long_unfixed_rule = BusinessRule(
            name="long_unfixed_defect",
            description="长期未修复缺陷定义",
            rule_type="business",
            condition="creation_time <= date('now', '-30 days') AND status NOT IN ('Fixed', 'Closed')",
            action="标记为长期未修复，需要升级处理"
        )
        self.rules["long_unfixed_defect"] = long_unfixed_rule

        # 测试覆盖率规则
        coverage_rule = BusinessRule(
            name="test_coverage_threshold",
            description="测试覆盖率阈值",
            rule_type="business",
            condition="coverage_percent < 70",
            action="标记为低覆盖率，需要重点关注"
        )
        self.rules["test_coverage_threshold"] = coverage_rule

    def _add_default_terms(self):
        """添加默认业务术语"""
        # Pingpong
        pingpong_term = BusinessTerm(
            term="pingpong",
            definition="缺陷被重新打开的次数，反映了问题的复杂性和解决的难度",
            synonyms=["重开", "再次打开", "回滚"],
            category="质量指标",
            examples=[
                "这个缺陷的 pingpong 是 5，说明很复杂",
                "pingpong 越过 3 的缺陷需要重点关注"
            ]
        )
        self.terms["pingpong"] = pingpong_term

        # 通过率
        pass_rate_term = BusinessTerm(
            term="通过率",
            definition="测试用例通过的比例 = (通过数 / 总数) × 100%",
            synonyms=["成功率", "pass rate", "success rate"],
            category="质量指标",
            examples=[
                "测试通过率是 95%，说明质量很好",
                "通过率低于 80% 的模块需要改进"
            ]
        )
        self.terms["pass_rate"] = pass_rate_term

        # 测试覆盖率
        coverage_term = BusinessTerm(
            term="测试覆盖率",
            definition="测试覆盖的功能范围，通常用百分比表示",
            synonyms=["代码覆盖率", "test coverage", "coverage"],
            category="质量指标",
            examples=[
                "测试覆盖率是 85%，大部分功能已被测试",
                "低覆盖率 (<70%) 表示有很多功能未被测试"
            ]
        )
        self.terms["test_coverage"] = coverage_term

        # TopIssue
        top_issue_term = BusinessTerm(
            term="TopIssue",
            definition="高频、高影响或长期未修复的严重缺陷",
            synonyms=["高风险", "严重问题", "关键问题"],
            category="问题分类",
            examples=[
                "这是一个 Critical 级别的 TopIssue",
                "TopIssue 需要立即处理"
            ]
        )
        self.terms["top_issue"] = top_issue_term

    def add_entity(self, entity: BusinessEntity) -> str:
        """添加实体"""
        self.entities[entity.name] = entity
        logger.info(f"添加实体: {entity.name}")
        return entity.name

    def add_relation(self, relation: BusinessRelation) -> str:
        """添加关系"""
        self.relations[relation.name] = relation
        logger.info(f"添加关系: {relation.name}")
        return relation.name

    def add_rule(self, rule: BusinessRule) -> str:
        """添加规则"""
        self.rules[rule.name] = rule
        logger.info(f"添加规则: {rule.name}")
        return rule.name

    def add_term(self, term: BusinessTerm) -> str:
        """添加术语"""
        self.terms[term.term] = term
        logger.info(f"添加术语: {term.term}")
        return term.term

    def parse_question(
        self,
        question: str
    ) -> Dict[str, Any]:
        """
        解析用户问题，提取实体、关系、术语

        Args:
            question: 用户问题

        Returns:
            解析结果
        """
        question_lower = question.lower()

        result = {
            "question": question,
            "entities": [],
            "relations": [],
            "terms": [],
            "attributes": [],
            "patterns": []
        }

        # 识别实体
        for entity_name, entity in self.entities.items():
            # 检查实体名称
            if entity.display_name in question_lower:
                result["entities"].append({
                    "name": entity_name,
                    "display_name": entity.display_name,
                    "table": entity.table_name
                })

            # 检查属性
            for attr_name, attr_info in entity.attributes.items():
                if attr_info.get("description", "") in question_lower:
                    result["attributes"].append({
                        "entity": entity_name,
                        "attribute": attr_name,
                        "description": attr_info.get("description", "")
                    })

        # 识别关系
        for rel_name, relation in self.relations.items():
            if relation.description in question_lower:
                result["relations"].append({
                    "name": rel_name,
                    "from": relation.from_entity,
                    "to": relation.to_entity,
                    "type": relation.relation_type
                })

        # 识别术语
        for term_name, term in self.terms.items():
            # 检查术语本身
            if term.term in question_lower:
                result["terms"].append({
                    "term": term.term,
                    "definition": term.definition,
                    "category": term.category
                })

            # 检查同义词
            for synonym in term.synonyms:
                if synonym in question_lower:
                    result["terms"].append({
                        "term": term.term,
                        "definition": term.definition,
                        "category": term.category,
                        "matched_via": synonym
                    })

        # 识别查询模式
        patterns = self._identify_query_patterns(question_lower)
        result["patterns"] = patterns

        return result

    def _identify_query_patterns(self, question: str) -> List[str]:
        """识别查询模式"""
        patterns = []

        # 统计查询
        if any(k in question for k in ["统计", "数量", "计数", "总数"]):
            patterns.append("统计")

        # 排名查询
        if any(k in question for k in ["排名", "top", "最高", "最低", "最大", "最小"]):
            patterns.append("排名")

        # 趋势查询
        if any(k in question for k in ["趋势", "变化", "增长", "下降", "按月", "按周"]):
            patterns.append("趋势")

        # 通过率查询
        if "通过率" in question or "pass rate" in question:
            patterns.append("通过率")

        # 覆盖率查询
        if "覆盖率" in question or "coverage" in question:
            patterns.append("覆盖率")

        # 对比查询
        if "对比" in question or "比较" in question or "差异" in question:
            patterns.append("对比")

        # 时间范围查询
        if any(k in question for k in ["最近", "本周", "本月", "7天", "30天", "今天", "昨天"]):
            patterns.append("时间范围")

        return patterns

    def generate_schema_context(self, parsed: Dict[str, Any]) -> str:
        """生成 Schema 上下文"""
        context_parts = []

        # 添加识别的实体
        if parsed["entities"]:
            context_parts.append("\n## 相关实体\n")
            for entity in parsed["entities"][:5]:  # 只显示前 5 个
                entity_info = self.entities.get(entity["name"])
                if entity_info:
                    context_parts.append(
                        f"- {entity_info.display_name} (表: {entity_info.table_name})"
                    )

        # 添加识别的属性
        if parsed["attributes"]:
            context_parts.append("\n## 相关字段\n")
            for attr in parsed["attributes"][:5]:
                entity_info = self.entities.get(attr["entity"])
                if entity_info:
                    attr_info_detail = entity_info.attributes.get(attr["attribute"], {})
                    context_parts.append(
                        f"- {entity_info.display_name}.{attr['attribute']}: "
                        f"{attr_info_detail.get('description', '')}"
                    )

        # 添加识别的关系
        if parsed["relations"]:
            context_parts.append("\n## 实体关系\n")
            for rel in parsed["relations"][:3]:  # 只显示前 3 个
                context_parts.append(
                    f"- {rel['from']} --{rel['name']}--> {rel['to']}"
                )

        # 添加查询模式
        if parsed["patterns"]:
            context_parts.append("\n## 查询类型\n")
            for pattern in parsed["patterns"]:
                context_parts.append(f"- {pattern}")

        # 添加识别的术语
        if parsed["terms"]:
            context_parts.append("\n## 业务术语\n")
            for term in parsed["terms"][:3]:  # 只显示前 3 个
                context_parts.append(
                    f"- {term['term']}: {term['definition'][:80]}..."
                )

        return "\n".join(context_parts)

    def get_knowledge_summary(self) -> Dict[str, Any]:
        """获取知识图谱摘要"""
        return {
            "entities_count": len(self.entities),
            "relations_count": len(self.relations),
            "rules_count": len(self.rules),
            "terms_count": len(self.terms),
            "entities": list(self.entities.keys()),
            "relations": list(self.relations.keys()),
            "rules": list(self.rules.keys()),
            "terms": list(self.terms.keys())
        }


# ============================================================================
# 查询解析器
# ============================================================================

class QueryParser:
    """查询解析器"""

    def __init__(self, knowledge_graph: BusinessKnowledgeGraph):
        """
        初始化查询解析器

        Args:
            knowledge_graph: 业务知识图谱
        """
        self.kg = knowledge_graph

    def parse(self, question: str) -> Dict[str, Any]:
        """
        解析查询

        Args:
            question: 用户问题

        Returns:
            解析结果
        """
        # 使用知识图谱解析
        parsed = self.kg.parse_question(question)

        # 生成增强的解析结果
        enhanced_parsed = self._enhance_parse(parsed)

        return enhanced_parsed

    def _enhance_parse(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """增强解析结果"""
        enhanced = parsed.copy()

        # 添加建议
        enhanced["suggestions"] = self._generate_suggestions(parsed)

        # 添加注意事项
        enhanced["notes"] = self._generate_notes(parsed)

        return enhanced

    def _generate_suggestions(self, parsed: Dict[str, Any]) -> List[str]:
        """生成查询建议"""
        suggestions = []

        # 基于实体生成建议
        if parsed["entities"]:
            entities = [e["name"] for e in parsed["entities"]]
            if "defect" in entities and "test" not in entities:
                suggestions.append("考虑关联测试数据以获得更全面的信息")

            if "project" in entities and "module" not in entities:
                suggestions.append("可以按模块分组查询以获得更细粒度的数据")

        # 基于模式生成建议
        if "排名" in parsed["patterns"]:
            suggestions.append("考虑使用 ORDER BY 和 LIMIT 来获取排名")

        if "趋势" in parsed["patterns"]:
            suggestions.append("考虑使用 strftime() 函数按时间分组")

        return suggestions

    def _generate_notes(self, parsed: Dict[str, Any]) -> List[str]:
        """生成注意事项"""
        notes = []

        # 基于术语生成注意事项
        if parsed["terms"]:
            terms = parsed["terms"]
            for term in terms:
                if term["category"] == "质量指标":
                    notes.append(f"{term['term']} 的计算公式：{term['definition']}")

        return notes

    def get_entity_schema(self, entity_name: str) -> Optional[Dict[str, Any]]:
        """获取实体的 Schema 信息"""
        entity = self.kg.entities.get(entity_name)
        if entity:
            return {
                "name": entity.name,
                "display_name": entity.display_name,
                "table_name": entity.table_name,
                "description": entity.description,
                "type": entity.type,
                "attributes": entity.attributes,
                "relationships": entity.relationships
            }
        return None


# ============================================================================
# 演示和测试
# ============================================================================

def demo_knowledge_graph():
    """演示业务知识图谱"""
    print("=" * 70)
    print("长期优化项目 1: 实现业务知识图谱")
    print("=" * 70 + "\n")

    # 创建知识图谱
    kg = BusinessKnowledgeGraph()

    # 添加额外的实体和规则
    print("添加额外的业务知识...\n")

    # 添加枚举实体
    status_entity = BusinessEntity(
        name="status",
        display_name="缺陷状态",
        table_name="defects",
        description="缺陷的生命周期状态",
        type="enum",
        attributes={
            "New": {"value": "New", "level": 0, "description": "新发现并记录的缺陷"},
            "Open": {"value": "Open", "level": 1, "description": "已分配但未开始修复"},
            "In Progress": {"value": "In Progress", "level": 2, "description": "正在修复中"},
            "Fixed": {"value": "Fixed", "level": 3, "description": "修复完成，等待验证"},
            "Closed": {"value": "Closed", "level": 4, "description": "已验证修复并关闭"}
        },
        relationships=["defect"]
    )
    kg.add_entity(status_entity)

    # 添加测试状态实体
    test_status_entity = BusinessEntity(
        name="test_status",
        display_name="测试状态",
        table_name="test_runs",
        description="测试执行的结果",
        type="enum",
        attributes={
            "Passed": {"value": "Passed", "level": 3, "description": "测试成功"},
            "Failed": {"value": "Failed", "level": 0, "description": "测试失败，发现问题"},
            "Blocked": {"value": "Blocked", "level": 1, "description": "无法执行，被其他问题阻塞"},
            "No Run": {"value": "No Run", "level": 2, "description": "尚未执行"}
        },
        relationships=["test"]
    )
    kg.add_entity(test_status_entity)

    # 添加业务术语
    high_runner_term = BusinessTerm(
        term="High Runner",
        definition="测试用例执行失败率高（通常 > 30%）的测试用例",
        synonyms=["不稳定用例", "易失败用例"],
        category="问题分类",
        examples=[
            "这是一个 High Runner 测试用例",
            "High Runner 需要重点优化"
        ]
    )
    kg.add_term(high_runner_term)

    long_runner_term = BusinessTerm(
        term="Long Runner",
        definition="执行时间长的测试用例（通常 > 30 分钟）",
        synonyms=["慢速用例", "长时间用例"],
        category="问题分类",
        examples=[
            "这是一个 Long Runner 测试用例",
            "Long Runner 影响测试效率"
        ]
    )
    kg.add_term(long_runner_term)

    # 添加业务规则
    fix_rate_rule = BusinessRule(
        name="low_fix_rate",
        description="低修复率规则",
        rule_type="business",
        condition="severity = 'Critical' AND (fixed_time - creation_time) > 7 days",
        action="标记为低修复率，需要重点关注"
    )
    kg.add_rule(fix_rate_rule)

    # 获取知识图谱摘要
    print("知识图谱摘要:\n")
    summary = kg.get_knowledge_summary()

    print(f"  实体数量: {summary['entities_count']}")
    print(f"  关系数量: {summary['relations_count']}")
    print(f"  规则数量: {summary['rules_count']}")
    print(f"  术语数量: {summary['terms_count']}")
    print()

    # 创建查询解析器
    print("创建查询解析器...\n")
    parser = QueryParser(kg)

    # 测试查询解析
    print("测试查询解析:\n")

    test_questions = [
        "查找 Critical 级别且 pingpong > 2 的高优先级缺陷",
        "统计每个项目的测试通过率",
        "最近一周的缺陷趋势分析",
        "测试通过率低的模块",
        "TopIssue 的缺陷数量",
        "High Runner 的测试用例",
        "项目 AIDA 的测试覆盖率"
    ]

    for i, question in enumerate(test_questions, 1):
        print(f"测试 {i}: {question}")
        print("-" * 70)

        parsed = parser.parse(question)

        if parsed["entities"]:
            print(f"  识别的实体: {[e['display_name'] for e in parsed['entities']]}")
        if parsed["relations"]:
            print(f"  识别的关系: {[r['name'] for r in parsed['relations']]}")
        if parsed["terms"]:
            print(f"  识别的术语: {[t['term'] for t in parsed['terms']]}")
        if parsed["patterns"]:
            print(f"  识别的模式: {parsed['patterns']}")

        # 生成上下文
        context = kg.generate_schema_context(parsed)
        print(f"  生成的上下文 (前 200 字符):")
        print(f"    {context[:200]}...")

        # 获取建议
        if parsed.get("suggestions"):
            print(f"  建议:")
            for suggestion in parsed["suggestions"][:2]:
                print(f"    - {suggestion}")

        print()

    # 获取实体 Schema
    print("获取实体 Schema:\n")
    defect_schema = parser.get_entity_schema("defect")
    if defect_schema:
        print(f"缺陷实体 Schema:")
        print(f"  名称: {defect_schema['display_name']}")
        print(f"  表名: {defect_schema['table_name']}")
        print(f"  描述: {defect_schema['description']}")
        print(f"  类型: {defect_schema['type']}")
        print(f"  属性数量: {len(defect_schema['attributes'])}")
        print(f"  关系: {', '.join(defect_schema['relationships'])}")
        print()

    print("=" * 70)
    print("长期优化项目 1 完成总结")
    print("=" * 70 + "\n")

    print("✅ 完成的工作:")
    print("  1. 实现了业务知识图谱框架（BusinessKnowledgeGraph）")
    print("  2. 实现了业务实体定义（BusinessEntity）")
    print("  3. 实现了业务关系定义（BusinessRelation）")
    print("  4. 实现了业务规则定义（BusinessRule）")
    print("  5. 实现了业务术语定义（BusinessTerm）")
    print("  6. 实现了查询解析器（QueryParser）")
    print("  7. 初始化了默认业务知识")
    print("  8. 添加了额外的实体和规则")

    print(f"\n📊 核心功能:")
    print("  1. 业务实体管理（表、列、枚举）")
    print("  2. 实体关系管理（1:N, N:N, 1:1）")
    print("  3. 业务规则管理（约束、业务、计算）")
    print("  4. 业务术语管理（定义、同义词、示例）")
    print("  5. 查询解析（实体、关系、术语、模式识别）")
    print("  6. Schema 上下文生成")
    print("  7. 查询建议生成")
    print("  8. 注意事项生成")

    print(f"\n🎯 预期效果:")
    print(f"  准确率提升: +5-8%")
    print(f"  工作时间: 2周")

    print(f"\n📋 默认业务知识:")
    print(f"  - 实体: {len(kg.entities)} 个")
    print(f"  - 关系: {len(kg.relations)} 个")
    print(f"  - 规则: {len(kg.rules)} 个")
    print(f"  - 术语: {len(kg.terms)} 个")

    print("\n" + "=" * 70)
    print("✅ 长期优化项目 1 完成！")
    print("=" * 70 + "\n")


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("长期优化项目 1: 实现业务知识图谱")
    print("=" * 70 + "\n")

    # 演示业务知识图谱
    demo_knowledge_graph()


if __name__ == "__main__":
    main()
