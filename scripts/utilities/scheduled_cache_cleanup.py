#!/usr/bin/env python3
"""
定时缓存清理脚本
可以设置为crontab定时任务运行

使用方法:
    # 直接运行
    python scripts/utilities/scheduled_cache_cleanup.py
    
    # 设置crontab定时任务（每天凌晨2点清理）
    0 2 * * * cd /path/to/your/project && python scripts/utilities/scheduled_cache_cleanup.py

配置定时任务:
    1. 编辑crontab: crontab -e
    2. 添加行: 0 2 * * * cd /Users/tonyorz/pre-analysis && python scripts/utilities/scheduled_cache_cleanup.py
    3. 保存退出
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(project_root))

from cache_manager import CacheManager

def setup_logging(log_file=None):
    """设置日志记录"""
    if log_file is None:
        log_file = project_root / "cache_cleanup.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return logging.getLogger(__name__)

def run_cleanup(config=None):
    """执行定时清理
    
    Args:
        config (dict): 清理配置，包含max_size_gb, max_age_days等参数
    """
    logger = setup_logging()
    
    # 默认配置
    default_config = {
        'max_size_gb': 8.0,      # 8GB限制，比默认的10GB更积极
        'max_age_days': 21,      # 保留21天
        'unused_days': 5,        # 5天未访问即清理
        'target_size_gb': 6.0    # 清理到6GB
    }
    
    if config:
        default_config.update(config)
    
    try:
        logger.info("开始定时缓存清理任务")
        
        # 创建缓存管理器
        cache_dir = project_root / "cache"
        cache_manager = CacheManager(
            cache_dir=str(cache_dir),
            max_size_gb=default_config['max_size_gb'],
            max_age_days=default_config['max_age_days']
        )
        
        # 获取清理前状态
        initial_stats = cache_manager.get_cache_stats()
        logger.info(f"清理前状态: {initial_stats['total_files']} 文件, "
                   f"{initial_stats['total_size_gb']:.2f}GB")
        
        # 检查是否需要清理
        if (initial_stats['total_size_gb'] < default_config['max_size_gb'] * 0.7 and
            initial_stats['total_files'] < 1000):
            logger.info("缓存状态良好，无需清理")
            return True
        
        # 执行智能清理
        results = cache_manager.smart_cleanup(
            target_size_gb=default_config['target_size_gb'],
            max_age_days=default_config['max_age_days'],
            unused_days=default_config['unused_days']
        )
        
        # 记录结果
        logger.info(f"清理结果:")
        logger.info(f"  - 过期文件: {results['expired_files']}")
        logger.info(f"  - 未使用文件: {results['unused_files']}")
        logger.info(f"  - 超大小文件: {results['oversized_files']}")
        logger.info(f"  - 总删除: {results['total_deleted']}")
        logger.info(f"  - 释放空间: {results['size_freed_gb']:.2f}GB")
        
        # 获取清理后状态
        final_stats = cache_manager.get_cache_stats()
        logger.info(f"清理后状态: {final_stats['total_files']} 文件, "
                   f"{final_stats['total_size_gb']:.2f}GB")
        
        # 检查是否需要发送警告
        if final_stats['total_size_gb'] > default_config['max_size_gb'] * 0.9:
            logger.warning(f"清理后缓存大小仍然很大: {final_stats['total_size_gb']:.2f}GB")
        
        # 如果清理效果显著，记录成功
        if results['total_deleted'] > 0:
            logger.info(f"定时缓存清理任务完成，成功释放 {results['size_freed_gb']:.2f}GB 空间")
        else:
            logger.info("定时缓存清理任务完成，无需清理")
        
        return True
        
    except Exception as e:
        logger.error(f"定时清理任务失败: {e}")
        return False

def get_cleanup_config():
    """获取清理配置（可从环境变量或配置文件读取）"""
    config = {}
    
    # 从环境变量读取配置
    if os.getenv('CACHE_MAX_SIZE_GB'):
        config['max_size_gb'] = float(os.getenv('CACHE_MAX_SIZE_GB'))
    
    if os.getenv('CACHE_MAX_AGE_DAYS'):
        config['max_age_days'] = int(os.getenv('CACHE_MAX_AGE_DAYS'))
    
    if os.getenv('CACHE_UNUSED_DAYS'):
        config['unused_days'] = int(os.getenv('CACHE_UNUSED_DAYS'))
    
    if os.getenv('CACHE_TARGET_SIZE_GB'):
        config['target_size_gb'] = float(os.getenv('CACHE_TARGET_SIZE_GB'))
    
    return config

def main():
    """主函数"""
    # 获取配置
    config = get_cleanup_config()
    
    # 执行清理
    success = run_cleanup(config)
    
    # 退出码
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 