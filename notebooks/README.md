# Notebooks 使用指南

## 🚀 快速开始

### 方法1：使用虚拟环境启动Jupyter（推荐）

```bash
# 从项目根目录启动
source .venv/bin/activate
jupyter lab
```

### 方法2：使用启动脚本

```bash
# 从任何目录运行
python scripts/utilities/jupyter_start.py
```

## 📝 在Notebook中设置环境

### 方法1：使用统一设置模块（推荐）

在notebook的第一个cell中添加：

```python
# Notebook环境设置
import sys
from pathlib import Path

# 查找项目根目录
notebook_dir = Path().absolute()
project_root = notebook_dir
while project_root.parent != project_root:
    if (project_root / 'requirements.txt').exists():
        break
    project_root = project_root.parent

# 添加scripts路径
scripts_path = project_root / 'scripts'
if str(scripts_path) not in sys.path:
    sys.path.insert(0, str(scripts_path))

# 使用设置模块
from utilities.notebook_setup import setup_notebook_environment
env_info = setup_notebook_environment(verbose=True)
```

### 方法2：简单手动设置

```python
import sys
import os
from pathlib import Path

# 找到项目根目录
current_dir = Path().absolute()
project_root = current_dir
while project_root.parent != project_root:
    if (project_root / 'requirements.txt').exists():
        break
    project_root = project_root.parent

# 设置路径
sys.path.insert(0, str(project_root))
os.chdir(project_root)
print(f"项目根目录: {project_root}")
```

## 🔧 Jupyter Kernel 设置

确保使用正确的Python kernel：

1. 在Jupyter Lab中，点击右上角的kernel名称
2. 选择 "Pre-Analysis Python (.venv)" kernel
3. 如果没有这个选项，运行：
   ```bash
   source .venv/bin/activate
   python -m ipykernel install --user --name=pre-analysis --display-name="Pre-Analysis Python (.venv)"
   ```

## 📁 目录结构

```
notebooks/
├── analysis/           # 分析类notebook
│   ├── Test Management 2025.ipynb
│   └── Defect Management 2025.ipynb
├── data_profiling/     # 数据分析notebook
│   └── Data_Profiling_Demo.ipynb
├── downloader/         # 下载相关notebook
│   └── Downloader.ipynb
└── README.md          # 本文件
```

## ⚠ 常见问题解决

### 问题1：导入模块失败
- 确保运行了环境设置代码
- 检查虚拟环境是否激活
- 确认kernel选择正确

### 问题2：数据文件找不到
- 检查工作目录是否为项目根目录
- 使用相对于项目根目录的路径

### 问题3：pygwalker等库无法使用
- 确保在虚拟环境中安装了所有依赖：
  ```bash
  source .venv/bin/activate
  pip install -r requirements.txt
  pip install jupyter ipykernel ipywidgets seaborn matplotlib pygwalker
  ```

## 🎯 最佳实践

1. **始终在第一个cell设置环境**
2. **使用项目根目录的相对路径**
3. **保持notebook简洁，复杂逻辑放到模块中**
4. **定期保存notebook和清理输出**

## 📞 需要帮助？

如果遇到问题，请检查：
1. 虚拟环境是否正确激活
2. Jupyter kernel是否选择正确
3. 环境设置代码是否正确运行
4. 项目依赖是否完整安装 