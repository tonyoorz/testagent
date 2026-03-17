#!/usr/bin/env python3
"""
Agent V2 完整集成测试

测试所有新增功能：
1. 向量检索引擎
2. 多 Agent 协作
3. 自我反思机制
4. 钩子与追踪系统

作者: AI Assistant
日期: 2025-01-19
"""

import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_vector_search():
    """测试向量检索引擎"""
    print("\n" + "=" * 70)
    print("测试 1: 向量检索引擎")
    print("=" * 70)
    
    try:
        from vector_search_engine import VectorSearchEngine, create_vector_engine
        
        # 创建引擎
        engine = create_vector_engine()
        print("  ✅ 向量引擎创建成功")
        
        # 测试文档
        documents = [
            {"id": 1, "text": "ABS 刹车系统故障", "project": "ABS"},
            {"id": 2, "text": "IDCEVO 显示屏异常", "project": "IDCEVO"},
            {"id": 3, "text": "ADC 传感器失效", "project": "ADC"},
        ]
        
        # 索引
        engine.index_documents(documents)
        print(f"  ✅ 索引完成: {len(documents)} 个文档")
        
        # 搜索
        results = engine.search("刹车问题", k=2)
        print(f"  ✅ 搜索完成: {len(results)} 个结果")
        
        for r in results[:2]:
            print(f"      - [{r.score:.3f}] {r.text}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multi_agent():
    """测试多 Agent 协作"""
    print("\n" + "=" * 70)
    print("测试 2: 多 Agent 协作")
    print("=" * 70)
    
    try:
        from multi_agent_system import (
            CoordinatorAgent,
            DefectAnalyst,
            TestAnalyst,
            RiskAssessor,
            StrategyAdvisor,
            AgentContext,
            create_multi_agent_system
        )
        
        # 创建协调者
        coordinator = create_multi_agent_system()
        print("  ✅ 多 Agent 系统创建成功")
        
        # 测试场景
        test_questions = [
            "最近两周 ABS 模块的缺陷趋势",
            "测试覆盖率风险评估",
            "给我一个测试策略建议",
        ]
        
        for question in test_questions:
            context = AgentContext(question=question)
            result = coordinator.run(context)
            
            status = "✅" if result.success else "❌"
            print(f"  {status} '{question[:30]}...'")
            print(f"      - 参与 Agent: {result.metadata.get('agents_used', [])}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_reflection():
    """测试自我反思机制"""
    print("\n" + "=" * 70)
    print("测试 3: 自我反思机制")
    print("=" * 70)
    
    try:
        from reflection_system import (
            ReflectionLoop,
            OutputValidator,
            Reflector,
            create_reflection_loop
        )
        
        # 创建反思循环
        loop = create_reflection_loop(max_iterations=3)
        print("  ✅ 反思循环创建成功")
        
        # 验证器测试
        validator = OutputValidator()
        validation = validator.validate(
            "ABS 模块的缺陷趋势",
            {"trend": "上升", "count": 10}
        )
        print(f"  ✅ 验证器工作正常，分数: {validation.score:.2f}")
        
        # 反思器测试
        reflector = Reflector()
        issues, improvements = reflector.reflect(
            "ABS 模块的缺陷趋势",
            {"trend": "上升"},
            validation
        )
        print(f"  ✅ 反思器工作正常，发现 {len(issues)} 个问题")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_hooks_and_tracing():
    """测试钩子和追踪系统"""
    print("\n" + "=" * 70)
    print("测试 4: 钩子与追踪系统")
    print("=" * 70)
    
    try:
        from hooks_and_tracing import (
            HookManager,
            TracingManager,
            TrackedAgent,
            HookType,
            HookContext,
            HookResult,
            create_hook_manager,
            create_tracing_manager,
            generate_trace_report
        )
        
        # 创建钩子管理器
        hook_manager = create_hook_manager()
        print("  ✅ 钩子管理器创建成功")
        
        # 创建追踪管理器
        tracing_manager = create_tracing_manager()
        print("  ✅ 追踪管理器创建成功")
        
        # 创建追踪 Agent
        agent = TrackedAgent("test_agent")
        print("  ✅ 追踪 Agent 创建成功")
        
        # 执行任务
        result = agent.run("测试问题")
        print(f"  ✅ 任务执行完成: {result.get('answer', '')[:30]}...")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_integration():
    """测试完整集成"""
    print("\n" + "=" * 70)
    print("测试 5: 完整集成")
    print("=" * 70)
    
    try:
        from multi_agent_system import create_multi_agent_system, AgentContext
        from reflection_system import create_reflection_loop
        from hooks_and_tracing import TrackedAgent, HookType
        import pandas as pd
        
        print("  正在组装所有组件...")
        
        # 创建数据
        df = pd.DataFrame({
            "id": [1, 2, 3, 4, 5],
            "tproject": ["ABS", "IDCEVO", "ABS", "ADC", "ABS"],
            "severity_group": ["高", "中", "高", "低", "高"],
            "tcreationtime": pd.date_range(start="2024-01-01", periods=5)
        })
        
        # 创建多 Agent 系统
        coordinator = create_multi_agent_system()
        
        # 创建反思循环
        reflection_loop = create_reflection_loop(max_iterations=2)
        
        # 执行分析
        question = "ABS 模块的高风险缺陷分析"
        context = AgentContext(question=question, data=df)
        
        print(f"  问题: {question}")
        
        # 运行协调者
        result = coordinator.run(context)
        
        print(f"  ✅ 分析完成:")
        print(f"      - 成功: {result.success}")
        print(f"      - 参与 Agent: {result.metadata.get('agents_used', [])}")
        print(f"      - 分析结果: {list(result.output.get('analyses', {}).keys())}")
        
        # 验证
        quality = reflection_loop.quick_validate(question, result.output)
        print(f"      - 输出质量: {quality:.2f}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 70)
    print("Agent V2 完整功能测试")
    print("=" * 70)
    
    results = {
        "向量检索引擎": test_vector_search(),
        "多 Agent 协作": test_multi_agent(),
        "自我反思机制": test_reflection(),
        "钩子与追踪": test_hooks_and_tracing(),
        "完整集成": test_integration(),
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
        print("\n  🎉 所有测试通过！Agent V2 全部功能就绪！")
    else:
        print("\n  ⚠️ 部分测试失败，请检查错误信息")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
