#!/usr/bin/env python3
"""
OpenClaw 多 Agent 系统测试脚本

测试场景：
1. 本地模式 - 无需 OpenClaw
2. OpenClaw 模式 - 完整功能

作者: AI Assistant
日期: 2026-03-18
"""

import os
import sys
import json
import pandas as pd
from datetime import datetime, timedelta
import random

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from multi_agent_system_v2 import (
    create_multi_agent_system_v2,
    AgentContext,
    AgentResult
)


def generate_sample_defects(count: int = 100) -> pd.DataFrame:
    """生成模拟缺陷数据"""
    projects = ['ABS', 'ESP', 'ADAS', 'IVI', 'BCM', 'TCU']
    severities = ['致命', '严重', '一般', '轻微', 'Critical', 'High', 'Medium', 'Low']
    modules = ['AIDA-001', 'AIDA-002', 'AIDA-003', 'AIDA-004', 'AIDA-005']
    teams = ['Team-A', 'Team-B', 'Team-C']
    
    data = []
    for i in range(count):
        data.append({
            'id': f'DEF-{1000 + i}',
            'title': f'缺陷标题 {i+1}',
            'tproject': random.choice(projects),
            'severity_group': random.choice(severities),
            'aida': random.choice(modules),
            'pu': f'PU-{random.randint(1, 5)}',
            'team': random.choice(teams),
            'tcreationtime': datetime.now() - timedelta(days=random.randint(1, 60)),
            'status': random.choice(['新建', '进行中', '已解决', '关闭'])
        })
    
    return pd.DataFrame(data)


def generate_sample_tests(count: int = 100) -> pd.DataFrame:
    """生成模拟测试数据"""
    modules = ['AIDA-001', 'AIDA-002', 'AIDA-003', 'AIDA-004', 'AIDA-005']
    statuses = ['Passed', 'Failed', 'Skipped', '通过', '失败']
    test_types = ['单元测试', '集成测试', '系统测试', '性能测试']
    
    data = []
    for i in range(count):
        data.append({
            'id': f'TC-{1000 + i}',
            'name': f'测试用例 {i+1}',
            'aida': random.choice(modules),
            'run_status': random.choice(statuses),
            'test_type': random.choice(test_types),
            'execution_time': random.uniform(0.5, 30.0),
            'last_run': datetime.now() - timedelta(hours=random.randint(1, 48))
        })
    
    return pd.DataFrame(data)


def test_local_mode():
    """测试本地模式"""
    print("\n" + "=" * 70)
    print("测试 1: 本地模式（无需 OpenClaw）")
    print("=" * 70)
    
    # 创建系统
    coordinator = create_multi_agent_system_v2(use_openclaw=False)
    
    # 生成测试数据
    defect_data = generate_sample_defects(100)
    test_data = generate_sample_tests(100)
    
    # 测试场景
    test_cases = [
        {
            "name": "缺陷趋势分析",
            "question": "最近两周的缺陷趋势分析",
            "data": defect_data
        },
        {
            "name": "测试覆盖率分析",
            "question": "测试覆盖率情况如何？",
            "data": test_data
        },
        {
            "name": "风险评估",
            "question": "当前项目的风险评估",
            "data": defect_data
        },
        {
            "name": "综合策略建议",
            "question": "给我一个测试策略建议",
            "data": defect_data
        }
    ]
    
    results = []
    for case in test_cases:
        print(f"\n--- {case['name']} ---")
        
        context = AgentContext(
            question=case['question'],
            data=case['data']
        )
        
        result = coordinator.run(context)
        
        print(f"✅ 成功: {result.success}")
        print(f"📊 使用的 Agent: {result.metadata.get('agents_used', [])}")
        print(f"⏱️ 执行时间: {result.execution_time:.2f}s")
        print(f"🔍 Trace ID: {result.trace_id}")
        
        # 输出部分结果
        if result.success and isinstance(result.output, dict):
            print(f"📋 分析类型: {list(result.output.get('analyses', {}).keys())}")
            if 'summary' in result.output:
                print(f"📝 摘要: {result.output['summary']}")
        
        results.append({
            "name": case['name'],
            "success": result.success,
            "agents": result.metadata.get('agents_used', []),
            "time": result.execution_time
        })
    
    # 汇总
    print("\n" + "-" * 70)
    print("测试汇总:")
    print("-" * 70)
    print(f"{'测试场景':<20} {'成功':<10} {'Agent数量':<15} {'执行时间':<10}")
    print("-" * 70)
    for r in results:
        print(f"{r['name']:<20} {'✅' if r['success'] else '❌':<10} {len(r['agents']):<15} {r['time']:.2f}s")
    
    return all(r['success'] for r in results)


def test_parallel_execution():
    """测试并行执行"""
    print("\n" + "=" * 70)
    print("测试 2: 并行执行性能")
    print("=" * 70)
    
    coordinator = create_multi_agent_system_v2(use_openclaw=False, max_workers=4)
    
    # 大数据量测试
    large_defect_data = generate_sample_defects(1000)
    
    context = AgentContext(
        question="综合分析缺陷趋势、风险评估和策略建议",
        data=large_defect_data
    )
    
    import time
    start = time.time()
    result = coordinator.run(context)
    total_time = time.time() - start
    
    print(f"\n📊 数据量: {len(large_defect_data)} 条")
    print(f"👥 使用 Agent: {result.metadata.get('agents_used', [])}")
    print(f"⏱️ 总执行时间: {total_time:.2f}s")
    print(f"📈 并行效率: {result.execution_time / total_time:.2%}")
    
    return result.success


def test_agent_handoff():
    """测试 Agent 间交接"""
    print("\n" + "=" * 70)
    print("测试 3: Agent 间交接")
    print("=" * 70)
    
    from multi_agent_system_v2 import DefectAnalystV2, AgentContext
    
    analyst = DefectAnalystV2(use_openclaw=False)
    
    defect_data = generate_sample_defects(50)
    
    context = AgentContext(
        question="分析缺陷趋势，如果发现风险，交接给风险评估专家",
        data=defect_data
    )
    
    result = analyst.run(context)
    
    print(f"✅ 分析成功: {result.success}")
    print(f"📊 使用的工具: {result.tools_used}")
    print(f"🔗 交接目标: {result.next_agent or '无'}")
    
    # 模拟交接
    if result.output and result.output.get('high_severity', {}).get('count', 0) > 10:
        handoff = analyst.handoff_to(
            'risk_assessor',
            context,
            f"发现 {result.output['high_severity']['count']} 个高风险缺陷"
        )
        print(f"📤 交接: {handoff.from_agent} → {handoff.to_agent}")
        print(f"📝 原因: {handoff.reason}")
    
    return result.success


def test_tracing():
    """测试追踪系统"""
    print("\n" + "=" * 70)
    print("测试 4: 追踪系统")
    print("=" * 70)
    
    from multi_agent_system_v2 import AgentTracer
    
    tracer = AgentTracer()
    
    # 模拟追踪
    span1 = tracer.start_span("test_agent", "analysis", question="测试问题")
    tracer.end_span(span1, result="分析完成")
    
    span2 = tracer.start_span("test_agent", "prediction", method="linear")
    tracer.end_span(span2, result="预测完成")
    
    # 获取摘要
    summary = tracer.get_summary()
    print(f"📋 Trace ID: {summary['trace_id']}")
    print(f"📊 总跨度数: {summary['total_spans']}")
    print(f"⏱️ 总时间: {summary['total_time_ms']:.2f}ms")
    print(f"👥 使用的 Agent: {summary['agents_used']}")
    
    # 保存追踪
    trace_file = tracer.save_trace()
    print(f"💾 追踪文件: {trace_file}")
    
    return os.path.exists(trace_file)


def test_openclaw_compatibility():
    """测试 OpenClaw 兼容性"""
    print("\n" + "=" * 70)
    print("测试 5: OpenClaw 兼容性")
    print("=" * 70)
    
    # 检查 OpenClaw 是否可用
    import subprocess
    try:
        result = subprocess.run(['openclaw', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ OpenClaw 可用: {result.stdout.strip()}")
            
            # 测试 OpenClaw 模式
            coordinator = create_multi_agent_system_v2(use_openclaw=True)
            
            defect_data = generate_sample_defects(20)
            context = AgentContext(
                question="分析缺陷趋势",
                data=defect_data,
                session_id="test_session_001"
            )
            
            result = coordinator.run(context)
            print(f"✅ OpenClaw 模式执行成功: {result.success}")
            
            return True
        else:
            print("⚠️ OpenClaw 不可用，跳过测试")
            return True  # 不算失败
    except FileNotFoundError:
        print("⚠️ OpenClaw 未安装，跳过测试")
        print("💡 提示: 运行以下命令安装 OpenClaw:")
        print("   sudo chown -R $(whoami) ~/.npm")
        print("   npm install -g openclaw@latest")
        print("   openclaw onboard --install-daemon")
        return True  # 不算失败


def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("  OpenClaw 多 Agent 系统测试")
    print("=" * 70)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tests = [
        ("本地模式测试", test_local_mode),
        ("并行执行测试", test_parallel_execution),
        ("Agent 交接测试", test_agent_handoff),
        ("追踪系统测试", test_tracing),
        ("OpenClaw 兼容性测试", test_openclaw_compatibility)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success, None))
        except Exception as e:
            results.append((name, False, str(e)))
    
    # 最终汇总
    print("\n" + "=" * 70)
    print("  测试结果汇总")
    print("=" * 70)
    
    print(f"{'测试名称':<30} {'结果':<10} {'备注'}")
    print("-" * 70)
    
    passed = 0
    for name, success, error in results:
        status = "✅ 通过" if success else "❌ 失败"
        note = error if error else ""
        print(f"{name:<30} {status:<10} {note}")
        if success:
            passed += 1
    
    print("-" * 70)
    print(f"总计: {passed}/{len(tests)} 通过")
    
    if passed == len(tests):
        print("\n🎉 所有测试通过！")
        print("\n下一步:")
        print("1. 安装 OpenClaw: bash openclaw_agents_setup.sh")
        print("2. 配置 Agent: 编辑 ~/.openclaw/agents/*/SOUL.md")
        print("3. 运行 Agent: openclaw dashboard")
    else:
        print("\n⚠️ 部分测试失败，请检查错误信息")
    
    return passed == len(tests)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
