#!/usr/bin/env python3
"""
Text-to-SQL Agent 集成示例

展示如何将 text-to-SQL agent 集成到现有的 testagent 项目中。

集成方式：
1. 集成到 ai_chat_with_sql.py
2. 集成到 enhanced_ai_chat_with_sql.py
3. 作为独立服务使用

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-28
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ============================================================================
# 集成方式 1: 集成到 ai_chat_with_sql.py
# =============================================================================

class AIChatWithTextToSQL:
    """
    集成 text-to-SQL agent 到 ai_chat_with_sql.py
    
    替换原有的 sql_query_engine，使用 LangChain + Few-shot 学习
    """
    
    def __init__(self, db_path: str = None):
        """
        初始化
        
        Args:
            db_path: 数据库路径
        """
        # 导入 text-to-SQL agent
        from chatdb.text_to_sql_agent import create_text_to_sql_agent
        
        # 创建 agent
        self.sql_agent = create_text_to_sql_agent(
            db_path=db_path or "database/local_data.db",
            schema_path="chatdb/schema_description.md",
            business_rules_path="chatdb/business_rules.py",
            fewshot_path="chatdb/fewshot_examples.md",
            max_retries=3,
            enable_cache=True
        )
        
        print("✅ AI Chat with Text-to-SQL 初始化完成")
    
    def ask(self, question: str, enable_sql: bool = True) -> dict:
        """
        提问并回答
        
        Args:
            question: 用户问题
            enable_sql: 是否启用 SQL 查询
        
        Returns:
            {
                "success": bool,
                "answer": str,
                "sql": Optional[str],
                "data": Optional[pd.DataFrame],
                "source": "sql" | "llm"
            }
        """
        if enable_sql and self._is_sql_question(question):
            # 使用 text-to-SQL agent
            result = self.sql_agent.query(question)
            
            if result["success"]:
                return {
                    "success": True,
                    "answer": result["answer"],
                    "sql": result["sql"],
                    "data": result["data"],
                    "source": "sql"
                }
            else:
                # 降级到 LLM
                return {
                    "success": False,
                    "answer": f"SQL 查询失败: {result['error']}",
                    "source": "sql_failed"
                }
        else:
            # 直接用 LLM 回答
            return {
                "success": True,
                "answer": f"这个问题需要更多信息才能回答。",
                "source": "llm"
            }
    
    def _is_sql_question(self, question: str) -> bool:
        """判断问题是否需要 SQL 查询"""
        sql_keywords = [
            "多少", "数量", "统计", "排名", "最高", "最低", "平均",
            "查询", "列出", "展示", "显示", "查看",
            "通过率", "覆盖率", "缺陷", "测试", "失败", "成功",
            "趋势", "对比", "分布", "top", "前"
        ]
        
        return any(keyword in question for keyword in sql_keywords)


# ============================================================================
# 集成方式 2: 集成到 enhanced_ai_chat_with_sql.py
# =============================================================================

class EnhancedAIChatWithTextToSQL:
    """
    集成 text-to-SQL agent 到 enhanced_ai_chat_with_sql.py
    
    提供智能路由和高级分析功能
    """
    
    def __init__(self, db_path: str = None, enable_agent: bool = True):
        """
        初始化
        
        Args:
            db_path: 数据库路径
            enable_agent: 是否启用智能 Agent
        """
        from chatdb.text_to_sql_agent import create_text_to_sql_agent
        
        # 创建 text-to-SQL agent
        self.sql_agent = create_text_to_sql_agent(
            db_path=db_path or "database/local_data.db",
            schema_path="chatdb/schema_description.md",
            business_rules_path="chatdb/business_rules.py",
            fewshot_path="chatdb/fewshot_examples.md",
            max_retries=3,
            enable_cache=True
        )
        
        self.enable_agent = enable_agent
        
        print("✅ Enhanced AI Chat with Text-to-SQL 初始化完成")
    
    def ask(self, question: str, use_intelligent_routing: bool = True) -> dict:
        """
        提问并回答（智能路由）
        
        Args:
            question: 用户问题
            use_intelligent_routing: 是否使用智能路由
        
        Returns:
            {
                "success": bool,
                "answer": str,
                "route": "sql" | "agent" | "llm",
                "sql": Optional[str],
                "data": Optional[pd.DataFrame]
            }
        """
        if use_intelligent_routing:
            # 智能路由
            route = self._intelligent_route(question)
        else:
            # 默认路由
            route = "sql" if self._is_sql_question(question) else "llm"
        
        if route == "sql":
            # 使用 text-to-SQL agent
            result = self.sql_agent.query(question)
            
            return {
                "success": result["success"],
                "answer": result["answer"],
                "route": "sql",
                "sql": result.get("sql"),
                "data": result.get("data"),
                "error": result.get("error")
            }
        
        elif route == "agent" and self.enable_agent:
            # 使用智能 Agent
            # 这里可以集成 multi_agent_system
            return {
                "success": True,
                "answer": "智能 Agent 模式（待实现）",
                "route": "agent"
            }
        
        else:
            # 使用 LLM
            return {
                "success": True,
                "answer": "这个问题需要更多信息才能回答。",
                "route": "llm"
            }
    
    def _intelligent_route(self, question: str) -> str:
        """智能路由判断"""
        # SQL 查询关键词
        sql_keywords = [
            "多少", "数量", "统计", "排名", "最高", "最低", "平均",
            "查询", "列出", "展示", "显示", "查看",
            "通过率", "覆盖率", "缺陷", "测试", "失败", "成功",
            "趋势", "对比", "分布", "top", "前"
        ]
        
        # Agent 分析关键词
        agent_keywords = [
            "分析", "报告", "洞察", "建议", "优化",
            "为什么", "原因", "问题", "影响"
        ]
        
        question_lower = question.lower()
        
        if any(keyword in question for keyword in sql_keywords):
            return "sql"
        elif any(keyword in question for keyword in agent_keywords):
            return "agent"
        else:
            return "llm"
    
    def _is_sql_question(self, question: str) -> bool:
        """判断问题是否需要 SQL 查询"""
        sql_keywords = [
            "多少", "数量", "统计", "排名", "最高", "最低", "平均",
            "查询", "列出", "展示", "显示", "查看",
            "通过率", "覆盖率", "缺陷", "测试", "失败", "成功",
            "趋势", "对比", "分布", "top", "前"
        ]
        
        return any(keyword in question for keyword in sql_keywords)


# ============================================================================
# 集成方式 3: 作为独立服务使用
# =============================================================================

class TextToSQLService:
    """
    Text-to-SQL 独立服务
    
    提供REST API或RPC接口，可以被其他服务调用
    """
    
    def __init__(self, db_path: str = None):
        """
        初始化服务
        
        Args:
            db_path: 数据库路径
        """
        from chatdb.text_to_sql_agent import create_text_to_sql_agent
        
        # 创建 agent
        self.agent = create_text_to_sql_agent(
            db_path=db_path or "database/local_data.db",
            schema_path="chatdb/schema_description.md",
            business_rules_path="chatdb/business_rules.py",
            fewshot_path="chatdb/fewshot_examples.md",
            max_retries=3,
            enable_cache=True
        )
        
        # 统计信息
        self.stats = {
            "total_queries": 0,
            "successful_queries": 0,
            "failed_queries": 0,
            "cache_hits": 0
        }
        
        print("✅ Text-to-SQL Service 初始化完成")
    
    def query(self, question: str) -> dict:
        """
        执行查询
        
        Args:
            question: 用户问题
        
        Returns:
            {
                "success": bool,
                "answer": str,
                "sql": Optional[str],
                "data": Optional[list],  # 转换为 list
                "execution_time_ms": int,
                "from_cache": bool
            }
        """
        # 更新统计
        self.stats["total_queries"] += 1
        
        # 执行查询
        result = self.agent.query(question)
        
        # 转换数据格式
        if result["success"]:
            self.stats["successful_queries"] += 1
            
            if result["from_cache"]:
                self.stats["cache_hits"] += 1
            
            return {
                "success": True,
                "answer": result["answer"],
                "sql": result["sql"],
                "data": result["data"].to_dict('records') if result["data"] is not None else None,
                "execution_time_ms": result["execution_time_ms"],
                "from_cache": result["from_cache"]
            }
        else:
            self.stats["failed_queries"] += 1
            
            return {
                "success": False,
                "answer": result["answer"],
                "error": result["error"],
                "execution_time_ms": result["execution_time_ms"]
            }
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        total = self.stats["total_queries"]
        if total > 0:
            success_rate = (self.stats["successful_queries"] / total) * 100
            cache_hit_rate = (self.stats["cache_hits"] / total) * 100
        else:
            success_rate = 0
            cache_hit_rate = 0
        
        return {
            "total_queries": total,
            "successful_queries": self.stats["successful_queries"],
            "failed_queries": self.stats["failed_queries"],
            "cache_hits": self.stats["cache_hits"],
            "success_rate": round(success_rate, 2),
            "cache_hit_rate": round(cache_hit_rate, 2)
        }
    
    def clear_cache(self):
        """清空缓存"""
        self.agent.clear_cache()


# ============================================================================
# 示例使用
# =============================================================================

def example_1_basic_usage():
    """示例 1: 基本使用"""
    print("\n" + "=" * 60)
    print("示例 1: 基本使用")
    print("=" * 60)
    
    chat = AIChatWithTextToSQL()
    
    questions = [
        "查询所有 TopIssue 缺陷，按风险评分降序排列",
        "按项目统计缺陷总数",
        "查询所有 High Runner 缺陷"
    ]
    
    for question in questions:
        print(f"\n问题: {question}")
        result = chat.ask(question)
        
        if result["success"]:
            print(f"✅ 回答: {result['answer'][:100]}...")
            print(f"   SQL: {result['sql'][:80]}...")
            print(f"   数据行数: {len(result['data'])}")
        else:
            print(f"❌ 错误: {result['answer']}")


def example_2_enhanced_usage():
    """示例 2: 增强使用（智能路由）"""
    print("\n" + "=" * 60)
    print("示例 2: 增强使用（智能路由）")
    print("=" * 60)
    
    chat = EnhancedAIChatWithTextToSQL()
    
    questions = [
        "查询所有 TopIssue 缺陷",  # SQL 路由
        "分析缺陷趋势",  # Agent 路由
        "你好"  # LLM 路由
    ]
    
    for question in questions:
        print(f"\n问题: {question}")
        result = chat.ask(question, use_intelligent_routing=True)
        
        print(f"✅ 路由: {result['route']}")
        print(f"   回答: {result['answer'][:100]}...")


def example_3_service_usage():
    """示例 3: 服务使用"""
    print("\n" + "=" * 60)
    print("示例 3: 服务使用")
    print("=" * 60)
    
    service = TextToSQLService()
    
    questions = [
        "查询所有 TopIssue 缺陷",
        "查询所有 TopIssue 缺陷",  # 第二次，应该命中缓存
        "按项目统计缺陷总数"
    ]
    
    for question in questions:
        print(f"\n问题: {question}")
        result = service.query(question)
        
        if result["success"]:
            print(f"✅ 回答: {result['answer'][:100]}...")
            print(f"   缓存: {'命中' if result['from_cache'] else '未命中'}")
            print(f"   执行时间: {result['execution_time_ms']}ms")
        else:
            print(f"❌ 错误: {result['error']}")
    
    # 显示统计信息
    print("\n" + "-" * 60)
    print("统计信息:")
    stats = service.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    print("=" * 60)
    print("Text-to-SQL Agent 集成示例")
    print("=" * 60)
    
    # 运行示例
    example_1_basic_usage()
    example_2_enhanced_usage()
    example_3_service_usage()
    
    print("\n" + "=" * 60)
    print("✅ 所有示例运行完成")
    print("=" * 60)
