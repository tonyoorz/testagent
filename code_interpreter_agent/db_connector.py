"""
Database Connector - 数据库连接器
安全地连接和查询 SQLite 数据库
"""

import os
import sqlite3
import logging
from typing import Dict, List, Any, Optional
from contextlib import contextmanager
import threading

logger = logging.getLogger(__name__)


class DatabaseConnector:
    """
    数据库连接器
    
    提供安全的数据库访问接口，支持：
    - 连接池管理
    - 安全的查询执行
    - Schema 信息获取
    - 线程安全
    """
    
    def __init__(self, db_path: str):
        """
        初始化数据库连接器
        
        Args:
            db_path: SQLite 数据库文件路径
        """
        self.db_path = db_path
        self._local = threading.local()
        self._schema_cache = None
        
        # 验证数据库文件存在
        if not os.path.exists(db_path):
            logger.warning(f"Database file not found: {db_path}")
            # 尝试创建目录
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        logger.info(f"DatabaseConnector initialized for: {db_path}")
    
    @contextmanager
    def _get_connection(self):
        """获取线程安全的数据库连接"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            try:
                self._local.connection = sqlite3.connect(
                    self.db_path,
                    check_same_thread=False,
                    timeout=30.0
                )
                # 启用外键约束
                self._local.connection.execute("PRAGMA foreign_keys = ON")
                # 设置行工厂，返回字典
                self._local.connection.row_factory = sqlite3.Row
            except sqlite3.Error as e:
                logger.error(f"Failed to connect to database: {e}")
                raise
        
        try:
            yield self._local.connection
        except Exception as e:
            logger.error(f"Database operation error: {e}")
            self._local.connection.rollback()
            raise
    
    def execute_query(
        self,
        sql: str,
        params: Optional[List[Any]] = None,
        fetch_all: bool = True
    ) -> Dict[str, Any]:
        """
        执行 SQL 查询
        
        Args:
            sql: SQL 查询语句
            params: 查询参数
            fetch_all: 是否获取所有结果
            
        Returns:
            查询结果字典
        """
        with self._get_connection() as conn:
            try:
                cursor = conn.cursor()
                
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                
                if fetch_all:
                    rows = cursor.fetchall()
                    columns = [description[0] for description in cursor.description] if cursor.description else []
                    
                    # 转换为字典列表
                    data = []
                    for row in rows:
                        row_dict = {}
                        for i, col in enumerate(columns):
                            value = row[i]
                            # 处理特殊类型
                            if isinstance(value, bytes):
                                value = value.decode('utf-8', errors='ignore')
                            row_dict[col] = value
                        data.append(row_dict)
                    
                    return {
                        "success": True,
                        "data": data,
                        "columns": columns,
                        "row_count": len(data)
                    }
                else:
                    conn.commit()
                    return {
                        "success": True,
                        "row_count": cursor.rowcount,
                        "last_row_id": cursor.lastrowid
                    }
                    
            except sqlite3.Error as e:
                logger.error(f"SQL execution error: {e}\nSQL: {sql}\nParams: {params}")
                return {
                    "success": False,
                    "error": str(e),
                    "sql": sql
                }
    
    def get_schema(self) -> Dict[str, Any]:
        """
        获取数据库 Schema
        
        Returns:
            Schema 信息字典
        """
        if self._schema_cache:
            return self._schema_cache
        
        schema = {}
        
        try:
            # 获取所有表名
            tables_result = self.execute_query(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            
            if not tables_result.get("success"):
                return schema
            
            tables = [row["name"] for row in tables_result.get("data", [])]
            
            # 获取每个表的结构
            for table_name in tables:
                # 跳过系统表
                if table_name.startswith("sqlite_"):
                    continue
                
                table_info = {
                    "name": table_name,
                    "columns": [],
                    "indexes": [],
                    "row_count": 0
                }
                
                # 获取列信息
                columns_result = self.execute_query(f"PRAGMA table_info({table_name})")
                
                if columns_result.get("success"):
                    for col in columns_result.get("data", []):
                        table_info["columns"].append({
                            "name": col.get("name"),
                            "type": col.get("type"),
                            "notnull": bool(col.get("notnull")),
                            "pk": bool(col.get("pk")),
                            "description": self._get_column_description(table_name, col.get("name"))
                        })
                
                # 获取索引信息
                indexes_result = self.execute_query(f"PRAGMA index_list({table_name})")
                
                if indexes_result.get("success"):
                    for idx in indexes_result.get("data", []):
                        table_info["indexes"].append({
                            "name": idx.get("name"),
                            "unique": bool(idx.get("unique"))
                        })
                
                # 获取行数
                count_result = self.execute_query(f"SELECT COUNT(*) as count FROM {table_name}")
                if count_result.get("success") and count_result.get("data"):
                    table_info["row_count"] = count_result["data"][0].get("count", 0)
                
                schema[table_name] = table_info
            
            # 缓存 Schema
            self._schema_cache = schema
            
        except Exception as e:
            logger.error(f"Get schema error: {e}")
        
        return schema
    
    def _get_column_description(self, table_name: str, column_name: str) -> str:
        """获取列的业务描述"""
        # 预定义的业务描述
        descriptions = {
            "defects": {
                "defect_id": "缺陷唯一标识符",
                "year": "缺陷年份",
                "creation_time": "创建时间",
                "summary": "缺陷摘要/标题",
                "description": "缺陷详细描述",
                "status_phase": "缺陷状态阶段",
                "severity": "严重性等级",
                "project": "所属项目/ECU",
                "detected_by": "发现人",
                "detected_in_release": "发现版本",
                "domain": "领域/模块",
                "aidas": "AIDA 产品区域列表",
                "top_aida": "主要 AIDA",
                "tags": "标签列表",
                "classification": "分类",
                "pingpong": "重开次数",
                "vin": "车辆识别码"
            },
            "test_runs": {
                "run_id": "测试运行 ID",
                "report_period": "报告周期",
                "test_id": "测试用例 ID",
                "test_name": "测试用例名称",
                "run_status": "运行状态",
                "tester": "测试执行人",
                "finished_time": "完成时间",
                "test_week": "测试周",
                "project": "项目",
                "model": "车型/型号",
                "aidas": "AIDA 列表",
                "top_aida": "主要 AIDA"
            },
            "history_log": {
                "log_id": "日志 ID",
                "object_id": "关联对象 ID",
                "log_timestamp": "时间戳",
                "user": "操作用户",
                "action_type": "操作类型",
                "change_details": "变更详情"
            }
        }
        
        return descriptions.get(table_name, {}).get(column_name, "")
    
    def get_table_sample(self, table_name: str, limit: int = 5) -> Dict[str, Any]:
        """
        获取表数据样本
        
        Args:
            table_name: 表名
            limit: 返回行数
            
        Returns:
            样本数据
        """
        return self.execute_query(f"SELECT * FROM {table_name} LIMIT ?", [limit])
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取数据库统计信息
        
        Returns:
            统计信息字典
        """
        stats = {
            "tables": {},
            "total_records": 0,
            "database_size_mb": 0
        }
        
        try:
            # 获取文件大小
            if os.path.exists(self.db_path):
                stats["database_size_mb"] = round(
                    os.path.getsize(self.db_path) / (1024 * 1024), 2
                )
            
            # 获取各表统计
            schema = self.get_schema()
            
            for table_name, table_info in schema.items():
                row_count = table_info.get("row_count", 0)
                stats["tables"][table_name] = {
                    "row_count": row_count,
                    "column_count": len(table_info.get("columns", []))
                }
                stats["total_records"] += row_count
            
        except Exception as e:
            logger.error(f"Get statistics error: {e}")
        
        return stats
    
    def close(self):
        """关闭数据库连接"""
        if hasattr(self._local, 'connection') and self._local.connection:
            try:
                self._local.connection.close()
                self._local.connection = None
                logger.info("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
    
    def __del__(self):
        """析构函数"""
        self.close()
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
