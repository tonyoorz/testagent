# Deterministic SQL Regression Report

- generated_at: 2026-04-01T17:11:55.070601
- db_path: database/local_data_rebuilt.db
- total: 19
- success: 19
- nonempty: 19

## Case 1

- Question: 请基于缺陷趋势和测试效率给出改进建议
- Table: octane_defects
- Success: True
- RowCount: 16
- Rules: 12
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_test_week_definition | test_week 时间桶定义
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_classification_and_domain_extraction | classification/domain 提取口径
  - - br_risk_analysis_coverage_formula | Risk Analysis 覆盖率口径
  - - br_risk_analysis_level_threshold | Risk Level 分层阈值
  - - br_test_status_normalization | Test Status 归一化口径
  - - br_test_frequency_pass_rate_definition | Test Frequency 与 Pass Rate 口径

SQL:

```sql
SELECT strftime('%Y-W%W', creation_time) AS week, COUNT(*) AS defect_count, SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) AS closed_count, ROUND(100.0 * SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS close_rate FROM "octane_defects"  WHERE creation_time IS NOT NULL GROUP BY week ORDER BY week DESC LIMIT 16
```

## Case 2

- Question: 请看TopIssue风险和关闭率趋势
- Table: octane_defects
- Success: True
- RowCount: 16
- Rules: 12
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_topissue_child_master_score_selection | Child/Master 风险分取高口径
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_test_week_definition | test_week 时间桶定义
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_classification_and_domain_extraction | classification/domain 提取口径
  - - br_risk_analysis_coverage_formula | Risk Analysis 覆盖率口径
  - - br_risk_analysis_level_threshold | Risk Level 分层阈值
  - - br_test_status_normalization | Test Status 归一化口径

SQL:

```sql
SELECT strftime('%Y-W%W', creation_time) AS week, COUNT(*) AS defect_count, SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) AS closed_count, ROUND(100.0 * SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS close_rate FROM "octane_defects"  WHERE creation_time IS NOT NULL GROUP BY week ORDER BY week DESC LIMIT 16
```

## Case 3

- Question: 请分析DTSV团队高风险缺陷趋势
- Table: octane_defects
- Success: True
- RowCount: 16
- Rules: 12
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_test_week_definition | test_week 时间桶定义
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_classification_and_domain_extraction | classification/domain 提取口径
  - - br_risk_analysis_coverage_formula | Risk Analysis 覆盖率口径
  - - br_risk_analysis_level_threshold | Risk Level 分层阈值
  - - br_test_status_normalization | Test Status 归一化口径
  - - br_test_frequency_pass_rate_definition | Test Frequency 与 Pass Rate 口径

SQL:

```sql
SELECT strftime('%Y-W%W', creation_time) AS week, COUNT(*) AS defect_count, SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) AS closed_count, ROUND(100.0 * SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS close_rate FROM "octane_defects"  WHERE (LOWER(CAST(author AS TEXT)) LIKE LOWER('%DTSV%') OR LOWER(CAST(detected_by AS TEXT)) LIKE LOWER('%DTSV%') OR LOWER(CAST(owner AS TEXT)) LIKE LOWER('%DTSV%') OR LOWER(CAST(team AS TEXT)) LIKE LOWER('%DTSV%') OR LOWER(CAST(name AS TEXT)) LIKE LOWER('%DTSV%')) AND creation_time IS NOT NULL GROUP BY week ORDER BY week DESC LIMIT 16
```

## Case 4

- Question: 请分析缺陷矩阵分布和严重性问题
- Table: octane_defects
- Success: True
- RowCount: 60
- Rules: 12
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_test_week_definition | test_week 时间桶定义
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_classification_and_domain_extraction | classification/domain 提取口径
  - - br_risk_analysis_coverage_formula | Risk Analysis 覆盖率口径
  - - br_risk_analysis_level_threshold | Risk Level 分层阈值
  - - br_test_status_normalization | Test Status 归一化口径
  - - br_test_frequency_pass_rate_definition | Test Frequency 与 Pass Rate 口径

SQL:

```sql
SELECT COALESCE(NULLIF(TRIM(CAST(df.topissue_display AS TEXT)), ''), '未标注') AS matrix_zone, COALESCE(NULLIF(TRIM(CAST(d.severity AS TEXT)), ''), '未标注') AS severity, COUNT(*) AS defect_count FROM "octane_defects" d LEFT JOIN "defect_features" df ON CAST(df.defect_id AS TEXT) = CAST(d.defect_id AS TEXT)  GROUP BY 1, 2 ORDER BY defect_count DESC LIMIT 60
```

## Case 5

- Question: 请看IDCEVO项目近16周缺陷关闭率
- Table: octane_defects
- Success: True
- RowCount: 16
- Rules: 12
  - - br_year_inference_from_test_week | 年份推断与周排序口径
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_test_week_definition | test_week 时间桶定义
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_classification_and_domain_extraction | classification/domain 提取口径
  - - br_risk_analysis_coverage_formula | Risk Analysis 覆盖率口径
  - - br_risk_analysis_level_threshold | Risk Level 分层阈值
  - - br_test_status_normalization | Test Status 归一化口径

SQL:

```sql
SELECT strftime('%Y-W%W', creation_time) AS week, COUNT(*) AS defect_count, SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) AS closed_count, ROUND(100.0 * SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS close_rate FROM "octane_defects"  WHERE (LOWER(CAST(author AS TEXT)) LIKE LOWER('%IDCEVO%') OR LOWER(CAST(detected_by AS TEXT)) LIKE LOWER('%IDCEVO%') OR LOWER(CAST(owner AS TEXT)) LIKE LOWER('%IDCEVO%') OR LOWER(CAST(team AS TEXT)) LIKE LOWER('%IDCEVO%') OR LOWER(CAST(name AS TEXT)) LIKE LOWER('%IDCEVO%')) AND creation_time IS NOT NULL GROUP BY week ORDER BY week DESC LIMIT 16
```

## Case 6

- Question: 请统计本月各状态缺陷分布
- Table: octane_defects
- Success: True
- RowCount: 16
- Rules: 12
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_test_week_definition | test_week 时间桶定义
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_classification_and_domain_extraction | classification/domain 提取口径
  - - br_risk_analysis_coverage_formula | Risk Analysis 覆盖率口径
  - - br_risk_analysis_level_threshold | Risk Level 分层阈值
  - - br_test_status_normalization | Test Status 归一化口径
  - - br_test_frequency_pass_rate_definition | Test Frequency 与 Pass Rate 口径

SQL:

```sql
SELECT strftime('%Y-W%W', creation_time) AS week, COUNT(*) AS defect_count, SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) AS closed_count, ROUND(100.0 * SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS close_rate FROM "octane_defects"  WHERE creation_time IS NOT NULL GROUP BY week ORDER BY week DESC LIMIT 16
```

## Case 7

- Question: 请看提票人Wei Yang相关缺陷趋势
- Table: octane_defects
- Success: True
- RowCount: 16
- Rules: 12
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_test_week_definition | test_week 时间桶定义
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_classification_and_domain_extraction | classification/domain 提取口径
  - - br_risk_analysis_coverage_formula | Risk Analysis 覆盖率口径
  - - br_risk_analysis_level_threshold | Risk Level 分层阈值
  - - br_test_status_normalization | Test Status 归一化口径
  - - br_test_frequency_pass_rate_definition | Test Frequency 与 Pass Rate 口径

SQL:

```sql
SELECT strftime('%Y-W%W', creation_time) AS week, COUNT(*) AS defect_count, SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) AS closed_count, ROUND(100.0 * SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS close_rate FROM "octane_defects"  WHERE (LOWER(CAST(author AS TEXT)) LIKE LOWER('%Wei%') OR LOWER(CAST(detected_by AS TEXT)) LIKE LOWER('%Wei%') OR LOWER(CAST(owner AS TEXT)) LIKE LOWER('%Wei%')) AND (LOWER(CAST(author AS TEXT)) LIKE LOWER('%Yang%') OR LOWER(CAST(detected_by AS TEXT)) LIKE LOWER('%Yang%') OR LOWER(CAST(owner AS TEXT)) LIKE LOWER('%Yang%')) AND creation_time IS NOT NULL GROUP BY week ORDER BY week DESC LIMIT 16
```

## Case 8

- Question: 请看G70相关缺陷走势并给建议
- Table: octane_defects
- Success: True
- RowCount: 16
- Rules: 12
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_test_week_definition | test_week 时间桶定义
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_classification_and_domain_extraction | classification/domain 提取口径
  - - br_risk_analysis_coverage_formula | Risk Analysis 覆盖率口径
  - - br_risk_analysis_level_threshold | Risk Level 分层阈值
  - - br_test_status_normalization | Test Status 归一化口径
  - - br_test_frequency_pass_rate_definition | Test Frequency 与 Pass Rate 口径

SQL:

```sql
SELECT strftime('%Y-W%W', creation_time) AS week, COUNT(*) AS defect_count, SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) AS closed_count, ROUND(100.0 * SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS close_rate FROM "octane_defects"  WHERE (LOWER(CAST(author AS TEXT)) LIKE LOWER('%G70%') OR LOWER(CAST(detected_by AS TEXT)) LIKE LOWER('%G70%') OR LOWER(CAST(owner AS TEXT)) LIKE LOWER('%G70%') OR LOWER(CAST(team AS TEXT)) LIKE LOWER('%G70%') OR LOWER(CAST(name AS TEXT)) LIKE LOWER('%G70%')) AND creation_time IS NOT NULL GROUP BY week ORDER BY week DESC LIMIT 16
```

## Case 9

- Question: 请看NA6高风险缺陷周趋势
- Table: octane_defects
- Success: True
- RowCount: 16
- Rules: 12
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_test_week_definition | test_week 时间桶定义
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_classification_and_domain_extraction | classification/domain 提取口径
  - - br_risk_analysis_coverage_formula | Risk Analysis 覆盖率口径
  - - br_risk_analysis_level_threshold | Risk Level 分层阈值
  - - br_test_status_normalization | Test Status 归一化口径
  - - br_test_frequency_pass_rate_definition | Test Frequency 与 Pass Rate 口径

SQL:

```sql
SELECT strftime('%Y-W%W', creation_time) AS week, COUNT(*) AS defect_count, SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) AS closed_count, ROUND(100.0 * SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS close_rate FROM "octane_defects"  WHERE (LOWER(CAST(author AS TEXT)) LIKE LOWER('%NA6%') OR LOWER(CAST(detected_by AS TEXT)) LIKE LOWER('%NA6%') OR LOWER(CAST(owner AS TEXT)) LIKE LOWER('%NA6%') OR LOWER(CAST(team AS TEXT)) LIKE LOWER('%NA6%') OR LOWER(CAST(name AS TEXT)) LIKE LOWER('%NA6%')) AND creation_time IS NOT NULL GROUP BY week ORDER BY week DESC LIMIT 16
```

## Case 10

- Question: 请分析测试覆盖率和高风险AIDA并给改进建议
- Table: octane_manual_runs
- Success: True
- RowCount: 20
- Rules: 12
  - - br_risk_analysis_coverage_formula | Risk Analysis 覆盖率口径
  - - br_classification_and_domain_extraction | classification/domain 提取口径
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_test_week_definition | test_week 时间桶定义
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_risk_analysis_level_threshold | Risk Level 分层阈值
  - - br_test_status_normalization | Test Status 归一化口径
  - - br_test_frequency_pass_rate_definition | Test Frequency 与 Pass Rate 口径

SQL:

```sql
SELECT strftime('%Y-W%W', creation_time) AS week, COUNT(*) AS run_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('passed','pass') OR LOWER(CAST(status AS TEXT)) LIKE 'pass%') THEN 1 ELSE 0 END) AS passed_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('failed','failure') OR LOWER(CAST(status AS TEXT)) LIKE 'fail%') THEN 1 ELSE 0 END) AS failed_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('blocked','requires attention','requires_attention','attention required') OR LOWER(CAST(status AS TEXT)) LIKE '%block%' OR LOWER(CAST(status AS TEXT)) LIKE '%require%attention%' OR LOWER(CAST(status AS TEXT)) LIKE '%attention required%') THEN 1 ELSE 0 END) AS blocked_count, ROUND(100.0 * SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('passed','pass') OR LOWER(CAST(status AS TEXT)) LIKE 'pass%') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS pass_rate FROM "octane_manual_runs"  GROUP BY strftime('%Y-W%W', creation_time) ORDER BY week DESC LIMIT 20
```

## Case 11

- Question: 请看DTSV团队测试通过率趋势并给建议
- Table: octane_manual_runs
- Success: True
- RowCount: 20
- Rules: 12
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_test_week_definition | test_week 时间桶定义
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_classification_and_domain_extraction | classification/domain 提取口径
  - - br_risk_analysis_coverage_formula | Risk Analysis 覆盖率口径
  - - br_risk_analysis_level_threshold | Risk Level 分层阈值
  - - br_test_status_normalization | Test Status 归一化口径
  - - br_test_frequency_pass_rate_definition | Test Frequency 与 Pass Rate 口径

SQL:

```sql
SELECT strftime('%Y-W%W', creation_time) AS week, COUNT(*) AS run_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('passed','pass') OR LOWER(CAST(status AS TEXT)) LIKE 'pass%') THEN 1 ELSE 0 END) AS passed_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('failed','failure') OR LOWER(CAST(status AS TEXT)) LIKE 'fail%') THEN 1 ELSE 0 END) AS failed_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('blocked','requires attention','requires_attention','attention required') OR LOWER(CAST(status AS TEXT)) LIKE '%block%' OR LOWER(CAST(status AS TEXT)) LIKE '%require%attention%' OR LOWER(CAST(status AS TEXT)) LIKE '%attention required%') THEN 1 ELSE 0 END) AS blocked_count, ROUND(100.0 * SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('passed','pass') OR LOWER(CAST(status AS TEXT)) LIKE 'pass%') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS pass_rate FROM "octane_manual_runs"  WHERE (LOWER(CAST(run_by AS TEXT)) LIKE LOWER('%DTSV%') OR LOWER(CAST(author AS TEXT)) LIKE LOWER('%DTSV%') OR LOWER(CAST(name AS TEXT)) LIKE LOWER('%DTSV%') OR LOWER(CAST(test_name AS TEXT)) LIKE LOWER('%DTSV%') OR LOWER(CAST(test_id AS TEXT)) LIKE LOWER('%DTSV%')) GROUP BY strftime('%Y-W%W', creation_time) ORDER BY week DESC LIMIT 20
```

## Case 12

- Question: 请看执行状态中Blocked和Failed周趋势
- Table: octane_manual_runs
- Success: True
- RowCount: 20
- Rules: 12
  - - br_test_status_normalization | Test Status 归一化口径
  - - br_test_week_status_priority | 同周状态优先级口径
  - - br_status_field_priority_extraction | 缺陷状态字段优先级口径
  - - br_test_week_definition | test_week 时间桶定义
  - - br_year_inference_from_test_week | 年份推断与周排序口径
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_classification_and_domain_extraction | classification/domain 提取口径

SQL:

```sql
SELECT strftime('%Y-W%W', creation_time) AS week, COUNT(*) AS run_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('passed','pass') OR LOWER(CAST(status AS TEXT)) LIKE 'pass%') THEN 1 ELSE 0 END) AS passed_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('failed','failure') OR LOWER(CAST(status AS TEXT)) LIKE 'fail%') THEN 1 ELSE 0 END) AS failed_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('blocked','requires attention','requires_attention','attention required') OR LOWER(CAST(status AS TEXT)) LIKE '%block%' OR LOWER(CAST(status AS TEXT)) LIKE '%require%attention%' OR LOWER(CAST(status AS TEXT)) LIKE '%attention required%') THEN 1 ELSE 0 END) AS blocked_count, ROUND(100.0 * SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('passed','pass') OR LOWER(CAST(status AS TEXT)) LIKE 'pass%') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS pass_rate FROM "octane_manual_runs"  GROUP BY strftime('%Y-W%W', creation_time) ORDER BY week DESC LIMIT 20
```

## Case 13

- Question: 所有测试人员测试用例执行情况
- Table: octane_manual_runs
- Success: True
- RowCount: 1
- Rules: 12
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_test_week_definition | test_week 时间桶定义
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_classification_and_domain_extraction | classification/domain 提取口径
  - - br_risk_analysis_coverage_formula | Risk Analysis 覆盖率口径
  - - br_risk_analysis_level_threshold | Risk Level 分层阈值
  - - br_test_status_normalization | Test Status 归一化口径
  - - br_test_frequency_pass_rate_definition | Test Frequency 与 Pass Rate 口径

SQL:

```sql
SELECT COALESCE(NULLIF(TRIM(CAST(run_by AS TEXT)), ''), '未标注') AS tester, COUNT(DISTINCT NULLIF(TRIM(CAST(test_id AS TEXT)), '')) AS testcase_count, COUNT(*) AS run_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('passed','pass') OR LOWER(CAST(status AS TEXT)) LIKE 'pass%') THEN 1 ELSE 0 END) AS passed_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('failed','failure') OR LOWER(CAST(status AS TEXT)) LIKE 'fail%') THEN 1 ELSE 0 END) AS failed_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('blocked','requires attention','requires_attention','attention required') OR LOWER(CAST(status AS TEXT)) LIKE '%block%' OR LOWER(CAST(status AS TEXT)) LIKE '%require%attention%' OR LOWER(CAST(status AS TEXT)) LIKE '%attention required%') THEN 1 ELSE 0 END) AS blocked_count, ROUND(100.0 * SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('passed','pass') OR LOWER(CAST(status AS TEXT)) LIKE 'pass%') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS pass_rate FROM "octane_manual_runs"  GROUP BY 1 ORDER BY run_count DESC, pass_rate DESC LIMIT 30
```

## Case 14

- Question: please summarize test cases execution
- Table: octane_manual_runs
- Success: True
- RowCount: 20
- Rules: 12
  - - br_test_frequency_pass_rate_definition | Test Frequency 与 Pass Rate 口径
  - - br_test_status_normalization | Test Status 归一化口径
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_test_week_definition | test_week 时间桶定义
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_classification_and_domain_extraction | classification/domain 提取口径
  - - br_risk_analysis_coverage_formula | Risk Analysis 覆盖率口径
  - - br_risk_analysis_level_threshold | Risk Level 分层阈值

SQL:

```sql
SELECT strftime('%Y-W%W', creation_time) AS week, COUNT(*) AS run_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('passed','pass') OR LOWER(CAST(status AS TEXT)) LIKE 'pass%') THEN 1 ELSE 0 END) AS passed_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('failed','failure') OR LOWER(CAST(status AS TEXT)) LIKE 'fail%') THEN 1 ELSE 0 END) AS failed_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('blocked','requires attention','requires_attention','attention required') OR LOWER(CAST(status AS TEXT)) LIKE '%block%' OR LOWER(CAST(status AS TEXT)) LIKE '%require%attention%' OR LOWER(CAST(status AS TEXT)) LIKE '%attention required%') THEN 1 ELSE 0 END) AS blocked_count, ROUND(100.0 * SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('passed','pass') OR LOWER(CAST(status AS TEXT)) LIKE 'pass%') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS pass_rate FROM "octane_manual_runs"  GROUP BY strftime('%Y-W%W', creation_time) ORDER BY week DESC LIMIT 20
```

## Case 15

- Question: 请比较Passed与Failed周变化
- Table: octane_manual_runs
- Success: True
- RowCount: 20
- Rules: 12
  - - br_test_status_normalization | Test Status 归一化口径
  - - br_test_week_status_priority | 同周状态优先级口径
  - - br_status_field_priority_extraction | 缺陷状态字段优先级口径
  - - br_year_inference_from_test_week | 年份推断与周排序口径
  - - br_test_frequency_pass_rate_definition | Test Frequency 与 Pass Rate 口径
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_test_week_definition | test_week 时间桶定义
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询

SQL:

```sql
SELECT strftime('%Y-W%W', creation_time) AS week, COUNT(*) AS run_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('passed','pass') OR LOWER(CAST(status AS TEXT)) LIKE 'pass%') THEN 1 ELSE 0 END) AS passed_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('failed','failure') OR LOWER(CAST(status AS TEXT)) LIKE 'fail%') THEN 1 ELSE 0 END) AS failed_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('blocked','requires attention','requires_attention','attention required') OR LOWER(CAST(status AS TEXT)) LIKE '%block%' OR LOWER(CAST(status AS TEXT)) LIKE '%require%attention%' OR LOWER(CAST(status AS TEXT)) LIKE '%attention required%') THEN 1 ELSE 0 END) AS blocked_count, ROUND(100.0 * SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('passed','pass') OR LOWER(CAST(status AS TEXT)) LIKE 'pass%') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS pass_rate FROM "octane_manual_runs"  GROUP BY strftime('%Y-W%W', creation_time) ORDER BY week DESC LIMIT 20
```

## Case 16

- Question: 请看requires attention趋势
- Table: octane_manual_runs
- Success: True
- RowCount: 20
- Rules: 12
  - - br_test_status_normalization | Test Status 归一化口径
  - - br_test_week_status_priority | 同周状态优先级口径
  - - br_status_field_priority_extraction | 缺陷状态字段优先级口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_year_inference_from_test_week | 年份推断与周排序口径
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_test_week_definition | test_week 时间桶定义
  - - br_classification_and_domain_extraction | classification/domain 提取口径

SQL:

```sql
SELECT strftime('%Y-W%W', creation_time) AS week, COUNT(*) AS run_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('passed','pass') OR LOWER(CAST(status AS TEXT)) LIKE 'pass%') THEN 1 ELSE 0 END) AS passed_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('failed','failure') OR LOWER(CAST(status AS TEXT)) LIKE 'fail%') THEN 1 ELSE 0 END) AS failed_count, SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('blocked','requires attention','requires_attention','attention required') OR LOWER(CAST(status AS TEXT)) LIKE '%block%' OR LOWER(CAST(status AS TEXT)) LIKE '%require%attention%' OR LOWER(CAST(status AS TEXT)) LIKE '%attention required%') THEN 1 ELSE 0 END) AS blocked_count, ROUND(100.0 * SUM(CASE WHEN (LOWER(CAST(status AS TEXT)) IN ('passed','pass') OR LOWER(CAST(status AS TEXT)) LIKE 'pass%') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS pass_rate FROM "octane_manual_runs"  GROUP BY strftime('%Y-W%W', creation_time) ORDER BY week DESC LIMIT 20
```

## Case 17

- Question: 状态变更记录
- Table: octane_defect_histories
- Success: True
- RowCount: 120
- Rules: 12
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_test_week_definition | test_week 时间桶定义
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_classification_and_domain_extraction | classification/domain 提取口径
  - - br_risk_analysis_coverage_formula | Risk Analysis 覆盖率口径
  - - br_risk_analysis_level_threshold | Risk Level 分层阈值
  - - br_test_status_normalization | Test Status 归一化口径
  - - br_test_frequency_pass_rate_definition | Test Frequency 与 Pass Rate 口径

SQL:

```sql
SELECT defect_id, team, total_count, fetched_at FROM "octane_defect_histories" ORDER BY COALESCE(total_count, 0) DESC, fetched_at DESC LIMIT 120
```

## Case 18

- Question: 请看AIDA维度缺陷状态分布
- Table: octane_defects
- Success: True
- RowCount: 20
- Rules: 12
  - - br_risk_analysis_coverage_formula | Risk Analysis 覆盖率口径
  - - br_classification_and_domain_extraction | classification/domain 提取口径
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_test_week_definition | test_week 时间桶定义
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_risk_analysis_level_threshold | Risk Level 分层阈值
  - - br_test_status_normalization | Test Status 归一化口径
  - - br_test_frequency_pass_rate_definition | Test Frequency 与 Pass Rate 口径

SQL:

```sql
SELECT COALESCE(NULLIF(TRIM(CAST(aida_english AS TEXT)), ''), '未标注') AS aida, COUNT(*) AS defect_count FROM "octane_defects"  GROUP BY 1 ORDER BY defect_count DESC LIMIT 20
```

## Case 19

- Question: 请给出当前数据库里最需要优先处理的问题趋势
- Table: octane_defects
- Success: True
- RowCount: 16
- Rules: 12
  - - br_defect_critical_classification_default | Critical Issue Severity Definition
  - - br_field_mapping_defect_core | Defect 字段映射口径
  - - br_matrix_extraction_and_order | Matrix 提取与排序
  - - br_topissue_risk_score_non_linear | TopIssue 风险分非线性算法
  - - br_test_week_definition | test_week 时间桶定义
  - - br_tester_intent_resolution | 提票人/测试员语义口径
  - - br_analysis_intent_fallback | 趋势/效率/建议问题降级查询
  - - br_classification_and_domain_extraction | classification/domain 提取口径
  - - br_risk_analysis_coverage_formula | Risk Analysis 覆盖率口径
  - - br_risk_analysis_level_threshold | Risk Level 分层阈值
  - - br_test_status_normalization | Test Status 归一化口径
  - - br_test_frequency_pass_rate_definition | Test Frequency 与 Pass Rate 口径

SQL:

```sql
SELECT strftime('%Y-W%W', creation_time) AS week, COUNT(*) AS defect_count, SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) AS closed_count, ROUND(100.0 * SUM(CASE WHEN (LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%conclud%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%resolv%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%clos%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%fix%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%complet%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已关闭%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已解决%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%已修复%' OR LOWER(CAST(COALESCE(phase, status_phase) AS TEXT)) LIKE '%结案%') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS close_rate FROM "octane_defects"  WHERE creation_time IS NOT NULL GROUP BY week ORDER BY week DESC LIMIT 16
```

