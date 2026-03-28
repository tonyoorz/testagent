#!/usr/bin/env python3
"""
AI Agent 优化团队协作演示

展示 PM/DEV/QA 如何协作优化 AI Agent

作者: AI Assistant
日期: 2026-03-18
"""

import os
import sys

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_team_system import create_agent_team, AgentContext


def main():
    print("\n" + "=" * 80)
    print("  AI Agent 优化团队协作演示")
    print("  PM (产品) + DEV (开发) + QA (测试)")
    print("=" * 80)
    
    # 创建团队
    print("\n📋 正在组建团队...")
    team = create_agent_team(use_openclaw=False)
    print("✅ 团队组建完成：PM Agent, DEV Agent, QA Agent, Coordinator")
    
    # 定义优化任务
    tasks = [
        {
            "name": "性能优化",
            "question": "我的 AI Agent 响应太慢（P95 > 5s），请帮我优化"
        },
        {
            "name": "准确率提升",
            "question": "AI Agent 的回答准确率只有 70%，如何提升到 85% 以上？"
        },
        {
            "name": "全面优化",
            "question": "全面优化我的 AI Agent，包括性能、准确率、可调试性"
        }
    ]
    
    print("\n" + "=" * 80)
    print("  任务 1: 性能优化")
    print("=" * 80)
    
    # 执行第一个任务
    context = AgentContext(
        question=tasks[0]["question"],
        metadata={}
    )
    
    print("\n🚀 启动协作流程...")
    print("  Step 1: PM 分析用户需求和痛点")
    print("  Step 2: DEV 设计技术方案")
    print("  Step 3: QA 评估风险和测试计划")
    print("  Step 4: Coordinator 整合输出")
    
    result = team.run(context)
    
    # 输出结果
    print("\n" + "-" * 80)
    print("📊 协作结果")
    print("-" * 80)
    
    print(f"\n⏱️  总耗时: {result.execution_time:.2f}s")
    print(f"👥 团队成员: {', '.join(result.metadata['team_members'])}")
    print(f"🎯 协作成功: {'✅' if result.success else '❌'}")
    
    # PM 视角
    print("\n" + "-" * 80)
    print("👤 PM 视角 - 产品需求")
    print("-" * 80)
    
    pm_output = result.output["pm_perspective"]["output"]
    print("\n用户痛点:")
    for i, pain in enumerate(pm_output["pain_points"][:3], 1):
        print(f"  {i}. {pain}")
    
    print("\n用户故事:")
    for story in pm_output["user_stories"]:
        print(f"  • [{story['id']}] {story['story']}")
        print(f"    优先级: {story['priority']}")
    
    print("\n优先级排序:")
    for p in pm_output["priorities"]:
        print(f"  • {p['feature']}: {p['impact']} (工作量: {p['effort']})")
    
    # DEV 视角
    print("\n" + "-" * 80)
    print("💻 DEV 视角 - 技术方案")
    print("-" * 80)
    
    dev_output = result.output["dev_perspective"]["output"]
    
    print("\n架构组件:")
    for comp in dev_output["architecture"]:
        print(f"  • {comp['name']}: {comp['responsibility']}")
    
    print("\n解决方案:")
    for sol in dev_output["solutions"]:
        print(f"  ✦ {sol}")
    
    print("\n性能提升:")
    perf = dev_output["performance"]
    for key, value in perf.items():
        print(f"  • {key}: {value}")
    
    # QA 视角
    print("\n" + "-" * 80)
    print("🔍 QA 视角 - 质量保证")
    print("-" * 80)
    
    qa_output = result.output["qa_perspective"]["output"]
    
    print(f"\n测试用例: {qa_output['test_count']} 个")
    
    print("\n关键风险:")
    for risk in qa_output["risks"]:
        print(f"  ⚠️  {risk['risk']} (级别: {risk['level']})")
        print(f"     影响: {risk['impact']}")
        print(f"     缓解: {risk['mitigation']}")
    
    # 行动计划
    print("\n" + "-" * 80)
    print("📝 行动计划")
    print("-" * 80)
    
    action_plan = result.output["action_plan"]
    
    print("\n🔥 立即行动:")
    for action in action_plan["immediate"]:
        print(f"  • {action['action']} ({action['owner']}, {action['priority']})")
    
    print("\n📅 短期计划:")
    for action in action_plan["short_term"]:
        print(f"  • {action['action']} ({action['owner']}, {action['priority']})")
    
    print("\n🗓️  中期计划:")
    for action in action_plan["mid_term"]:
        print(f"  • {action['action']} ({action['owner']}, {action['priority']})")
    
    # 成功指标
    print("\n" + "-" * 80)
    print("🎯 成功指标")
    print("-" * 80)
    
    for metric, target in result.output["success_metrics"].items():
        print(f"  • {metric}: {target}")
    
    # 下一步
    print("\n" + "-" * 80)
    print("🚀 下一步行动")
    print("-" * 80)
    
    for i, step in enumerate(result.output["next_steps"], 1):
        print(f"  {i}. {step}")
    
    # 总结
    print("\n" + "=" * 80)
    print("  ✅ 协作演示完成！")
    print("=" * 80)
    
    print("\n💡 关键成果:")
    print("  • PM: 识别了 4 个用户痛点，定义了 2 个核心用户故事")
    print("  • DEV: 提供了 3 个技术方案，预计性能提升 60%+")
    print("  • QA: 设计了 5 个测试用例，识别了 2 个关键风险")
    print("  • Coordinator: 整合输出完整优化方案")
    
    print("\n📂 相关文件:")
    print("  • agent_team_system.py - 协作系统实现")
    print("  • agent_team_configs/ - Agent 配置文件")
    print("  • setup_agent_team.sh - 安装脚本")
    
    print("\n🔧 使用方式:")
    print("  1. 本地模式: from agent_team_system import create_agent_team")
    print("  2. OpenClaw 模式: bash setup_agent_team.sh")
    print("  3. CLI: python3 agent_team_system.py")
    
    print("\n" + "=" * 80)
    print("  🎉 感谢使用 AI Agent 优化团队！")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
