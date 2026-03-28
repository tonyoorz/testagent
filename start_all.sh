#!/usr/bin/env zsh
# ============================================================
# PreAnalysis 项目一键启动脚本
# 
# 使用方法：
#   chmod +x start_all.sh
#   ./start_all.sh             # 启动所有服务
#   ./start_all.sh dashboard   # 只启动主看板
#   ./start_all.sh openclaw    # 只启动 OpenClaw
#   ./start_all.sh stop        # 停止所有服务
#   ./start_all.sh status      # 查看服务状态
# ============================================================

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目路径
SCRIPT_DIR="$(cd "$(dirname "${(%):-%x}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
LOG_DIR="$PROJECT_DIR/logs"

# OpenClaw 相关
OPENCLAW_BIN="$HOME/.npm-global/bin/openclaw"
OPENCLAW_CC_DIR="$HOME/WorkBuddy/openclaw-control-center"
NVM_DIR="$HOME/.nvm"

# 日志目录
mkdir -p "$LOG_DIR"

# ============================================================
# 工具函数
# ============================================================

log_info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
log_section() { echo -e "\n${BLUE}==== $1 ====${NC}"; }

check_port() {
    local port=$1
    lsof -i ":$port" > /dev/null 2>&1
}

wait_for_port() {
    local port=$1
    local name=$2
    local max_wait=${3:-15}
    local count=0
    while ! check_port "$port" && [ $count -lt $max_wait ]; do
        sleep 1
        count=$((count + 1))
    done
    if check_port "$port"; then
        log_info "✅ $name 已就绪 (端口 $port)"
        return 0
    else
        log_warn "⚠️ $name 启动超时 (端口 $port)"
        return 1
    fi
}

# ============================================================
# 加载 nvm（Node.js 环境）
# ============================================================

load_nvm() {
    if [ -s "$NVM_DIR/nvm.sh" ]; then
        source "$NVM_DIR/nvm.sh" 2>/dev/null
        nvm use v22.16.0 > /dev/null 2>&1
        return 0
    fi
    return 1
}

# ============================================================
# 启动函数
# ============================================================

start_openclaw_gateway() {
    log_section "OpenClaw Gateway"
    if check_port 18789; then
        log_info "Gateway 已在运行 (端口 18789)"
        return 0
    fi
    load_nvm
    if [ ! -f "$OPENCLAW_BIN" ]; then
        log_warn "openclaw 未安装，跳过 Gateway"
        return 1
    fi
    "$OPENCLAW_BIN" gateway > "$LOG_DIR/openclaw-gateway.log" 2>&1 &
    echo $! > "$LOG_DIR/openclaw-gateway.pid"
    wait_for_port 18789 "OpenClaw Gateway"
}

start_openclaw_control_center() {
    log_section "OpenClaw Control Center"
    if check_port 4310; then
        log_info "Control Center 已在运行 (端口 4310)"
        return 0
    fi
    if [ ! -d "$OPENCLAW_CC_DIR" ]; then
        log_warn "Control Center 目录不存在: $OPENCLAW_CC_DIR，跳过"
        return 1
    fi
    load_nvm
    cd "$OPENCLAW_CC_DIR"
    npm run dev:ui > "$LOG_DIR/openclaw-cc.log" 2>&1 &
    echo $! > "$LOG_DIR/openclaw-cc.pid"
    wait_for_port 4310 "Control Center"
    cd "$PROJECT_DIR"
}

start_main_dashboard() {
    log_section "主看板 (defect_explore.py)"
    if check_port 8051; then
        log_info "主看板已在运行 (端口 8051)"
        return 0
    fi
    cd "$PROJECT_DIR"
    python3 defect_explore.py > "$LOG_DIR/main-dashboard.log" 2>&1 &
    echo $! > "$LOG_DIR/main-dashboard.pid"
    wait_for_port 8051 "主看板" 20
}

start_risk_analysis() {
    log_section "风险分析看板 (risk_analysis.py)"
    if check_port 8057; then
        log_info "风险分析已在运行 (端口 8057)"
        return 0
    fi
    cd "$PROJECT_DIR"
    python3 risk_analysis.py > "$LOG_DIR/risk-analysis.log" 2>&1 &
    echo $! > "$LOG_DIR/risk-analysis.pid"
    wait_for_port 8057 "风险分析" 15
}

start_code_interpreter() {
    log_section "Code Interpreter API"
    if check_port 8080; then
        log_info "Code Interpreter 已在运行 (端口 8080)"
        return 0
    fi
    cd "$PROJECT_DIR"
    python3 -m uvicorn code_interpreter_agent.api:app --host 0.0.0.0 --port 8080 > "$LOG_DIR/code-interpreter.log" 2>&1 &
    echo $! > "$LOG_DIR/code-interpreter.pid"
    wait_for_port 8080 "Code Interpreter" 10
}

# ============================================================
# 停止函数
# ============================================================

stop_all() {
    log_section "停止所有服务"
    
    # 按 PID 文件停止
    for pid_file in "$LOG_DIR"/*.pid; do
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file")
            name=$(basename "$pid_file" .pid)
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null
                log_info "已停止 $name (PID $pid)"
            fi
            rm -f "$pid_file"
        fi
    done
    
    # 强制关闭占用端口的进程
    for port in 8051 8057 8080 4310 18789; do
        pid=$(lsof -t -i ":$port" 2>/dev/null)
        if [ -n "$pid" ]; then
            kill "$pid" 2>/dev/null
            log_info "已关闭端口 $port 的进程 (PID $pid)"
        fi
    done
    
    log_info "所有服务已停止"
}

# ============================================================
# 状态检查
# ============================================================

status_all() {
    log_section "服务状态"
    
    services=(
        "OpenClaw Gateway:18789"
        "OpenClaw Control Center:4310"
        "主看板:8051"
        "风险分析:8057"
        "Code Interpreter:8080"
        "测试覆盖率:8055"
        "缺陷矩阵:8053"
        "缺陷长跑:8062"
    )
    
    for service_port in "${services[@]}"; do
        name="${service_port%%:*}"
        port="${service_port##*:}"
        if check_port "$port"; then
            echo -e "  ${GREEN}●${NC} $name (端口 $port) - 运行中"
        else
            echo -e "  ${RED}○${NC} $name (端口 $port) - 未运行"
        fi
    done
    
    echo ""
    log_info "访问地址："
    echo "  主看板:             http://127.0.0.1:8051"
    echo "  风险分析:           http://127.0.0.1:8057"
    echo "  Code Interpreter:   http://127.0.0.1:8080/docs"
    echo "  Mission Control:    http://127.0.0.1:4310"
}

# ============================================================
# 主逻辑
# ============================================================

case "${1:-all}" in
    "all")
        log_section "启动 PreAnalysis 所有服务"
        start_openclaw_gateway
        start_openclaw_control_center
        start_main_dashboard
        # start_risk_analysis      # 按需取消注释
        # start_code_interpreter   # 按需取消注释
        echo ""
        status_all
        ;;
    "dashboard")
        start_main_dashboard
        ;;
    "openclaw")
        start_openclaw_gateway
        start_openclaw_control_center
        ;;
    "risk")
        start_risk_analysis
        ;;
    "code-interpreter")
        start_code_interpreter
        ;;
    "stop")
        stop_all
        ;;
    "status")
        status_all
        ;;
    "restart")
        stop_all
        sleep 2
        exec "$0" all
        ;;
    *)
        echo "用法: $0 [all|dashboard|openclaw|risk|code-interpreter|stop|status|restart]"
        exit 1
        ;;
esac
