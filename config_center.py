"""
配置中心 - PreAnalysis 项目统一配置入口
========================================

所有 API Key、路径、服务配置统一从这里读取。
优先级：环境变量 > .env 文件 > 默认值

使用方法：
    from config_center import cfg
    
    # 获取 DeepSeek API Key
    api_key = cfg.DEEPSEEK_API_KEY
    
    # 获取智谱 API Key
    zhipu_key = cfg.ZHIPU_API_KEY
    
    # 获取项目根目录
    root = cfg.PROJECT_ROOT

作者: AI Assistant (多 Agent 协作优化)
日期: 2026-03-22
版本: 1.0
"""

import os
import sys
from pathlib import Path
from typing import Optional


def _load_dotenv(dotenv_path: str):
    """手动加载 .env 文件（不依赖 python-dotenv）"""
    if not os.path.exists(dotenv_path):
        return
    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception as e:
        print(f"⚠️ 加载 .env 失败: {e}")


# ============================================================
# 加载 .env 文件
# ============================================================

_THIS_DIR = Path(__file__).parent.resolve()
_DOT_ENV_PATH = _THIS_DIR / ".env"
_load_dotenv(str(_DOT_ENV_PATH))


class ProjectConfig:
    """项目统一配置类 - 单例模式"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        """初始化所有配置项"""

        # ============================================================
        # 路径配置
        # ============================================================
        self.PROJECT_ROOT: Path = Path(os.environ.get("PROJECT_ROOT", str(_THIS_DIR)))
        self.DATA_DIR: Path = self.PROJECT_ROOT / os.environ.get("DATA_DIR", "defect")
        self.MR_DIR: Path = self.PROJECT_ROOT / os.environ.get("MR_DIR", "mr")
        self.AIDA_DIR: Path = self.PROJECT_ROOT / os.environ.get("AIDA_DIR", "aida")
        self.DATABASE_DIR: Path = self.PROJECT_ROOT / os.environ.get("DATABASE_DIR", "database")
        self.DATABASE_FILE: Path = self.DATABASE_DIR / "local_data.db"

        # ============================================================
        # DeepSeek 配置（内网优先）
        # ============================================================
        self.DEEPSEEK_ACCESS_CODE: str = os.environ.get("DEEPSEEK_ACCESS_CODE", "")
        _internal_base_tpl = "https://aistudio.bmwbrill.cn/api/service/160/{access_code}/llama4/v2/chat/completions"
        _internal_base = _internal_base_tpl.format(access_code=self.DEEPSEEK_ACCESS_CODE) if self.DEEPSEEK_ACCESS_CODE else ""

        self.DEEPSEEK_API_KEY: str = (
            os.environ.get("DEEPSEEK_API_KEY")
            or (f"ACCESSCODE {self.DEEPSEEK_ACCESS_CODE}" if self.DEEPSEEK_ACCESS_CODE else "")
        )
        self.DEEPSEEK_API_BASE: str = (
            os.environ.get("DEEPSEEK_API_BASE")
            or _internal_base
            or "https://api.deepseek.com/v1"
        )
        self.DEEPSEEK_MODEL: str = os.environ.get("DEEPSEEK_MODEL", "deepseek-v3.2")

        # 备用公网
        self.DEEPSEEK_API_KEY_BACKUP: str = os.environ.get("DEEPSEEK_API_KEY_BACKUP", "")
        self.DEEPSEEK_API_BASE_BACKUP: str = os.environ.get("DEEPSEEK_API_BASE_BACKUP", "https://api.deepseek.com/v1")
        self.DEEPSEEK_MODEL_BACKUP: str = os.environ.get("DEEPSEEK_MODEL_BACKUP", "deepseek-reasoner")

        # ============================================================
        # 智谱 ZhipuAI 配置
        # ============================================================
        self.ZHIPU_API_KEY: str = os.environ.get("ZHIPU_API_KEY", "")
        self.ZHIPU_BASE_URL: str = os.environ.get("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
        self.ZHIPU_MODEL: str = os.environ.get("ZHIPU_MODEL", "glm-4.7")
        # Anthropic 兼容接口（用于 Coding Plan）
        self.ZHIPU_ANTHROPIC_BASE_URL: str = "https://open.bigmodel.cn/api/anthropic"

        # ============================================================
        # 应用服务配置
        # ============================================================
        self.HOST: str = os.environ.get("HOST", "0.0.0.0")
        self.PORT: int = int(os.environ.get("PORT", "8051"))
        self.DEBUG: bool = os.environ.get("DEBUG", "False").lower() == "true"
        self.SECRET_KEY: str = os.environ.get("SECRET_KEY", "please-change-this-to-a-random-string")

        # ============================================================
        # OpenClaw 配置
        # ============================================================
        self.OPENCLAW_GATEWAY_URL: str = os.environ.get("OPENCLAW_GATEWAY_URL", "ws://127.0.0.1:18789")
        self.OPENCLAW_TOKEN: str = os.environ.get("OPENCLAW_TOKEN", "")

    def get_db_path(self) -> str:
        """获取数据库路径（字符串形式）"""
        return str(self.DATABASE_FILE)

    def get_defect_data_pattern(self) -> str:
        """获取缺陷数据文件 glob 模式"""
        return str(self.DATA_DIR / "*.json")

    def get_master_data_file(self) -> str:
        """获取主数据文件路径"""
        return str(self.DATA_DIR / "2025_defect_master.json")

    def validate(self) -> dict:
        """验证关键配置是否存在，返回验证报告"""
        issues = []
        warnings = []

        # 关键 API Key 检查
        if not self.DEEPSEEK_API_KEY and not self.DEEPSEEK_API_KEY_BACKUP:
            issues.append("❌ DeepSeek API Key 未配置（DEEPSEEK_ACCESS_CODE 或 DEEPSEEK_API_KEY_BACKUP）")
        elif not self.DEEPSEEK_API_KEY:
            warnings.append("⚠️ DeepSeek 内网 Key 未配置，将使用公网备用")

        if not self.ZHIPU_API_KEY:
            warnings.append("⚠️ 智谱 API Key 未配置（ZHIPU_API_KEY）")

        if self.SECRET_KEY == "please-change-this-to-a-random-string":
            warnings.append("⚠️ SECRET_KEY 使用默认值，生产环境请修改")

        # 路径检查
        if not self.DATABASE_DIR.exists():
            warnings.append(f"⚠️ 数据库目录不存在：{self.DATABASE_DIR}")

        return {
            "ok": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
        }

    def __repr__(self):
        return (
            f"ProjectConfig("
            f"root={self.PROJECT_ROOT}, "
            f"deepseek={'✅' if self.DEEPSEEK_API_KEY else '❌'}, "
            f"zhipu={'✅' if self.ZHIPU_API_KEY else '❌'}, "
            f"port={self.PORT}"
            f")"
        )


# ============================================================
# 全局单例
# ============================================================
cfg = ProjectConfig()


# ============================================================
# 命令行验证入口
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("PreAnalysis 配置中心验证")
    print("=" * 60)
    print(f"\n{cfg}\n")

    report = cfg.validate()
    if report["issues"]:
        print("❌ 严重问题：")
        for issue in report["issues"]:
            print(f"  {issue}")
    else:
        print("✅ 关键配置验证通过")

    if report["warnings"]:
        print("\n⚠️ 警告：")
        for w in report["warnings"]:
            print(f"  {w}")

    print(f"\n路径配置：")
    print(f"  PROJECT_ROOT   = {cfg.PROJECT_ROOT}")
    print(f"  DATABASE_FILE  = {cfg.get_db_path()}")
    print(f"  DATA_DIR       = {cfg.DATA_DIR}")
    print(f"  ZHIPU_MODEL    = {cfg.ZHIPU_MODEL}")
    print(f"  DEEPSEEK_MODEL = {cfg.DEEPSEEK_MODEL}")
    print()
