#!/usr/bin/env python3
"""
OpenClaw Agent 协作任务 - 智谱Coding Plan版本
使用Anthropic兼容API格式
"""

import os
import sys
import json
import requests
from datetime import datetime

# 智谱Coding Plan配置（Anthropic兼容格式）- 优先从 config_center 读取
try:
    from config_center import cfg
    ZHIPU_API_KEY = cfg.ZHIPU_API_KEY
    ZHIPU_BASE_URL = cfg.ZHIPU_ANTHROPIC_BASE_URL
    ZHIPU_MODEL = cfg.ZHIPU_MODEL
except ImportError:
    ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "")
    ZHIPU_BASE_URL = os.environ.get("ZHIPU_ANTHROPIC_BASE_URL", "https://open.bigmodel.cn/api/anthropic")
    ZHIPU_MODEL = os.environ.get("ZHIPU_MODEL", "glm-4.7")

class ZhipuCodingAgent:
    """智谱Coding Plan Agent - Anthropic兼容格式"""
    
    def __init__(self, name, role, system_prompt):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.history = []
    
    def chat(self, message):
        """调用智谱Coding Plan API（Anthropic格式）"""
        headers = {
            "Content-Type": "application/json",
            "x-api-key": ZHIPU_API_KEY,  # Anthropic使用 x-api-key
            "anthropic-version": "2023-06-01"
        }
        
        # 构建消息（Anthropic格式）
        messages = []
        for msg in self.history:
            messages.append(msg)
        messages.append({"role": "user", "content": message})
        
        payload = {
            "model": ZHIPU_MODEL,
            "max_tokens": 4096,
            "system": self.system_prompt,  # Anthropic使用单独的system字段
            "messages": messages
        }
        
        try:
            response = requests.post(
                f"{ZHIPU_BASE_URL}/v1/messages",
                headers=headers,
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                result = response.json()
                # Anthropic响应格式
                reply = result["content"][0]["text"]
                self.history.append({"role": "user", "content": message})
                self.history.append({"role": "assistant", "content": reply})
                return reply
            else:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = json.dumps(error_json, ensure_ascii=False)
                except:
                    pass
                return f"❌ API错误 {response.status_code}: {error_detail}"
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
    # prompts 模块不可用时使用精简版
    PM_PROMPT = """你是专业的产品经理。分析需求，输出：
1. 用户痛点
2. 用户故事（标准格式）
3. 验收标准
4. 优先级建议"""

    DEV_PROMPT = """你是资深的开发工程师。基于需求设计技术方案，输出：
1. 架构设计
2. 实施步骤
3. 技术要点
4. 预期效果"""

    QA_PROMPT = """你是专业的测试工程师。设计测试方案，输出：
1. 测试策略
2. 核心测试用例
3. 风险评估
4. 质量建议"""

    COORDINATOR_PROMPT = """你是团队协调者。整合PM/DEV/QA的输出，形成完整的优化方案。"""

def run_collaboration_task(task_description):
    """运行协作任务"""
    
    print("=" * 60)
    print("🦞 OpenClaw Agent 协作任务 - 智谱Coding Plan")
    print("=" * 60)
    print(f"\n📋 任务: {task_description[:50]}...")
    print(f"🤖 模型: {ZHIPU_MODEL}")
    print(f"🔗 Endpoint: {ZHIPU_BASE_URL}")
    print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 创建Agent团队
    pm_agent = ZhipuCodingAgent("pm-agent", "产品经理", PM_PROMPT)
    dev_agent = ZhipuCodingAgent("dev-agent", "开发工程师", DEV_PROMPT)
    qa_agent = ZhipuCodingAgent("qa-agent", "测试工程师", QA_PROMPT)
    coordinator = ZhipuCodingAgent("coordinator", "协调者", COORDINATOR_PROMPT)
    
    # 步骤1: PM分析需求
    print("━" * 60)
    print("👤 [PM Agent] 需求分析中...")
    print("━" * 60)
    
    pm_task = f"""分析以下AI Agent优化需求，输出需求分析、用户故事、验收标准、优先级建议：

{task_description}"""
    
    pm_result = pm_agent.chat(pm_task)
    print(f"\n{pm_result}\n")
    
    # 步骤2: DEV设计技术方案
    print("━" * 60)
    print("💻 [DEV Agent] 技术方案设计中...")
    print("━" * 60)
    
    dev_task = f"""基于PM分析，设计技术方案：

{pm_result}

输出架构设计、实施步骤、技术要点、预期效果。"""
    
    dev_result = dev_agent.chat(dev_task)
    print(f"\n{dev_result}\n")
    
    # 步骤3: QA设计测试方案
    print("━" * 60)
    print("🔍 [QA Agent] 测试方案设计中...")
    print("━" * 60)
    
    qa_task = f"""基于需求和方案，设计测试方案：

需求分析:
{pm_result}

技术方案:
{dev_result}

输出测试策略、核心测试用例、风险评估、质量建议。"""
    
    qa_result = qa_agent.chat(qa_task)
    print(f"\n{qa_result}\n")
    
    # 步骤4: Coordinator整合输出
    print("━" * 60)
    print("🎯 [Coordinator] 整合最终方案...")
    print("━" * 60)
    
    coord_task = f"""整合团队输出形成完整方案：

【PM观点】{pm_result}

【DEV观点】{dev_result}

【QA观点】{qa_result}

输出最终方案摘要、行动计划、风险与缓解措施。"""
    
    final_result = coordinator.chat(coord_task)
    print(f"\n{final_result}\n")
    
    # 保存结果
    result = {
        "task": task_description,
        "model": ZHIPU_MODEL,
        "endpoint": ZHIPU_BASE_URL,
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
    output_file = f"{output_dir}/coding_collaboration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print("=" * 60)
    print("✅ 协作任务完成!")
    print("=" * 60)
    print(f"\n📄 结果已保存: {output_file}\n")
    
    return result

if __name__ == "__main__":
    # 获取项目路径
    try:
        from config_center import cfg
        project_path = str(cfg.PROJECT_ROOT)
    except ImportError:
        import os
        project_path = os.path.dirname(os.path.abspath(__file__))

    task = f"""分析并优化本地 AI Agent 项目

项目位置: {project_path}
核心功能: 缺陷分析、测试分析、风险评估

当前问题:
1. Token 消耗过高（120,000 tokens）
2. 响应速度慢
3. 缺乏智能上下文管理
4. 缺乏多Agent协作机制

优化目标:
- Token 消耗降低 50%
- 响应速度提升 3-5 倍
- 实现智能上下文工程
- 建立多Agent协作架构"""

    run_collaboration_task(task)
