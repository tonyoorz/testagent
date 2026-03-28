#!/usr/bin/env python3
"""
测试运行器 - 运行所有单元测试

用法:
    python3 run_unit_tests.py [选项]

选项:
    -v, --verbose    详细输出
    -p, --pattern    测试文件模式 (默认: test_*.py)
"""

import sys
import os
import unittest
import argparse
from pathlib import Path


def discover_tests(test_dir="tests", pattern="test_*.py"):
    """
    发现并运行测试

    Args:
        test_dir: 测试目录
        pattern: 测试文件模式

    Returns:
        测试结果
    """
    # 获取项目根目录
    project_root = Path(__file__).parent
    test_path = project_root / test_dir

    # 检查测试目录是否存在
    if not test_path.exists():
        print(f"❌ 测试目录不存在: {test_path}")
        return None

    # 发现测试
    loader = unittest.TestLoader()
    start_dir = str(test_path)

    try:
        suite = loader.discover(start_dir, pattern=pattern)
    except Exception as e:
        print(f"❌ 发现测试失败: {e}")
        return None

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result


def print_summary(result):
    """
    打印测试摘要

    Args:
        result: 测试结果
    """
    if result is None:
        return

    print("\n" + "=" * 70)
    print("测试摘要")
    print("=" * 70)

    # 统计信息
    total_tests = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped)
    success = total_tests - failures - errors

    print(f"✅ 总测试数: {total_tests}")
    print(f"✅ 成功: {success}")
    print(f"❌ 失败: {failures}")
    print(f"💥 错误: {errors}")
    print(f"⏭️  跳过: {skipped}")

    # 计算成功率
    if total_tests > 0:
        success_rate = (success / total_tests) * 100
        print(f"📊 成功率: {success_rate:.1f}%")

    # 打印失败的测试
    if result.failures:
        print("\n❌ 失败的测试:")
        for test, traceback in result.failures[:5]:  # 只显示前5个
            print(f"  - {test}")

    # 打印错误的测试
    if result.errors:
        print("\n💥 错误的测试:")
        for test, traceback in result.errors[:5]:  # 只显示前5个
            print(f"  - {test}")

    # 最终结果
    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("✅ 所有测试通过！")
    else:
        print("❌ 有测试失败或错误")
    print("=" * 70 + "\n")

    return result.wasSuccessful()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="运行单元测试")
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="详细输出"
    )
    parser.add_argument(
        "-p", "--pattern",
        default="test_*.py",
        help="测试文件模式"
    )
    parser.add_argument(
        "-d", "--dir",
        default="tests",
        help="测试目录"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("单元测试运行器")
    print("=" * 70 + "\n")

    # 运行测试
    result = discover_tests(
        test_dir=args.dir,
        pattern=args.pattern
    )

    # 打印摘要
    success = print_summary(result)

    # 返回退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
