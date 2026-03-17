#!/bin/bash
"""
设置缓存定时清理任务

使用方法:
    bash scripts/utilities/setup_cache_cron.sh

功能:
    - 自动检测项目路径和Python路径
    - 创建定时任务脚本
    - 可选择性地添加到crontab
    - 提供多种定时清理选项
"""

# 获取项目根目录（脚本的上上级目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON_PATH=$(which python3)

echo "🔧 设置缓存定时清理任务"
echo "="*50
echo "项目目录: $PROJECT_DIR"
echo "Python路径: $PYTHON_PATH"
echo "脚本目录: $SCRIPT_DIR"

# 创建定时任务运行脚本
CRON_SCRIPT="$PROJECT_DIR/run_cache_cleanup.sh"

cat > "$CRON_SCRIPT" << EOF
#!/bin/bash
# 缓存清理定时任务脚本
# 自动生成于 $(date)

# 设置工作目录
cd "$PROJECT_DIR"

# 设置环境变量（可选）
export PATH="\$PATH:$(dirname $PYTHON_PATH)"
export PYTHONPATH="$PROJECT_DIR:\$PYTHONPATH"

# 设置缓存清理配置（可选）
# export CACHE_MAX_SIZE_GB=8.0
# export CACHE_MAX_AGE_DAYS=21
# export CACHE_UNUSED_DAYS=5
# export CACHE_TARGET_SIZE_GB=6.0

# 运行清理脚本，输出到日志文件
$PYTHON_PATH "$SCRIPT_DIR/scheduled_cache_cleanup.py" >> "$PROJECT_DIR/cache_cleanup.log" 2>&1

# 记录执行时间
echo "清理任务执行于: \$(date)" >> "$PROJECT_DIR/cache_cleanup.log"
EOF

chmod +x "$CRON_SCRIPT"

echo "✅ 已创建定时任务脚本: $CRON_SCRIPT"

# 显示可用的定时任务选项
echo ""
echo "📅 推荐的定时任务设置:"
echo "1. 每天凌晨2点清理 (推荐):"
echo "   0 2 * * * $CRON_SCRIPT"
echo ""
echo "2. 每周日凌晨3点清理:"
echo "   0 3 * * 0 $CRON_SCRIPT"
echo ""
echo "3. 每12小时清理一次:"
echo "   0 */12 * * * $CRON_SCRIPT"
echo ""
echo "4. 每天凌晨2点和下午2点清理:"
echo "   0 2,14 * * * $CRON_SCRIPT"
echo ""

# 显示手动运行命令
echo "🔧 手动测试命令:"
echo "bash $CRON_SCRIPT"
echo ""

# 询问是否要自动设置
read -p "是否要自动设置每天凌晨2点的定时任务? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # 检查是否已经存在相同的定时任务
    if crontab -l 2>/dev/null | grep -q "$CRON_SCRIPT"; then
        echo "⚠️  定时任务已存在"
        echo "当前crontab中已有该任务:"
        crontab -l 2>/dev/null | grep "$CRON_SCRIPT"
    else
        # 添加定时任务
        (crontab -l 2>/dev/null; echo "0 2 * * * $CRON_SCRIPT") | crontab -
        echo "✅ 已设置每天凌晨2点的定时清理任务"
        echo "新增的crontab条目:"
        echo "0 2 * * * $CRON_SCRIPT"
    fi
else
    echo "📋 手动设置定时任务:"
    echo "1. 编辑crontab: crontab -e"
    echo "2. 添加以下行之一:"
    echo "   0 2 * * * $CRON_SCRIPT    # 每天凌晨2点"
    echo "   0 3 * * 0 $CRON_SCRIPT    # 每周日凌晨3点"
    echo "3. 保存并退出"
fi

echo ""
echo "📊 管理命令:"
echo "查看当前定时任务: crontab -l"
echo "编辑定时任务: crontab -e"
echo "删除定时任务: crontab -r"
echo ""
echo "📝 查看日志:"
echo "tail -f $PROJECT_DIR/cache_cleanup.log"
echo ""
echo "🧪 立即测试清理:"
echo "python $SCRIPT_DIR/cache_management.py info"
echo "python $SCRIPT_DIR/cache_management.py clean --type smart"
echo ""
echo "✅ 缓存定时清理设置完成！" 