"""
数据层 - 数据库 Schema 和字段含义
"""

DB_SCHEMA_CONTEXT = """
## 数据库结构（SQLite）

路径：database/local_data.db

### 表 1：test_runs（测试执行主表）
| 字段 | 类型 | 说明 |
|------|------|------|
| run_id | TEXT UNIQUE | 唯一执行ID |
| test_id | TEXT | 测试用例ID |
| test_name | TEXT | 测试名称 |
| test_type | TEXT | 测试类型（unit/integration/system） |
| status | TEXT | 执行状态（pending/running/completed/failed/blocked）|
| result | TEXT | 结果（passed/failed/skipped/error） |
| tester | TEXT | 执行人 |
| project | TEXT | 所属项目（ABS/EPS/IDCEVO等） |
| module | TEXT | 所属模块 |
| component | TEXT | 所属组件 |
| test_week | TEXT | 测试周（格式：25-CW10） |
| build_number | TEXT | 构建版本号 |
| duration_seconds | REAL | 执行时长（秒） |
| tags | TEXT | JSON 格式标签 |
| metadata | TEXT | JSON 格式扩展字段 |

索引：status, project, tester, test_week, module

### 表 2：defects（缺陷主表）
| 字段 | 类型 | 说明 |
|------|------|------|
| defect_id | TEXT UNIQUE | 唯一缺陷ID |
| title | TEXT | 缺陷标题 |
| severity | TEXT | 严重性（Critical/Major/Minor/Trivial） |
| priority | TEXT | 优先级（P1-P4） |
| status | TEXT | 当前状态 |
| phase | TEXT | 详细阶段（00-Draft 到 10-Closed） |
| project | TEXT | 所属项目 |
| module | TEXT | 所属模块 |
| detected_by | TEXT | 发现人 |
| assigned_to | TEXT | 负责人 |
| creation_time | TEXT | 创建时间 |
| closed_time | TEXT | 关闭时间 |
| root_cause | TEXT | 根因描述 |
| pingpong | INTEGER | 重开次数（关键指标！） |
| aidas | TEXT | JSON 格式 AIDA 区域列表 |
| tags | TEXT | JSON 格式标签 |
| metadata | TEXT | JSON 格式扩展字段 |

索引：severity, status, project, module, detected_by, creation_time

### 表 3：test_coverage（测试覆盖率聚合表）
| 字段 | 类型 | 说明 |
|------|------|------|
| module | TEXT NOT NULL | 模块名 |
| component | TEXT | 组件名 |
| total_tests | INTEGER | 总测试数 |
| passed_tests | INTEGER | 通过数 |
| failed_tests | INTEGER | 失败数 |
| blocked_tests | INTEGER | 阻塞数 |
| coverage_percent | REAL | 覆盖率百分比 |
| test_week | TEXT | 测试周 |
| build_number | TEXT | 构建号 |

UNIQUE 约束：(module, component, test_week)
索引：module, test_week

### 表 4：defect_trends（缺陷趋势聚合表）
| 字段 | 类型 | 说明 |
|------|------|------|
| project | TEXT NOT NULL | 项目 |
| module | TEXT | 模块 |
| test_week | TEXT NOT NULL | 测试周 |
| total_defects | INTEGER | 总缺陷数 |
| new_defects | INTEGER | 新增缺陷数 |
| closed_defects | INTEGER | 关闭缺陷数 |
| open_defects | INTEGER | 未关闭数 |
| critical_defects | INTEGER | 严重缺陷数 |
| major_defects | INTEGER | 主要缺陷数 |

UNIQUE 约束：(project, module, test_week)
索引：project, test_week

### 表 5：test_results（测试步骤明细）
| 字段 | 类型 | 说明 |
|------|------|------|
| run_id | TEXT | 关联 test_runs(run_id)（外键） |
| test_case_id | TEXT | 测试用例ID |
| test_case_name | TEXT | 用例名称 |
| step_name | TEXT | 步骤名称 |
| step_number | INTEGER | 步骤序号 |
| status | TEXT | 步骤状态 |
| error_message | TEXT | 错误信息 |
| duration_ms | INTEGER | 步骤耗时（毫秒） |

外键：run_id → test_runs(run_id)
索引：run_id, status

## 表关系

```
test_runs (1) ←→ (N) test_results    [硬外键]
test_runs (N) ←→ (1) test_coverage   [通过 module+test_week 软关联]
test_runs (N) ←→ (1) defect_trends   [通过 project+test_week 软关联]
test_runs (N) ←→ (N) defects         [通过 project+module+build 软关联]
```

## 重要说明

1. **外键默认未启用**：每次连接需执行 `PRAGMA foreign_keys = ON;`
2. **JSON 字段**：tags/aidas/metadata 存储 JSON 字符串，查询需用 `json_extract()`
3. **时间格式**：ISO 8601（如 `2025-03-22T10:00:00`）
4. **test_week 格式**：`YY-CWNN`（如 `25-CW10`），不是标准日期
"""


def get_db_context(include_examples: bool = False) -> str:
    """获取数据库上下文，可选是否包含查询示例"""
    if not include_examples:
        return DB_SCHEMA_CONTEXT

    examples = """
## 常用查询示例

```sql
-- 启用外键
PRAGMA foreign_keys = ON;

-- 查询各模块未关闭缺陷数量
SELECT module, COUNT(*) as open_count
FROM defects
WHERE status NOT IN ('Closed', 'Concluded')
GROUP BY module
ORDER BY open_count DESC;

-- 查询最近4周的缺陷趋势
SELECT test_week, SUM(new_defects) as new_count, SUM(closed_defects) as closed_count
FROM defect_trends
WHERE test_week >= '25-CW09'
GROUP BY test_week
ORDER BY test_week;

-- 查询高 pingpong 缺陷（热土豆）
SELECT defect_id, title, pingpong, severity, status
FROM defects
WHERE pingpong >= 2
ORDER BY pingpong DESC
LIMIT 20;

-- 查询测试通过率
SELECT module, 
       ROUND(100.0 * passed_tests / NULLIF(total_tests, 0), 1) as pass_rate
FROM test_coverage
WHERE test_week = '25-CW10'
ORDER BY pass_rate ASC;
```
"""
    return DB_SCHEMA_CONTEXT + examples
