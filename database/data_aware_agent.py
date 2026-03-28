#!/usr/bin/env python3
"""
数据感知Agent - 集成智谱AI和数据理解能力
让用户可以用自然语言查询测试和缺陷数据
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.agent_data_understanding import AgentDataUnderstanding
from database.optimized_db_manager import OptimizedDatabaseManager
import requests
import json
from datetime import datetime
from typing import Dict, List, Any

# 智谱AI配置 - 优先从 config_center 读取
try:
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from config_center import cfg as _cfg
    ZHIPU_API_KEY = _cfg.ZHIPU_API_KEY
    ZHIPU_BASE_URL = _cfg.ZHIPU_ANTHROPIC_BASE_URL
    ZHIPU_MODEL = _cfg.ZHIPU_MODEL
except ImportError:
    import os as _os
    ZHIPU_API_KEY = _os.environ.get("ZHIPU_API_KEY", "")
    ZHIPU_BASE_URL = _os.environ.get("ZHIPU_ANTHROPIC_BASE_URL", "https://open.bigmodel.cn/api/anthropic")
    ZHIPU_MODEL = _os.environ.get("ZHIPU_MODEL", "glm-4.7")

class DataAwareAgent:
    """数据感知Agent - 能够理解和查询测试/缺陷数据"""
    
    def __init__(self, db_path: str = 'database/local_data.db'):
        self.db_path = db_path
        self.data_understanding = AgentDataUnderstanding(db_path)
        self.db_manager = OptimizedDatabaseManager(db_path)
        self.history = []
        
        # 系统提示词
        self.system_prompt = f"""你是一个专业的测试数据分析师，能够帮助用户查询和分析测试和缺陷数据。

## 你的能力

1. **数据查询**: 可以查询测试运行数据和缺陷数据
2. **数据分析**: 提供测试通过率、缺陷分布等分析
3. **趋势报告**: 展示测试和缺陷的趋势变化
4. **问题诊断**: 帮助识别质量问题和高风险模块

## 数据库结构

{self.data_understanding.schema_context}

## 回答规则

1. 当用户询问测试或缺陷相关问题时，先使用工具查询数据
2. 基于查询结果给出专业的分析和建议
3. 使用表格和列表让数据更易读
4. 如果数据不足，说明情况并建议补充数据

## 查询示例

- "测试通过率是多少?" → 查询测试统计
- "有多少个Open的缺陷?" → 查询缺陷状态分布
- "ABS系统的测试情况?" → 按项目筛选查询
- "显示Critical缺陷列表" → 列出严重缺陷
"""
    
    def chat_with_llm(self, message: str) -> str:
        """调用智谱AI LLM"""
        headers = {
            "Content-Type": "application/json",
            "x-api-key": ZHIPU_API_KEY,
            "anthropic-version": "2023-06-01"
        }
        
        messages = []
        for msg in self.history:
            messages.append(msg)
        messages.append({"role": "user", "content": message})
        
        payload = {
            "model": ZHIPU_MODEL,
            "max_tokens": 4096,
            "system": self.system_prompt,
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
                reply = result["content"][0]["text"]
                self.history.append({"role": "user", "content": message})
                self.history.append({"role": "assistant", "content": reply})
                return reply
            else:
                return f"❌ API错误: {response.status_code}"
        except Exception as e:
            return f"❌ 请求失败: {str(e)}"
    
    def process_message(self, message: str) -> str:
        """处理用户消息"""
        # 先检查是否是数据查询
        intent = self.data_understanding.understand_question(message)
        
        if intent["domain"] in ["test", "defect"]:
            # 是数据查询，先查询数据
            query_result = self.data_understanding.execute_query(intent)
            
            if query_result["success"]:
                # 构建上下文消息给LLM
                context_message = f"""
用户问题: {message}

数据库查询结果:
{json.dumps(query_result['data'], ensure_ascii=False, indent=2)}

请基于以上数据回答用户的问题，提供专业的分析和建议。使用表格和列表让数据更清晰。
"""
                return self.chat_with_llm(context_message)
            else:
                return f"❌ 查询失败: {query_result['message']}"
        else:
            # 普通对话，直接交给LLM
            return self.chat_with_llm(message)
    
    def load_sample_data(self):
        """加载示例数据"""
        # 添加测试运行示例
        test_runs = [
            {'run_id': 'TR-26-001', 'test_name': '用户登录测试', 'status': 'Passed', 'tester': '张三', 'project': 'ABS系统', 'module': '用户管理', 'test_week': '26-CW11'},
            {'run_id': 'TR-26-002', 'test_name': '数据导入测试', 'status': 'Failed', 'tester': '李四', 'project': 'ABS系统', 'module': '数据处理', 'test_week': '26-CW11'},
            {'run_id': 'TR-26-003', 'test_name': '报表生成测试', 'status': 'Passed', 'tester': '张三', 'project': 'ABS系统', 'module': '报表', 'test_week': '26-CW11'},
            {'run_id': 'TR-26-004', 'test_name': '接口联调测试', 'status': 'Passed', 'tester': '王五', 'project': 'ABS系统', 'module': '接口', 'test_week': '26-CW10'},
            {'run_id': 'TR-26-005', 'test_name': '性能测试', 'status': 'Failed', 'tester': '李四', 'project': 'ABC系统', 'module': '性能', 'test_week': '26-CW11'},
        ]
        self.db_manager.bulk_insert_test_runs(test_runs)
        
        # 添加缺陷示例
        defects = [
            {'defect_id': 'DEF-26-001', 'title': '登录失败时无提示信息', 'severity': 'Major', 'status': 'Open', 'project': 'ABS系统', 'module': '用户管理', 'detected_by': '张三', 'creation_time': '2026-03-15'},
            {'defect_id': 'DEF-26-002', 'title': '数据导入时系统崩溃', 'severity': 'Critical', 'status': 'In Progress', 'project': 'ABS系统', 'module': '数据处理', 'detected_by': '李四', 'creation_time': '2026-03-16'},
            {'defect_id': 'DEF-26-003', 'title': '报表导出格式错误', 'severity': 'Minor', 'status': 'Closed', 'project': 'ABS系统', 'module': '报表', 'detected_by': '张三', 'creation_time': '2026-03-14'},
            {'defect_id': 'DEF-26-004', 'title': '接口响应超时', 'severity': 'Major', 'status': 'Open', 'project': 'ABC系统', 'module': '接口', 'detected_by': '王五', 'creation_time': '2026-03-17'},
            {'defect_id': 'DEF-26-005', 'title': '性能测试未达标', 'severity': 'Major', 'status': 'Open', 'project': 'ABC系统', 'module': '性能', 'detected_by': '李四', 'creation_time': '2026-03-18'},
        ]
        self.db_manager.bulk_insert_defects(defects)
        
        print("✅ 示例数据加载完成")
    
    def start_interactive_session(self):
        """启动交互式对话"""
        print("=" * 60)
        print("🤖 数据感知Agent已启动 (智谱AI + 数据库)")
        print("=" * 60)
        print("\n你可以问我关于测试和缺陷的问题，例如：")
        print("- 测试通过率是多少?")
        print("- 有多少个Open的缺陷?")
        print("- ABS系统的测试情况怎么样?")
        print("- 显示所有的Critical缺陷")
        print("\n输入 'quit' 退出\n")
        
        while True:
            try:
                user_input = input("👤 你: ").strip()
                
                if user_input.lower() in ['quit', 'exit', '退出']:
                    print("\n👋 再见!")
                    break
                
                if not user_input:
                    continue
                
                print("\n🤖 Agent: ", end="")
                response = self.process_message(user_input)
                print(response)
                print()
                
            except KeyboardInterrupt:
                print("\n\n👋 再见!")
                break
            except Exception as e:
                print(f"\n❌ 错误: {str(e)}\n")
    
    def close(self):
        """关闭资源"""
        self.data_understanding.close()
        self.db_manager.close()


def main():
    """主函数"""
    # 动态获取数据库路径
    try:
        from config_center import cfg
        db_path = str(cfg.DATABASE_FILE)
    except ImportError:
        import os
        _this_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(_this_dir, 'local_data.db')

    # 创建Agent
    agent = DataAwareAgent(db_path)
    
    # 加载示例数据
    print("📦 加载示例数据...")
    agent.load_sample_data()
    
    # 启动交互式对话
    agent.start_interactive_session()
    
    # 清理
    agent.close()


if __name__ == "__main__":
    main()
