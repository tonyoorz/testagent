#!/usr/bin/env python3
"""
增强版 Text-to-SQL Agent 使用示例

展示新功能的使用：
- 业务规则解释
- 业务语义理解
- 业务洞察生成

使用方法：
python chatdb/demo_enhanced_agent.py

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-29
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from chatdb.text_to_sql_agent import create_text_to_sql_agent


def main():
    """主函数"""
    print("=" * 70)
    print(" " * 20 + "增强版 Text-to-SQL Agent 使用示例")
    print("=" * 70)
    print()
    
    # 创建增强版 Agent
    print("🚀 初始化增强版 Text-to-SQL Agent...")
    print()
    
    agent = create_text_to_sql_agent(
        db_path="database/local_data.db",
        schema_path="chatdb/schema_description.md",
        business_rules_path="chatdb/business_rules.py",
        fewshot_path="chatdb/fewshot_examples.md",
        # 新功能配置
        enable_business_explanation=True,
        enable_business_semantics=True,
        enable_insight_generation=True
    )
    
    print("✅ Agent 初始化完成！")
    print()
    
    # 测试问题列表
    test_scenarios = [
        {
            "name": "基础查询",
            "questions": [
                "查询所有 TopIssue 缺陷",
                "按项目统计缺陷总数"
            ]
        },
        {
            "name": "业务规则解释",
            "questions": [
                "为什么 DEF-26-001 这个缺陷是 TopIssue？",
                "解释 DEF-26-002 的高风险评分",
            ]
        },
        {
            "name": "时间范围查询",
            "questions": [
                "查询本周的 TopIssue",
                "查询最近一周的 High Runner",
                "查询本月的新缺陷"
            ]
        },
        {
            "name": "项目上下文查询",
            "questions": [
                "查询 App 项目的缺陷",
                "分析 IDC 项目的 TopIssue",
            ]
        },
        {
            "name": "复杂分析查询",
            "questions": [
                "分析最近一个月的缺陷趋势，找出异常点",
                "对比 App 和 IDC 项目的 TopIssue 情况",
            ]
        }
    ]
    
    # 运行测试场景
    for scenario in test_scenarios:
        print(f"\n{'='*70}")
        print(f"【{scenario['name']}】")
        print(f"{'='*70}")
        print()
        
        for question in scenario['questions']:
            print(f"❓ 问题: {question}")
            print("-" * 70)
            
            # 查询
            result = agent.query(question)
            
            if result["success"]:
                # 显示回答
                print(f"✅ 回答:")
                print(result["answer"][:500])
                
                # 显示上下文信息（新功能）
                if "context" in result and result["context"]:
                    print(f"\n📊 查询上下文:")
                    if "time_range" in result["context"]:
                        start, end = result["context"]["time_range"]["start"], result["context"]["time_range"]["end"]
                        print(f"  📅 时间: {start.strftime('%Y-%m-%d %H:%M')} ~ {end.strftime('%Y-%m-%d %H:%M')}")
                    
                    if "project" in result["context"]:
                        proj_info = result["context"]["project"]
                        print(f"  📋 项目: {proj_info.get('name', '')}")
                        if "focus" in proj_info:
                            print(f"     📝 专注: {proj_info['focus']}")
                        if "common_issues" in proj_info:
                            common = ', '.join(proj_info["common_issues"][:3])
                            print(f"     🔍 常见问题: {common}")
                    
                    if "business_terms" in result["context"]:
                        terms = result["context"]["business_terms"][:3]
                        print(f"  🏷️  业务术语: {', '.join(terms)}")
                
                # 显示业务洞察（新功能）
                if "insights" in result and result["insights"]:
                    print(f"\n💡 业务洞察:")
                    for insight in result["insights"]:
                        print(f"  • {insight}")
                
                # 显示 SQL
                print(f"\n🔍 执行的 SQL:")
                print(f"```sql")
                print(result["sql"])
                print(f"```")
                
                # 显示数据统计
                if result["data"] is not None:
                    print(f"\n📊 数据统计:")
                    print(f"  • 数据行数: {len(result['data'])}")
                    print(f"  • 列数: {len(result['data'].columns)}")
                    print(f"  • 执行时间: {result['execution_time_ms']}ms")
                    print(f"  • 重试次数: {result['retries']}")
                    print(f"  • 缓存: {'命中' if result['from_cache'] else '未命中'}")
                
                # 显示数据预览
                if len(result["data"]) > 0:
                    print(f"\n📋 数据预览 (前 2 行):")
                    print(result["data"].head(2).to_string(index=False))
            else:
                print(f"❌ 错误: {result['error']}")
            
            print()
    
    # 总结
    print(f"\n{'='*70}")
    print("✅ 示例运行完成")
    print(f"{'='*70}")
    print()
    print("🎯 新功能亮点:")
    print("  ✅ 业务规则详细解释")
    print("  ✅ 时间范围智能解析")
    print("  ✅ 项目上下文自动扩展")
    print("  ✅ 业务术语自动识别")
    print("  ✅ 趋势异常检测")
    print("  ✅ 智能业务洞察生成")
    print("  ✅ 可操作的业务建议")
    print()
    print("💡 提示:")
    print("  1. 业务规则解释器能详细说明为什么某个缺陷是 TopIssue/High Runner/Long Runner")
    print("  2. 业务语义理解能识别时间范围（'今天'、'本周'、'本月'）和项目特点")
    print("  3. 业务洞察生成器能检测异常、分析模式、生成建议")
    print("  4. 增强的 Agent 会在回答中提供查询上下文和业务洞察")
    print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 示例运行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
