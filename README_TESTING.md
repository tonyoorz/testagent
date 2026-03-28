# 测试框架文档

## 概述

本项目已经建立了完整的测试框架，包括：

- ✅ 单元测试 (33 个测试)
- ✅ 集成测试
- ✅ 性能测试
- ✅ CI/CD 自动化流水线

## 测试结构

```
testagent/
├── tests/                          # 测试目录
│   ├── __init__.py                 # 测试包初始化
│   ├── test_sql_validator.py       # SQL 验证器测试
│   ├── test_schema_manager.py     # Schema 管理器测试
│   └── test_fewshot_examples.py  # Few-shot 示例测试
├── run_unit_tests.py              # 单元测试运行器
├── test_fewshot_expansion.py     # Few-shot 扩充测试
├── .github/workflows/
│   └── ci-cd.yml                 # CI/CD 配置
└── README_TESTING.md             # 本文档
```

## 快速开始

### 运行所有单元测试

```bash
cd ~/WorkBuddy/Claw/testagent
python3 run_unit_tests.py
```

### 运行特定测试

```bash
# 运行 SQL 验证器测试
python3 -m unittest tests.test_sql_validator

# 运行 Schema 管理器测试
python3 -m unittest tests.test_schema_manager

# 运行 Few-shot 示例测试
python3 -m unittest tests.test_fewshot_examples
```

### 运行详细输出

```bash
python3 run_unit_tests.py -v
```

## 测试覆盖范围

### 1. SQL 验证器测试 (test_sql_validator.py)

测试内容：
- ✅ 安全的 SELECT 查询验证
- ✅ 危险操作拦截（DROP, DELETE, UPDATE, CREATE, ALTER, TRUNCATE）
- ✅ 非 SELECT 语句拒绝
- ✅ SQL 清理（注释移除、空格压缩）
- ✅ 块注释清理
- ✅ 复杂查询验证
- ✅ 关键词大小写不敏感

测试数量：13 个

### 2. Schema 管理器测试 (test_schema_manager.py)

测试内容：
- ✅ 基础 Schema 获取
- ✅ Schema 缓存机制
- ✅ 强制刷新 Schema
- ✅ 表样本数据获取
- ✅ 无效表处理
- ✅ Schema 格式验证
- ✅ 多表支持
- ✅ 主键标记
- ✅ 数据类型显示

测试数量：9 个

### 3. Few-shot 示例测试 (test_fewshot_examples.py)

测试内容：
- ✅ 示例数量验证（60 个）
- ✅ 示例结构完整性
- ✅ SQL 语法正确性
- ✅ 限制数量获取
- ✅ 默认限制数量
- ✅ 相似示例查找
- ✅ 无匹配示例处理
- ✅ 示例分类覆盖
- ✅ 无重复问题
- ✅ SQL 质量检查
- ✅ 示例格式化输出

测试数量：11 个

### 4. Few-shot 扩充测试 (test_fewshot_expansion.py)

测试内容：
- ✅ Few-shot 示例数量统计
- ✅ 示例结构验证
- ✅ SQL 语法验证
- ✅ SQL 查询引擎集成测试
- ✅ 复杂查询测试
- ✅ 测试摘要生成

## CI/CD 流水线

### 触发条件

- 推送到 `main` 或 `develop` 分支
- 针对 `main` 或 `develop` 分支的 Pull Request

### 流水线任务

1. **单元测试**
   - Python 版本：3.9, 3.10, 3.11
   - 运行所有单元测试
   - 生成测试覆盖率报告
   - 上传到 Codecov

2. **代码质量检查**
   - Black 格式检查
   - isort 导入排序检查
   - Flake8 代码检查
   - MyPy 类型检查

3. **安全扫描**
   - Bandit 安全扫描
   - Safety 已知漏洞检查

4. **性能测试**
   - 运行性能基准测试
   - 生成性能报告

5. **集成测试**
   - Few-shot 扩充测试
   - 增强 SQL 聊天测试

6. **文档构建**
   - MkDocs 文档构建
   - 静态站点生成

7. **发布通知**
   - 检查所有任务状态
   - 发送成功/失败通知

## 测试统计

当前测试状态：

| 测试类型 | 测试数量 | 通过率 |
|---------|---------|--------|
| SQL 验证器 | 13 | 100% |
| Schema 管理器 | 9 | 100% |
| Few-shot 示例 | 11 | 100% |
| **总计** | **33** | **100%** |

## 添加新测试

### 1. 创建测试文件

在 `tests/` 目录下创建新的测试文件，例如 `test_new_feature.py`：

```python
#!/usr/bin/env python3
"""
测试新功能
"""

import unittest

class TestNewFeature(unittest.TestCase):
    """新功能测试"""

    def setUp(self):
        """测试前准备"""
        pass

    def tearDown(self):
        """测试后清理"""
        pass

    def test_example(self):
        """示例测试"""
        self.assertTrue(True)

if __name__ == '__main__':
    unittest.main()
```

### 2. 运行新测试

```bash
# 运行特定测试文件
python3 -m unittest tests.test_new_feature

# 运行所有测试（包括新的）
python3 run_unit_tests.py
```

## 最佳实践

### 1. 测试命名

使用描述性的测试名称：

```python
# 好的命名
def test_validate_safe_select_query(self):
    pass

# 不好的命名
def test_1(self):
    pass
```

### 2. 测试隔离

每个测试应该独立运行，不依赖其他测试：

```python
def setUp(self):
    """每个测试前都会执行"""
    self.test_data = create_test_data()

def tearDown(self):
    """每个测试后都会执行"""
    cleanup_test_data()
```

### 3. 断言使用

使用合适的断言方法：

```python
# 检查值相等
self.assertEqual(expected, actual)

# 检查布尔值
self.assertTrue(condition)
self.assertFalse(condition)

# 检查异常
with self.assertRaises(ValueError):
    some_function()
```

### 4. 测试数据管理

使用临时数据，避免污染生产环境：

```python
import tempfile

def setUp(self):
    self.temp_db = tempfile.NamedTemporaryFile(delete=False)
    self.temp_db.close()
    self.db_path = self.temp_db.name

def tearDown(self):
    if os.path.exists(self.db_path):
        os.unlink(self.db_path)
```

## 持续集成

### GitHub Actions 工作流程

1. 提交代码到 GitHub
2. 自动触发 CI/CD 流水线
3. 运行所有测试
4. 生成测试报告
5. 检查代码质量
6. 安全扫描
7. 性能测试
8. 发送通知

### 查看测试结果

访问 GitHub 仓库的 Actions 标签页：
```
https://github.com/your-username/testagent/actions
```

## 故障排查

### 问题：测试失败

**解决方案：**

1. 查看详细错误信息：
   ```bash
   python3 run_unit_tests.py -v
   ```

2. 运行单个失败的测试：
   ```bash
   python3 -m unittest tests.test_sql_validator.TestSQLValidator.test_validate_safe_select
   ```

3. 检查测试日志：
   ```bash
   python3 -m unittest tests.test_sql_validator -v 2>&1 | tee test.log
   ```

### 问题：导入错误

**解决方案：**

确保项目路径正确：
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
```

### 问题：数据库连接失败

**解决方案：**

确保测试数据库存在且可访问：
```bash
ls -la database/local_data.db
```

## 贡献指南

添加新测试时，请遵循以下规则：

1. ✅ 每个测试函数只测试一个功能点
2. ✅ 使用描述性的测试名称
3. ✅ 保持测试独立性
4. ✅ 清理测试资源
5. ✅ 添加必要的注释
6. ✅ 确保测试快速执行

## 许可证

MIT License

---

**祝测试愉快！🚀**
