#!/usr/bin/env python3
"""
本地多 Agent 协作分析系统
不依赖外部 API，直接分析代码和数据库，模拟多 Agent 协作

Agent 角色：
1. PM-Agent (产品经理) - 分析业务需求和测试资产价值
2. Dev-Agent (开发工程师) - 分析技术实现和优化方案
3. QA-Agent (测试工程师) - 验证和测试改进效果
4. Coordinator (协调者) - 整合分析结果并输出报告

作者: AI Assistant
日期: 2026-03-19
"""

import os
import sys
import json
import sqlite3
import ast
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class AgentAnalysisResult:
    """Agent 分析结果"""
    agent_name: str
    role: str
    findings: List[str]
    issues: List[str]
    recommendations: List[str]
    score: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


class LocalMultiAgentAnalyzer:
    """本地多 Agent 分析器"""
    
    def __init__(self, db_path: str, project_path: str):
        self.db_path = db_path
        self.project_path = project_path
        self.results: Dict[str, AgentAnalysisResult] = {}
        
        # 加载数据
        self.db_schema = self._load_database_schema()
        self.db_stats = self._load_database_stats()
        self.code_structure = self._analyze_code_structure()
    
    def _load_database_schema(self) -> Dict[str, Any]:
        """加载数据库结构"""
        schema = {}
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 获取所有表
            cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
            for name, sql in cursor.fetchall():
                if sql:
                    # 解析字段
                    fields = re.findall(r'(\w+)\s+(\w+(?:\([^)]+\))?)', sql)
                    schema[name] = {
                        'sql': sql,
                        'fields': {f[0]: f[1] for f in fields if f[0] not in ['PRIMARY', 'FOREIGN', 'UNIQUE', 'CHECK']}
                    }
            
            conn.close()
        except Exception as e:
            logger.error(f"加载数据库结构失败: {e}")
        
        return schema
    
    def _load_database_stats(self) -> Dict[str, Any]:
        """加载数据库统计"""
        stats = {}
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 各表记录数
            for table in self._load_database_schema().keys():
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    stats[f"{table}_count"] = cursor.fetchone()[0]
                except:
                    pass
            
            # 测试运行统计
            try:
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) as passed,
                        SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) as failed,
                        COUNT(DISTINCT project) as projects,
                        COUNT(DISTINCT module) as modules,
                        COUNT(DISTINCT tester) as testers
                    FROM test_runs
                """)
                row = cursor.fetchone()
                stats['test_runs_stats'] = {
                    'total': row[0], 'passed': row[1], 'failed': row[2],
                    'projects': row[3], 'modules': row[4], 'testers': row[5]
                }
            except:
                pass
            
            # 缺陷统计
            try:
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'Open' THEN 1 ELSE 0 END) as open_count,
                        SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) as critical,
                        SUM(CASE WHEN severity = 'Major' THEN 1 ELSE 0 END) as major,
                        COUNT(DISTINCT project) as projects,
                        COUNT(DISTINCT module) as modules
                    FROM defects
                """)
                row = cursor.fetchone()
                stats['defects_stats'] = {
                    'total': row[0], 'open': row[1], 'critical': row[2], 'major': row[3],
                    'projects': row[4], 'modules': row[5]
                }
            except:
                pass
            
            conn.close()
        except Exception as e:
            logger.error(f"加载数据库统计失败: {e}")
        
        return stats
    
    def _analyze_code_structure(self) -> Dict[str, Any]:
        """分析代码结构"""
        structure = {
            'files': {},
            'classes': {},
            'functions': {},
            'imports': defaultdict(list)
        }
        
        key_files = [
            'intelligent_agent.py',
            'database/agent_data_understanding.py',
            'multi_agent_system_v2.py',
            'database/enhanced_data_understanding.py'
        ]
        
        for file_name in key_files:
            file_path = os.path.join(self.project_path, file_name)
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # 解析 AST
                    try:
                        tree = ast.parse(content)
                        
                        classes = []
                        functions = []
                        
                        for node in ast.walk(tree):
                            if isinstance(node, ast.ClassDef):
                                classes.append({
                                    'name': node.name,
                                    'methods': [n.name for n in node.body if isinstance(n, ast.FunctionDef)],
                                    'docstring': ast.get_docstring(node) or ''
                                })
                            elif isinstance(node, ast.FunctionDef) and node.col_offset == 0:
                                functions.append({
                                    'name': node.name,
                                    'args': [arg.arg for arg in node.args.args],
                                    'docstring': ast.get_docstring(node) or ''
                                })
                        
                        structure['files'][file_name] = {
                            'size': len(content),
                            'classes': classes,
                            'functions': functions,
                            'line_count': content.count('\n')
                        }
                    except:
                        structure['files'][file_name] = {
                            'size': len(content),
                            'line_count': content.count('\n')
                        }
                        
                except Exception as e:
                    logger.error(f"分析文件 {file_name} 失败: {e}")
        
        return structure
    
    # ========================================================================
    # PM-Agent: 产品经理视角分析
    # ========================================================================
    def run_pm_agent(self) -> AgentAnalysisResult:
        """PM Agent 分析 - 业务价值和需求视角"""
        logger.info("🔍 PM-Agent: 分析业务价值和测试资产...")
        
        findings = []
        issues = []
        recommendations = []
        details = {}
        
        # 1. 分析测试资产价值
        test_stats = self.db_stats.get('test_runs_stats', {})
        if test_stats:
            findings.append(f"📊 测试资产包含 {test_stats.get('total', 0)} 条测试执行记录")
            findings.append(f"📊 覆盖 {test_stats.get('projects', 0)} 个项目，{test_stats.get('modules', 0)} 个模块")
            
            pass_rate = 0
            if test_stats.get('total', 0) > 0:
                pass_rate = test_stats.get('passed', 0) / test_stats.get('total', 0) * 100
            findings.append(f"📊 整体通过率: {pass_rate:.1f}%")
            details['pass_rate'] = pass_rate
        
        # 2. 分析缺陷资产价值
        defect_stats = self.db_stats.get('defects_stats', {})
        if defect_stats:
            findings.append(f"🐛 缺陷资产包含 {defect_stats.get('total', 0)} 条缺陷记录")
            findings.append(f"🐛 其中 {defect_stats.get('open', 0)} 条未关闭，{defect_stats.get('critical', 0)} 条 Critical 级别")
            
            if defect_stats.get('critical', 0) > 0:
                issues.append(f"⚠️ 存在 {defect_stats.get('critical', 0)} 条 Critical 缺陷需要关注")
        
        # 3. 分析 Agent 对业务场景的理解
        code_files = self.code_structure.get('files', {})
        
        # 检查 agent_data_understanding.py
        understanding_file = code_files.get('database/agent_data_understanding.py', {})
        if understanding_file:
            classes = understanding_file.get('classes', [])
            for cls in classes:
                if 'understand' in cls['name'].lower():
                    methods = cls.get('methods', [])
                    if 'understand_question' in methods:
                        findings.append("✅ Agent 具有问题意图理解能力")
                    else:
                        issues.append("❌ Agent 缺少问题意图理解方法")
                    
                    if 'execute_query' in methods:
                        findings.append("✅ Agent 具有查询执行能力")
                    else:
                        issues.append("❌ Agent 缺少查询执行方法")
        
        # 4. 业务场景覆盖分析
        scenarios = [
            ("测试通过率分析", "pass_rate" in str(code_files)),
            ("缺陷趋势分析", "defect" in str(code_files).lower() and "trend" in str(code_files).lower()),
            ("风险评估", "risk" in str(code_files).lower()),
            ("项目对比", "project" in str(code_files).lower()),
            ("人员绩效", "tester" in str(code_files).lower() or "user" in str(code_files).lower())
        ]
        
        covered = [s[0] for s in scenarios if s[1]]
        not_covered = [s[0] for s in scenarios if not s[1]]
        
        findings.append(f"📋 已覆盖业务场景: {len(covered)}/{len(scenarios)}")
        if not_covered:
            issues.append(f"❌ 未覆盖业务场景: {', '.join(not_covered)}")
        
        details['covered_scenarios'] = covered
        details['missing_scenarios'] = not_covered
        
        # 5. 生成建议
        recommendations.extend([
            "💡 建议1: 增强 Agent 对测试周（如 26-CW11）格式的理解",
            "💡 建议2: 添加测试效率分析场景（执行时长、瓶颈识别）",
            "💡 建议3: 实现跨项目对比分析能力",
            "💡 建议4: 添加缺陷生命周期追踪能力",
            "💡 建议5: 实现智能风险预警功能"
        ])
        
        # 计算评分
        score = (len(covered) / max(len(scenarios), 1)) * 40 + \
                (1 if 'understand_question' in str(code_files) else 0) * 20 + \
                (1 if test_stats else 0) * 20 + \
                (1 if defect_stats else 0) * 20
        
        result = AgentAnalysisResult(
            agent_name="pm-agent",
            role="产品经理",
            findings=findings,
            issues=issues,
            recommendations=recommendations,
            score=min(score, 100),
            details=details
        )
        
        self.results['pm-agent'] = result
        logger.info(f"✅ PM-Agent 分析完成，评分: {result.score:.1f}")
        return result
    
    # ========================================================================
    # Dev-Agent: 开发工程师视角分析
    # ========================================================================
    def run_dev_agent(self) -> AgentAnalysisResult:
        """Dev Agent 分析 - 技术实现视角"""
        logger.info("🔧 Dev-Agent: 分析技术实现...")
        
        findings = []
        issues = []
        recommendations = []
        details = {}
        
        code_files = self.code_structure.get('files', {})
        
        # 1. 分析 intelligent_agent.py
        intel_file = code_files.get('intelligent_agent.py', {})
        if intel_file:
            size_kb = intel_file.get('size', 0) / 1024
            findings.append(f"📁 intelligent_agent.py: {size_kb:.1f} KB, {intel_file.get('line_count', 0)} 行")
            
            classes = intel_file.get('classes', [])
            findings.append(f"📁 包含 {len(classes)} 个类: {[c['name'] for c in classes]}")
            
            # 检查工具类
            tool_classes = [c for c in classes if 'Tool' in c['name']]
            if tool_classes:
                findings.append(f"✅ 发现 {len(tool_classes)} 个工具类")
            else:
                issues.append("❌ 未发现工具类定义")
            
            # 检查方法
            for cls in classes:
                methods = cls.get('methods', [])
                if 'execute' in methods:
                    findings.append(f"✅ 类 {cls['name']} 实现了 execute 方法")
        
        # 2. 分析数据理解层
        understanding_file = code_files.get('database/agent_data_understanding.py', {})
        if understanding_file:
            classes = understanding_file.get('classes', [])
            for cls in classes:
                methods = cls.get('methods', [])
                findings.append(f"📁 数据理解类 {cls['name']}: {len(methods)} 个方法")
                
                # 检查意图识别
                if 'understand_question' in methods:
                    findings.append("✅ 实现了问题意图识别")
                    details['has_intent_recognition'] = True
                else:
                    issues.append("❌ 缺少问题意图识别功能")
                
                # 检查查询生成
                if 'execute_query' in methods:
                    findings.append("✅ 实现了动态查询生成")
                    details['has_query_generation'] = True
                else:
                    issues.append("❌ 缺少动态查询生成功能")
        
        # 3. 分析数据库 Schema 理解能力
        schema = self.db_schema
        if schema:
            tables = list(schema.keys())
            findings.append(f"🗄️ 数据库包含 {len(tables)} 个表: {tables}")
            
            # 检查关键字段理解
            for table in ['test_runs', 'defects']:
                if table in schema:
                    fields = schema[table].get('fields', {})
                    findings.append(f"🗄️ {table} 表: {len(fields)} 个字段")
                    
                    # 检查业务关键字段
                    key_fields = {
                        'test_runs': ['status', 'project', 'module', 'tester', 'test_week'],
                        'defects': ['severity', 'status', 'project', 'module', 'detected_by']
                    }
                    
                    for kf in key_fields.get(table, []):
                        if kf in fields:
                            findings.append(f"  ✅ 理解字段: {kf}")
                        else:
                            issues.append(f"  ❌ 缺少对字段 {kf} 的理解")
        
        # 4. 代码质量分析
        total_lines = sum(f.get('line_count', 0) for f in code_files.values())
        findings.append(f"📏 核心代码总行数: {total_lines}")
        
        # 5. 技术改进建议
        recommendations.extend([
            "🔧 建议1: 实现 Schema 自动发现和映射机制",
            "🔧 建议2: 添加语义层（Semantic Layer）抽象数据库细节",
            "🔧 建议3: 实现 Few-Shot 学习优化意图识别",
            "🔧 建议4: 添加查询缓存机制提升性能",
            "🔧 建议5: 实现增量式数据同步而非全量加载",
            "🔧 建议6: 添加 SQL 注入防护和数据脱敏",
            "🔧 建议7: 实现多数据源适配器模式"
        ])
        
        # 计算评分
        score = 0
        if intel_file:
            score += 20
        if understanding_file:
            score += 20
        if details.get('has_intent_recognition'):
            score += 20
        if details.get('has_query_generation'):
            score += 20
        if schema:
            score += 20
        
        result = AgentAnalysisResult(
            agent_name="dev-agent",
            role="开发工程师",
            findings=findings,
            issues=issues,
            recommendations=recommendations,
            score=min(score, 100),
            details=details
        )
        
        self.results['dev-agent'] = result
        logger.info(f"✅ Dev-Agent 分析完成，评分: {result.score:.1f}")
        return result
    
    # ========================================================================
    # QA-Agent: 测试工程师视角分析
    # ========================================================================
    def run_qa_agent(self) -> AgentAnalysisResult:
        """QA Agent 分析 - 质量验证视角"""
        logger.info("🧪 QA-Agent: 分析质量和测试覆盖...")
        
        findings = []
        issues = []
        recommendations = []
        details = {}
        
        # 1. 功能正确性测试
        test_questions = [
            ("测试通过率是多少？", "test", "count"),
            ("有多少个Open的缺陷？", "defect", "count"),
            ("ABS系统的测试情况", "test", "analyze"),
            ("本周的缺陷趋势", "defect", "trend"),
            ("Critical缺陷列表", "defect", "list")
        ]
        
        # 模拟意图识别测试
        understanding_file = self.code_structure.get('files', {}).get('database/agent_data_understanding.py', {})
        if understanding_file:
            # 检查支持的意图
            content = ''
            file_path = os.path.join(self.project_path, 'database/agent_data_understanding.py')
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            supported_intents = []
            if "'test'" in content or '"test"' in content:
                supported_intents.append('test')
            if "'defect'" in content or '"defect"' in content:
                supported_intents.append('defect')
            if "'count'" in content or '"count"' in content:
                supported_intents.append('count')
            if "'trend'" in content or '"trend"' in content:
                supported_intents.append('trend')
            if "'list'" in content or '"list"' in content:
                supported_intents.append('list')
            if "'analyze'" in content or '"analyze"' in content:
                supported_intents.append('analyze')
            
            findings.append(f"🧪 支持的意图类型: {supported_intents}")
            details['supported_intents'] = supported_intents
            
            # 检查测试覆盖
            covered_tests = []
            for question, domain, action in test_questions:
                if domain in supported_intents and action in supported_intents:
                    covered_tests.append(question)
                else:
                    issues.append(f"❌ 可能无法处理: '{question}'")
            
            findings.append(f"🧪 测试问题覆盖: {len(covered_tests)}/{len(test_questions)}")
            details['test_coverage'] = len(covered_tests) / len(test_questions) * 100
        
        # 2. 边界情况测试
        edge_cases = [
            "空数据库查询",
            "无效的项目名称",
            "不存在的时间范围",
            "特殊字符输入",
            "超长查询字符串"
        ]
        
        # 检查错误处理
        if 'try' in str(understanding_file) and 'except' in str(understanding_file):
            findings.append("✅ 代码包含异常处理机制")
        else:
            issues.append("❌ 缺少异常处理机制")
        
        edge_case_handling = 0
        if 'None' in str(understanding_file):
            edge_case_handling += 1
        if 'NULL' in str(understanding_file).upper() or 'null' in str(understanding_file):
            edge_case_handling += 1
        if 'empty' in str(understanding_file).lower():
            edge_case_handling += 1
        
        findings.append(f"🧪 边界情况处理: {edge_case_handling}/3 检查点")
        details['edge_case_handling'] = edge_case_handling
        
        # 3. 数据完整性测试
        if self.db_stats.get('test_runs_count', 0) > 0:
            findings.append(f"✅ test_runs 表有数据")
        if self.db_stats.get('defects_count', 0) > 0:
            findings.append(f"✅ defects 表有数据")
        
        # 4. 质量改进建议
        recommendations.extend([
            "🧪 建议1: 添加单元测试覆盖意图识别逻辑",
            "🧪 建议2: 实现集成测试验证端到端流程",
            "🧪 建议3: 添加输入验证和清洗机制",
            "🧪 建议4: 实现返回结果的格式化验证",
            "🧪 建议5: 添加性能基准测试",
            "🧪 建议6: 实现回归测试套件"
        ])
        
        # 计算评分
        score = details.get('test_coverage', 0) * 0.5 + \
                edge_case_handling * 10 + \
                (20 if 'try' in str(understanding_file) else 0) + \
                (20 if self.db_stats.get('test_runs_count', 0) > 0 else 0)
        
        result = AgentAnalysisResult(
            agent_name="qa-agent",
            role="测试工程师",
            findings=findings,
            issues=issues,
            recommendations=recommendations,
            score=min(score, 100),
            details=details
        )
        
        self.results['qa-agent'] = result
        logger.info(f"✅ QA-Agent 分析完成，评分: {result.score:.1f}")
        return result
    
    # ========================================================================
    # Coordinator: 整合分析结果
    # ========================================================================
    def run_coordinator(self) -> Dict[str, Any]:
        """协调者整合所有分析结果"""
        logger.info("📋 Coordinator: 整合分析结果...")
        
        # 运行所有 Agent
        pm_result = self.run_pm_agent()
        dev_result = self.run_dev_agent()
        qa_result = self.run_qa_agent()
        
        # 整合发现
        all_findings = []
        all_issues = []
        all_recommendations = []
        
        for result in [pm_result, dev_result, qa_result]:
            all_findings.extend([f"[{result.agent_name}] {f}" for f in result.findings])
            all_issues.extend([f"[{result.agent_name}] {i}" for i in result.issues])
            all_recommendations.extend([f"[{result.agent_name}] {r}" for r in result.recommendations])
        
        # 计算综合评分
        overall_score = (pm_result.score + dev_result.score + qa_result.score) / 3
        
        # 生成最终报告
        report = {
            "timestamp": datetime.now().isoformat(),
            "project_path": self.project_path,
            "database_path": self.db_path,
            "overall_score": overall_score,
            "agent_scores": {
                "pm-agent": pm_result.score,
                "dev-agent": dev_result.score,
                "qa-agent": qa_result.score
            },
            "summary": {
                "total_findings": len(all_findings),
                "total_issues": len(all_issues),
                "total_recommendations": len(all_recommendations)
            },
            "findings": all_findings,
            "issues": all_issues,
            "recommendations": all_recommendations,
            "priority_improvements": self._prioritize_improvements(all_issues, all_recommendations),
            "implementation_plan": self._create_implementation_plan(all_recommendations),
            "agent_details": {
                "pm-agent": {
                    "findings": pm_result.findings,
                    "issues": pm_result.issues,
                    "recommendations": pm_result.recommendations,
                    "details": pm_result.details
                },
                "dev-agent": {
                    "findings": dev_result.findings,
                    "issues": dev_result.issues,
                    "recommendations": dev_result.recommendations,
                    "details": dev_result.details
                },
                "qa-agent": {
                    "findings": qa_result.findings,
                    "issues": qa_result.issues,
                    "recommendations": qa_result.recommendations,
                    "details": qa_result.details
                }
            }
        }
        
        logger.info(f"📋 整合完成，综合评分: {overall_score:.1f}")
        return report
    
    def _prioritize_improvements(self, issues: List[str], recommendations: List[str]) -> List[Dict]:
        """优先级排序改进项"""
        improvements = []
        
        # 从问题中提取改进项（高优先级）
        for issue in issues:
            if '❌' in issue:
                improvements.append({
                    "priority": "HIGH",
                    "type": "问题修复",
                    "description": issue.replace('❌ ', ''),
                    "source": issue.split(']')[0].replace('[', '') if ']' in issue else 'unknown'
                })
        
        # 从建议中提取改进项
        for rec in recommendations:
            if '💡' in rec or '🔧' in rec or '🧪' in rec:
                priority = "MEDIUM" if '建议1' in rec or '建议2' in rec or '建议3' in rec else "LOW"
                improvements.append({
                    "priority": priority,
                    "type": "功能增强",
                    "description": rec.replace('💡 ', '').replace('🔧 ', '').replace('🧪 ', ''),
                    "source": rec.split(']')[0].replace('[', '') if ']' in rec else 'unknown'
                })
        
        # 按优先级排序
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        improvements.sort(key=lambda x: priority_order.get(x["priority"], 3))
        
        return improvements[:15]  # 返回前15个
    
    def _create_implementation_plan(self, recommendations: List[str]) -> List[Dict]:
        """创建实施计划"""
        phases = [
            {
                "phase": "Phase 1: 核心能力增强",
                "duration": "1-2周",
                "tasks": []
            },
            {
                "phase": "Phase 2: 业务场景扩展",
                "duration": "2-3周",
                "tasks": []
            },
            {
                "phase": "Phase 3: 质量和性能优化",
                "duration": "1-2周",
                "tasks": []
            }
        ]
        
        for rec in recommendations:
            if '意图' in rec or 'Schema' in rec or '语义层' in rec:
                phases[0]["tasks"].append(rec)
            elif '场景' in rec or '分析' in rec or '能力' in rec:
                phases[1]["tasks"].append(rec)
            elif '测试' in rec or '性能' in rec or '缓存' in rec:
                phases[2]["tasks"].append(rec)
        
        return phases


def main():
    """主函数"""
    # 动态获取路径
    try:
        from config_center import cfg
        db_path = str(cfg.DATABASE_FILE)
        project_path = str(cfg.PROJECT_ROOT)
    except ImportError:
        import os
        _this_dir = os.path.dirname(os.path.abspath(__file__))
        project_path = os.path.dirname(_this_dir)
        db_path = os.path.join(project_path, 'database', 'local_data.db')

    print("=" * 80)
    print("🚀 本地多 Agent 协作分析系统")
    print("=" * 80)
    print()

    # 创建分析器
    analyzer = LocalMultiAgentAnalyzer(db_path, project_path)
    
    # 运行协作分析
    report = analyzer.run_coordinator()
    
    # 保存报告
    output_path = os.path.join(project_path, "multi_agent_analysis_report.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n📁 分析报告已保存到: {output_path}")
    
    # 打印报告摘要
    print("\n" + "=" * 80)
    print("📊 分析报告摘要")
    print("=" * 80)
    print(f"\n综合评分: {report['overall_score']:.1f}/100")
    print(f"\nAgent 评分:")
    for agent, score in report['agent_scores'].items():
        print(f"  - {agent}: {score:.1f}")
    
    print(f"\n发现: {report['summary']['total_findings']} 项")
    print(f"问题: {report['summary']['total_issues']} 项")
    print(f"建议: {report['summary']['total_recommendations']} 项")
    
    print("\n" + "=" * 80)
    print("🔥 优先改进项 (TOP 10)")
    print("=" * 80)
    for i, imp in enumerate(report['priority_improvements'][:10], 1):
        print(f"{i}. [{imp['priority']}] {imp['description']}")
    
    return report


if __name__ == "__main__":
    main()
