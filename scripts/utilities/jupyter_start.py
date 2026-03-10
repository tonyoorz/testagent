#!/usr/bin/env python
"""
Jupyter启动脚本
用于从notebooks子目录启动Jupyter，并确保正确的Python路径和虚拟环境
"""

import os
import sys
import subprocess
from pathlib import Path

def setup_jupyter_environment():
    """设置Jupyter环境"""
    # 找到项目根目录
    current_dir = Path.cwd()
    project_root = current_dir
    
    # 向上查找，直到找到包含requirements.txt的目录
    while project_root.parent != project_root:
        if (project_root / 'requirements.txt').exists():
            break
        project_root = project_root.parent
    
    print(f"项目根目录: {project_root}")
    
    # 设置环境变量
    os.environ['PYTHONPATH'] = str(project_root)
    
    # 检查虚拟环境
    venv_path = project_root / '.venv'
    if venv_path.exists():
        python_path = venv_path / 'bin' / 'python'
        if python_path.exists():
            print(f"使用虚拟环境: {venv_path}")
            # 激活虚拟环境
            os.environ['VIRTUAL_ENV'] = str(venv_path)
            os.environ['PATH'] = f"{venv_path / 'bin'}:{os.environ.get('PATH', '')}"
        else:
            print("警告: 虚拟环境存在但Python解释器未找到")
    else:
        print("警告: 未找到.venv虚拟环境")
    
    return project_root

def start_jupyter(project_root):
    """启动Jupyter"""
    try:
        # 切换到项目根目录
        os.chdir(project_root)
        
        # 启动Jupyter Lab
        cmd = ['jupyter', 'lab', '--notebook-dir=.', '--ip=0.0.0.0', '--port=8888']
        print(f"启动命令: {' '.join(cmd)}")
        print(f"工作目录: {os.getcwd()}")
        
        # 启动Jupyter
        subprocess.run(cmd)
        
    except FileNotFoundError:
        print("错误: 未找到jupyter命令")
        print("请确保已在虚拟环境中安装jupyter:")
        print("source .venv/bin/activate && pip install jupyter")
    except KeyboardInterrupt:
        print("\nJupyter已停止")
    except Exception as e:
        print(f"启动Jupyter时发生错误: {e}")

if __name__ == "__main__":
    project_root = setup_jupyter_environment()
    start_jupyter(project_root) 