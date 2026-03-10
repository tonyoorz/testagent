# TopIssue Risk Scoring Algorithm

## 🎯 Overview

The **TopIssue Risk Scoring Algorithm** is a comprehensive 8-dimensional risk assessment system designed for defect prioritization and management. It provides intelligent scoring based on severity, complexity, and processing efficiency metrics.

### Key Features
- **200-point scoring scale** with 8 evaluation dimensions
- **Intelligent inheritance mechanism** for parent-child ticket relationships
- **Multi-weight system** prioritizing critical factors
- **Real-time dynamic calculation** with performance optimization

---

## 📊 Risk Classification

| Risk Level | Score Range | Description |
|------------|-------------|-------------|
| 🔴 **Extremely High** | ≥140 points | Critical issues requiring immediate attention |
| 🟠 **High Risk** | ≥100 points | Serious issues requiring urgent handling |
| 🟡 **Medium Risk** | ≥60 points | Important issues requiring priority handling (**TopIssue**) |
| 🟢 **Low Risk** | ≥30 points | General issues requiring normal handling |
| ⚪ **No Risk** | <30 points | Minor issues with standard processing |

> **TopIssue Threshold**: ≥60 points

---

## ⚖️ Dimension Weights

### High Weight Dimensions (30 points each)
- **Matrix Severity** - Problem severity assessment
- **Classification Labels** - Critical blocking issue identification  
- **ECU Transfer Count** - Technical complexity measurement
- **Parent Complexity** - Project management complexity
- **Child Complexity** - Master ticket complexity inheritance

### Medium Weight Dimensions (20 points each)
- **Domain Transfer Count** - Cross-domain coordination complexity
- **Processing Cycle** - Processing efficiency evaluation

### Low Weight Dimensions (10 points each)
- **Shift PU Status** - Deferred fix identification

**Total Maximum Score**: 200 points (5×30 + 2×20 + 1×10)

---

## 📋 Detailed Scoring Rules

### 1. Matrix Severity (30 points) 🔥
*Linear decreasing scoring from highest to lowest severity*

| Matrix Level | Score | Severity Category |
|--------------|-------|-------------------|
| Matrix-1A | 30 pts | High Severity |
| Matrix-1B | 28 pts | High Severity |
| Matrix-1C | 26 pts | High Severity |
| Matrix-1D | 24 pts | High Severity |
| Matrix-1E | 22 pts | High Severity |
| Matrix-2A | 20 pts | High Severity |
| Matrix-2B | 18 pts | High Severity |
| Matrix-3A | 16 pts | High Severity |
| Matrix-2D | 14 pts | Medium Severity |
| Matrix-2E | 12 pts | Medium Severity |
| Matrix-3B | 10 pts | Medium Severity |
| Matrix-3C | 8 pts | Medium Severity |
| Matrix-3D | 6 pts | Medium Severity |
| Matrix-4A | 4 pts | Medium Severity |
| Matrix-3E/4B/4C/4D/4E | 2 pts | Low Severity |

### 2. Classification Labels (30 points) 🏷️

| Classification | Score | Priority Level |
|----------------|-------|----------------|
| Showstopper_Confirmed | 30 pts | Highest Priority |
| Preventing Maturity Grade ConDrive | 30 pts | Highest Priority |
| Showstopper_Candidate | 20 pts | High Priority |
| Obstructing Maturity Grade ConDrive | 10 pts | Medium Priority |
| Homologation L-labelled | 10 pts | Medium Priority |
| Other or None | 0 pts | No Priority |

### 3. ECU Transfer Count (30 points) 🔄

| Transfer Count | Score | Complexity Level |
|----------------|-------|------------------|
| ≥5 transfers | 30 pts | Extremely High |
| ≥3 transfers | 24 pts | High |
| ≥1 transfer | 20 pts | Medium |
| 0 transfers | 0 pts | None |

### 4. Domain Transfer Count (20 points) 🌐

| Transfer Count | Score | Complexity Level |
|----------------|-------|------------------|
| ≥5 transfers | 20 pts | Extremely High |
| ≥3 transfers | 14 pts | High |
| ≥1 transfer | 10 pts | Medium |
| 0 transfers | 0 pts | None |

### 5. Parent Complexity (30 points) 👨‍👩‍👧‍👦

| Child Tickets | Score | Complexity Level |
|---------------|-------|------------------|
| ≥5 children | 30 pts | Extremely High |
| ≥3 children | 20 pts | High |
| ≥1 child | 10 pts | Medium |
| 0 children or not parent | 0 pts | None |

### 6. Child Complexity (30 points) 👶

| Master's Children | Score | Complexity Level |
|-------------------|-------|------------------|
| Master has ≥5 children | 30 pts | Extremely High |
| Master has ≥3 children | 20 pts | High |
| Master has ≥1 child | 10 pts | Medium |
| Master has 0 children or not child | 0 pts | None |

### 7. Processing Cycle (20 points) ⏱️

| Processing Days | Score | Cycle Length |
|-----------------|-------|--------------|
| ≥30 days | 20 pts | Long Cycle |
| ≥15 days | 14 pts | Medium-Long Cycle |
| ≥7 days | 6 pts | Short Cycle |
| <7 days | 0 pts | Very Short Cycle |

### 8. Shift PU Status (10 points) ⏸️

| Status | Score | Description |
|--------|-------|-------------|
| Has value | 10 pts | Deferred fix - has postponement identifier |
| No value or empty | 0 pts | Normal processing |

---

## 🧠 Intelligent Features

### Smart Inheritance Mechanism
- **Child tickets** automatically compare their score with their **master ticket's score**
- **Higher score is selected** to ensure accurate risk assessment
- Master scores are marked with **asterisk (*)** for identification

### Performance Optimization
- **Master data caching** for efficient lookup
- **Real-time calculation** of processing days and metrics
- **Compensation mechanism** for missing master ticket data

### Display Logic
- Shows **actual calculated score**
- Master-inherited scores marked with **asterisk (*)**
- Zero scores displayed as **"0"** for clarity

### Intelligent Recommendation System
The algorithm generates comprehensive recommendations based on **4 core assessment dimensions**:

#### 1. **SEVERITY** (Dimensions 1-2: Matrix + Classification)
- Evaluates the **criticality and impact** of the defect
- **Critical severity**: Matrix-1A/1B issues with immediate business impact
- **Blocking severity**: Showstopper issues preventing system functionality
- **High severity**: Other high-priority Matrix levels and classifications

#### 2. **HIGH RUNNER** (Dimensions 3-4: ECU + Domain Transfers)
- Measures **cross-system coordination complexity**
- **Multiple transfers**: Issues bouncing between 5+ systems indicating coordination challenges
- **System transfer complexity**: ECU or domain transfers requiring multi-team collaboration
- **Coordination overhead**: Resource-intensive issues requiring extensive communication

#### 3. **COMPLEXITY** (Dimensions 5-6: Parent + Child Relationships)
- Assesses **project management and structural complexity**
- **Extremely high complexity**: Large ticket hierarchies with 5+ related tickets
- **High complexity**: Multiple related tickets requiring coordinated resolution
- **Standard complexity**: Simple parent-child relationships

#### 4. **LONG RUNNER** (Dimensions 7-8: Processing Cycle + Shift PU)
- Evaluates **resolution timeline and processing efficiency**
- **Long-term processing**: Issues open for 30+ days requiring immediate attention
- **Deferred processing**: Shift PU assignments indicating postponement risks
- **Extended timeline**: Processing delays affecting delivery schedules

---

## 🔧 Implementation Highlights

### Scoring Methods
- **Linear Scoring**: Matrix dimension uses linear decreasing from 30 to 2 points
- **Threshold-based Scoring**: Other dimensions use threshold ranges (≥5, ≥3, ≥1, 0)

### Data Processing
- **Dynamic calculation** of processing cycle days
- **Automatic detection** of parent-child relationships
- **Intelligent fallback** mechanisms for missing data

### Quality Assurance
- **Comprehensive validation** of all scoring dimensions
- **Consistent scoring logic** across all ticket types
- **Transparent calculation** with detailed reasoning

---

## 📈 Usage Examples

### High-Risk Ticket Example
```
Ticket ID: 2157632
- Matrix-1A: 30 points
- Showstopper_Confirmed: 30 points  
- ECU Transfers (9): 30 points
- Total Score: 90 points → Medium Risk (TopIssue)

Recommendation: 
MEDIUM RISK: Priority handling recommended | 
SEVERITY: Critical severity issue - Matrix Level Matrix-1A (High Severity, 30pts); Showstopper Confirmed (30pts) | 
HIGH RUNNER: System transfer complexity detected - ECU Transfer 9 times (30pts)
```

### Medium-Risk Ticket Example
```
Ticket ID: 2281701
- Matrix-1E: 22 points
- Processing Days: 16 days
- Total Score: 22 points → No Risk

Recommendation:
MINIMAL RISK: Routine processing appropriate | 
SEVERITY: Critical severity issue - Matrix Level Matrix-1E (High Severity, 22pts)
```

### Complex Parent Ticket Example
```
Ticket ID: 2219734
- Matrix-1A: 30 points
- Showstopper_Confirmed: 30 points
- ECU Transfers (4): 24 points
- Parent with multiple children
- Total Score: 84 points → Medium Risk (TopIssue)

Recommendation:
MEDIUM RISK: Priority handling recommended | 
SEVERITY: Critical severity issue - Matrix Level Matrix-1A (High Severity, 30pts); Showstopper Confirmed (30pts) | 
HIGH RUNNER: System transfer complexity detected - ECU Transfer 4 times (24pts)
```

---

## 🎯 Benefits

✅ **Objective Risk Assessment** - Eliminates subjective bias in prioritization  
✅ **Comprehensive Evaluation** - Considers multiple complexity factors across 4 core dimensions  
✅ **Intelligent Automation** - Reduces manual effort in risk scoring and recommendation generation  
✅ **Scalable Solution** - Handles large volumes of tickets efficiently with optimized algorithms  
✅ **Transparent Logic** - Provides clear reasoning for each score with detailed explanations  
✅ **Actionable Insights** - Categorizes risks into Severity, High Runner, Complexity, and Long Runner aspects  
✅ **Strategic Guidance** - Helps teams understand WHY a ticket is risky and HOW to prioritize resources  
✅ **Multi-dimensional Analysis** - Balances immediate impact, coordination complexity, structural complexity, and timeline risks  

---

*Last Updated: December 2024*  
*Algorithm Version: 2.0 (200-point scale)* 