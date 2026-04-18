# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PreAnalysis is a comprehensive automotive testing data analysis platform that integrates multiple data visualization tools for defect management, test coverage analysis, and risk assessment. The system helps testing teams and management understand key metrics like test coverage, defect distribution, and risk assessment to optimize testing strategies.

## Key Architecture

### Main Application Entry Points
- `defect_explore.py` - Main dashboard application (port 8051)
- `app_launcher.py` - Unified application launcher with optimization features
- `run_app.py` - Alternative application runner

### Core Data Processing
- `data_processor.py` - Core data processing module with advanced Risk Score algorithm and caching
- `config.py` - Centralized configuration management with modular navigation
- `db_storage.py` - Database storage and retrieval operations

### Dashboard Modules
Individual dashboard modules run on separate ports:
- `defect_matrix.py` (port 8053) - Defect matrix analysis with AI chat integration
- `defect_trend.py` (port 8052) - Defect trend analysis
- `defect_map.py` (port 8054) - Geographic defect distribution
- `risk_analysis.py` (port 8057) - Risk assessment dashboard
- `test_coverage.py` (port 8055) - Test coverage analysis
- `defect_coverage.py` (port 8056) - Defect coverage analysis
- `word_cloud.py` (port 8073) - Word cloud analysis

### AI Integration
- `ai_chat_manager.py` - Unified AI chat management system for all dashboards
- DeepSeek API integration for intelligent data analysis
- Context-aware AI assistance across multiple dashboard types

### Data Sources
- `defect/` - Defect data files (JSON format)
- `history/` - Historical defect data files
- `aida/` - AIDA mapping data and test case information
- `cache/` - Performance caching directory

## Common Development Commands

### Running the Application
```bash
# Main application (recommended)
python defect_explore.py

# Using launcher with optimization
python app_launcher.py --quick-start

# Individual dashboards
python defect_matrix.py
python risk_analysis.py
python test_coverage.py
```

### Performance Testing
```bash
# Run performance tests
python app_launcher.py --mode test

# Monitor performance
python app_launcher.py --mode monitor
```

### Cache Management
```bash
# Check cache status
python cleanup_cache.py

# Clear Python cache
find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null
```

### Data Processing
```bash
# Download and update data
python downloader3.py --defect-years 2025 --auth-method cookie

# Update AIDA mappings
python aida_mapping_updater.py
```

## Key Configuration

### Environment Variables
- `PORT` - Application port (default: 8051)
- `DEBUG` - Debug mode (default: True)
- `DEEPSEEK_API_KEY` - Required for AI chat functionality

### Data File Requirements
Ensure these files exist for full functionality:
- `defect/2025_defect.json` - Main defect data
- `defect/2025_defect_master.json` - Master defect data
- `aida/top_aida_project_fv_mapping.xlsx` - AIDA project mapping
- `login_info.txt` - Authentication credentials (JSON format)

## Performance Optimization

The application includes several performance optimizations:
- **Data Caching**: Intelligent caching system for frequently accessed data
- **History Preloading**: Background preloading of historical data files
- **Singleton Data Management**: Prevents duplicate data loading
- **LRU Cache**: Efficient memory management for large datasets

Optimizations are automatically enabled when running `defect_explore.py`.

## Modular Architecture

The system uses a modular configuration approach:
- Navigation items are configured in `config.py:NAVIGATION_CONFIG`
- Page components are managed in `page_components.py`
- Themes and styles are centralized in `dash_common_styles.py`

To add new modules:
1. Update `NAVIGATION_CONFIG` in `config.py`
2. Add component function to `page_components.py`
3. Register callbacks if needed

## AI Chat Integration

The AI system provides intelligent data analysis across all dashboards:
- Unified chat interface with context awareness
- Support for multiple dashboard types (defect, test, trend, general)
- Streaming responses for better user experience
- Automatic fallback to basic analysis if API key unavailable

## Testing

### Data Requirements for Testing
- Ensure sample data files exist in `defect/` and `history/` directories
- Test files should follow the established JSON schema patterns
- AIDA mapping files required for full feature testing

### Performance Testing
The application includes built-in performance monitoring and testing capabilities through the launcher system.

## Deployment

### Local Development
```bash
pip install -r requirements.txt
python defect_explore.py
```

### Production Deployment
```bash
python deploy.py start  # Production mode
python deploy.py dev    # Development mode
```

Access the application at `http://localhost:8051` or `http://YOUR_IP:8051` for network access.

## Common Patterns

### Data Loading Pattern
The system uses a centralized data management approach with caching and optimization. Most modules follow this pattern:
1. Check for optimized data manager availability
2. Fall back to standard loading if optimization unavailable
3. Use caching for frequently accessed data

### Dashboard Integration Pattern
New dashboards should:
1. Follow the modular configuration approach
2. Use unified filter components from `create_unified_filters()`
3. Integrate AI chat functionality when relevant
4. Follow the established styling patterns

## Development Principles (Karpathy Coding Guidelines)

> These principles bias toward caution over speed. For trivial tasks (typo fixes, one-liners), use judgment.

### 1. 先想再写 (Think Before Coding)

**不要假设。不要隐藏困惑。主动暴露权衡。**

- 实现前，明确列出你的假设。不确定就问。
- 如果有多种理解，全部列出来 — 不要悄悄选一个。
- 如果有更简单的方案，说出来。该反驳就反驳。
- 搞不清楚时停下来，说清楚哪里不懂，然后问。

### 2. 简单优先 (Simplicity First)

**用最少的代码解决问题。不要做没要求的推测性实现。**

- 不加没要求的功能
- 不为一次性代码建抽象
- 不加没要求的"灵活性"或"可配置性"
- 不处理不可能发生的错误场景
- 如果你写了200行但其实50行就够了，重写它

**自检：** 一个资深工程师会认为这过度复杂吗？如果是，简化。

### 3. 精准手术 (Surgical Changes)

**只动必须动的。只清理自己造成的。**

编辑现有代码时：
- 不要"顺手改进"相邻的代码、注释或格式
- 不要重构没坏的东西
- 匹配已有代码风格，即使你不会那样写
- 如果发现不相关的死代码，提一句 — 不要直接删

你的修改产生孤立代码时：
- 删除因你的修改而变为无用的 import/变量/函数
- 不要删除以前就存在的死代码，除非被要求

**自检：** 每一行变更都应该能追溯到用户的请求。

### 4. 目标驱动执行 (Goal-Driven Execution)

**定义成功标准。循环直到验证通过。**

把任务转化为可验证的目标：
- "加上验证" → "先写无效输入的测试，再让它通过"
- "修复bug" → "先写一个能复现的测试，再让它通过"
- "重构X" → "确保重构前后测试都通过"

多步骤任务，先列简要计划：
```
1. [步骤] → 验证: [检查方式]
2. [步骤] → 验证: [检查方式]
3. [步骤] → 验证: [检查方式]
```

明确的成功标准让你能独立循环。模糊的标准（"让它能用"）需要反复确认。

---

**原则生效的标志：** diff 中不必要的变更更少、过度复杂导致的重写更少、澄清问题在实现前就提出了、PR 干净最小化。

## Important Notes

- The system automatically handles reloader processes to avoid unnecessary imports
- Performance monitoring is built-in for functions taking >1 second
- History data caching significantly improves response times
- AI functionality gracefully degrades if API key not configured
- Cache management is automated but can be manually controlled