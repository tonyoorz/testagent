# 性能优化模块

这个目录包含了项目的性能优化相关脚本和工具。

## 📁 目录结构

```
scripts/performance/
├── README.md                    # 说明文档
├── optimization.md             # 性能优化指南（原PERFORMANCE_OPTIMIZATION.md）
├── cache/                      # 缓存相关模块
│   ├── __init__.py
│   ├── cache_manager.py        # 缓存管理器核心模块
│   ├── cache_management.py     # 缓存管理命令行工具
│   └── scheduled_cleanup.py    # 定时缓存清理
├── loaders/                    # 数据加载优化
│   ├── __init__.py
│   └── data_loader_optimized.py
├── startup/                    # 启动优化
│   ├── __init__.py
│   └── run_optimized.py
└── tools/                      # 辅助工具
    ├── __init__.py
    └── refactor_helper.py
```

## 🚀 使用方法

### 缓存管理
```bash
# 查看缓存状态
python scripts/performance/cache/cache_management.py info

# 智能清理缓存
python scripts/performance/cache/cache_management.py clean --type smart
```

### 优化启动
```bash
# 使用优化模式启动应用
python scripts/performance/startup/run_optimized.py
```

### 数据加载优化
```python
# 在应用中使用优化的数据加载器
from scripts.performance.loaders.data_loader_optimized import get_defect_data
df = get_defect_data()
```

## 📝 迁移说明

这些文件已从根目录迁移到此目录，以改善项目结构：
- `PERFORMANCE_OPTIMIZATION.md` → `scripts/performance/optimization.md`
- `cache_manager.py` → `scripts/performance/cache/cache_manager.py`
- `data_loader_optimized.py` → `scripts/performance/loaders/data_loader_optimized.py`
- `run_optimized.py` → `scripts/performance/startup/run_optimized.py`
- `refactor_helper.py` → `scripts/performance/tools/refactor_helper.py`

## ⚠️ 重要提醒

移动这些文件后，需要更新相关的导入路径：
1. 在 `defect_explore.py` 中更新数据加载器的导入
2. 在其他使用缓存管理器的地方更新导入路径
3. 确保所有导入路径都使用相对于项目根目录的正确路径 