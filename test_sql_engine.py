#!/usr/bin/env python3
"""
快速测试 SQL 查询引擎
"""

import sys
sys.path.insert(0, "/Users/kangyongge/WorkBuddy/Claw/testagent")

from sql_query_engine import create_sql_engine, SchemaManager

# 创建引擎
engine = create_sql_engine("database/local_data.db")

# 测试问题
test_questions = [
    "统计所有缺陷的数量",
    "各模块的缺陷数量统计",
    "测试通过率是多少"
]

print("=" * 60)
print("SQL 查询引擎测试")
print("=" * 60)

for i, question in enumerate(test_questions, 1):
    print(f"\n问题 {i}: {question}")
    print("-" * 60)
    
    # 由于没有实际 LLM，我们只能测试框架
    # 这里模拟 LLM 返回
    def mock_llm_generate(prompt):
        print(f"[Mock LLM] Prompt 长度: {len(prompt)} 字符")
        # 返回硬编码的 SQL（用于测试）
        if "数量" in question:
            return "SELECT COUNT(*) FROM defects"
        elif "通过率" in question:
            return "SELECT ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) FROM test_runs"
        elif "模块" in question:
            return "SELECT module, COUNT(*) FROM defects GROUP BY module"
        return "SELECT * FROM defects LIMIT 10"
    
    # 测试查询（使用 mock）
    try:
        # 注意：实际使用时需要真实的 LLM
        result = engine.query(
            question=question,
            llm_generate_func=mock_llm_generate,
            use_cache=False
        )
        
        if result["success"]:
            print(f"✅ 查询成功")
            print(f"SQL: {result['sql']}")
            print(f"结果行数: {len(result['result'])}")
            print(f"执行时间: {result['execution_time_ms']:.0f}ms")
        else:
            print(f"❌ 查询失败: {result.get('error')}")
    except Exception as e:
        print(f"❌ 异常: {e}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
