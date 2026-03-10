#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键清理缓存脚本 (已升级为统一缓存管理)
使用统一缓存管理器清理项目中的各种缓存文件
"""

import os
import sys
import argparse
import glob
import shutil
from datetime import datetime
from pathlib import Path

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from unified_cache_manager import UnifiedCacheManager
except ImportError:
    print("错误：无法导入统一缓存管理器")
    print("请确保 unified_cache_manager.py 文件存在于当前目录")
    sys.exit(1)

# 导入数据处理模块以清除inflow/outflow缓存（保持向后兼容）
try:
    from data_processor import clear_inflow_outflow_cache
    INFLOW_OUTFLOW_CACHE_AVAILABLE = True
except ImportError:
    INFLOW_OUTFLOW_CACHE_AVAILABLE = False

def clean_pycache():
    """清理__pycache__目录"""
    print("🧹 清理__pycache__目录...")
    count = 0
    
    for root, dirs, files in os.walk("."):
        if "__pycache__" in dirs and not root.startswith("./.venv"):
            pycache_path = os.path.join(root, "__pycache__")
            try:
                shutil.rmtree(pycache_path)
                print(f"   ✅ 删除: {pycache_path}")
                count += 1
            except Exception as e:
                print(f"   ❌ 错误: {pycache_path} - {e}")
    
    print(f"   清理完成: {count} 个__pycache__目录")
    return count

def clean_old_cache_files(days=7):
    """清理旧的缓存文件"""
    print(f"🧹 清理{days}天以上的缓存文件...")
    count = 0
    freed_size = 0
    
    if os.path.exists("cache"):
        cache_files = glob.glob("cache/*.pkl")
        now = datetime.now()
        
        for f in cache_files:
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(f))
                age_days = (now - mtime).days
                
                if age_days > days:
                    size = os.path.getsize(f)
                    os.remove(f)
                    print(f"   ✅ 删除: {os.path.basename(f)} ({age_days}天前)")
                    count += 1
                    freed_size += size
            except Exception as e:
                print(f"   ❌ 错误: {f} - {e}")
    
    print(f"   清理完成: {count} 个文件, 释放空间: {freed_size/(1024**2):.1f}MB")
    return count, freed_size

def clean_inflow_outflow_cache():
    """清除inflow/outflow缓存"""
    print("🧹 清理inflow/outflow缓存...")
    
    if INFLOW_OUTFLOW_CACHE_AVAILABLE:
        try:
            clear_inflow_outflow_cache()
            print("   ✅ inflow/outflow缓存已清除")
            return True
        except Exception as e:
            print(f"   ❌ 清除inflow/outflow缓存失败: {e}")
            return False
    else:
        print("   ⚠️  inflow/outflow缓存清理功能不可用")
        return False

def clean_empty_dirs():
    """清理空目录"""
    print("🧹 清理空目录...")
    count = 0
    
    empty_dirs = ["test_cache"]
    for dir_name in empty_dirs:
        if os.path.exists(dir_name) and not os.listdir(dir_name):
            try:
                os.rmdir(dir_name)
                print(f"   ✅ 删除空目录: {dir_name}")
                count += 1
            except Exception as e:
                print(f"   ❌ 错误: {dir_name} - {e}")
    
    return count

def show_cache_stats():
    """显示缓存统计信息"""
    print("📊 缓存统计信息:")
    
    # cache目录统计
    if os.path.exists("cache"):
        cache_files = glob.glob("cache/*.pkl")
        total_size = sum(os.path.getsize(f) for f in cache_files)
        print(f"   📁 cache/: {len(cache_files)} 文件, {total_size/(1024**3):.2f}GB")
    else:
        print("   📁 cache/: 不存在")
    
    # __pycache__统计
    pycache_count = 0
    for root, dirs, files in os.walk("."):
        if "__pycache__" in dirs and not root.startswith("./.venv"):
            pycache_count += 1
    print(f"   📁 __pycache__: {pycache_count} 个目录")
    
    # 空目录统计
    empty_count = 0
    if os.path.exists("test_cache") and not os.listdir("test_cache"):
        empty_count += 1
    print(f"   📁 空目录: {empty_count} 个")

def legacy_cleanup():
    """传统清理方法（保持向后兼容）"""
    print("🚀 Pre-Analysis 一键缓存清理工具 (传统模式)")
    print("=" * 50)
    
    # 显示清理前状态
    print("\n清理前状态:")
    show_cache_stats()
    
    # 执行清理
    print("\n开始清理...")
    
    # 1. 清理__pycache__（安全）
    pycache_count = clean_pycache()
    
    # 2. 清理空目录
    empty_count = clean_empty_dirs()
    
    # 3. 询问是否清理inflow/outflow缓存
    print(f"\n🤔 是否清理inflow/outflow缓存？")
    print("   注意：这将清除票据收敛趋势图的缓存数据")
    choice = input("   输入 y 确认，其他键跳过: ").strip().lower()
    
    inflow_outflow_cleared = False
    if choice == 'y':
        inflow_outflow_cleared = clean_inflow_outflow_cache()
    
    # 4. 询问是否清理旧缓存文件
    print(f"\n🤔 是否清理7天以上的缓存文件？")
    print("   注意：这可能会影响应用启动速度")
    choice = input("   输入 y 确认，其他键跳过: ").strip().lower()
    
    old_cache_count = 0
    freed_size = 0
    if choice == 'y':
        old_cache_count, freed_size = clean_old_cache_files(7)
    
    # 显示清理后状态
    print("\n清理后状态:")
    show_cache_stats()
    
    # 总结
    print(f"\n✅ 清理完成!")
    print(f"   - __pycache__目录: {pycache_count} 个")
    print(f"   - 空目录: {empty_count} 个")
    print(f"   - inflow/outflow缓存: {'已清除' if inflow_outflow_cleared else '未清除'}")
    print(f"   - 旧缓存文件: {old_cache_count} 个")
    print(f"   - 释放空间: {freed_size/(1024**2):.1f}MB")
    
    if pycache_count > 0 or old_cache_count > 0 or inflow_outflow_cleared:
        print("\n💡 提示：下次运行应用时可能需要更多时间来重新生成缓存")

def main():
    """主函数 - 使用统一缓存管理器"""
    parser = argparse.ArgumentParser(description='统一缓存清理工具')
    parser.add_argument('--all', action='store_true', 
                       help='清理所有类型的缓存（推荐）')
    parser.add_argument('--python-only', action='store_true', 
                       help='仅清理Python字节码缓存')
    parser.add_argument('--status', action='store_true', 
                       help='显示缓存状态信息')
    parser.add_argument('--optimize', action='store_true', 
                       help='优化缓存设置')
    parser.add_argument('--legacy', action='store_true', 
                       help='使用传统清理方法（保持向后兼容）')
    parser.add_argument('--interactive', action='store_true', 
                       help='交互式清理（传统模式）')
    parser.add_argument('--root-dir', type=str, default='.', 
                       help='项目根目录 (默认: 当前目录)')
    parser.add_argument('--quiet', action='store_true', 
                       help='静默模式，减少输出')
    
    args = parser.parse_args()
    
    # 如果没有参数或使用传统模式，则使用传统清理方法
    if args.legacy or args.interactive or (not any([args.all, args.python_only, args.status, args.optimize])):
        if not args.legacy and not args.interactive:
            print("💡 未指定参数，使用交互式传统模式")
            print("   使用 --all 参数可启用统一缓存管理器")
            print("   使用 --help 查看所有选项\n")
        legacy_cleanup()
        return
    
    root_dir = Path(args.root_dir).resolve()
    
    # 使用统一缓存管理器
    try:
        manager = UnifiedCacheManager(str(root_dir))
        
        if args.status:
            print("📊 缓存状态信息:")
            status = manager.get_cache_status()
            import json
            print(json.dumps(status, indent=2, ensure_ascii=False))
            
        elif args.optimize:
            print("⚙️ 优化缓存设置:")
            optimizations = manager.optimize_cache_settings()
            import json
            print(json.dumps(optimizations, indent=2, ensure_ascii=False))
            
        elif args.python_only:
            print("🐍 仅清理Python字节码缓存...")
            result = manager.clear_python_cache()
            if not args.quiet:
                print(f"✅ 清理完成：删除了 {result['cleared_dirs']} 个目录，释放 {result['total_size_mb']} MB")
                
        elif args.all:
            print("🧹 开始全面缓存清理...")
            result = manager.clear_all_caches(verbose=not args.quiet)
            if not args.quiet:
                summary = result['summary']
                print(f"\n📈 清理总结:")
                print(f"   ⏱️  用时: {result['total_time_seconds']} 秒")
                print(f"   📁 Python缓存目录: {summary['python_cache_dirs']} 个")
                print(f"   🥒 Pickle文件: {summary['pickle_files']} 个")
                print(f"   📄 JSON文件: {summary['json_files']} 个")
                print(f"   💾 总释放空间: {summary['total_size_mb']:.2f} MB")
                    
    except Exception as e:
        print(f"❌ 统一缓存管理器执行失败: {e}")
        print("🔄 回退到传统清理方法...")
        legacy_cleanup()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序被中断")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")