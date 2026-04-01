---
invokable: true
---

Review this code for potential issues, including:

## BMW/Automotive Testing Domain Specific

- **Octane API Integration**: Check for proper error handling when Octane API calls fail. Ensure SSO authentication is properly managed and tokens are refreshed.
- **Data Integrity**: Verify that defect IDs, testcase IDs, and other identifiers are properly validated before database operations.
- **BMW Naming Conventions**: Ensure variable names follow project conventions (e.g., `defect_id`, `run_id`, `test_week` format: 'YY-CWww').
- **Sensitive Data Handling**: Check for hardcoded credentials, API keys, or internal URLs that should be in environment variables. Look for `HARDCODED_*` variables that need to be moved to configuration.

## Python Dashboard Development

- **Dash Callbacks**: Verify callback inputs/outputs are properly defined. Check for missing `PreventUpdate` handling. Ensure callbacks don't cause circular dependencies.
- **Performance**: Look for expensive operations inside callbacks that should be cached. Check for missing `@lru_cache` decorators on frequently called functions. Identify potential N+1 query problems.
- **Data Loading**: Ensure proper use of singleton pattern for data managers. Check that `IS_RELOADER` guards are in place to prevent duplicate imports during hot reload.
- **Error Handling**: Verify try-catch blocks around file I/O, API calls, and database operations. Check for proper logging instead of silent failures.
- **Modular Navigation**: Verify new modules are properly registered in `config.py:NAVIGATION_CONFIG`. Check that page components follow the established pattern in `page_components.py`.

## Database Operations

- **SQL Injection**: Check for string formatting in SQL queries. Ensure parameterized queries are used.
- **Connection Management**: Verify database connections are properly closed. Check for connection pooling if needed.
- **Transaction Safety**: Ensure proper commit/rollback handling for multi-step operations.
- **Index Usage**: Identify queries that might benefit from indexes on frequently queried columns.
- **Large Database Handling**: Main database is ~4GB. Check for proper query optimization, pagination, and memory management.

## AI Integration Specific

- **API Key Management**: Check for hardcoded API keys (especially DeepSeek). Verify fallback to internal BMW AI services.
- **Streaming Responses**: Ensure proper handling of streaming responses from AI APIs. Check for timeout handling.
- **Context Window**: Verify that context sent to AI models doesn't exceed limits. Check for proper truncation strategies.
- **Error Recovery**: Ensure graceful degradation when AI services are unavailable (check `ai_chat_manager.py` for fallback logic).

## Data Processing Pipeline

- **Batch Processing**: Check for proper chunking in data downloaders (especially for large datasets). Verify concurrent request limits are reasonable (`--max-concurrent-requests`).
- **Cache Invalidation**: Ensure cache is properly invalidated when source data changes. Check for cache key versioning (`cache_versioning.py`).
- **File Handling**: Verify proper encoding (UTF-8) for file operations. Check for proper handling of large files (~47MB defect files).
- **Memory Management**: Look for potential memory leaks with large pandas DataFrames. Check for proper cleanup of temporary objects.
- **LRU Cache**: Verify `HistoryCache` class is properly used with appropriate cache size limits.

## Risk Score Algorithm Specific

- **Algorithm Correctness**: Verify the 8-dimension Risk Score calculation follows the documented formula:
  - Matrix severity: `30 × e^(-0.25 × order)` (exponential decay)
  - Parent/child complexity: `10 × log(count+1) × 2.5` (logarithmic growth)
  - Processing time: Dual-peak distribution (0-3 days and 30+ days)
- **Score Boundaries**: Ensure risk levels are correctly classified:
  - ≥140: Extreme high risk
  - ≥100: High risk
  - ≥60: Medium risk (TopIssue threshold)
  - ≥30: Low risk
  - <30: No risk
- **Edge Cases**: Check handling of missing data in any dimension.

## Code Quality

- **Type Hints**: Check for missing or incorrect type annotations in function signatures.
- **Documentation**: Verify complex functions have docstrings explaining purpose, parameters, and return values.
- **Imports**: Look for unused imports or circular dependencies. Check for proper use of `__init__.py` files.
- **Logging**: Ensure sensitive data isn't logged. Check for appropriate log levels (INFO, WARNING, ERROR).
- **Large Files**: Many core files exceed 50,000 characters. Recommend modular refactoring where appropriate for maintainability.

## Configuration Management

- **Environment Variables**: Check that all configurable values use environment variables with sensible defaults.
- **Config File Security**: Verify `login_info.txt` and `.env` are in `.gitignore`.
- **Port Conflicts**: Ensure different dashboard modules use different ports as configured in `SUBMODULES_CONFIG`.
- **Theme Configuration**: Verify theme changes follow `THEME_CONFIG` structure in `config.py`.

## Testing & Validation

- **Data Validation**: Check that input data is validated before processing. Verify date/time parsing handles multiple formats.
- **Edge Cases**: Look for handling of empty datasets, null values, and missing fields in JSON/API responses.
- **Cross-Platform**: Ensure file paths work on both Windows and Linux/Mac (use `os.path.join` or `pathlib`).
- **Encoding Issues**: This repository contains Chinese text. Verify UTF-8 encoding is explicitly specified. Check for mojibake issues (e.g., `defect_explore.py.mojibake.bak`).

## Common Patterns to Check

- **Singleton Pattern**: Data managers should use singleton pattern to prevent duplicate loading
- **Reloader Guards**: Check for `IS_RELOADER` pattern to prevent duplicate imports during Flask hot reload:
  ```python
  DISABLE_RELOADER = os.environ.get("DISABLE_RELOADER", "1").lower() in ("1", "true", "yes")
  IS_RELOADER = (not DISABLE_RELOADER) and (os.environ.get("WERKZEUG_RUN_MAIN") != "true")
  ```
- **Fallback Pattern**: Data loading should follow: optimized manager → standard loading → error
- **Safe Get Pattern**: Use `safe_get()`, `safe_get_name()`, `safe_get_id()` helpers for nested JSON access

Provide specific, actionable feedback for improvements. For each issue found, reference the file location and line numbers where possible, and provide corrected code examples.
