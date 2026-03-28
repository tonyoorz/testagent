# 数据分析 Agent 能力差距分析

**项目**: TestAgent - 车载软件缺陷管理智能 Agent
**目标**: 强大的数据分析 Agent，真正理解业务数据
**分析日期**: 2026-03-28

---

## 🎯 评估维度：Agent 的核心能力

| 能力维度 | 当前评分 | 说明 |
|---------|---------|------|
| **业务理解** | ⭐⭐⭐⭐ | 业务规则已定义，但深度不够 |
| **自然语言理解** | ⭐⭐⭐ | 基本问题能理解，复杂问题困难 |
| **SQL 生成准确性** | ⭐⭐⭐ | 依赖 LLM，复杂查询有误差 |
| **数据洞察** | ⭐⭐ | 有基础统计，缺少深度洞察 |
| **上下文记忆** | ⭐⭐⭐ | 基础记忆，缺少长期记忆 |
| **可视化** | ⭐⭐⭐⭐⭐ | 丰富的图表，可视化能力强 |
| **智能路由** | ⭐⭐ | 简单关键词匹配，不够智能 |
| **建议能力** | ⭐⭐ | 能回答问题，但主动建议弱 |
| **数据验证** | ⭐⭐ | 有基本验证，缺少异常检测 |
| **连续对话** | ⭐⭐⭐ | 能记住近期上下文 |

**总体评分**: ⭐⭐⭐ (3/5) - **良好，但有很大提升空间**

---

## 🔴 核心差距分析

### 1. 业务理解深度不足

#### 当前状态
✅ **已有的业务知识**：
- `business_rules.py` - 定义了 TopIssue、High Runner、Long Runner 等规则
- `schema_description.md` - 完整的数据库结构
- `fewshot_examples.md` - 20 个查询示例

❌ **存在的问题**：
- 业务规则是**静态的**，无法动态调整
- 缺少**因果关系分析**（例如：为什么这个是 TopIssue？）
- 缺少**业务语义理解**（例如："最近" vs "上周" vs "本月"）
- 缺少**行业知识**（例如：车载软件开发的特殊流程）

#### 举例说明

**用户问题**：
> "为什么这个缺陷是 TopIssue？"

**当前回答**：
```
根据 TopIssue 评分系统，这个缺陷的风险评分为 145 分，超过了 60 分的阈值，所以是 TopIssue。
```

**理想回答**（应该包含）：
```
这个缺陷是 TopIssue，原因如下：

1. **高严重性** (Matrix-1A, 30分)
   - 这是最高级别的严重性，需要立即关注

2. **频繁转移** (ECU 转移 5 次, 24分)
   - 这个缺陷在 IuK_HU 和 DIPS_HU 之间来回转移了 5 次
   - 可能是两个团队对问题理解不一致，导致责任推诿

3. **长期未解决** (处理周期 45 天, 18分)
   - 已经 45 天未解决，严重影响了项目进度

4. **主票影响** (主票有 3 个子票, 17分)
   - 这个主票有 3 个子票，说明问题影响范围广

**业务洞察**：
这是一个典型的"跨团队协作问题"。问题可能在 IuK_HU 和 DIPS_HU 之间反复转移，建议：
- 召开跨团队会议，统一对问题的理解
- 指定一个负责人，避免责任推诿
- 检查相关联的子票，是否有共性
```

#### 改进方案

**步骤 1: 增强业务规则解释**

在 `business_rules.py` 中添加：

```python
class BusinessRuleExplainer:
    """业务规则解释器"""
    
    def explain_top_issue(self, defect: Dict) -> str:
        """解释为什么是 TopIssue"""
        reasons = []
        
        # 1. Matrix 严重性
        if 'matrix' in defect:
            matrix = defect['matrix']
            severity_score = self._calculate_matrix_score(matrix)
            if severity_score > 20:
                reasons.append(
                    f"**高严重性** (Matrix-{matrix[-1]}, {severity_score}分)\n"
                    f"   - 这是{'最高' if severity_score >= 28 else '较高'}级别的严重性"
                )
        
        # 2. ECU 转移
        if 'ecu_no_of_changes' in defect and defect['ecu_no_of_changes'] >= 3:
            transfers = defect['ecu_no_of_changes']
            score = self._calculate_transfer_score(transfers)
            reasons.append(
                f"**频繁转移** (ECU 转移 {transfers} 次, {score}分)\n"
                f"   - 问题在 {', '.join(self._get_ecu_path(defect))} 之间转移"
            )
        
        # 3. 处理周期
        if 'processing_cycle_days' in defect:
            days = defect['processing_cycle_days']
            if days >= 30:
                score = self._calculate_cycle_score(days)
                reasons.append(
                    f"**长期未解决** (处理周期 {days} 天, {score}分)\n"
                    f"   - 已经{days}天未解决，严重影响项目进度"
                )
        
        # 4. 主票影响
        if 'parent_child' == 'Parent' and 'child_count' in defect:
            children = defect['child_count']
            if children >= 3:
                score = self._calculate_parent_score(children)
                reasons.append(
                    f"**主票影响** ({children} 个子票, {score}分)\n"
                    f"   - 这个主票有 {children} 个子票，说明问题影响范围广"
                )
        
        # 5. 业务建议
        insights = self._generate_business_insights(defect)
        
        return self._format_explanation(reasons, insights)
    
    def _generate_business_insights(self, defect: Dict) -> List[str]:
        """生成业务洞察"""
        insights = []
        
        # 洞察 1: 跨团队问题
        if defect.get('ecu_no_of_changes', 0) >= 5:
            insights.append(
                "这是一个典型的**跨团队协作问题**。"
                "问题在不同 ECU 之间反复转移，建议："
                "1. 召开跨团队会议，统一对问题的理解"
                "2. 指定一个负责人，避免责任推诿"
            )
        
        # 洞察 2: 新票快速响应
        if defect.get('processing_cycle_days', 0) <= 3:
            insights.append(
                "这是一个**新票**，需要快速响应。"
                "建议："
                "1. 立即分配给相应的 ECU 负责人"
                "2. 制定 24 小时内给出初步分析的计划"
            )
        
        # 洞察 3: Long Runner 风险
        if defect.get('processing_cycle_days', 0) >= 30:
            insights.append(
                "这是一个 **Long Runner**，需要重点关注。"
                "可能原因："
                "1. 问题复杂，技术难度大"
                "2. 资源不足，处理人员被其他问题占用"
                "3. 优先级不够，被低优先级问题阻塞"
            )
        
        return insights
```

**步骤 2: 添加业务语义理解**

在 `chatdb/text_to_sql_agent.py` 中添加：

```python
class BusinessSemantics:
    """业务语义理解"""
    
    TIME_RANGES = {
        '今天': lambda: (datetime.now(), datetime.now()),
        '昨天': lambda: (datetime.now() - timedelta(days=1), datetime.now()),
        '最近3天': lambda: (datetime.now() - timedelta(days=3), datetime.now()),
        '本周': lambda: (self._week_start(), datetime.now()),
        '上周': lambda: (self._week_start() - timedelta(weeks=1), self._week_start()),
        '本月': lambda: (self._month_start(), datetime.now()),
        '上月': lambda: (self._month_start() - timedelta(days=1), self._month_start()),
        '最近一周': lambda: (datetime.now() - timedelta(weeks=1), datetime.now()),
        '最近一月': lambda: (datetime.now() - timedelta(days=30), datetime.now()),
    }
    
    PROJECT_CONTEXT = {
        'App': {
            'focus': '移动应用功能',
            'common_issues': ['导航', '蓝牙', '音频', 'Car Apps'],
            'typical_ecu': 'IuK_HU'
        },
        'IDC': {
            'focus': '互联驾驶功能',
            'common_issues': ['导航', '地图显示', '车机交互'],
            'typical_ecu': 'DIPS_HU'
        },
        'MGU': {
            'focus': '媒体和图形',
            'common_issues': ['音频', '视频', '显示屏'],
            'typical_ecu': 'IuK_HU'
        },
        'RSU': {
            'focus': '远程软件更新',
            'common_issues': ['更新失败', '版本管理'],
            'typical_ecu': 'IuK_HU'
        },
    }
    
    def parse_time_range(self, text: str) -> Optional[Tuple[datetime, datetime]]:
        """解析时间范围"""
        text_lower = text.lower()
        
        for keyword, range_func in self.TIME_RANGES.items():
            if keyword in text_lower:
                start, end = range_func()
                return start, end
        
        return None
    
    def get_project_context(self, project: str) -> Dict:
        """获取项目上下文"""
        return self.PROJECT_CONTEXT.get(project, {})
    
    def expand_query_with_context(self, query: str, project: str = None) -> str:
        """根据上下文扩展查询"""
        expanded_query = query
        
        # 如果用户提到"导航"等关键词，添加相关上下文
        if '导航' in query and project:
            context = self.get_project_context(project)
            if 'common_issues' in context:
                expanded_query += f" (相关功能: {', '.join(context['common_issues'])})"
        
        return expanded_query
```

---

### 2. SQL 生成准确性有待提高

#### 当前状态
✅ **已有的机制**：
- 基于 LangChain 的 SQLDatabaseChain
- Few-shot 示例学习
- 业务规则集成
- 错误重试机制

❌ **存在的问题**：
- **复杂查询准确率低** - 多表 JOIN、子查询容易出错
- **业务术语映射不完整** - 很多业务术语没有对应的 SQL 条件
- **缺少查询优化** - 生成的 SQL 可能效率低
- **缺少自我纠正** - 生成错误的 SQL 后无法自我检测和修正

#### 举例说明

**用户问题**：
> "查询每个项目的 TopIssue 数量，以及平均风险评分"

**理想 SQL**：
```sql
SELECT 
    project,
    COUNT(*) as topissue_count,
    AVG(topissue_risk_score) as avg_risk_score
FROM defects
WHERE is_topissue = 1
GROUP BY project
ORDER BY topissue_count DESC;
```

**可能生成的错误 SQL**（基于当前机制）：
```sql
-- 错误 1: 忘记 WHERE 条件
SELECT 
    project,
    COUNT(*) as topissue_count,
    AVG(topissue_risk_score) as avg_risk_score
FROM defects
GROUP BY project;

-- 错误 2: 分组错误
SELECT 
    project,
    id,
    COUNT(*) as topissue_count,
    AVG(topissue_risk_score) as avg_risk_score
FROM defects
WHERE is_topissue = 1
GROUP BY project;

-- 错误 3: 缺少 ORDER BY
SELECT 
    project,
    COUNT(*) as topissue_count,
    AVG(topissue_risk_score) as avg_risk_score
FROM defects
WHERE is_topissue = 1
GROUP BY project;
```

#### 改进方案

**步骤 1: 增强Few-shot示例**

在 `chatdb/fewshot_examples.md` 中添加更多复杂查询：

```markdown
### 示例 X.1: 多表 JOIN 查询

**用户问题：**
> 查询每个项目的 TopIssue 数量，以及这些 TopIssue 的平均风险评分

**SQL 查询：**
```sql
SELECT 
    d.project,
    COUNT(*) as topissue_count,
    ROUND(AVG(d.topissue_risk_score), 2) as avg_risk_score,
    MAX(d.topissue_risk_score) as max_risk_score
FROM defects d
WHERE d.is_topissue = 1
GROUP BY d.project
ORDER BY topissue_count DESC;
```

**查询说明：**
- 使用 `COUNT(*)` 统计 TopIssue 数量
- 使用 `AVG()` 计算平均风险评分
- 使用 `MAX()` 获取最高风险评分
- `WHERE is_topissue = 1` 筛选 TopIssue
- `GROUP BY project` 按项目分组
- `ORDER BY topissue_count DESC` 按数量降序排序
```

**步骤 2: 添加 SQL 验证和自我纠正**

在 `chatdb/text_to_sql_agent.py` 中添加：

```python
class SQLValidatorAndCorrector:
    """SQL 验证和自我纠正器"""
    
    def validate_and_correct(self, sql: str, question: str) -> str:
        """验证并纠正 SQL"""
        issues = self._detect_issues(sql, question)
        
        if not issues:
            return sql
        
        # 如果有问题，尝试纠正
        corrected_sql = self._correct_sql(sql, question, issues)
        
        # 验证纠正后的 SQL
        if self._validate_syntax(corrected_sql):
            return corrected_sql
        else:
            # 如果纠正失败，使用安全模式
            return self._safe_fallback_sql(question)
    
    def _detect_issues(self, sql: str, question: str) -> List[str]:
        """检测 SQL 问题"""
        issues = []
        
        # 问题 1: 检查是否缺少 WHERE 条件（根据问题判断）
        if 'TopIssue' in question and 'WHERE' not in sql.upper():
            issues.append("缺少 TopIssue 筛选条件")
        
        # 问题 2: 检查 GROUP BY 是否正确
        if '按项目' in question and 'GROUP BY project' not in sql.lower():
            issues.append("缺少 GROUP BY project")
        
        # 问题 3: 检查聚合函数是否正确
        if '平均' in question and 'AVG(' not in sql.upper():
            issues.append("缺少 AVG() 聚合函数")
        
        # 问题 4: 检查排序
        if '降序' in question or '从高到低' in question:
            if 'DESC' not in sql.upper():
                issues.append("缺少 ORDER BY ... DESC")
        
        return issues
    
    def _correct_sql(self, sql: str, question: str, issues: List[str]) -> str:
        """纠正 SQL"""
        corrected_sql = sql
        
        for issue in issues:
            if "缺少 TopIssue 筛选条件" in issue:
                # 添加 WHERE 条件
                if 'WHERE' in corrected_sql.upper():
                    corrected_sql = corrected_sql.replace(
                        'WHERE',
                        'WHERE is_topissue = 1 AND'
                    )
                else:
                    corrected_sql = corrected_sql.replace(
                        'FROM defects',
                        'FROM defects WHERE is_topissue = 1'
                    )
            
            elif "缺少 GROUP BY project" in issue:
                # 添加 GROUP BY
                if 'ORDER BY' in corrected_sql.upper():
                    corrected_sql = corrected_sql.replace(
                        'ORDER BY',
                        'GROUP BY project ORDER BY'
                    )
                else:
                    corrected_sql += ' GROUP BY project'
            
            elif "缺少 AVG() 聚合函数" in issue:
                # 简单的 AVG 纠正（可能需要更复杂的逻辑）
                # 这里需要更智能的推断
                pass
        
        return corrected_sql
```

---

### 3. 数据洞察深度不够

#### 当前状态
✅ **已有的功能**：
- 基础统计（总数、平均值、最大/最小值）
- 趋势分析（缺陷入出流）
- 分类统计（按项目、ECU、严重性）

❌ **缺失的功能**：
- **因果分析** - 为什么会出现这种情况？
- **异常检测** - 哪些数据异常？
- **预测分析** - 未来趋势如何？
- **对比分析** - 与历史数据对比
- **模式识别** - 数据中的隐藏模式

#### 举例说明

**用户问题**：
> "分析最近一个月的缺陷趋势，找出异常点"

**当前回答**：
```
最近一个月的缺陷数量：
- 第1周：50 个
- 第2周：60 个
- 第3周：45 个
- 第4周：55 个
```

**理想回答**：
```
最近一个月的缺陷趋势分析：

📊 整体趋势：
- 总缺陷数：210 个
- 平均每周：52.5 个
- 趋势：相对稳定，有轻微波动

🔍 异常检测发现：

1. **第2周激增异常** (+10 个，+20%)
   - **可能原因**：第2周是新版本发布周
   - **影响**：IDC 项目导航模块缺陷激增
   - **建议**：加强新版本测试，避免类似问题

2. **第3周骤降异常** (-15 个，-25%)
   - **可能原因**：第3周是测试周，测试人员减少
   - **影响**：整体缺陷发现数量下降
   - **建议**：确保测试覆盖率，不要因为测试人员减少而漏测

🎯 模式识别：

**TopIssue 模式**：
- TopIssue 通常是高严重性 (Matrix-1A/1B) + 频繁转移的组合
- 90% 的 TopIssue 至少跨越 2 个 ECU

**High Runner 模式**：
- High Runner 主要集中在 IDC 项目
- 70% 的 High Runner 涉及导航模块

**建议**：
1. 针对第2周的激增，加强 IDC 项目导航模块的回归测试
2. 针对 High Runner，建立跨团队协作机制，减少责任推诿
3. 针对 TopIssue，优先处理 Matrix-1A/1B 且频繁转移的缺陷
```

#### 改进方案

**步骤 1: 添加异常检测**

```python
class AnomalyDetector:
    """异常检测器"""
    
    def detect_trend_anomalies(self, data: pd.DataFrame) -> List[Dict]:
        """检测趋势异常"""
        anomalies = []
        
        # 1. 突增检测（比上周增加 > 50%）
        data['change_pct'] = data['count'].pct_change()
        spike_threshold = 0.5
        
        spikes = data[data['change_pct'] > spike_threshold]
        for _, row in spikes.iterrows():
            anomalies.append({
                'type': 'spike',
                'week': row['week'],
                'value': row['count'],
                'change_pct': row['change_pct'] * 100,
                'severity': 'high' if row['change_pct'] > 1.0 else 'medium'
            })
        
        # 2. 骤降检测（比上周减少 > 30%）
        drops = data[data['change_pct'] < -0.3]
        for _, row in drops.iterrows():
            anomalies.append({
                'type': 'drop',
                'week': row['week'],
                'value': row['count'],
                'change_pct': row['change_pct'] * 100,
                'severity': 'medium'
            })
        
        # 3. 偏离平均值检测（超过平均值的 2 个标准差）
        mean = data['count'].mean()
        std = data['count'].std()
        outliers = data[(data['count'] > mean + 2*std) | (data['count'] < mean - 2*std)]
        
        for _, row in outliers.iterrows():
            anomalies.append({
                'type': 'outlier',
                'week': row['week'],
                'value': row['count'],
                'mean': mean,
                'std': std,
                'deviation': (row['count'] - mean) / std,
                'severity': 'high' if abs((row['count'] - mean) / std) > 3 else 'medium'
            })
        
        return anomalies
```

**步骤 2: 添加因果分析**

```python
class CausalAnalyzer:
    """因果分析器"""
    
    def analyze_causes(self, defects: pd.DataFrame) -> Dict:
        """分析缺陷原因"""
        causes = {}
        
        # 原因 1: 版本发布导致缺陷激增
        # 检查：是否有某个版本发布后，缺陷数量激增
        # 方法：按版本分组，比较版本前后的缺陷数量
        
        # 原因 2: 测试不足导致缺陷遗漏
        # 检查：Long Runner 缺陷中，有多少是在测试阶段应该发现的
        
        # 原因 3: 跨团队沟通不足导致 High Runner
        # 检查：High Runner 中有多少是跨 ECU 的
        
        return causes
```

---

### 4. 自然语言理解待提升

#### 当前状态
✅ **已有的能力**：
- 基础关键词匹配
- 业务术语映射
- Few-shot 示例学习

❌ **存在的问题**：
- **上下文理解弱** - 无法理解"刚才那个问题"
- **模糊表达处理差** - 无法理解"大概"、"可能"、"好像"
- **多轮对话能力弱** - 无法进行连续的追问和澄清
- **领域知识不足** - 无法理解车载软件开发的特殊术语

#### 举例说明

**用户连续对话**：
```
用户: 查询最近一周的 TopIssue
Agent: 返回了 10 个 TopIssue

用户: 那些项目中最多？
Agent: (需要理解"那些"指的是"返回的 10 个 TopIssue")
       当前可能返回所有项目的 TopIssue，而不是筛选后的

用户: 看起来 IDC 的问题比较多
Agent: (需要理解这句话是对前面分析结果的评论）
       需要回应"是的，IDC 确实比较多"
       然后继续分析 IDC 的问题特点
```

#### 改进方案

**步骤 1: 添加对话历史管理**

```python
class ConversationMemory:
    """对话记忆管理"""
    
    def __init__(self):
        self.history = []
        self.context = {
            'last_query': None,
            'last_result': None,
            'entities': {},  # 提取的实体
            'intent': None,  # 用户意图
        }
    
    def add_interaction(self, query: str, result: Dict):
        """添加一次交互"""
        self.history.append({
            'query': query,
            'result': result,
            'timestamp': datetime.now()
        })
        
        # 更新上下文
        self._update_context(query, result)
    
    def _update_context(self, query: str, result: Dict):
        """更新上下文"""
        self.context['last_query'] = query
        self.context['last_result'] = result
        
        # 提取实体
        self.context['entities'] = self._extract_entities(query)
    
    def _extract_entities(self, query: str) -> Dict:
        """提取实体"""
        entities = {}
        
        # 提取项目名
        projects = ['App', 'IDC', 'MGU', 'RSU', 'IDCevo']
        for project in projects:
            if project in query:
                entities['project'] = project
        
        # 提取时间范围
        if '今天' in query:
            entities['time_range'] = 'today'
        elif '本周' in query:
            entities['time_range'] = 'week'
        elif '本月' in query:
            entities['time_range'] = 'month'
        
        # 提取业务术语
        business_terms = ['TopIssue', 'High Runner', 'Long Runner']
        for term in business_terms:
            if term in query:
                entities['business_term'] = term
        
        return entities
    
    def get_context(self) -> Dict:
        """获取当前上下文"""
        return self.context
    
    def is_follow_up(self, current_query: str) -> bool:
        """判断是否是追问"""
        # 检查是否包含代词或指代词
        follow_up_keywords = ['那些', '这些', '这个', '那个', '看起来', '感觉']
        return any(keyword in current_query for keyword in follow_up_keywords)
```

---

## 🎯 改进优先级

### 🔴 立即改进（1-2 周）

1. **增强业务理解** 
   - 添加业务规则解释器
   - 添加业务语义理解
   - 生成业务洞察

2. **提高 SQL 准确性**
   - 扩充 Few-shot 示例
   - 添加 SQL 验证和自我纠正
   - 增加业务术语映射

3. **加强自然语言理解**
   - 添加对话记忆
   - 处理追问和连续对话
   - 提取和识别实体

### 🟡 中期改进（3-4 周）

4. **添加数据洞察**
   - 异常检测
   - 因果分析
   - 模式识别

5. **增强建议能力**
   - 主动建议
   - 预测分析
   - 对比分析

6. **优化查询性能**
   - 查询优化
   - 缓存策略
   - 并行处理

### 🟢 长期改进（1-2 个月）

7. **添加高级分析**
   - 机器学习预测
   - 智能推荐
   - 自动化报告生成

8. **优化用户体验**
   - 可视化增强
   - 交互优化
   - 个性化推荐

---

## 📊 改进路线图

### Phase 1: 核心能力增强（2 周）

**目标**: 显著提高 SQL 生成准确性和业务理解

- [ ] Week 1:
  - [ ] 扩充 Few-shot 示例到 50+
  - [ ] 添加 SQL 验证和自我纠正
  - [ ] 增加业务术语映射

- [ ] Week 2:
  - [ ] 添加业务规则解释器
  - [ ] 添加业务语义理解
  - [ ] 测试和优化

### Phase 2: 洞察和分析（2 周）

**目标**: 添加数据洞察和因果分析

- [ ] Week 3:
  - [ ] 实现异常检测
  - [ ] 实现因果分析
  - [ ] 实现模式识别

- [ ] Week 4:
  - [ ] 生成业务洞察
  - [ ] 添加建议能力
  - [ ] 测试和优化

### Phase 3: 交互优化（2 周）

**目标**: 增强自然语言理解和多轮对话

- [ ] Week 5:
  - [ ] 实现对话记忆
  - [ ] 实现追问处理
  - [ ] 实现实体识别

- [ ] Week 6:
  - [ ] 优化多轮对话
  - [ ] 优化上下文理解
  - [ ] 测试和优化

---

## 📝 总结

你的 TestAgent 已经有了很好的基础：
- ✅ 完整的业务规则
- ✅ 丰富的可视化
- ✅ 先进的 Text-to-SQL Agent
- ✅ 多 Agent 协作

但要成为一个**真正强大的数据分析 Agent**，还需要重点改进：

### 最关键的 3 个改进方向：

1. **增强业务理解深度** 🔴
   - 不仅仅是"知道"规则，而是能"解释"为什么
   - 生成有价值的业务洞察
   - 理解业务语义（时间范围、项目特点等）

2. **提高 SQL 生成准确性** 🔴
   - 扩充 Few-shot 示例
   - 添加 SQL 验证和自我纠正
   - 减少复杂查询的错误率

3. **添加数据洞察能力** 🔴
   - 异常检测
   - 因果分析
   - 模式识别
   - 主动建议

按照这个路线图逐步改进，你的 Agent 会越来越强大！🚀
