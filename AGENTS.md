# PreAnalysis - AGENTS.md

## Project Description

**PreAnalysis** is a comprehensive automotive testing data analysis platform designed for BMW's DTSV (Development Test System Validation) team. The system integrates multiple data visualization tools, AI-powered intelligent analysis, and modern web interfaces to help testing teams and management understand key metrics such as test coverage, defect distribution, and risk assessment.

### Key Technologies

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Backend** | Python Dash 2.13.0 | Web application framework |
| **Data Processing** | Pandas, NumPy, SQLite | Data analysis and storage |
| **Visualization** | Plotly 5.14+ | Interactive charts |
| **AI Integration** | DeepSeek API (OpenAI SDK) | Intelligent data analysis |
| **Frontend (Agent UI)** | Next.js 16 + React 19 | Modern chat interface |
| **Authentication** | BMW SSO | Enterprise authentication |

---

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface Layer                     │
├─────────────────────────────────────────────────────────────┤
│  Dash Dashboards (8051-8073)  │  Agent UI (Next.js, :3000)  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                         │
├─────────────────────────────────────────────────────────────┤
│  defect_explore.py (主应用)  │  ai_chat_manager.py (AI)     │
│  data_processor.py (数据处理) │  config.py (配置管理)         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Data Layer                              │
├─────────────────────────────────────────────────────────────┤
│  SQLite Database  │  JSON Files  │  Cache System            │
│  (octane_*)       │  (defect/)   │  (cache/)                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   External Services                          │
├─────────────────────────────────────────────────────────────┤
│  Octane API (BMW)  │  DeepSeek API  │  BMW SSO              │
└─────────────────────────────────────────────────────────────┘
```

### Main Components and Relationships

1. **Main Dashboard** (`defect_explore.py` - Port 8051)
   - Central hub for all analysis modules
   - Modular navigation system via `NAVIGATION_CONFIG`
   - Integrates all sub-modules through iframe/routing

2. **Sub-Dashboards** (Independent Ports)
   - `defect_matrix.py` (8053) - Defect matrix analysis
   - `defect_trend.py` (8052) - Trend analysis
   - `risk_analysis.py` (8057) - Risk assessment
   - `test_coverage.py` (8055) - AIDA test coverage
   - `defect_coverage.py` (8056) - Coverage analysis
   - `word_cloud.py` (8073) - Text analysis

3. **AI System** (`agent/` + `ai_chat_manager.py`)
   - `agent/core/intelligent_agent.py` - Main AI agent
   - `agent/core/ai_chat_manager.py` - Chat management
   - Supports multiple dashboard contexts (defect, test, trend)

4. **Data Pipeline**
   - `download/octane_downloader.py` - High-frequency sync (defect, MR, history)
   - `download/testcase_downloader.py` - Low-frequency sync (testcase relations)
   - `data_processor.py` - Core data transformation
   - `octane_db.py` - SQLite storage layer

### Data Flow

```
Octane API → Downloader → SQLite DB → Data Processor → Dashboard
                │                           │
                └── JSON Files ──────────────┘
                         │
                         └── Cache System
```

---

## Directory Structure

### Core Application Files

| File/Dir | Purpose | Lines |
|----------|---------|-------|
| `defect_explore.py` | Main dashboard application (8051) | ~5500 |
| `data_processor.py` | Core data processing, Risk Score algorithm | ~3900 |
| `ai_chat_manager.py` | Unified AI chat management | ~2100 |
| `config.py` | Centralized configuration, navigation | ~300 |
| `db_storage.py` | Database operations (ETL) | ~700 |
| `octane_db.py` | SQLite storage layer | ~1000 |

### Key Directories

```
TPMDashbaord/
├── 📊 Core Dashboards
│   ├── defect_explore.py          # Main application (8051)
│   ├── defect_matrix.py           # Matrix analysis (8053)
│   ├── risk_analysis.py           # Risk assessment (8057)
│   └── test_coverage.py           # Test coverage (8055)
│
├── 🤖 AI System
│   ├── agent/                     # AI agent framework
│   │   ├── core/                  # Core AI components
│   │   ├── tools/                 # AI tools
│   │   └── memory/                # Memory management
│   └── ai_chat_manager.py         # Chat integration
│
├── 📥 Data Pipeline
│   └── download/
│       ├── octane_downloader.py   # Main data sync
│       └── testcase_downloader.py # Testcase relations
│
├── 💾 Data Storage
│   ├── database/                  # SQLite databases
│   │   └── local_data_rebuilt.db  # Main DB (~4GB)
│   ├── defect/                    # Defect JSON files
│   ├── history/                   # History logs
│   └── cache/                     # Performance cache
│
├── 🎨 UI Components
│   ├── dash_common_styles.py      # Theme & styles
│   ├── page_components.py         # Page components
│   └── navigation_manager.py      # Navigation system
│
└── 📁 Configuration
    ├── config.py                  # Centralized config
    ├── requirements.txt           # Python dependencies
    └── login_info.txt             # Authentication (not in git)
```

### Entry Points

1. **Main Application**: `python defect_explore.py`
2. **Individual Dashboards**: `python <module_name>.py`
3. **Data Sync**: `python download/octane_downloader.py`
4. **Agent UI**: `cd agent_ui && npm run dev`

---

## Development Workflow

### Environment Setup

```bash
# 1. Clone and navigate
cd TPMDashbaord

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure authentication
# Create login_info.txt with BMW SSO credentials
# Or use cookie authentication
```

### Running the Application

```bash
# Main dashboard (recommended)
python defect_explore.py
# Access: http://localhost:8051

# Individual modules
python defect_matrix.py      # Port 8053
python risk_analysis.py      # Port 8057
python test_coverage.py      # Port 8055

# Production (Windows)
python serve_waitress.py --host 0.0.0.0 --port 8051 --threads 8

# Production (Linux)
gunicorn -w 4 -b 0.0.0.0:8051 defect_explore:server
```

### Data Synchronization

```bash
# High-frequency sync (defect + MR + history)
python download/octane_downloader.py --team DTSV_China --auth-method cookie --skip-mr-relations

# DB-only mode (no JSON files)
python download/octane_downloader.py --team DTSV_China --auth-method cookie --skip-file-output

# Testcase relations
python download/testcase_downloader.py --dtsv-all --team-name DTSV_China --save-db

# Cache warmup
python warmup_cache.py --years 2025,2026 --weeks 52
```

### Testing

```bash
# Run tests
pytest tests/

# Performance testing
python app_launcher.py --mode test

# Monitor performance
python app_launcher.py --mode monitor
```

### Lint and Format

```bash
# Format code
black *.py

# Lint
flake8 *.py --max-line-length=120

# Type checking (optional)
mypy *.py
```

### Cache Management

```bash
# Check cache status
python cleanup_cache.py

# Clear Python cache
# Windows
Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

# Linux/Mac
find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null
```

---

## Key Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 8051 | Application port |
| `DEBUG` | False | Debug mode |
| `DEEPSEEK_API_KEY` | - | Required for AI features |
| `OCTANE_DB_PATH` | `database/local_data_rebuilt.db` | Database path |
| `OCTANE_TEAM` | `DTSV_China` | Default team |

### Data Files Requirements

- `defect/2025_defect.json` - Main defect data (~47MB)
- `database/local_data_rebuilt.db` - SQLite database (~4GB)
- `login_info.txt` - Authentication credentials (JSON format)

### Navigation Configuration

Add new modules by updating `config.py`:

```python
NAVIGATION_CONFIG = [
    {
        'id': 'tab-new-module',
        'label': 'New Module',
        'icon': 'fas fa-chart-bar',
        'component': 'new_module_page',
        'enabled': True
    },
    # ... existing modules
]
```

---

## Important Notes for Developers

### Performance Considerations

1. **Large Files**: Many core files exceed 50,000 characters
   - Use `Get-Content` (Windows) or `head` (Linux) to read portions
   - Consider modular refactoring for maintainability

2. **Database Size**: Main database is ~4GB
   - Use indexed queries
   - Implement pagination for large result sets
   - Cache frequently accessed data

3. **Memory Management**
   - History data uses LRU cache (2000 items)
   - Singleton pattern prevents duplicate loading
   - Background preloading improves response times

### AI Integration

- Graceful degradation when API key unavailable
- Context-aware responses based on dashboard type
- Streaming responses for better UX

### Encoding Issues

Some files contain mixed encoding (Chinese + special characters). When reading:
- Use `encoding='utf-8'` explicitly
- Handle encoding errors gracefully

### Modular Architecture

The system follows a modular configuration approach:
- Navigation: `config.py:NAVIGATION_CONFIG`
- Pages: `page_components.py`
- Styles: `dash_common_styles.py`
- Callbacks: Registered per-module

---

## Common Issues and Solutions

### Issue: Data Download Fails
- Check VPN connection (BMW internal network required)
- Verify `login_info.txt` credentials
- Try `--auth-method cookie` parameter

### Issue: AI Features Not Working
- Verify `DEEPSEEK_API_KEY` environment variable
- Check network connectivity to API endpoint
- Review browser console for errors

### Issue: Slow Performance
- Run cache warmup: `python warmup_cache.py`
- Check database indexes
- Reduce concurrent requests

### Issue: Module Not Loading
- Verify module is enabled in `NAVIGATION_CONFIG`
- Check port availability
- Review console errors

---

## Technology Stack Summary

**Backend (Python)**
- Dash 2.13.0 - Web framework
- Pandas 2.0+ - Data analysis
- SQLite - Data storage
- OpenAI SDK - AI integration
- Plotly 5.14+ - Visualization

**Frontend (Next.js)**
- Next.js 16.1.1
- React 19.2.3
- Vercel AI SDK 6.0.3
- Tailwind CSS 3.4+

**Data Sources**
- Octane API (BMW internal)
- JSON files
- SQLite database

---

**Last Updated**: 2026-03-30
**Version**: 2.0.0
**Maintainer**: PreAnalysis Team
