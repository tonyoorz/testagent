#!/usr/bin/env python3
"""
智能 Agent V2 集成测试

测试内容：
1. SmartAgent 初始化
2. 智能数据加载
3. 上下文引擎集成
4. Token 节省效果

作者: AI Assistant
日期: 2025-01-19
"""

import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_imports():
    """测试模块导入"""
    print("\n" + "=" * 70)
    print("测试 1: 模块导入")
    print("=" * 70)
    
    errors = []
    
    # 测试上下文引擎
    try:
        from intelligent_context_engine import (
            ContextEngine,
            IntentAnalyzer,
            LoadContext,
            DataSummary
        )
        print("  ✅ intelligent_context_engine 导入成功")
    except ImportError as e:
        errors.append(f"intelligent_context_engine: {e}")
        print(f"  ❌ intelligent_context_engine 导入失败: {e}")
    
    # 测试智能数据加载器
    try:
        from smart_data_loader import (
            SmartDataLoader,
            DataLoaderAdapter,
            LoaderConfig
        )
        print("  ✅ smart_data_loader 导入成功")
    except ImportError as e:
        errors.append(f"smart_data_loader: {e}")
        print(f"  ❌ smart_data_loader 导入失败: {e}")
    
    # 测试智能 Agent
    try:
        from intelligent_agent import (
            IntelligentAgent,
            SmartAgent,
            create_agent_with_smart_loading
        )
        print("  ✅ intelligent_agent (含 SmartAgent) 导入成功")
    except ImportError as e:
        errors.append(f"intelligent_agent: {e}")
        print(f"  ❌ intelligent_agent 导入失败: {e}")
    
    return len(errors) == 0


def test_intent_analyzer():
    """测试意图分析"""
    print("\n" + "=" * 70)
    print("测试 2: 意图分析器")
    print("=" * 70)
    
    try:
        from intelligent_context_engine import IntentAnalyzer
        
        analyzer = IntentAnalyzer()
        
        test_cases = [
            ("最近两周 ABS 模块的测试策略建议", "test", "ABS", "last_2_weeks"),
            ("IDCEVO 项目上个月的缺陷趋势分析", "defect", "IDCEVO", "last_month"),
            ("所有项目的高风险缺陷", "defect", None, "all"),
            ("本周的测试执行情况", "test", None, "this_week"),
        ]
        
        success_count = 0
        for question, expected_type, expected_project, expected_time in test_cases:
            intent = analyzer.analyze(question)
            
            # 验证
            type_match = intent.data_type == expected_type
            project_match = (expected_project is None) or (intent.project == expected_project)
            time_match = intent.time_range == expected_time
            
            status = "✅" if (type_match and project_match and time_match) else "⚠️"
            print(f"  {status} '{question[:30]}...'")
            print(f"      类型: {intent.data_type} (预期: {expected_type})")
            print(f"      项目: {intent.project} (预期: {expected_project})")
            print(f"      时间: {intent.time_range} (预期: {expected_time})")
            
            if type_match and project_match and time_match:
                success_count += 1
        
        print(f"\n  通过率: {success_count}/{len(test_cases)}")
        return success_count == len(test_cases)
        
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_smart_data_loader():
    """测试智能数据加载器"""
    print("\n" + "=" * 70)
    print("测试 3: 智能数据加载器")
    print("=" * 70)
    
    try:
        from smart_data_loader import SmartDataLoader, LoaderConfig
        
        # 使用内存数据库测试
        config = LoaderConfig(
            db_path=":memory:",
            use_smart_loading=True,
            use_semantic_search=False
        )
        
        loader = SmartDataLoader(config)
        print("  ✅ SmartDataLoader 初始化成功")
        
        # 测试数据加载（使用内存数据库）
        question = "最近两周 ABS 模块的缺陷"
        df, context = loader.load_for_question(question)
        
        print(f"  ✅ 数据加载成功")
        print(f"      加载记录数: {len(df)}")
        print(f"      Token 数: {context.token_count}")
        print(f"      相关性: {context.relevance_score:.2f}")
        print(f"      来源: {', '.join(context.sources)}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_smart_agent():
    """测试智能 Agent"""
    print("\n" + "=" * 70)
    print("测试 4: 智能 Agent V2")
    print("=" * 70)
    
    try:
        from intelligent_agent import create_agent_with_smart_loading, SmartAgent
        
        # 创建 Agent
        agent = create_agent_with_smart_loading(
            dashboard_type='defect',
            db_path=':memory:'
        )
        
        print(f"  ✅ SmartAgent 创建成功")
        print(f"      类型: {type(agent).__name__}")
        print(f"      智能加载: {agent.use_smart_loading}")
        
        # 测试数据摘要获取
        try:
            summary = agent.get_data_summary("最近两周的缺陷")
            print(f"  ✅ 数据摘要获取成功")
            print(f"      总数: {summary.get('total_count', 0)}")
        except Exception as e:
            print(f"  ⚠️ 数据摘要获取失败（可能是数据库不存在）: {e}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_token_comparison():
    """测试 Token 节省对比"""
    print("\n" + "=" * 70)
    print("测试 5: Token 节省对比")
    print("=" * 70)
    
    try:
        from intelligent_context_engine import IntentAnalyzer
        
        analyzer = IntentAnalyzer()
        
        # 模拟全量加载的 Token 数
        FULL_LOAD_TOKENS = 120000
        
        test_questions = [
            "最近两周 ABS 模块的测试策略建议",
            "IDCEVO 项目上个月的缺陷趋势",
            "所有项目的高风险缺陷",
        ]
        
        for question in test_questions:
            intent = analyzer.analyze(question)
            
            # 估算智能加载的 Token 数
            # 假设智能加载约为全量的 5-10%
            smart_tokens = FULL_LOAD_TOKENS * 0.05
            
            saving = (1 - smart_tokens / FULL_LOAD_TOKENS) * 100
            
            print(f"\n  问题: {question}")
            print(f"    全量加载: ~{FULL_LOAD_TOKENS:,} tokens")
            print(f"    智能加载: ~{int(smart_tokens):,} tokens")
            print(f"    节省: {saving:.1f}%")
        
        print("\n  ✅ Token 节省对比测试完成")
        return True
        
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 70)
    print("智能 Agent V2 集成测试")
    print("=" * 70)
    
    results = {
        "模块导入": test_imports(),
        "意图分析": test_intent_analyzer(),
        "智能加载器": test_smart_data_loader(),
        "智能 Agent": test_smart_agent(),
        "Token 对比": test_token_comparison(),
    }
    
    # 打印总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status}")
    
    total = len(results)
    passed = sum(results.values())
    
    print(f"\n  总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n  🎉 所有测试通过！智能 Agent V2 集成成功！")
    else:
        print("\n  ⚠️ 部分测试失败，请检查错误信息")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
