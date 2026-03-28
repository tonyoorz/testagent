# 车载软件缺陷管理系统数据库 Schema 描述

## 📋 数据库概览

本系统用于管理车载软件缺陷、测试执行、票据关系和历史变更，支持多维度分析和风险评估。

---

## 🗂️ 主要数据表

### 1. defects 表 - 核心缺陷表

存储所有缺陷（Defect）的详细信息，包括状态、严重性、责任分配、风险评估等。

#### 核心字段

| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| **id** | INTEGER | 缺陷唯一标识 | 123456 |
| **name** | TEXT | 缺陷名称 | "Car Apps 导航无法启动" |
| **creation_time** | DATETIME | 创建时间 | 2025-03-28 10:30:00 |
| **test_week** | TEXT | 测试周（年-CW周） | "2025-CW42" |
| **data_year** | INTEGER | 数据年份 | 2025 |

#### 项目归属字段

| 字段名 | 类型 | 说明 | 可选值 |
|--------|------|------|--------|
| **project** | TEXT | 项目名称 | App, IDCevo, IDC, MGU, RSU |
| **vin_udf** | TEXT | 车辆VIN码（多个用逗号分隔） | "WBA123456,WBA234567" |
| **market** | TEXT | 市场 | CN, US, DE, INT |

#### 功能维度字段

| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| **aida_english** | TEXT | AIDA英文标识 | "Navigation" |
| **aidas_json** | TEXT | AIDA列表（JSON格式） | `["Navigation", "Map Display"]` |
| **top_aida** | TEXT | 主要AIDA | "Navigation" |
| **fv** | TEXT | Function Variant（功能变体） | "IuK_TSP_Navi" |
| **fvp** | TEXT | FVP负责人 | "Tony" |
| **team** | TEXT | 团队 | DIPS, IUK |
| **pu** | TEXT | Production Usage | "SOP1" |
| **lead_model** | TEXT | 领先车型 | "HU-MGU_02_A" |

#### 责任分配字段

| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| **ecu** | TEXT | Electronic Control Unit（电子控制单元） | "IuK_HU" |
| **tester** | TEXT | 测试人员 | "John Doe" |

#### 状态管理字段

| 字段名 | 类型 | 说明 | 可选值 |
|--------|------|------|--------|
| **status_phase** | TEXT | 当前状态阶段 | 01-New, 02-In Pre-Analysis, 03-In Analysis, 04-In Progress, 05-In Testing, 07-In Pre-Verification, 08-In Verification, 09-Concluded without action, 10-Closed |
| **phase_name** | TEXT | 状态名称（备用） | "New" |
| **sub_status** | TEXT | 子状态（如重复票） | "Child (Duplicate)" |

#### 严重性评估字段

| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| **matrix** | TEXT | Matrix严重性等级 | Matrix-1A, Matrix-1B, ..., Matrix-4E |
| **matrix_order** | INTEGER | Matrix排序值（越小越严重） | 10 (1A), 48 (4E) |
| **matrix_display** | TEXT | Matrix显示用 | "1A", "1B", ..., "4E" |
| **classification_json** | TEXT | 分类列表（JSON） | `["Showstopper_Confirmed"]` |
| **classification_display** | TEXT | 分类显示 | "Showstopper Confirmed" |
| **severity_group** | TEXT | 严重性分组 | Critical Issues, General Issues |

#### 票据关系字段

| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| **parent_child** | TEXT | 票据关系 | Parent, Child, Child (candidate) |
| **parent_ticket_id** | INTEGER | 父票ID | 123456 |
| **relation_to_udf** | TEXT | 关联的子票ID列表（逗号分隔） | "789,790,791" |
| **child_count** | INTEGER | 当前票据的子票数 | 3 |
| **master_child_count** | INTEGER | 主票的子票数（用于Child票据） | 5 |

#### 流转分析字段

| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| **ecu_no_of_changes** | INTEGER | ECU转移次数 | 5 |
| **ecu_pingpong_display** | TEXT | ECU转移次数+路径 | "5, IuK_HU -> DIPS_HU -> IuK_HU" |
| **ecu_transition_path** | TEXT | 完整ECU转移路径（JSON） | `[{"from": "IuK_HU", "to": "DIPS_HU"}, ...]` |
| **domain** | TEXT | Solution Cluster（解决方案集群） | "Navigation Cluster" |
| **domain_pingpong_count** | INTEGER | Domain转移次数 | 2 |
| **domain_pingpong_display** | TEXT | Domain转移次数+路径 | "2, Navigation -> Display" |
| **domain_transition_path** | TEXT | 完整Domain转移路径 | `[{"from": "Navigation", "to": "Display"}]` |

#### 处理效率字段

| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| **processing_cycle_days** | INTEGER | 处理周期天数 | 45 |
| **shift_pu** | TEXT | 是否延期（Shift PU） | "SOP2" (表示已延期到SOP2) |

#### 风险评分字段

| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| **topissue_risk_score** | REAL | TopIssue风险评分（0-200+） | 145.5 |
| **topissue_display** | TEXT | 风险等级显示 | "145*", "*表示使用主票分数" |
| **topissue_recommend_reason** | TEXT | 推荐理由（多行文本） | "SEVERITY: Matrix 1A<br>HIGH RUNNER: ECU transfer 5 times<br>..." |
| **is_topissue** | BOOLEAN | 是否为TopIssue（≥60分） | 1 (True) / 0 (False) |
| **is_master_score** | BOOLEAN | 是否使用主票分数 | 1 (True) / 0 (False) |

#### 其他UDF字段

| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| **sab_comment_udf** | TEXT | SAB评论 | "Need more info" |
| **software_version** | TEXT | 软件版本 | "v1.2.3" |

---

### 2. test_executions 表 - 测试执行表

存储测试用例执行记录。

| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| **id** | INTEGER | 测试执行唯一标识 | 1001 |
| **test_id** | TEXT | 测试用例ID | "TC-001" |
| **test_name** | TEXT | 测试用例名称 | "Navigation start test" |
| **creation_time** | DATETIME | 创建时间 | 2025-03-28 10:30:00 |
| **test_week** | TEXT | 测试周 | "2025-CW42" |
| **project** | TEXT | 项目名称 | App, IDCevo, IDC, MGU, RSU |
| **model** | TEXT | 车型 | "HU-MGU_02_A" |
| **aida_english** | TEXT | AIDA英文标识 | "Navigation" |
| **aidas_json** | TEXT | AIDA列表（JSON） | `["Navigation"]` |
| **top_aida** | TEXT | 主要AIDA | "Navigation" |
| **fv** | TEXT | Function Variant | "IuK_TSP_Navi" |
| **fvp** | TEXT | FVP负责人 | "Tony" |
| **team** | TEXT | 团队 | IUK |
| **tester** | TEXT | 测试人员 | "John Doe" |
| **author_name** | TEXT | 作者 | "Jane Smith" |
| **pu** | TEXT | Production Usage | "SOP1" |
| **lead_model** | TEXT | 领先车型 | "HU-MGU_02_A" |
| **run_status** | TEXT | 执行状态 | Passed, Failed, Blocked |
| **test_event** | TEXT | 测试事件 | "Release 2025-03" |
| **target_ecu** | TEXT | 目标ECU | "IuK_HU" |
| **finished_udf** | DATETIME | 完成时间 | 2025-03-28 12:00:00 |

---

### 3. master_tickets 表 - 主票表

存储主票（Parent Ticket）的详细信息。

| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| **id** | INTEGER | 主票唯一标识 | 123456 |
| **name** | TEXT | 主票名称 | "Multiple navigation issues" |
| **phase** | TEXT | 当前状态阶段 | 01-New, ..., 09-Concluded |
| **phase_name** | TEXT | 状态名称 | "New" |
| **status** | TEXT | 状态（备用） | "New" |
| **relation_to_udf** | TEXT | 子票ID列表（逗号分隔） | "789,790,791" |
| **child_count** | INTEGER | 子票数量 | 3 |
| **created_time** | DATETIME | 创建时间 | 2025-03-28 10:30:00 |
| **last_updated** | DATETIME | 最后更新时间 | 2025-03-28 14:00:00 |
| **assigned_ecu** | TEXT | 分配的ECU | "IuK_HU" |
| **solution_cluster** | TEXT | 解决方案集群 | "Navigation Cluster" |

---

### 4. defect_relations 表 - 票据关系表

存储票据之间的各种关系。

| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| **id** | INTEGER | 关系唯一标识 | 1 |
| **parent_id** | INTEGER | 父票ID | 123456 |
| **child_id** | INTEGER | 子票ID | 789 |
| **relation_type** | TEXT | 关系类型 | parent_child, duplicate, related |

---

### 5. defect_history 表 - 缺陷历史表

存储缺陷的状态变更历史。

| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| **id** | INTEGER | 历史记录唯一标识 | 1001 |
| **defect_id** | INTEGER | 缺陷ID | 123456 |
| **timestamp** | DATETIME | 变更时间戳 | 2025-03-28 12:00:00 |
| **action** | TEXT | 操作类型 | create, update, delete |
| **user_id** | TEXT | 操作用户 | "john.doe" |
| **change_set_json** | TEXT | 变更详情（JSON） | `[{"field_name": "phase", "value_text": "04-In Progress"}]` |
| **phase_before** | TEXT | 变更前状态 | "03-In Analysis" |
| **phase_after** | TEXT | 变更后状态 | "04-In Progress" |
| **ecu_before** | TEXT | 变更前ECU | "IuK_HU" |
| **ecu_after** | TEXT | 变更后ECU | "DIPS_HU" |

---

### 6. defect_inflow_outflow 表 - 缺陷入出流表

存储每周的缺陷入出流统计数据。

| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| **id** | INTEGER | 记录唯一标识 | 1 |
| **week** | TEXT | 周（年-W周） | "2025-W42" |
| **inflow** | INTEGER | 新增缺陷数 | 50 |
| **outflow** | INTEGER | 解决缺陷数 | 45 |
| **net_change** | INTEGER | 净变化（inflow - outflow） | 5 |

---

### 7. project_config 表 - 项目配置表

存储项目相关的配置信息。

| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| **id** | INTEGER | 配置唯一标识 | 1 |
| **project** | TEXT | 项目名称 | App, IDCevo, IDC, MGU, RSU |
| **project_name** | TEXT | 项目全名 | "MyBMW App" |
| **fv_mapping_json** | TEXT | FV映射配置（JSON） | `{"Navigation": "IuK_TSP_Navi"}` |
| **team** | TEXT | 团队 | DIPS, IUK |
| **aida_fv_mapping_json** | TEXT | AIDA-FV映射配置（JSON） | `{"Navigation": ["IuK_TSP_Navi", "DIPS_TSP_Navi"]}` |
| **fvp_mapping_json** | TEXT | FVP映射配置（JSON） | `{"IuK_TSP_Navi": "Tony"}` |

---

## 📊 Matrix 严重性等级说明

Matrix 用于标识缺陷的严重性等级，按照数字和字母组合排序：

### High Severity（高严重性）
- Matrix-1A, Matrix-1B, Matrix-1C, Matrix-1D, Matrix-1E
- Matrix-2A, Matrix-2B, Matrix-2C
- Matrix-3A

### Medium Severity（中等严重性）
- Matrix-2D, Matrix-2E
- Matrix-3B, Matrix-3C, Matrix-3D
- Matrix-4A

### Low Severity（低严重性）
- Matrix-3E
- Matrix-4B, Matrix-4C, Matrix-4D, Matrix-4E

**排序规则：** 1A < 1B < 1C < ... < 4E（1A最严重）

---

## 🎯 TopIssue 风险评分说明

### 评分维度（总分最高200+）

| 维度 | 权重 | 说明 |
|------|------|------|
| 1. Matrix严重性 | 30分 | 指数衰减：1A(30分) → 1B(24分) → ... → 4E(2分) |
| 2. Classification | 30分 | Showstopper_Confirmed(30), Preventing Maturity ConDrive(30), Showstopper_Candidate(20) |
| 3. ECU转移次数 | 30分 | ≥5次(30分), ≥3次(24分), ≥1次(20分) |
| 4. Domain转移次数 | 20分 | ≥5次(20分), ≥3次(14分), ≥1次(10分) |
| 5. Parent子票数 | 30分 | 对数增长：1个(17分) → 10个(25分) → 上限30分 |
| 6. Child主票子票数 | 30分 | 同上，使用主票的子票数 |
| 7. 处理周期天数 | 20分 | 双峰分布：新票高(18-24分) → 正常低(5-15分) → Long Runner高(20-25分) |
| 8. Shift PU | 10分 | 延期标记(10分) |

### 风险等级划分

| 风险等级 | 分数范围 | 说明 |
|----------|----------|------|
| Extremely High Risk | ≥140分 | 极高风险，需要立即关注 |
| High Risk | 100-139分 | 高风险，优先处理 |
| Medium Risk | 60-99分 | 中等风险，正常监控 |
| Low Risk | 30-59分 | 低风险，可延后处理 |
| - | <30分 | 不视为TopIssue |

### 非线性调整规则

1. **维度交互效应：** 当关键维度组合同时高分时额外加分
   - 高严重性 + 长处理时间：+15分
   - 跨ECU + 跨Domain：+10分
   - 严重性 + 阻塞分类：+15分

2. **时间加速：** 超过30天后每10天额外+2分，最多+30分

3. **复杂度阈值：** 
   - 超大规模父票（>10子票）：(子票数-10)*2.5分
   - 极端ECU转移（>5次）：10*log(1+(转移数-5)/2)分

---

## 🔄 状态流转规则

### 主要状态

| 状态代码 | 状态名称 | 说明 |
|----------|----------|------|
| 00 | New (created) | 新创建 |
| 01 | New | 新建 |
| 02 | In Pre-Analysis | 预分析中 |
| 03 | In Analysis | 分析中 |
| 04 | In Progress | 进行中 |
| 05 | In Testing | 测试中 |
| 06 | Concluded | 已解决（最终状态） |
| 07 | In Pre-Verification | 预验证中 |
| 08 | In Verification | 验证中 |
| 09 | Concluded without action | 无行动关闭（最终状态） |
| 10 | Closed | 已关闭（最终状态） |

### 入流（Inflow）
每周从状态 00 或其他系统创建，进入状态 01 的缺陷数量。

### 出流（Outflow）
每周从任意状态进入最终状态（06, 09, 10）的缺陷数量。

---

## 🔍 业务术语映射

### TopIssue 相关

| 业务术语 | SQL查询条件 |
|----------|------------|
| TopIssue | `is_topissue = 1` 或 `topissue_risk_score >= 60` |
| 高风险TopIssue | `topissue_risk_score >= 100` |
| 极高风险TopIssue | `topissue_risk_score >= 140` |
| 使用主票分数的TopIssue | `is_master_score = 1` |

### High Runner 相关

| 业务术语 | SQL查询条件 |
|----------|------------|
| High Runner（ECU频繁转移） | `ecu_no_of_changes >= 3` |
| 极端High Runner | `ecu_no_of_changes >= 5` |
| Domain High Runner | `domain_pingpong_count >= 3` |
| 跨ECU+Domain High Runner | `ecu_no_of_changes >= 3 AND domain_pingpong_count >= 3` |

### Long Runner 相关

| 业务术语 | SQL查询条件 |
|----------|------------|
| Long Runner（长期未解决） | `processing_cycle_days >= 30 AND status_phase NOT IN ('06-Concluded', '09-Concluded without action', '10-Closed')` |
| 中期Long Runner | `processing_cycle_days >= 15 AND processing_cycle_days < 30` |
| 新票（快速响应） | `processing_cycle_days <= 3` |

### 严重性相关

| 业务术语 | SQL查询条件 |
|----------|------------|
| 高严重性缺陷 | `matrix LIKE 'Matrix-1%' OR matrix LIKE 'Matrix-2A%' OR matrix LIKE 'Matrix-2B%' OR matrix LIKE 'Matrix-2C%' OR matrix LIKE 'Matrix-3A%'` |
| 中等严重性缺陷 | `matrix LIKE 'Matrix-2D%' OR matrix LIKE 'Matrix-2E%' OR matrix LIKE 'Matrix-3B%' OR matrix LIKE 'Matrix-3C%' OR matrix LIKE 'Matrix-3D%' OR matrix LIKE 'Matrix-4A%'` |
| 低严重性缺陷 | `matrix LIKE 'Matrix-3E%' OR matrix LIKE 'Matrix-4B%' OR matrix LIKE 'Matrix-4C%' OR matrix LIKE 'Matrix-4D%' OR matrix LIKE 'Matrix-4E%'` |
| Showstopper | `classification_json LIKE '%Showstopper%'` |
| 阻塞成熟度 | `classification_json LIKE '%Preventing Maturity Grade%'` |

### 票据关系相关

| 业务术语 | SQL查询条件 |
|----------|------------|
| 主票（Parent） | `parent_child = 'Parent'` |
| 子票（Child） | `parent_child = 'Child' OR parent_child = 'Child (candidate)'` |
| 大规模主票（≥5子票） | `parent_child = 'Parent' AND child_count >= 5` |
| 超大规模主票（>10子票） | `parent_child = 'Parent' AND child_count > 10` |
| 重复子票 | `parent_child = 'Child' AND sub_status = 'Child (Duplicate)'` |

### 项目相关

| 业务术语 | 说明 | 可选值 |
|----------|------|--------|
| App项目 | 移动App项目 | App |
| IDCevo项目 | 新一代IDC项目 | IDCevo |
| IDC项目 | ID Connected项目 | IDC |
| MGU项目 | Media Graphics Unit项目 | MGU |
| RSU项目 | Remote Software Update项目 | RSU |

---

## 📈 常用查询场景

### 1. 查询TopIssue缺陷
```sql
SELECT id, name, project, ecu, matrix, topissue_display, 
       topissue_risk_score, topissue_recommend_reason, 
       processing_cycle_days, creation_time
FROM defects
WHERE is_topissue = 1
ORDER BY topissue_risk_score DESC
LIMIT 100;
```

### 2. 按项目统计缺陷
```sql
SELECT project, 
       COUNT(*) as total_defects,
       SUM(CASE WHEN matrix LIKE 'Matrix-1%' THEN 1 ELSE 0 END) as severe_defects,
       AVG(processing_cycle_days) as avg_processing_days,
       COUNT(DISTINCT ecu) as ecu_count
FROM defects
WHERE test_week BETWEEN '2025-CW01' AND '2025-CW52'
GROUP BY project
ORDER BY total_defects DESC;
```

### 3. 查询High Runner缺陷
```sql
SELECT id, name, ecu, ecu_no_of_changes, ecu_pingpong_display,
       domain_pingpong_count, processing_cycle_days, matrix
FROM defects
WHERE ecu_no_of_changes >= 3 OR domain_pingpong_count >= 3
ORDER BY (ecu_no_of_changes + domain_pingpong_count) DESC;
```

### 4. 查询Long Runner缺陷
```sql
SELECT id, name, project, ecu, status_phase, 
       processing_cycle_days, creation_time
FROM defects
WHERE processing_cycle_days >= 30 
  AND status_phase NOT IN ('06-Concluded', '09-Concluded without action', '10-Closed')
ORDER BY processing_cycle_days DESC;
```

### 5. 查询大规模主票
```sql
SELECT id, name, project, ecu, child_count, 
       topissue_risk_score, creation_time
FROM defects
WHERE parent_child = 'Parent' AND child_count >= 5
ORDER BY child_count DESC;
```

### 6. 缺陷入出流趋势
```sql
SELECT week, inflow, outflow, net_change
FROM defect_inflow_outflow
WHERE week BETWEEN '2025-W01' AND '2025-W52'
ORDER BY week;
```

### 7. 按ECU统计TopIssue
```sql
SELECT ecu, 
       COUNT(*) as total_topissues,
       AVG(topissue_risk_score) as avg_risk_score,
       SUM(CASE WHEN matrix LIKE 'Matrix-1%' THEN 1 ELSE 0 END) as severe_topissues
FROM defects
WHERE is_topissue = 1
GROUP BY ecu
ORDER BY total_topissues DESC;
```

### 8. 查询测试执行情况
```sql
SELECT project, tester, run_status, COUNT(*) as count
FROM test_executions
WHERE test_week BETWEEN '2025-CW01' AND '2025-CW52'
GROUP BY project, tester, run_status
ORDER BY project, tester, run_status;
```

---

## 🎯 使用建议

1. **查询时注意状态过滤：** 通常需要排除已解决的票据（`status_phase NOT IN ('06-Concluded', '09-Concluded without action', '10-Closed')`）来统计活跃票据
2. **关注测试周范围：** 大部分查询应限定在特定的测试周范围内（如 `test_week BETWEEN '2025-CW01' AND '2025-CW52'`）
3. **使用Matrix严重性分组：** `severity_group` 字段提供了高严重性和一般问题的快速分组
4. **注意父子关系：** Child票据的 `master_child_count` 字段显示其主票的子票数，用于评估主票的复杂度
5. **风险评分排序：** `topissue_risk_score` 字段提供了综合的风险评分，可以直接用于排序优先级
6. **流转路径分析：** `ecu_pingpong_display` 和 `domain_pingpong_display` 字段包含了完整的流转路径和次数，便于分析问题

---

## 📝 注意事项

1. **JSON字段：** `aidas_json`, `classification_json`, `change_set_json` 等字段存储JSON格式的数据，查询时需要使用JSON函数
2. **时间字段：** `creation_time`, `test_week` 等时间相关的字段需要注意时区问题，统一使用UTC时间
3. **NULL值处理：** 许多字段可能为NULL或空字符串，查询时需要使用 `COALESCE(field, '')` 或 `IFNULL(field, '')` 处理
4. **性能优化：** 建议在 `creation_time`, `test_week`, `project`, `ecu`, `status_phase`, `matrix`, `parent_child`, `topissue_risk_score` 等字段上建立索引
5. **父子关系查询：** 查询父子关系时，需要注意 `parent_child` 字段的值区分大小写
6. **历史数据查询：** `defect_history` 表包含所有历史变更，查询时可能需要关联 `defects` 表获取当前状态
