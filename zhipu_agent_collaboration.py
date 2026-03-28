#!/usr/bin/env python3
"""
OpenClaw Agent 协作任务 - 智谱AI版本
PM/DEV/QA 团队协作分析 AI Agent 项目
"""

import os
import sys
import json
import requests
from datetime import datetime

# 智谱AI配置 - 优先从 config_center 读取
try:
    from config_center import cfg
    ZHIPU_API_KEY = cfg.ZHIPU_API_KEY
    ZHIPU_BASE_URL = cfg.ZHIPU_BASE_URL
    ZHIPU_MODEL = cfg.ZHIPU_MODEL
except ImportError:
    ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "")
    ZHIPU_BASE_URL = os.environ.get("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    ZHIPU_MODEL = os.environ.get("ZHIPU_MODEL", "glm-4.7")

class ZhipuAgent:
    """智谱AI Agent"""
    
    def __init__(self, name, role, system_prompt):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.history = []
    
    def chat(self, message):
        """调用智谱AI API"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {ZHIPU_API_KEY}"
        }
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            *self.history,
            {"role": "user", "content": message}
        ]
        
        payload = {
            "model": ZHIPU_MODEL,
            "messages": messages,
            "max_tokens": 4096,
            "temperature": 0.7
        }
        
        try:
            response = requests.post(
                f"{ZHIPU_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                reply = result["choices"][0]["message"]["content"]
                self.history.append({"role": "user", "content": message})
                self.history.append({"role": "assistant", "content": reply})
                return reply
            else:
                return f"❌ API错误: {response.status_code} - {response.text}"
        except Exception as e:
            return f"❌ 请求失败: {str(e)}"

# 使用统一提示词模块
try:
    from prompts import get_role_prompt
    PM_PROMPT = get_role_prompt("pm")
    DEV_PROMPT = get_role_prompt("dev")
    QA_PROMPT = get_role_prompt("qa")
    COORDINATOR_PROMPT = get_role_prompt("coordinator")
except ImportError:
    # prompts 模块不可用时使用内置精简版
    PM_PROMPT = """你是专业的产品经理，擅长需求分析、用户故事、优先级管理。

核心职责：
1. 需求分析 - 理解用户痛点，转化模糊需求为清晰规格
2. 用户故事 - 编写标准格式："作为...我想要...以便..."
3. 优先级管理 - 基于价值、成本、风险评估优先级
4. 验收标准 - 定义清晰可测试的验收条件

输出格式：
- 需求分析
- 用户故事
- 验收标准
- 优先级建议"""

    DEV_PROMPT = """你是资深的开发工程师，精通架构设计、代码实现、技术方案。

核心职责：
1. 架构设计 - 设计可扩展、高性能的系统架构
2. 技术方案 - 评估技术选型，提供实施路径
3. 代码实现 - 编写高质量、可维护的代码
4. 性能优化 - 识别瓶颈，实施优化方案

输出格式：
- 技术方案
- 架构设计
- 实施步骤
- 代码示例（如需要）"""

    QA_PROMPT = """你是专业的测试工程师，擅长测试用例设计、质量保证、风险评估。

核心职责：
1. 测试设计 - 设计全面的测试用例和测试策略
2. 质量保证 - 确保交付物满足质量标准
3. 风险评估 - 识别潜在风险，提供缓解措施
4. 缺陷追踪 - 记录、分析、追踪缺陷

输出格式：
- 测试策略
- 测试用例
- 风险评估
- 质量建议"""

    COORDINATOR_PROMPT = """你是团队协调者，负责协调PM/DEV/QA的工作流程。

核心职责：
1. 任务分配 - 将任务分配给合适的专家
2. 结果整合 - 整合各Agent的输出形成最终方案
3. 冲突解决 - 识别并解决各方观点的冲突
4. 进度追踪 - 追踪任务执行进度

协作流程：
用户需求 → PM分析 → DEV设计 → QA测试 → 整合输出"""

def run_collaboration_task(task_description):
    """运行协作任务"""
    
    print("=" * 60)
    print("🦞 OpenClaw Agent 协作任务 - 智谱AI版本")
    print("=" * 60)
    print(f"\n📋 任务: {task_description}")
    print(f"🤖 模型: {ZHIPU_MODEL}")
    print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 创建Agent团队
    pm_agent = ZhipuAgent("pm-agent", "产品经理", PM_PROMPT)
    dev_agent = ZhipuAgent("dev-agent", "开发工程师", DEV_PROMPT)
    qa_agent = ZhipuAgent("qa-agent", "测试工程师", QA_PROMPT)
    coordinator = ZhipuAgent("coordinator", "协调者", COORDINATOR_PROMPT)
    
    # 步骤1: PM分析需求
    print("━" * 60)
    print("👤 [PM Agent] 需求分析中...")
    print("━" * 60)
    pm_task = f"""请分析以下AI Agent优化需求：

{task_description}

请提供：
1. 需求分析（用户痛点、目标用户、业务价值）
2. 用户故事（标准格式）
3. 验收标准
4. 优先级建议"""
    
    pm_result = pm_agent.chat(pm_task)
    print(f"\n📝 PM Agent 输出:\n")
    print(pm_result)
    print()
    
    # 步骤2: DEV设计技术方案
    print("━" * 60)
    print("💻 [DEV Agent] 技术方案设计中...")
    print("━" * 60)
    dev_task = f"""基于PM的分析，设计技术方案：

{pm_result}

请提供：
1. 技术方案概述
2. 架构设计
3. 实施步骤
4. 预期效果"""
    
    dev_result = dev_agent.chat(dev_task)
    print(f"\n📝 DEV Agent 输出:\n")
    print(dev_result)
    print()
    
    # 步骤3: QA设计测试方案
    print("━" * 60)
    print("🔍 [QA Agent] 测试方案设计中...")
    print("━" * 60)
    qa_task = f"""基于PM需求和DEV技术方案，设计测试方案：

需求分析:
{pm_result}

技术方案:
{dev_result}

请提供：
1. 测试策略
2. 核心测试用例
3. 风险评估
4. 质量建议"""
    
    qa_result = qa_agent.chat(qa_task)
    print(f"\n📝 QA Agent 输出:\n")
    print(qa_result)
    print()
    
    # 步骤4: Coordinator整合输出
    print("━" * 60)
    print("🎯 [Coordinator] 整合最终方案...")
    print("━" * 60)
    coord_task = f"""整合团队输出，形成完整的优化方案：

【PM 观点】
{pm_result}

【DEV 观点】
{dev_result}

【QA 观点】
{qa_result}

请整合形成：
1. 最终方案摘要
2. 行动计划
3. 风险与缓解措施
4. 预期成果"""
    
    final_result = coordinator.chat(coord_task)
    print(f"\n📝 Coordinator 最终输出:\n")
    print(final_result)
    print()
    
    # 保存结果
    result = {
        "task": task_description,
        "model": ZHIPU_MODEL,
        "timestamp": datetime.now().isoformat(),
        "agents": {
            "pm-agent": {"role": "产品经理", "output": pm_result},
            "dev-agent": {"role": "开发工程师", "output": dev_result},
            "qa-agent": {"role": "测试工程师", "output": qa_result},
            "coordinator": {"role": "团队协调者", "output": final_result}
        }
    }
    
    # 输出文件路径 - 优先从 config_center 读取
    try:
        from config_center import cfg
        output_dir = str(cfg.PROJECT_ROOT)
    except ImportError:
        import os
        output_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = f"{output_dir}/collaboration_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print("=" * 60)
    print("✅ 协作任务完成!")
    print("=" * 60)
    print(f"\n📄 结果已保存: {output_file}")
    print()
    
    return result

if __name__ == "__main__":
    # 获取项目路径
    try:
        from config_center import cfg
        project_path = str(cfg.PROJECT_ROOT)
    except ImportError:
        import os
        project_path = os.path.dirname(os.path.abspath(__file__))

    # 分析用户的AI Agent项目
    task = f"""分析并优化本地 AI Agent 项目

项目背景:
- 位置: {project_path}
- 类型: 智能数据分析 Agent 系统
- 核心功能: 缺陷分析、测试分析、风险评估

当前问题:
1. Token 消耗过高（单次分析可能消耗 120,000 tokens）
2. 响应速度慢
3. 缺乏智能上下文管理
4. 缺乏多 Agent 协作机制

目标:
- 降低 Token 消耗 50% 以上
- 提升响应速度 3-5 倍
- 实现智能上下文工程
- 建立多 Agent 协作架构"""
    
    run_collaboration_task(task)
