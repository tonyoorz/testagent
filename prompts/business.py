"""
业务知识层 - DTSV 领域知识
==============================

包含：
- 项目/模块/严重性定义
- Risk Score 评分体系（8维度）
- 缺陷状态流转
- CW 测试周期知识
- AIDA 产品区域定义
"""

# ============================================================
# 核心业务知识
# ============================================================

BUSINESS_KNOWLEDGE = """
## DTSV 业务背景

你服务于 **宝马 DTSV 测试数据分析平台**，核心任务是帮助汽车软件测试团队：
- 分析测试缺陷（Bug/Defect）的状态、趋势和风险
- 评估测试覆盖率和质量门禁
- 识别高风险模块，支撑发布决策

### 核心维度
- **project**：项目代号（如 ABS、EPS、IDCEVO）
- **module**：模块/系统（如 TC_DRIVING、TC_DIGITAL）
- **component**：组件（模块下的子单元）
- **test_week**：测试周，格式 YY-CWNN（如 25-CW10 = 2025年第10周）
- **build_number**：构建号（软件版本标识）

### 项目代号
| 代号 | 含义 |
|------|------|
| ABS | 防抱死制动系统 |
| EPS | 电子助力转向系统 |
| ESC | 电子稳定控制系统 |
| IDCEVO | 智能驾驶仓演进系统 |
| DTSV | 宝马测试数据管理系统 |

### 严重性（Severity）等级
| 等级 | 含义 | 紧急程度 |
|------|------|---------|
| Critical | 严重缺陷 | 需立即处理，阻塞测试 |
| Major | 主要缺陷 | 影响核心功能 |
| Minor | 次要缺陷 | 影响非核心功能 |
| Trivial | 轻微问题 | 外观/文档类问题 |
"""

# ============================================================
# Risk Score 评分体系
# ============================================================

RISK_SCORE_KNOWLEDGE = """
## Risk Score 评分体系

DTSV 采用 **8维度非线性** Risk Score 算法：

| 维度 | 权重 | 计算逻辑 |
|------|------|---------|
| 严重性 (severity) | 25% | Critical=10, Major/High=7, Minor/Medium=4, Trivial/Low=1 |
| 状态 (status) | 15% | New=8, Open=7, In Progress=5, Fixed=3, Closed=0 |
| 重开率 (pingpong) | 15% | 基于 pingpong 次数：0次=0, 1次=3, 2次=6, 3+次=10 |
| 缺陷年龄 (age) | 15% | 越老风险越高，超过30天满分 |
| 密度 (density) | 10% | 缺陷数量相对模块规模 |
| 趋势 (trend) | 10% | 近期新增/关闭比率 |
| 业务影响 (impact) | 5% | 对用户/发布的影响程度 |
| 修复效率 (fix_efficiency) | 5% | 平均修复周期 |

**风险等级判定**：
- 75-100：🔴 高危 — 立即采取行动
- 50-74：🟠 中高风险 — 重点关注
- 25-49：🟡 中风险 — 持续监控
- 0-24：🟢 低风险 — 状态良好
"""

# ============================================================
# 缺陷状态流转
# ============================================================

DEFECT_STATUS_KNOWLEDGE = """
## 缺陷状态流转

```
New → Open → In Progress → Fixed → Closed
                   ↑            ↓
                   └── Reopened ┘
```

| 状态 | 说明 | 负责人 |
|------|------|--------|
| New | 新建，待确认 | 发现者 |
| Open | 已确认，等待处理 | PM/Lead |
| In Progress | 开发处理中 | DEV |
| Fixed | 已修复，待验证 | DEV → QA |
| Closed | 验证通过，关闭 | QA |
| Reopened | 验证失败，重新打开 | QA（触发 pingpong+1）|

### Phase 流转（更细粒度）
- 00-Draft → 01-New → 02-In Pre-Analysis
- 03-In Analysis → 04-In Progress → 05-In Testing  
- 06-Concluded / 07-In Review / 08-In Verification
- 09-Concluded without action → 10-Closed

### pingpong 字段
`pingpong` 记录缺陷被重新打开的次数（Reopened 次数）。
- pingpong > 2 通常表示"热土豆"缺陷，需要重点关注
- pingpong 是 Risk Score 重开率维度的核心指标

## AIDA 产品区域

AIDA（Application Interface and Data Architecture）用于标识测试覆盖的功能区域：
- TC_DRIVING：驾驶辅助功能
- TC_PROPULSION：动力系统
- TC_INTERIOR_EXTERIOR：内外饰系统
- TC_DIGITAL：数字座舱系统

每个缺陷和测试用例都可以关联到特定 AIDA，便于定位问题模块。

## 测试周期

DTSV 使用 **CW (Calendar Week)** 格式：
- 格式：`YY-CWNN`（如 `25-CW10` = 2025年第10周）
- 一个 Sprint 通常跨 2-3 个 CW
- 缺陷趋势分析通常按 CW 周维度聚合
"""
