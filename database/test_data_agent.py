#!/usr/bin/env python3
"""测试数据感知Agent"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.optimized_db_manager import OptimizedDatabaseManager
from database.agent_data_understanding import AgentDataUnderstanding

# 动态获取数据库路径
try:
    from config_center import cfg
    DB_PATH = str(cfg.DATABASE_FILE)
except ImportError:
    import os
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(_this_dir, 'local_data.db')

def test_database():
    """测试数据库"""
    print("=" * 60)
    print("📊 测试数据库管理器")
    print("=" * 60)
    
    db = OptimizedDatabaseManager(DB_PATH)
    
    # 插入测试数据
    print("\n📦 插入测试数据...")
    test_runs = [
        {'run_id': 'TR-26-001', 'test_name': '用户登录测试', 'status': 'Passed', 'tester': '张三', 'project': 'ABS系统', 'module': '用户管理', 'test_week': '26-CW11'},
        {'run_id': 'TR-26-002', 'test_name': '数据导入测试', 'status': 'Failed', 'tester': '李四', 'project': 'ABS系统', 'module': '数据处理', 'test_week': '26-CW11'},
        {'run_id': 'TR-26-003', 'test_name': '报表生成测试', 'status': 'Passed', 'tester': '张三', 'project': 'ABS系统', 'module': '报表', 'test_week': '26-CW11'},
        {'run_id': 'TR-26-004', 'test_name': '接口联调测试', 'status': 'Passed', 'tester': '王五', 'project': 'ABS系统', 'module': '接口', 'test_week': '26-CW10'},
        {'run_id': 'TR-26-005', 'test_name': '性能测试', 'status': 'Failed', 'tester': '李四', 'project': 'ABC系统', 'module': '性能', 'test_week': '26-CW11'},
    ]
    db.bulk_insert_test_runs(test_runs)
    
    defects = [
        {'defect_id': 'DEF-26-001', 'title': '登录失败时无提示信息', 'severity': 'Major', 'status': 'Open', 'project': 'ABS系统', 'module': '用户管理', 'detected_by': '张三'},
        {'defect_id': 'DEF-26-002', 'title': '数据导入时系统崩溃', 'severity': 'Critical', 'status': 'In Progress', 'project': 'ABS系统', 'module': '数据处理', 'detected_by': '李四'},
        {'defect_id': 'DEF-26-003', 'title': '报表导出格式错误', 'severity': 'Minor', 'status': 'Closed', 'project': 'ABS系统', 'module': '报表', 'detected_by': '张三'},
        {'defect_id': 'DEF-26-004', 'title': '接口响应超时', 'severity': 'Major', 'status': 'Open', 'project': 'ABC系统', 'module': '接口', 'detected_by': '王五'},
        {'defect_id': 'DEF-26-005', 'title': '性能测试未达标', 'severity': 'Major', 'status': 'Open', 'project': 'ABC系统', 'module': '性能', 'detected_by': '李四'},
    ]
    db.bulk_insert_defects(defects)
    
    print("✅ 测试数据插入完成")
    db.close()

def test_data_understanding():
    """测试数据理解层"""
    print("\n" + "=" * 60)
    print("🧠 测试数据理解层")
    print("=" * 60)
    
    agent = AgentDataUnderstanding(DB_PATH)
    
    questions = [
        "测试通过率是多少?",
        "有多少个Open的缺陷?",
        "ABS系统的测试情况怎么样?",
        "显示所有的Critical缺陷",
        "测试趋势如何?"
    ]
    
    for q in questions:
        print(f"\n❓ 问题: {q}")
        answer = agent.answer_question(q)
        print(f"📝 回答:\n{answer}")
        print("-" * 40)
    
    agent.close()

if __name__ == "__main__":
    test_database()
    test_data_understanding()
    print("\n✅ 所有测试完成!")
