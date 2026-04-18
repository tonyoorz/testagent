# P1+P2 实施 Prompt

## P1：TestStrategyEvaluator + TestMaturityScore

### TestStrategyEvaluator（测试策略评估编排层）

创建 agent/tools/analysis/strategy_evaluator.py

这是一个**编排层工具**，把已有的5个深度分析模块串联起来，生成综合测试策略评估。

核心逻辑：
```python
class TestStrategyEvaluator:
    def evaluate(self, df, question, context):
        # 1. risk_heatmap → 哪些模块风险最高
        # 2. test_case_recommender → 高风险区域的覆盖够不够
        # 3. association_anomaly_discoverer → ECU乒乓/缺陷集中信号
        # 4. anomaly_detector → 近期恶化趋势
        # 5. 综合评分 + 建议输出
```

输出格式：
```
## 测试策略评估报告

### 总体评分: B (72/100)
- 风险控制: C (65分) — ICAS1, ADAS 风险偏高
- 覆盖充分性: B (78分) — 核心模块覆盖OK，边界场景不足
- 修复效率: A (85分) — 平均修复3.2天，优于基准
- 趋势健康度: B- (70分) — 近2周缺陷上升15%

### 关键发现
1. ICAS1 风险最高(87分)，测试用例只覆盖核心场景62%
2. 近2周缺陷上升35%，ECU乒乓率偏高(12%)
3. ADAS 功能域边界用例缺失

### 建议行动
1. 🔴 补充 ADAS 功能域边界用例 (优先级最高)
2. 🟡 重点关注 ICAS1↔ADAS 关联缺陷
3. 🟢 安排回归验证近期修复
```

### TestMaturityScore（测试成熟度评分）

创建 agent/core/test_maturity.py

量化指标，一个函数计算整体成熟度：

```python
def calculate_maturity(df) -> MaturityReport:
    scores = {
        "defect_detection_rate": ...,  # 缺陷数/测试用例数
        "severity_distribution": ...,  # Critical占比是否合理
        "close_rate": ...,             # 已关闭/总数
        "avg_fix_time": ...,           # 平均修复周期
        "pingpong_rate": ...,          # 反复开关的缺陷占比
        "coverage_uniformity": ...,    # 各模块覆盖是否均衡
        "trend_direction": ...,        # 整体在变好还是变差
    }
    # 加权平均 → 总分 0-100
    # 等级: A(90+), B(75-89), C(60-74), D(45-59), F(<45)
```

每个维度要有基准值（benchmark），让评分有参照系。

## P2：PredictiveRisk（风险预判）

创建 agent/tools/analysis/predictive_risk.py

基于当前数据的趋势外推：

```python
class PredictiveRiskAnalyzer:
    def predict(self, df, horizon_days=30):
        # 1. 各模块缺陷趋势外推（线性回归简单版）
        # 2. 识别加速恶化模块
        # 3. ECU乒乓未收敛列表
        # 4. 输出：预计下月新增缺陷数 + 高风险模块清单 + 预警
```

输出：
```
## 风险预判 (未来30天)

### 预计新增缺陷: ~45个 (置信度72%)
- ICAS1: +18个 (趋势加速 ⚠️)
- ADAS: +12个
- Connectivity: +8个
- 其他: +7个

### 预警
🔴 ICAS1 缺陷增速加快，如不干预可能触发 showstopper
🟡 ADAS 区域修复周期拉长(5.2天→7.8天)

### 建议干预
1. ICAS1: 安排专项测试，覆盖近期新增功能
2. ADAS: 增加开发资源，缩短修复周期
```

## 集成要求
- strategy_evaluator 和 predictive_risk 注册为 Tool
- 添加到 semantic_intent_detector 的意图（strategy, predict, 预测, 预判, 未来）
- 添加到 harness_router 的 _ADVANCED_KEYWORDS
- TestMaturityScore 可被 strategy_evaluator 调用，也可独立使用
