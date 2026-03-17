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

## Important Notes

- The system automatically handles reloader processes to avoid unnecessary imports
- Performance monitoring is built-in for functions taking >1 second
- History data caching significantly improves response times
- AI functionality gracefully degrades if API key not configured
- Cache management is automated but can be manually controlled