#!/usr/bin/env python3
"""
缓存管理工具
提供命令行界面来管理项目缓存
使用方法:
    python scripts/utilities/cache_management.py info --details
    python scripts/utilities/cache_management.py clean --type smart
    python scripts/utilities/cache_management.py monitor --check
"""

import argparse
import sys
import os
from datetime import datetime
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(project_root))

from cache_manager import CacheManager

def format_size(size_gb):
    """格式化文件大小显示"""
    if size_gb < 1:
        return f"{size_gb * 1024:.1f}MB"
    else:
        return f"{size_gb:.2f}GB"

def print_cache_info(cache_manager):
    """打印缓存信息"""
    stats = cache_manager.get_cache_stats()
    print("\n📊 缓存统计信息:")
    print("=" * 50)
    print(f"总文件数: {stats['total_files']}")
    print(f"总大小: {format_size(stats['total_size_gb'])}")
    
    if stats['oldest_file']:
        print(f"最旧文件: {stats['oldest_file'].strftime('%Y-%m-%d %H:%M:%S')}")
    if stats['newest_file']:
        print(f"最新文件: {stats['newest_file'].strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 配置信息
    print(f"\n⚙️ 缓存配置:")
    print(f"最大大小限制: {format_size(cache_manager.max_size_gb)}")
    print(f"最大保留天数: {cache_manager.max_age_days} 天")
    
    # 健康状态
    if stats['total_size_gb'] > cache_manager.max_size_gb:
        print(f"⚠️  警告: 缓存大小超出限制!")
    elif stats['total_size_gb'] > cache_manager.max_size_gb * 0.8:
        print(f"⚠️  注意: 缓存大小接近限制 ({stats['total_size_gb']/cache_manager.max_size_gb*100:.1f}%)")
    else:
        print(f"✅ 缓存大小正常 ({stats['total_size_gb']/cache_manager.max_size_gb*100:.1f}%)")

def print_file_details(cache_manager, limit=20):
    """打印文件详细信息"""
    file_info = cache_manager.get_file_info()
    if not file_info:
        print("没有缓存文件")
        return
    
    # 按大小排序显示最大的文件
    file_info.sort(key=lambda x: x['size_mb'], reverse=True)
    
    print(f"\n📁 缓存文件详情 (显示前{min(limit, len(file_info))}个最大的文件):")
    print("=" * 80)
    print(f"{'文件名':<50} {'大小':<10} {'年龄':<8} {'最后访问':<12}")
    print("-" * 80)
    
    for info in file_info[:limit]:
        name = info['name'][:47] + "..." if len(info['name']) > 50 else info['name']
        size = f"{info['size_mb']:.1f}MB"
        age = f"{info['age_days']}天"
        accessed = info['accessed'].strftime('%m-%d %H:%M')
        
        print(f"{name:<50} {size:<10} {age:<8} {accessed:<12}")

def main():
    parser = argparse.ArgumentParser(description="缓存管理工具")
    parser.add_argument("--cache-dir", default="cache", help="缓存目录路径")
    parser.add_argument("--max-size", type=float, default=10.0, help="最大缓存大小(GB)")
    parser.add_argument("--max-age", type=int, default=30, help="最大保留天数")
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 查看信息
    info_parser = subparsers.add_parser("info", help="显示缓存信息")
    info_parser.add_argument("--details", action="store_true", help="显示文件详情")
    info_parser.add_argument("--limit", type=int, default=20, help="显示文件数量限制")
    
    # 清理命令
    clean_parser = subparsers.add_parser("clean", help="清理缓存")
    clean_parser.add_argument("--type", choices=["old", "large", "unused", "smart", "all"], 
                             default="smart", help="清理类型")
    clean_parser.add_argument("--age", type=int, help="清理超过指定天数的文件")
    clean_parser.add_argument("--size", type=float, help="清理到指定大小(GB)")
    clean_parser.add_argument("--unused-days", type=int, default=7, help="清理未使用天数")
    clean_parser.add_argument("--dry-run", action="store_true", help="仅显示将要删除的文件，不实际删除")
    
    # 监控命令
    monitor_parser = subparsers.add_parser("monitor", help="监控缓存状态")
    monitor_parser.add_argument("--check", action="store_true", help="检查是否需要清理")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 设置缓存目录路径（相对于项目根目录）
    cache_dir = project_root / args.cache_dir
    
    # 创建缓存管理器
    cache_manager = CacheManager(
        cache_dir=str(cache_dir),
        max_size_gb=args.max_size,
        max_age_days=args.max_age
    )
    
    if args.command == "info":
        print_cache_info(cache_manager)
        if args.details:
            print_file_details(cache_manager, args.limit)
    
    elif args.command == "clean":
        if args.dry_run:
            print("🔍 模拟运行模式 - 仅显示将要删除的文件")
            # 显示将要删除的文件信息
            file_info = cache_manager.get_file_info()
            if args.type == "old":
                age_limit = args.age or cache_manager.max_age_days
                old_files = [f for f in file_info if f['age_days'] > age_limit]
                print(f"将删除 {len(old_files)} 个过期文件 (>{age_limit}天)")
                for f in old_files[:10]:  # 显示前10个
                    print(f"  - {f['name']} ({f['age_days']}天)")
            elif args.type == "unused":
                from datetime import datetime, timedelta
                cutoff = datetime.now() - timedelta(days=args.unused_days)
                unused_files = [f for f in file_info if f['accessed'] < cutoff]
                print(f"将删除 {len(unused_files)} 个未使用文件 (>{args.unused_days}天未访问)")
                for f in unused_files[:10]:
                    print(f"  - {f['name']} (最后访问: {f['accessed']})")
            return
        
        print_cache_info(cache_manager)
        
        if args.type == "old":
            age = args.age or cache_manager.max_age_days
            deleted = cache_manager.clean_old_cache(age)
            print(f"\n清理完成: 删除了 {deleted} 个过期文件 (>{age}天)")
        
        elif args.type == "large":
            size = args.size or cache_manager.max_size_gb
            deleted = cache_manager.clean_large_cache(size)
            print(f"\n清理完成: 删除了 {deleted} 个文件以控制大小")
        
        elif args.type == "unused":
            deleted = cache_manager.clean_unused_cache(args.unused_days)
            print(f"\n清理完成: 删除了 {deleted} 个未使用文件 (>{args.unused_days}天未访问)")
        
        elif args.type == "smart":
            results = cache_manager.smart_cleanup(
                target_size_gb=args.size,
                max_age_days=args.age,
                unused_days=args.unused_days
            )
            print(f"\n智能清理完成:")
            print(f"  - 过期文件: {results['expired_files']}")
            print(f"  - 未使用文件: {results['unused_files']}")
            print(f"  - 超大小文件: {results['oversized_files']}")
            print(f"  - 总删除: {results['total_deleted']}")
            print(f"  - 释放空间: {format_size(results['size_freed_gb'])}")
        
        elif args.type == "all":
            if input("⚠️  确定要删除所有缓存文件吗? (y/N): ").lower() == 'y':
                cache_manager.clear()
                print("所有缓存文件已删除")
            else:
                print("操作已取消")
    
    elif args.command == "monitor":
        print_cache_info(cache_manager)
        
        if args.check:
            needs_cleanup = cache_manager.schedule_cleanup()
            if needs_cleanup:
                print("\n✅ 已执行自动清理")
            else:
                print("\n✅ 缓存状态良好，无需清理")

if __name__ == "__main__":
    main() 