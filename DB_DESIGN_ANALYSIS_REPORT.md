# Testagent 数据库设计分析报告

> 生成时间：2026-03-22  
> 执行方式：OpenClaw Mission Control Center 多 Agent 协作  
> 参与 Agent：PM-Agent（业务）、DEV-Agent（技术）、QA-Agent（质量）、Coordinator（整合）

---

## 一、整体架构总结

Testagent 采用**核心明细表 + 预聚合表**的混合架构，使用5张表支撑汽车软件测试的完整业务流程：test_runs（测试执行主表）、test_results（测试步骤明细）、defects（缺陷管理）、test_coverage（覆盖率聚合）、defect_trends（缺陷趋势聚合）。设计遵循维度建模思想，以 project、module、component、test_week 四维度贯穿全局，采用实用主义策略平衡性能与灵活性（仅 test_results 启用外键、JSON字段扩展），整体评分 **6.7/10**，适合中小团队快速迭代场景。

---

## 二、ER 关系图

```
┌─────────────────┐
│   test_runs     │  测试执行主表
│  (测试执行记录)  │
├─────────────────┤
│ run_id (PK)     │
│ project, module │
│ test_week       │
│ build_number    │
│ tester, status  │
└────────┬────────┘
         │ 1:N（硬外键）
         ↓
┌─────────────────┐
│  test_results   │  测试步骤明细
│ (测试步骤结果)  │
├─────────────────┤
│ id (PK)         │
│ run_id (FK)  ←──┼── 唯一硬外键
│ test_case_name  │
│ step_number     │
│ status          │
└─────────────────┘

         (通过 build_number/project 软关联)
         ↓
┌─────────────────┐
│    defects      │  缺陷管理
│   (缺陷记录)    │
├─────────────────┤
│ defect_id (PK)  │
│ severity, priority│
│ detected_by     │
│ project, module │
│ creation_time   │
│ pingpong (流转) │  ← 亮点字段
└─────────────────┘

         (聚合关系，无直接外键)
         ↓                          ↓
┌─────────────────┐    ┌─────────────────┐
│ test_coverage   │    │ defect_trends   │
│  (覆盖率聚合)   │    │  (缺陷趋势聚合) │
├─────────────────┤    ├─────────────────┤
│ module          │    │ project, module │
│ component       │    │ test_week       │
│ coverage_percent│    │ new_defects     │
│ test_week       │    │ open_defects    │
│ UNIQUE(module,  │    │ UNIQUE(project, │
│  component,     │    │  module,        │
│  test_week)     │    │  test_week)     │
└─────────────────┘    └─────────────────┘
```

---

## 三、各表核心用途

| 表名 | 类型 | 核心用途 | 关键索引/约束 |
|------|------|----------|---------------|
| **test_runs** | 明细表 | 每次测试执行的完整生命周期（人员、时间、环境、结果） | run_id UNIQUE; idx: status, project, tester, test_week, module |
| **test_results** | 明细表 | 步骤级执行结果，支持失败根因精确定位 | run_id→test_runs(FK); idx: run_id, status |
| **defects** | 明细表 | 缺陷从发现到关闭的全生命周期管理（26字段） | defect_id UNIQUE; idx: severity, status, project, creation_time |
| **test_coverage** | 聚合表 | 模块/组件维度的测试覆盖情况，提升报表性能 | UNIQUE(module, component, test_week); idx: module, test_week |
| **defect_trends** | 聚合表 | 缺陷数量趋势和严重度分布，支持质量监控 | UNIQUE(project, module, test_week); idx: project, test_week |

---

## 四、设计亮点

1. **四维度贯穿设计**：project、module、component、test_week 四维度贯穿全局，支持多维交叉分析，为复杂看板奠定基础。

2. **预聚合表解决性能瓶颈**：test_coverage 和 defect_trends 作为预聚合表，有效解决明细表数据增长后的报表性能问题，体现前瞻性设计。

3. **实用主义权衡**：仅 test_results 启用外键，其他表采用软关联；JSON 字段（tags/aidas/metadata）支持快速迭代，灵活性与约束取得平衡。

4. **pingpong 字段**：缺陷重开次数追踪，可识别"热土豆"缺陷，评估团队协作效率，是最有业务价值的亮点字段。

5. **幂等写入设计**：test_coverage 和 defect_trends 使用 UNIQUE 约束实现幂等写入，支持定时同步多次运行不产生重复数据。

---

## 五、改进建议

### 🔴 P0（立即修复）

| # | 问题 | 修复方案 | 影响 |
|---|------|----------|------|
| P0-1 | 外键约束默认未启用 | 应用启动执行 `PRAGMA foreign_keys = ON;` | 防止孤儿数据 |
| P0-2 | 业务必需字段允许 NULL | test_runs（test_name/status/result/tester/project）、defects（title/severity/status/detected_by）加 NOT NULL | 防止脏数据 |
| P0-3 | 缺少枚举值约束 | 添加 CHECK 约束：status、severity 等枚举字段 | 防止状态不一致 |
| P0-4 | 聚合表未自动同步 | 建立触发器或定时任务，从明细表同步到 test_coverage/defect_trends | 修复功能缺失 |
| P0-5 | test_runs 与 defects 无关联 | defects 表添加 `detected_in_test_run_id` 外键字段 | 提升根因追溯性 |

### 🟡 P1（近期优化）

| # | 问题 | 优化方案 | 收益 |
|---|------|----------|------|
| P1-1 | JSON 字段查询性能差 | 为 tags/aidas/metadata 创建生成列索引 | 提升查询速度 |
| P1-2 | 缺少操作人员审计 | 所有表添加 created_by/updated_by | 支持责任追溯 |
| P1-3 | 复合索引缺失 | 添加 (project, test_week)、(module, component, status) 等 | 优化常用查询 |
| P1-4 | WAL 模式未启用 | `PRAGMA journal_mode = WAL;` | 提升并发性能 |
| P1-5 | defects 表偏宽（26字段）| 评估拆分扩展字段到子表 | 提升可维护性 |
| P1-6 | pingpong 语义不直观 | 重命名为 `reassignment_count` 或加注释 | 降低认知成本 |

### 🟢 P2（长期改进）

| # | 问题 | 改进方案 | 价值 |
|---|------|----------|------|
| P2-1 | 缺少测试用例库表 | 新增 test_cases 表，支持用例版本管理 | 完善业务流程 |
| P2-2 | 缺少回归测试集管理 | 新增 regression_sets 表 | 提升测试效率 |
| P2-3 | 缺少发布决策支持 | 新增 release_criteria 质量门禁表 | 支持发布管理 |
| P2-4 | ASPICE 合规性不明确 | 规范 aidas/phase/classification 字段语义 | 满足行业要求 |
| P2-5 | 历史数据无归档策略 | 建立归档表和定期清理机制 | 控制数据库规模 |

---

## 附录：快速修复 SQL

```sql
-- P0-1: 启用外键（每次连接都需执行）
PRAGMA foreign_keys = ON;

-- P1-4: 启用 WAL 模式（一次性）
PRAGMA journal_mode = WAL;

-- P0-3: 添加状态枚举约束（示例）
-- SQLite 不支持 ALTER TABLE ADD CHECK，需重建表
-- 建议在应用层校验：
-- status IN ('pending', 'running', 'completed', 'failed', 'blocked')
-- severity IN ('Critical', 'Major', 'Minor', 'Trivial')

-- P0-5: 添加 test_runs 与 defects 关联
ALTER TABLE defects ADD COLUMN detected_in_test_run_id TEXT 
    REFERENCES test_runs(run_id) ON DELETE SET NULL;

-- P1-1: JSON 字段生成列索引（示例）
-- SQLite 3.31+ 支持生成列
ALTER TABLE defects ADD COLUMN severity_cached TEXT
    GENERATED ALWAYS AS (json_extract(metadata, '$.severity')) STORED;
CREATE INDEX idx_defects_severity_cached ON defects(severity_cached);
```

---

**综合评分：** 6.7/10  
**适用场景：** 中小团队快速迭代，汽车软件测试管理（BMW DTSV）  
**报告版本：** v1.0 - 2026-03-22
