#!/usr/bin/env python3
"""
多 Agent 协作分析系统
使用智谱 API 实现真正的多 Agent 协作，分析 testagent 项目

Agent 角色：
1. pm-agent (产品经理) - 分析业务需求和测试资产价值
2. dev-agent (开发工程师) - 分析技术实现和优化方案
3. qa-agent (测试工程师) - 验证和测试改进效果
4. coordinator (协调者) - 整合分析结果并输出报告

作者: AI Assistant
日期: 2026-03-19
"""

import os
import sys
import json
import sqlite3
import requests
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 智谱 API 配置 - 优先从 config_center 读取
try:
    from config_center import cfg
    ZHIPU_API_KEY = cfg.ZHIPU_API_KEY
    ZHIPU_BASE_URL = cfg.ZHIPU_BASE_URL
    ZHIPU_MODEL = cfg.ZHIPU_MODEL
except ImportError:
    ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "")
    ZHIPU_BASE_URL = os.environ.get("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    ZHIPU_MODEL = os.environ.get("ZHIPU_MODEL", "glm-4.7")


@dataclass
class AgentMessage:
    """Agent 消息"""
    role: str
    agent_name: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AgentResult:
    """Agent 分析结果"""
    agent_name: str
    role: str
    analysis: str
    recommendations: List[str]
    issues_found: List[str]
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ZhipuClient:
    """智谱 API 客户端"""
    
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def chat(self, messages: List[Dict], temperature: float = 0.7, max_retries: int = 3) -> str:
        """发送聊天请求，带重试机制"""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4000
        }
        
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=self.headers, json=payload, timeout=120)
                response.raise_for_status()
                result = response.json()
                return result["choices"][0]["message"]["content"]
            except requests.exceptions.HTTPError as e:
                if "429" in str(e):
                    wait_time = 5 * (attempt + 1)  # 递增等待时间
                    logger.warning(f"API 限流，等待 {wait_time} 秒后重试 ({attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"API 调用失败: {e}")
                    return f"错误: {str(e)}"
            except Exception as e:
                logger.error(f"API 调用失败: {e}")
                return f"错误: {str(e)}"
        
        return "错误: 超过最大重试次数"


class MultiAgentCollaborator:
    """多 Agent 协作分析系统"""
    
    def __init__(self, db_path: str, project_path: str):
        self.db_path = db_path
        self.project_path = project_path
        self.client = ZhipuClient(ZHIPU_API_KEY, ZHIPU_BASE_URL, ZHIPU_MODEL)
        self.conversation_history: List[Dict] = []
        self.agent_results: Dict[str, AgentResult] = {}
        
        # 项目上下文
        self.project_context = self._build_project_context()
        self.database_context = self._build_database_context()
    
    def _build_project_context(self) -> str:
        """构建项目上下文"""
        context = """
## testagent 项目概述

### 项目结构
testagent/
├── database/              # 数据存储层
│   ├── local_data.db      # SQLite 数据库
│   ├── db_storage.py      # 数据存储接口
│   └── agent_data_understanding.py  # 数据理解层
├── intelligent_agent.py   # 主智能 Agent (132KB)
├── multi_agent_system_v2.py  # 多 Agent 协作系统
├── intelligent_context_engine.py  # 智能上下文引擎
├── reflection_system.py   # 自我反思系统
└── hooks_and_tracing.py   # 钩子追踪系统

### 核心文件分析
1. intelligent_agent.py - 主智能 Agent
   - 工具调用系统 (DataAnalysisTool)
   - 趋势分析工具 (TrendAnalysisTool)
   - 对话记忆系统
   - 知识库集成

2. agent_data_understanding.py - 数据理解层
   - 意图识别 (understand_question)
   - SQL 查询生成 (execute_query)
   - 支持的意图: test, defect, count, list, trend, analyze

3. multi_agent_system_v2.py - 多 Agent 系统
   - Agent 角色: COORDINATOR, DEFECT_ANALYST, TEST_ANALYST, RISK_ASSESSOR
   - OpenClaw 兼容性
   - A2A 通信支持
"""
        return context
    
    def _build_database_context(self) -> str:
        """构建数据库上下文"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 获取表结构
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table'")
            schemas = cursor.fetchall()
            
            # 获取数据统计
            stats = {}
            for table in ['test_runs', 'defects', 'test_coverage', 'defect_trends']:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    stats[table] = cursor.fetchone()[0]
                except:
                    stats[table] = 0
            
            # 获取样例数据
            cursor.execute("SELECT * FROM test_runs LIMIT 2")
            test_samples = [dict(zip([d[0] for d in cursor.description], row)) 
                           for row in cursor.fetchall()]
            
            cursor.execute("SELECT * FROM defects LIMIT 2")
            defect_samples = [dict(zip([d[0] for d in cursor.description], row)) 
                             for row in cursor.fetchall()]
            
            conn.close()
            
            context = f"""
## 数据库结构

### 表统计
- test_runs: {stats.get('test_runs', 0)} 条记录
- defects: {stats.get('defects', 0)} 条记录
- test_coverage: {stats.get('test_coverage', 0)} 条记录
- defect_trends: {stats.get('defect_trends', 0)} 条记录

### test_runs 表结构
关键字段: run_id, test_name, status, tester, project, module, test_week, duration_seconds

样例数据:
{json.dumps(test_samples, indent=2, ensure_ascii=False, default=str)}

### defects 表结构
关键字段: defect_id, title, severity, status, project, module, detected_by, creation_time, pingpong

样例数据:
{json.dumps(defect_samples, indent=2, ensure_ascii=False, default=str)}
"""
            return context
        except Exception as e:
            return f"数据库上下文获取失败: {e}"
    
    def _get_agent_system_prompt(self, agent_name: str) -> str:
        """获取 Agent 系统提示词 - 优先从统一提示词模块读取"""
        # agent_name 格式如 "pm-agent" 或 "coordinator"，映射到 prompts 模块的角色名
        _role_map = {
            "pm-agent": "pm",
            "dev-agent": "dev",
            "qa-agent": "qa",
            "coordinator": "coordinator",
        }
        role = _role_map.get(agent_name)
        if role:
            try:
                from prompts import get_role_prompt
                return get_role_prompt(role)
            except (ImportError, ValueError):
                pass
        return "你是一个智能 Agent，负责分析和优化软件测试相关问题。"
    
    def run_agent(self, agent_name: str, task: str, context: str = "") -> AgentResult:
        """运行单个 Agent"""
        logger.info(f"🤖 启动 {agent_name} 分析...")
        
        system_prompt = self._get_agent_system_prompt(agent_name)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"""
## 项目上下文
{self.project_context}

## 数据库上下文
{self.database_context}

## 额外上下文
{context}

## 任务
{task}

请进行深入分析，输出：
1. 分析结果
2. 发现的问题
3. 改进建议
"""}
        ]
        
        response = self.client.chat(messages)
        
        # 解析结果
        result = AgentResult(
            agent_name=agent_name,
            role=agent_name.split("-")[0].upper(),
            analysis=response,
            recommendations=self._extract_recommendations(response),
            issues_found=self._extract_issues(response),
            metadata={"timestamp": datetime.now().isoformat()}
        )
        
        self.agent_results[agent_name] = result
        logger.info(f"✅ {agent_name} 分析完成")
        
        return result
    
    def _extract_recommendations(self, text: str) -> List[str]:
        """提取建议"""
        recommendations = []
        lines = text.split("\n")
        for line in lines:
            if "建议" in line or "改进" in line or "优化" in line:
                if line.strip().startswith(("-", "•", "*", "1.", "2.", "3.", "4.", "5.")):
                    recommendations.append(line.strip())
        return recommendations[:10]
    
    def _extract_issues(self, text: str) -> List[str]:
        """提取问题"""
        issues = []
        lines = text.split("\n")
        for line in lines:
            if "问题" in line or "缺陷" in line or "不足" in line or "缺失" in line:
                if line.strip().startswith(("-", "•", "*", "1.", "2.", "3.", "4.", "5.")):
                    issues.append(line.strip())
        return issues[:10]
    
    def run_collaboration(self, main_question: str) -> Dict[str, Any]:
        """运行多 Agent 协作分析"""
        logger.info("=" * 60)
        logger.info("🚀 启动多 Agent 协作分析系统")
        logger.info("=" * 60)
        
        start_time = datetime.now()
        results = {
            "question": main_question,
            "start_time": start_time.isoformat(),
            "agent_results": {},
            "collaboration_log": []
        }
        
        # 1. PM Agent 分析业务价值
        pm_task = """
分析 testagent 项目的测试资产价值：

1. 当前 Agent 对测试数据的理解能力如何？
2. 测试资产（test_runs, defects）的业务价值是什么？
3. 如何让 Agent 更好地理解组织的测试资产？
4. 测试资产分析的典型业务场景有哪些？

请从产品经理视角给出深入分析。
"""
        pm_result = self.run_agent("pm-agent", pm_task)
        results["agent_results"]["pm-agent"] = {
            "analysis": pm_result.analysis,
            "recommendations": pm_result.recommendations,
            "issues": pm_result.issues_found
        }
        results["collaboration_log"].append({
            "agent": "pm-agent",
            "status": "completed",
            "timestamp": datetime.now().isoformat()
        })
        
        # 2. Dev Agent 分析技术实现
        dev_task = f"""
基于 PM Agent 的分析结果，分析技术实现：

PM Agent 分析摘要：
{pm_result.analysis[:1000]}

请分析：
1. 当前 agent_data_understanding.py 的技术实现有什么问题？
2. 如何提升 Agent 对数据库 Schema 的理解能力？
3. 如何实现智能查询生成和意图识别优化？
4. 建议使用哪些技术方案改进？

请给出具体的技术实现方案。
"""
        dev_result = self.run_agent("dev-agent", dev_task, context=pm_result.analysis)
        results["agent_results"]["dev-agent"] = {
            "analysis": dev_result.analysis,
            "recommendations": dev_result.recommendations,
            "issues": dev_result.issues_found
        }
        results["collaboration_log"].append({
            "agent": "dev-agent",
            "status": "completed",
            "timestamp": datetime.now().isoformat()
        })
        
        # 3. QA Agent 验证质量
        qa_task = f"""
验证 Agent 系统的数据理解能力：

Dev Agent 分析摘要：
{dev_result.analysis[:1000]}

请验证：
1. 当前 Agent 能否正确理解测试执行数据？
2. 当前 Agent 能否正确理解缺陷追踪数据？
3. 边界情况处理是否完善？
4. 数据理解能力的测试覆盖度如何？

请提出质量改进建议。
"""
        qa_result = self.run_agent("qa-agent", qa_task, context=f"{pm_result.analysis}\n{dev_result.analysis}")
        results["agent_results"]["qa-agent"] = {
            "analysis": qa_result.analysis,
            "recommendations": qa_result.recommendations,
            "issues": qa_result.issues_found
        }
        results["collaboration_log"].append({
            "agent": "qa-agent",
            "status": "completed",
            "timestamp": datetime.now().isoformat()
        })
        
        # 4. Coordinator 整合结果
        coordinator_task = f"""
整合多 Agent 分析结果：

## PM Agent 分析
{pm_result.analysis}

## Dev Agent 分析
{dev_result.analysis}

## QA Agent 分析
{qa_result.analysis}

请整合以上分析，输出：
1. 执行摘要
2. 关键发现
3. 优先改进建议（按重要性排序）
4. 具体实施步骤
5. 预期效果
"""
        coordinator_result = self.run_agent("coordinator", coordinator_task, 
                                            context=f"{pm_result.analysis}\n{dev_result.analysis}\n{qa_result.analysis}")
        results["agent_results"]["coordinator"] = {
            "analysis": coordinator_result.analysis,
            "recommendations": coordinator_result.recommendations,
            "issues": coordinator_result.issues_found
        }
        results["collaboration_log"].append({
            "agent": "coordinator",
            "status": "completed",
            "timestamp": datetime.now().isoformat()
        })
        
        end_time = datetime.now()
        results["end_time"] = end_time.isoformat()
        results["duration_seconds"] = (end_time - start_time).total_seconds()
        
        logger.info("=" * 60)
        logger.info(f"✅ 多 Agent 协作分析完成，耗时 {results['duration_seconds']:.1f} 秒")
        logger.info("=" * 60)
        
        return results


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

    # 创建协作分析器
    collaborator = MultiAgentCollaborator(db_path, project_path)
    
    # 运行协作分析
    question = "如何让 Agent 彻底理解组织测试资产的能力？"
    results = collaborator.run_collaboration(question)
    
    # 保存结果
    output_path = os.path.join(project_path, "multi_agent_analysis_result.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n📁 分析结果已保存到: {output_path}")
    
    # 打印协调者报告
    print("\n" + "=" * 80)
    print("📊 协调者综合报告")
    print("=" * 80)
    print(results["agent_results"]["coordinator"]["analysis"])
    
    return results


if __name__ == "__main__":
    main()
