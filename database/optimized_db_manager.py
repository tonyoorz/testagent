#!/usr/bin/env python3
"""
优化数据库管理器
- 创建优化的数据库结构
- 添加索引提升查询性能
- 支持测试数据和缺陷数据存储
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class OptimizedDatabaseManager:
    """优化的数据库管理器"""
    
    def __init__(self, db_path: str = 'database/local_data.db'):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self._connect()
        self._create_tables()
        self._create_indexes()
    
    def _connect(self):
        """连接数据库"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # 支持字典访问
            self.cursor = self.conn.cursor()
            # 启用性能优化
            self.cursor.execute("PRAGMA journal_mode=WAL")
            self.cursor.execute("PRAGMA synchronous=NORMAL")
            self.cursor.execute("PRAGMA cache_size=10000")
            self.cursor.execute("PRAGMA temp_store=MEMORY")
            logging.info(f"✅ 数据库连接成功: {self.db_path}")
        except sqlite3.Error as e:
            logging.error(f"❌ 数据库连接失败: {e}")
            raise
    
    def _create_tables(self):
        """创建优化的数据表"""
        
        # 测试运行表
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS test_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL UNIQUE,
            test_id TEXT,
            test_name TEXT,
            test_type TEXT,
            status TEXT,
            result TEXT,
            tester TEXT,
            project TEXT,
            module TEXT,
            component TEXT,
            start_time TEXT,
            end_time TEXT,
            duration_seconds REAL,
            test_week TEXT,
            build_number TEXT,
            environment TEXT,
            platform TEXT,
            tags TEXT,
            metadata TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 缺陷表
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS defects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            defect_id TEXT NOT NULL UNIQUE,
            title TEXT,
            description TEXT,
            severity TEXT,
            priority TEXT,
            status TEXT,
            phase TEXT,
            project TEXT,
            module TEXT,
            component TEXT,
            detected_by TEXT,
            assigned_to TEXT,
            detected_in_build TEXT,
            target_build TEXT,
            creation_time TEXT,
            modification_time TEXT,
            closed_time TEXT,
            root_cause TEXT,
            impact TEXT,
            tags TEXT,
            aidas TEXT,
            classification TEXT,
            pingpong INTEGER DEFAULT 0,
            metadata TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 测试覆盖率表
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS test_coverage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT NOT NULL,
            component TEXT,
            total_tests INTEGER DEFAULT 0,
            passed_tests INTEGER DEFAULT 0,
            failed_tests INTEGER DEFAULT 0,
            blocked_tests INTEGER DEFAULT 0,
            coverage_percent REAL DEFAULT 0,
            test_week TEXT,
            build_number TEXT,
            metadata TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(module, component, test_week)
        )
        ''')
        
        # 缺陷趋势表
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS defect_trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            module TEXT,
            test_week TEXT NOT NULL,
            total_defects INTEGER DEFAULT 0,
            new_defects INTEGER DEFAULT 0,
            closed_defects INTEGER DEFAULT 0,
            open_defects INTEGER DEFAULT 0,
            critical_defects INTEGER DEFAULT 0,
            major_defects INTEGER DEFAULT 0,
            minor_defects INTEGER DEFAULT 0,
            metadata TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project, module, test_week)
        )
        ''')
        
        # 测试结果明细表
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            test_case_id TEXT,
            test_case_name TEXT,
            step_name TEXT,
            step_number INTEGER,
            status TEXT,
            error_message TEXT,
            screenshot_path TEXT,
            duration_ms INTEGER,
            metadata TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (run_id) REFERENCES test_runs(run_id)
        )
        ''')
        
        self.conn.commit()
        logging.info("✅ 数据表创建完成")
    
    def _create_indexes(self):
        """创建优化索引"""
        indexes = [
            # 测试运行索引
            "CREATE INDEX IF NOT EXISTS idx_test_runs_status ON test_runs(status)",
            "CREATE INDEX IF NOT EXISTS idx_test_runs_project ON test_runs(project)",
            "CREATE INDEX IF NOT EXISTS idx_test_runs_tester ON test_runs(tester)",
            "CREATE INDEX IF NOT EXISTS idx_test_runs_week ON test_runs(test_week)",
            "CREATE INDEX IF NOT EXISTS idx_test_runs_module ON test_runs(module)",
            
            # 缺陷索引
            "CREATE INDEX IF NOT EXISTS idx_defects_severity ON defects(severity)",
            "CREATE INDEX IF NOT EXISTS idx_defects_status ON defects(status)",
            "CREATE INDEX IF NOT EXISTS idx_defects_project ON defects(project)",
            "CREATE INDEX IF NOT EXISTS idx_defects_module ON defects(module)",
            "CREATE INDEX IF NOT EXISTS idx_defects_detected_by ON defects(detected_by)",
            "CREATE INDEX IF NOT EXISTS idx_defects_creation ON defects(creation_time)",
            
            # 覆盖率索引
            "CREATE INDEX IF NOT EXISTS idx_coverage_module ON test_coverage(module)",
            "CREATE INDEX IF NOT EXISTS idx_coverage_week ON test_coverage(test_week)",
            
            # 趋势索引
            "CREATE INDEX IF NOT EXISTS idx_trends_project ON defect_trends(project)",
            "CREATE INDEX IF NOT EXISTS idx_trends_week ON defect_trends(test_week)",
            
            # 测试结果索引
            "CREATE INDEX IF NOT EXISTS idx_results_run ON test_results(run_id)",
            "CREATE INDEX IF NOT EXISTS idx_results_status ON test_results(status)",
        ]
        
        for idx_sql in indexes:
            self.cursor.execute(idx_sql)
        
        self.conn.commit()
        logging.info("✅ 索引创建完成")
    
    def insert_test_run(self, data: Dict) -> int:
        """插入测试运行记录"""
        columns = [
            'run_id', 'test_id', 'test_name', 'test_type', 'status', 'result',
            'tester', 'project', 'module', 'component', 'start_time', 'end_time',
            'duration_seconds', 'test_week', 'build_number', 'environment',
            'platform', 'tags', 'metadata'
        ]
        
        values = []
        placeholders = []
        actual_columns = []
        
        for col in columns:
            if col in data:
                actual_columns.append(col)
                values.append(json.dumps(data[col]) if col in ['tags', 'metadata'] else data[col])
                placeholders.append('?')
        
        sql = f"INSERT OR REPLACE INTO test_runs ({', '.join(actual_columns)}) VALUES ({', '.join(placeholders)})"
        self.cursor.execute(sql, values)
        self.conn.commit()
        return self.cursor.lastrowid
    
    def insert_defect(self, data: Dict) -> int:
        """插入缺陷记录"""
        columns = [
            'defect_id', 'title', 'description', 'severity', 'priority', 'status',
            'phase', 'project', 'module', 'component', 'detected_by', 'assigned_to',
            'detected_in_build', 'target_build', 'creation_time', 'modification_time',
            'closed_time', 'root_cause', 'impact', 'tags', 'aidas', 'classification',
            'pingpong', 'metadata'
        ]
        
        values = []
        placeholders = []
        actual_columns = []
        
        for col in columns:
            if col in data:
                actual_columns.append(col)
                values.append(json.dumps(data[col]) if col in ['tags', 'aidas', 'classification', 'metadata'] else data[col])
                placeholders.append('?')
        
        sql = f"INSERT OR REPLACE INTO defects ({', '.join(actual_columns)}) VALUES ({', '.join(placeholders)})"
        self.cursor.execute(sql, values)
        self.conn.commit()
        return self.cursor.lastrowid
    
    def bulk_insert_test_runs(self, records: List[Dict]):
        """批量插入测试运行"""
        for record in records:
            self.insert_test_run(record)
        logging.info(f"✅ 批量插入 {len(records)} 条测试运行记录")
    
    def bulk_insert_defects(self, records: List[Dict]):
        """批量插入缺陷"""
        for record in records:
            self.insert_defect(record)
        logging.info(f"✅ 批量插入 {len(records)} 条缺陷记录")
    
    def get_schema_info(self) -> Dict:
        """获取数据库结构信息（供Agent理解）"""
        return {
            "tables": {
                "test_runs": {
                    "description": "测试运行记录表，存储每次测试执行的详细信息",
                    "columns": {
                        "run_id": "测试运行唯一标识",
                        "test_id": "测试用例ID",
                        "test_name": "测试用例名称",
                        "test_type": "测试类型（单元测试、集成测试等）",
                        "status": "运行状态（Passed, Failed, Blocked等）",
                        "result": "测试结果",
                        "tester": "执行人",
                        "project": "所属项目",
                        "module": "所属模块",
                        "component": "所属组件",
                        "test_week": "测试周（格式：YY-CWww）",
                        "duration_seconds": "执行时长（秒）"
                    },
                    "common_queries": [
                        "查询某项目的测试通过率",
                        "查询某个测试人员的执行情况",
                        "查询某周的测试统计"
                    ]
                },
                "defects": {
                    "description": "缺陷记录表，存储缺陷的详细信息",
                    "columns": {
                        "defect_id": "缺陷唯一标识",
                        "title": "缺陷标题",
                        "description": "缺陷描述",
                        "severity": "严重程度（Critical, Major, Minor等）",
                        "priority": "优先级",
                        "status": "状态（Open, In Progress, Closed等）",
                        "phase": "所处阶段",
                        "project": "所属项目",
                        "module": "所属模块",
                        "detected_by": "发现人",
                        "assigned_to": "分配给",
                        "creation_time": "创建时间",
                        "pingpong": "往返次数"
                    },
                    "common_queries": [
                        "查询某模块的缺陷分布",
                        "查询某个严重程度的缺陷数量",
                        "查询某个时间段的缺陷趋势"
                    ]
                }
            }
        }
    
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            logging.info("数据库连接已关闭")


if __name__ == "__main__":
    # 动态获取数据库路径
    try:
        from config_center import cfg
        db_path = str(cfg.DATABASE_FILE)
    except ImportError:
        import os
        _this_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(_this_dir, 'local_data.db')
    # 创建数据库管理器
    db = OptimizedDatabaseManager(db_path)
    
    # 插入示例数据
    db.insert_test_run({
        'run_id': 'TR-2026-001',
        'test_id': 'TC-001',
        'test_name': '登录功能测试',
        'status': 'Passed',
        'tester': '张三',
        'project': 'ABS系统',
        'module': '用户管理',
        'test_week': '26-CW11'
    })
    
    db.insert_defect({
        'defect_id': 'DEF-2026-001',
        'title': '登录失败时提示信息不准确',
        'severity': 'Major',
        'status': 'Open',
        'project': 'ABS系统',
        'module': '用户管理',
        'detected_by': '李四'
    })
    
    # 打印schema信息
    print(json.dumps(db.get_schema_info(), ensure_ascii=False, indent=2))
    
    db.close()
