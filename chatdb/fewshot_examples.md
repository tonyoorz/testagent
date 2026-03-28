# Few-shot 查询示例

本文件包含了车载软件缺陷管理系统的常见查询场景和对应的SQL查询示例。
这些示例可以作为 ChatDB 或 text-to-SQL agent 的 Few-shot learning 数据。

---

## 示例说明

每个示例包含：
1. **用户问题**（中文）
2. **SQL 查询**
3. **查询说明**
4. **输出示例**

---

## 1. TopIssue 查询相关

### 示例 1.1: 查询所有 TopIssue 缺陷

**用户问题：**
> 查询所有 TopIssue 缺陷，按风险评分从高到低排序，显示前100个。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    project,
    ecu,
    matrix,
    topissue_display,
    topissue_risk_score,
    topissue_recommend_reason,
    processing_cycle_days,
    creation_time
FROM defects
WHERE is_topissue = 1
ORDER BY topissue_risk_score DESC
LIMIT 100;
```

**查询说明：**
- 使用 `is_topissue = 1` 筛选所有 TopIssue 缺陷
- 按 `topissue_risk_score` 降序排序，高风险排在前面
- 限制返回100条记录

**输出示例：**
| id | name | project | ecu | matrix | topissue_display | topissue_risk_score | processing_cycle_days | creation_time |
|----|------|---------|-----|--------|-----------------|-------------------|---------------------|---------------|
| 123456 | 导航无法启动 | App | IuK_HU | Matrix-1A | 145* | 145.5 | 45 | 2025-03-28 10:30:00 |
| 123457 | 蓝牙连接失败 | App | DIPS_HU | Matrix-1B | 132 | 132.0 | 38 | 2025-03-27 14:20:00 |

---

### 示例 1.2: 查询高风险 TopIssue

**用户问题：**
> 查询高风险（≥100分）的 TopIssue 缺陷。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    project,
    ecu,
    matrix,
    topissue_risk_score,
    topissue_recommend_reason
FROM defects
WHERE topissue_risk_score >= 100
ORDER BY topissue_risk_score DESC;
```

**查询说明：**
- 使用 `topissue_risk_score >= 100` 筛选高风险缺陷
- 风险评分≥100分定义为高风险

---

### 示例 1.3: 查询特定项目的 TopIssue

**用户问题：**
> 查询 App 项目的所有 TopIssue 缺陷。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    ecu,
    matrix,
    topissue_risk_score,
    processing_cycle_days,
    creation_time
FROM defects
WHERE project = 'App' AND is_topissue = 1
ORDER BY topissue_risk_score DESC;
```

**查询说明：**
- 同时筛选 `project = 'App'` 和 `is_topissue = 1`
- 返回 App 项目下的所有 TopIssue 缺陷

---

### 示例 1.4: 查询使用主票分数的 TopIssue

**用户问题：**
> 查询那些使用主票分数的 TopIssue 缺陷（即子票的风险来自其主票）。

**SQL 查询：**
```sql
SELECT 
    d.id,
    d.name,
    d.project,
    d.ecu,
    d.matrix,
    d.topissue_risk_score,
    d.topissue_recommend_reason,
    d.parent_ticket_id,
    d.master_child_count
FROM defects d
WHERE d.is_topissue = 1 AND d.is_master_score = 1
ORDER BY d.topissue_risk_score DESC;
```

**查询说明：**
- `is_master_score = 1` 表示该缺陷的风险评分来自其主票
- `parent_ticket_id` 是主票ID
- `master_child_count` 是主票的子票数量

---

## 2. High Runner 查询相关

### 示例 2.1: 查询所有 High Runner 缺陷

**用户问题：**
> 查询所有 High Runner 缺陷（ECU转移≥3次或Domain转移≥3次）。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    ecu,
    ecu_no_of_changes,
    ecu_pingpong_display,
    domain_pingpong_count,
    domain_pingpong_display,
    processing_cycle_days,
    matrix
FROM defects
WHERE ecu_no_of_changes >= 3 OR domain_pingpong_count >= 3
ORDER BY (ecu_no_of_changes + domain_pingpong_count) DESC;
```

**查询说明：**
- ECU转移≥3次或Domain转移≥3次视为 High Runner
- 按总转移次数降序排序

---

### 示例 2.2: 查询极端 High Runner

**用户问题：**
> 查询极端 High Runner 缺陷（ECU转移≥5次）。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    ecu,
    ecu_no_of_changes,
    ecu_transition_path,
    processing_cycle_days,
    matrix
FROM defects
WHERE ecu_no_of_changes >= 5
ORDER BY ecu_no_of_changes DESC;
```

**查询说明：**
- ECU转移≥5次视为极端 High Runner
- 显示完整的 ECU 转移路径

---

### 示例 2.3: 查询跨 ECU 和 Domain 的 High Runner

**用户问题：**
> 查询同时跨 ECU 和 Domain 的 High Runner 缺陷。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    ecu,
    ecu_no_of_changes,
    ecu_pingpong_display,
    domain,
    domain_pingpong_count,
    domain_pingpong_display,
    processing_cycle_days,
    matrix
FROM defects
WHERE ecu_no_of_changes >= 3 AND domain_pingpong_count >= 3
ORDER BY (ecu_no_of_changes + domain_pingpong_count) DESC;
```

**查询说明：**
- 同时满足 ECU 转移≥3次和 Domain 转移≥3次
- 这类缺陷通常涉及多个领域，复杂度高

---

## 3. Long Runner 查询相关

### 示例 3.1: 查询所有 Long Runner 缺陷

**用户问题：**
> 查询所有 Long Runner 缺陷（处理周期≥30天且未解决）。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    project,
    ecu,
    status_phase,
    processing_cycle_days,
    creation_time
FROM defects
WHERE processing_cycle_days >= 30 
  AND status_phase NOT IN ('06-Concluded', '09-Concluded without action', '10-Closed')
ORDER BY processing_cycle_days DESC;
```

**查询说明：**
- 处理周期≥30天且未解决（排除最终状态）视为 Long Runner
- 按处理周期降序排序

---

### 示例 3.2: 查询特定项目的 Long Runner

**用户问题：**
> 查询 IDC 项目的所有 Long Runner 缺陷。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    ecu,
    status_phase,
    processing_cycle_days,
    creation_time
FROM defects
WHERE project = 'IDC' 
  AND processing_cycle_days >= 30
  AND status_phase NOT IN ('06-Concluded', '09-Concluded without action', '10-Closed')
ORDER BY processing_cycle_days DESC;
```

**查询说明：**
- 同时筛选 `project = 'IDC'` 和 Long Runner 条件
- 只关注 IDC 项目的长期未解决缺陷

---

### 示例 3.3: 查询新票（需要快速响应）

**用户问题：**
> 查询处理周期≤3天的新票（需要快速响应的缺陷）。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    project,
    ecu,
    status_phase,
    processing_cycle_days,
    creation_time,
    matrix
FROM defects
WHERE processing_cycle_days <= 3 
  AND status_phase NOT IN ('06-Concluded', '09-Concluded without action', '10-Closed')
ORDER BY processing_cycle_days ASC, creation_time DESC;
```

**查询说明：**
- 处理周期≤3天且未解决的缺陷视为新票
- 按处理周期升序排序（先显示时间最短的），再按创建时间降序

---

## 4. 票据关系查询相关

### 示例 4.1: 查询所有主票

**用户问题：**
> 查询所有主票（Parent），按子票数量降序排序。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    project,
    ecu,
    child_count,
    topissue_risk_score,
    creation_time
FROM defects
WHERE parent_child = 'Parent'
ORDER BY child_count DESC;
```

**查询说明：**
- `parent_child = 'Parent'` 筛选所有主票
- 按 `child_count` 降序排序，子票多的排在前面

---

### 示例 4.2: 查询大规模主票（≥5子票）

**用户问题：**
> 查询大规模主票（子票数≥5个），按子票数量降序排序。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    project,
    ecu,
    child_count,
    topissue_risk_score,
    processing_cycle_days,
    creation_time
FROM defects
WHERE parent_child = 'Parent' AND child_count >= 5
ORDER BY child_count DESC;
```

**查询说明：**
- 同时满足主票和子票数≥5个
- 大规模主票通常代表广泛的问题

---

### 示例 4.3: 查询超大规模主票（>10子票）

**用户问题：**
> 查询超大规模主票（子票数>10个）。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    project,
    ecu,
    child_count,
    topissue_risk_score,
    creation_time
FROM defects
WHERE parent_child = 'Parent' AND child_count > 10
ORDER BY child_count DESC;
```

**查询说明：**
- 子票数>10个视为超大规模主票
- 这类问题通常需要重点关注

---

### 示例 4.4: 查询子票

**用户问题：**
> 查询所有子票（Child），显示其主票信息。

**SQL 查询：**
```sql
SELECT 
    child.id,
    child.name,
    child.ecu,
    child.status_phase,
    child.parent_ticket_id,
    child.master_child_count,
    parent.name as parent_name,
    parent.ecu as parent_ecu
FROM defects child
LEFT JOIN defects parent ON child.parent_ticket_id = parent.id
WHERE child.parent_child IN ('Child', 'Child (candidate)')
ORDER BY child.master_child_count DESC;
```

**查询说明：**
- 筛选 `parent_child` 为 `Child` 或 `Child (candidate)` 的记录
- 关联主票表获取主票信息
- 按主票的子票数降序排序

---

## 5. 项目统计查询相关

### 示例 5.1: 按项目统计缺陷总数

**用户问题：**
> 按项目统计缺陷总数、高严重性缺陷数、平均处理周期。

**SQL 查询：**
```sql
SELECT 
    project,
    COUNT(*) as total_defects,
    SUM(CASE WHEN matrix LIKE 'Matrix-1%' THEN 1 ELSE 0 END) as severe_defects,
    ROUND(AVG(processing_cycle_days), 2) as avg_processing_days,
    COUNT(DISTINCT ecu) as ecu_count
FROM defects
WHERE test_week BETWEEN '2025-CW01' AND '2025-CW52'
GROUP BY project
ORDER BY total_defects DESC;
```

**查询说明：**
- 统计每个项目的总缺陷数
- 高严重性缺陷定义为 Matrix-1x
- 计算平均处理周期天数
- 限定在2025年的测试周

---

### 示例 5.2: 按项目统计 TopIssue 数量

**用户问题：**
> 按项目统计 TopIssue 数量和平均风险评分。

**SQL 查询：**
```sql
SELECT 
    project,
    COUNT(*) as total_topissues,
    AVG(topissue_risk_score) as avg_risk_score,
    SUM(CASE WHEN matrix LIKE 'Matrix-1%' THEN 1 ELSE 0 END) as severe_topissues,
    ROUND(AVG(processing_cycle_days), 2) as avg_processing_days
FROM defects
WHERE is_topissue = 1
GROUP BY project
ORDER BY total_topissues DESC;
```

**查询说明：**
- 筛选所有 TopIssue
- 按项目分组统计
- 计算平均风险评分

---

### 示例 5.3: 按项目统计 High Runner 数量

**用户问题：**
> 按项目统计 High Runner 数量。

**SQL 查询：**
```sql
SELECT 
    project,
    COUNT(*) as total_high_runners,
    AVG(ecu_no_of_changes + domain_pingpong_count) as avg_transfer_count,
    MAX(ecu_no_of_changes) as max_ecu_transfers,
    ROUND(AVG(processing_cycle_days), 2) as avg_processing_days
FROM defects
WHERE ecu_no_of_changes >= 3 OR domain_pingpong_count >= 3
GROUP BY project
ORDER BY total_high_runners DESC;
```

**查询说明：**
- 筛选所有 High Runner
- 按项目分组统计
- 计算平均转移次数

---

### 示例 5.4: 按项目统计 Long Runner 数量

**用户问题：**
> 按项目统计 Long Runner 数量。

**SQL 查询：**
```sql
SELECT 
    project,
    COUNT(*) as total_long_runners,
    ROUND(AVG(processing_cycle_days), 2) as avg_processing_days,
    MAX(processing_cycle_days) as max_processing_days
FROM defects
WHERE processing_cycle_days >= 30
  AND status_phase NOT IN ('06-Concluded', '09-Concluded without action', '10-Closed')
GROUP BY project
ORDER BY total_long_runners DESC;
```

**查询说明：**
- 筛选所有 Long Runner（未解决且处理周期≥30天）
- 按项目分组统计

---

## 6. ECU 统计查询相关

### 示例 6.1: 按 ECU 统计缺陷总数

**用户问题：**
> 按 ECU 统计缺陷总数、TopIssue 数量、平均处理周期。

**SQL 查询：**
```sql
SELECT 
    ecu,
    COUNT(*) as total_defects,
    SUM(CASE WHEN is_topissue = 1 THEN 1 ELSE 0 END) as total_topissues,
    ROUND(AVG(topissue_risk_score), 2) as avg_topissue_score,
    ROUND(AVG(processing_cycle_days), 2) as avg_processing_days,
    COUNT(DISTINCT project) as project_count
FROM defects
WHERE ecu != '' AND ecu IS NOT NULL
GROUP BY ecu
ORDER BY total_defects DESC;
```

**查询说明：**
- 按 ECU 分组统计
- 统计每个 ECU 的 TopIssue 数量和平均风险评分

---

### 示例 6.2: 按 ECU 统计 High Runner 数量

**用户问题：**
> 按 ECU 统计 High Runner 数量和平均转移次数。

**SQL 查询：**
```sql
SELECT 
    ecu,
    COUNT(*) as total_high_runners,
    ROUND(AVG(ecu_no_of_changes), 2) as avg_ecu_transfers,
    MAX(ecu_no_of_changes) as max_ecu_transfers,
    ROUND(AVG(processing_cycle_days), 2) as avg_processing_days
FROM defects
WHERE ecu_no_of_changes >= 3
GROUP BY ecu
ORDER BY total_high_runners DESC;
```

**查询说明：**
- 筛选所有 High Runner
- 按 ECU 分组统计平均转移次数

---

### 示例 6.3: 查询频繁转移的 ECU 路径

**用户问题：**
> 查询 ECU 转移路径最多的前10个缺陷。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    ecu,
    ecu_no_of_changes,
    ecu_pingpong_display,
    ecu_transition_path,
    processing_cycle_days
FROM defects
WHERE ecu_no_of_changes >= 3
ORDER BY ecu_no_of_changes DESC
LIMIT 10;
```

**查询说明：**
- 筛选 ECU 转移≥3次的缺陷
- 显示完整的 ECU 转移路径
- 限制返回10条记录

---

## 7. 严重性分析查询相关

### 示例 7.1: 按严重性分组统计

**用户问题：**
> 按严重性分组（高/中/低）统计缺陷数量。

**SQL 查询：**
```sql
SELECT 
    CASE 
        WHEN matrix LIKE 'Matrix-1%' OR matrix LIKE 'Matrix-2A%' OR matrix LIKE 'Matrix-2B%' OR matrix LIKE 'Matrix-2C%' OR matrix LIKE 'Matrix-3A%' THEN 'High Severity'
        WHEN matrix LIKE 'Matrix-2D%' OR matrix LIKE 'Matrix-2E%' OR matrix LIKE 'Matrix-3B%' OR matrix LIKE 'Matrix-3C%' OR matrix LIKE 'Matrix-3D%' OR matrix LIKE 'Matrix-4A%' THEN 'Medium Severity'
        WHEN matrix LIKE 'Matrix-3E%' OR matrix LIKE 'Matrix-4B%' OR matrix LIKE 'Matrix-4C%' OR matrix LIKE 'Matrix-4D%' OR matrix LIKE 'Matrix-4E%' THEN 'Low Severity'
        ELSE 'Unknown'
    END as severity_group,
    COUNT(*) as total_defects,
    SUM(CASE WHEN is_topissue = 1 THEN 1 ELSE 0 END) as total_topissues,
    ROUND(AVG(processing_cycle_days), 2) as avg_processing_days
FROM defects
WHERE matrix != '' AND matrix IS NOT NULL
GROUP BY severity_group
ORDER BY 
    CASE severity_group
        WHEN 'High Severity' THEN 1
        WHEN 'Medium Severity' THEN 2
        WHEN 'Low Severity' THEN 3
        ELSE 4
    END;
```

**查询说明：**
- 根据 Matrix 值划分严重性分组
- High Severity 最严重，Low Severity 最不严重

---

### 示例 7.2: 查询 Showstopper 缺陷

**用户问题：**
> 查询所有 Showstopper 缺陷。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    project,
    ecu,
    matrix,
    classification_display,
    topissue_risk_score,
    status_phase,
    creation_time
FROM defects
WHERE classification_json LIKE '%Showstopper%'
ORDER BY topissue_risk_score DESC;
```

**查询说明：**
- 筛选 `classification_json` 包含 'Showstopper' 的记录
- Showstopper 是最高优先级的缺陷

---

### 示例 7.3: 查询阻塞成熟度的缺陷

**用户问题：**
> 查询所有阻塞成熟度的缺陷。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    project,
    ecu,
    matrix,
    classification_display,
    topissue_risk_score,
    status_phase,
    processing_cycle_days
FROM defects
WHERE classification_json LIKE '%Preventing Maturity Grade%'
ORDER BY topissue_risk_score DESC;
```

**查询说明：**
- 筛选 `classification_json` 包含 'Preventing Maturity Grade' 的记录
- 这类缺陷会阻塞项目的成熟度评估

---

## 8. 入出流趋势查询相关

### 示例 8.1: 查询缺陷入出流趋势

**用户问题：**
> 查询2025年的缺陷入出流趋势（每周的 inflow 和 outflow）。

**SQL 查询：**
```sql
SELECT 
    week,
    inflow,
    outflow,
    net_change,
    ROUND(
        (SUM(outflow) OVER (ORDER BY week) * 1.0 / 
         NULLIF(SUM(inflow) OVER (ORDER BY week), 0)) * 100, 
        2
    ) as cumulative_convergence_rate
FROM defect_inflow_outflow
WHERE week BETWEEN '2025-W01' AND '2025-W52'
ORDER BY week;
```

**查询说明：**
- 查询每周的 inflow 和 outflow
- 计算累计收敛率（outflow/inflow）

---

### 示例 8.2: 查询入出流汇总统计

**用户问题：**
> 查询2025年的缺陷入出流汇总统计。

**SQL 查询：**
```sql
SELECT 
    SUM(inflow) as total_inflow,
    SUM(outflow) as total_outflow,
    SUM(inflow) - SUM(outflow) as net_accumulation,
    ROUND(AVG(inflow), 2) as avg_weekly_inflow,
    ROUND(AVG(outflow), 2) as avg_weekly_outflow,
    ROUND(SUM(outflow) * 100.0 / NULLIF(SUM(inflow), 0), 2) as overall_convergence_rate
FROM defect_inflow_outflow
WHERE week BETWEEN '2025-W01' AND '2025-W52';
```

**查询说明：**
- 统计总入流、总出流、净累积
- 计算平均周入流、周出流
- 计算总体收敛率（解决率）

---

### 示例 8.3: 查询入出流异常周

**用户问题：**
> 查询入流或出流异常的周（超过平均值2倍）。

**SQL 查询：**
```sql
SELECT 
    week,
    inflow,
    outflow,
    net_change,
    CASE 
        WHEN inflow > (SELECT AVG(inflow) FROM defect_inflow_outflow) * 2 THEN 'High Inflow'
        WHEN outflow > (SELECT AVG(outflow) FROM defect_inflow_outflow) * 2 THEN 'High Outflow'
        WHEN net_change > (SELECT AVG(net_change) FROM defect_inflow_outflow) * 2 THEN 'High Accumulation'
        ELSE 'Normal'
    END as anomaly_type
FROM defect_inflow_outflow
WHERE week BETWEEN '2025-W01' AND '2025-W52'
  AND (inflow > (SELECT AVG(inflow) FROM defect_inflow_outflow) * 2
       OR outflow > (SELECT AVG(outflow) FROM defect_inflow_outflow) * 2
       OR net_change > (SELECT AVG(net_change) FROM defect_inflow_outflow) * 2)
ORDER BY week;
```

**查询说明：**
- 筛选入流、出流或净变化超过平均值2倍的周
- 标记异常类型

---

## 9. 测试执行查询相关

### 示例 9.1: 按项目统计测试执行情况

**用户问题：**
> 按项目统计测试执行情况（总数、通过、失败、阻塞）。

**SQL 查询：**
```sql
SELECT 
    project,
    COUNT(*) as total_tests,
    SUM(CASE WHEN run_status = 'Passed' THEN 1 ELSE 0 END) as passed_tests,
    SUM(CASE WHEN run_status = 'Failed' THEN 1 ELSE 0 END) as failed_tests,
    SUM(CASE WHEN run_status = 'Blocked' THEN 1 ELSE 0 END) as blocked_tests,
    ROUND(SUM(CASE WHEN run_status = 'Passed' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) as pass_rate
FROM test_executions
WHERE test_week BETWEEN '2025-CW01' AND '2025-CW52'
GROUP BY project
ORDER BY total_tests DESC;
```

**查询说明：**
- 统计每个项目的测试总数
- 计算通过、失败、阻塞的数量
- 计算通过率

---

### 示例 9.2: 按测试人员统计执行情况

**用户问题：**
> 按测试人员统计执行情况。

**SQL 查询：**
```sql
SELECT 
    tester,
    project,
    COUNT(*) as total_tests,
    SUM(CASE WHEN run_status = 'Passed' THEN 1 ELSE 0 END) as passed_tests,
    SUM(CASE WHEN run_status = 'Failed' THEN 1 ELSE 0 END) as failed_tests,
    ROUND(SUM(CASE WHEN run_status = 'Passed' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) as pass_rate
FROM test_executions
WHERE test_week BETWEEN '2025-CW01' AND '2025-CW52'
GROUP BY tester, project
ORDER BY total_tests DESC;
```

**查询说明：**
- 按测试人员和项目分组统计
- 计算每个测试人员的通过率

---

### 示例 9.3: 查询失败的测试用例

**用户问题：**
> 查询2025年所有失败的测试用例。

**SQL 查询：**
```sql
SELECT 
    id,
    test_id,
    test_name,
    project,
    tester,
    aida_english,
    fv,
    run_status,
    finished_udf
FROM test_executions
WHERE run_status = 'Failed'
  AND test_week BETWEEN '2025-CW01' AND '2025-CW52'
ORDER BY finished_udf DESC;
```

**查询说明：**
- 筛选所有失败的测试用例
- 按完成时间降序排序

---

## 10. 复杂查询示例

### 示例 10.1: 查询 TopIssue 且是 High Runner 的缺陷

**用户问题：**
> 查询同时是 TopIssue 且是 High Runner 的缺陷。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    project,
    ecu,
    matrix,
    topissue_risk_score,
    ecu_no_of_changes,
    domain_pingpong_count,
    processing_cycle_days,
    creation_time
FROM defects
WHERE is_topissue = 1 
  AND (ecu_no_of_changes >= 3 OR domain_pingpong_count >= 3)
ORDER BY topissue_risk_score DESC;
```

**查询说明：**
- 同时满足 TopIssue 和 High Runner 条件
- 这类缺陷既风险高又频繁转移，需要重点关注

---

### 示例 10.2: 查询大规模主票且是 TopIssue 的缺陷

**用户问题：**
> 查询大规模主票（≥5子票）且是 TopIssue 的缺陷。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    project,
    ecu,
    child_count,
    topissue_risk_score,
    processing_cycle_days,
    creation_time
FROM defects
WHERE parent_child = 'Parent' 
  AND child_count >= 5 
  AND is_topissue = 1
ORDER BY child_count DESC, topissue_risk_score DESC;
```

**查询说明：**
- 同时满足主票、子票数≥5、TopIssue
- 按子票数和风险评分排序

---

### 示例 10.3: 查询高严重性且 Long Runner 的缺陷

**用户问题：**
> 查询高严重性（Matrix-1x）且 Long Runner 的缺陷。

**SQL 查询：**
```sql
SELECT 
    id,
    name,
    project,
    ecu,
    matrix,
    status_phase,
    processing_cycle_days,
    topissue_risk_score,
    creation_time
FROM defects
WHERE matrix LIKE 'Matrix-1%' 
  AND processing_cycle_days >= 30
  AND status_phase NOT IN ('06-Concluded', '09-Concluded without action', '10-Closed')
ORDER BY processing_cycle_days DESC, topissue_risk_score DESC;
```

**查询说明：**
- 高严重性且长期未解决的缺陷
- 按处理周期和风险评分排序

---

### 示例 10.4: 按周统计 TopIssue 趋势

**用户问题：**
> 按周统计 TopIssue 数量趋势。

**SQL 查询：**
```sql
SELECT 
    test_week,
    COUNT(*) as total_topissues,
    ROUND(AVG(topissue_risk_score), 2) as avg_risk_score,
    SUM(CASE WHEN matrix LIKE 'Matrix-1%' THEN 1 ELSE 0 END) as severe_topissues
FROM defects
WHERE is_topissue = 1
GROUP BY test_week
ORDER BY test_week;
```

**查询说明：**
- 按测试周分组统计 TopIssue
- 计算平均风险评分

---

### 示例 10.5: 查询活跃缺陷的汇总统计

**用户问题：**
> 查询所有活跃缺陷（未解决）的汇总统计。

**SQL 查询：**
```sql
SELECT 
    COUNT(*) as total_active_defects,
    SUM(CASE WHEN is_topissue = 1 THEN 1 ELSE 0 END) as total_topissues,
    SUM(CASE WHEN ecu_no_of_changes >= 3 OR domain_pingpong_count >= 3 THEN 1 ELSE 0 END) as total_high_runners,
    SUM(CASE WHEN processing_cycle_days >= 30 THEN 1 ELSE 0 END) as total_long_runners,
    SUM(CASE WHEN matrix LIKE 'Matrix-1%' THEN 1 ELSE 0 END) as total_severe_defects,
    ROUND(AVG(processing_cycle_days), 2) as avg_processing_days,
    ROUND(AVG(topissue_risk_score), 2) as avg_topissue_score
FROM defects
WHERE status_phase NOT IN ('06-Concluded', '09-Concluded without action', '10-Closed');
```

**查询说明：**
- 统计所有活跃缺陷（未解决）
- 分类统计 TopIssue、High Runner、Long Runner、高严重性缺陷
- 计算平均处理周期和平均风险评分

---

## 使用建议

1. **模板化使用：** 这些示例可以作为 SQL 查询模板，根据具体需求调整参数
2. **组合查询：** 可以将多个查询条件组合起来，实现更复杂的筛选
3. **性能优化：** 对于大表查询，建议在筛选字段上建立索引
4. **时区注意：** 时间相关的字段注意时区问题，统一使用 UTC 时间
5. **NULL 值处理：** 许多字段可能为 NULL，使用 `COALESCE` 或 `IFNULL` 处理

---

## 扩展阅读

- Schema 说明文档：`schema_description.md`
- 业务规则文档：`business_rules.py`
- 业务术语映射：`business_term_mapping.py`
