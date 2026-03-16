#!/usr/bin/env bash
# =============================================================
# MSPBots SQL Gateway Dashboard — 一键部署脚本 (Linux)
# 适用系统：Ubuntu 20.04+ / Debian 11+ / CentOS 8+
# 用法：
#   chmod +x deploy_linux.sh
#   sudo ./deploy_linux.sh            # 以 root 执行（推荐）
#   ./deploy_linux.sh                 # 普通用户（自动用 sudo 提权）
# =============================================================

set -euo pipefail

# ─── 可修改配置 ───────────────────────────────────────────
APP_DIR="/opt/pg_proxy"            # 应用部署目录
SERVICE_USER="pgproxy"             # 运行服务的系统用户
SERVICE_NAME="pgproxy-dashboard"   # systemd 服务名
PYTHON_MIN="3.9"                   # 最低 Python 版本
LISTEN_HOST="0.0.0.0"             # Dashboard 监听地址（0.0.0.0 允许外部访问）
LISTEN_PORT="5000"                 # Dashboard 监听端口
# ──────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOLD='\033[1m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }
section() { echo -e "\n${BOLD}━━━ $* ━━━${NC}"; }

# 非 root 时给 sudo 前缀
SUDO=""
[[ $EUID -ne 0 ]] && SUDO="sudo"

# ─── 1. 检查系统 ──────────────────────────────────────────
section "1. 系统检查"

# 检测包管理器
if command -v apt-get &>/dev/null; then
    PKG_MGR="apt-get"
    PKG_INSTALL="$SUDO apt-get install -y"
    $SUDO apt-get update -qq
elif command -v dnf &>/dev/null; then
    PKG_MGR="dnf"
    PKG_INSTALL="$SUDO dnf install -y"
elif command -v yum &>/dev/null; then
    PKG_MGR="yum"
    PKG_INSTALL="$SUDO yum install -y"
else
    error "未找到支持的包管理器（apt/dnf/yum），请手动安装依赖。"
fi
info "包管理器: $PKG_MGR"

# ─── 2. 安装系统依赖 ──────────────────────────────────────
section "2. 安装系统依赖"

if [[ "$PKG_MGR" == "apt-get" ]]; then
    $PKG_INSTALL python3 python3-pip python3-venv python3-dev \
                 libpq-dev gcc curl git
else
    $PKG_INSTALL python3 python3-pip python3-devel \
                 postgresql-devel gcc curl git
fi

# 检查 Python 版本
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Python 版本: $PY_VER"
python3 -c "
import sys
min_v = tuple(int(x) for x in '${PYTHON_MIN}'.split('.'))
if sys.version_info[:2] < min_v:
    print(f'Python >= ${PYTHON_MIN} required, got {sys.version_info[:2]}')
    sys.exit(1)
" || error "Python 版本不满足要求（需要 >= ${PYTHON_MIN}）"

# ─── 3. 创建系统用户 ──────────────────────────────────────
section "3. 创建服务用户"

if ! id "$SERVICE_USER" &>/dev/null; then
    $SUDO useradd -r -s /sbin/nologin -d "$APP_DIR" "$SERVICE_USER"
    info "已创建用户: $SERVICE_USER"
else
    info "用户已存在: $SERVICE_USER"
fi

# ─── 4. 部署应用文件 ──────────────────────────────────────
section "4. 部署应用文件"

$SUDO mkdir -p "$APP_DIR"

# 需要部署的核心文件列表
DEPLOY_FILES=(
    "web_dashboard.py"
    "dashboard.html"
    "config.yaml"
    "collect_gateway_sql_resource_usage.py"
    "requirements_web.txt"
)

for f in "${DEPLOY_FILES[@]}"; do
    if [[ -f "$SCRIPT_DIR/$f" ]]; then
        $SUDO cp "$SCRIPT_DIR/$f" "$APP_DIR/$f"
        info "已复制: $f"
    else
        warn "文件不存在，跳过: $f"
    fi
done

# 可选 SQL 文件
for sql in "$SCRIPT_DIR"/*.sql; do
    [[ -f "$sql" ]] && $SUDO cp "$sql" "$APP_DIR/" && info "已复制: $(basename $sql)"
done

$SUDO chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"
info "目录权限已设置: $APP_DIR"

# ─── 5. Python 虚拟环境 & 依赖 ────────────────────────────
section "5. 安装 Python 依赖"

VENV_DIR="$APP_DIR/venv"

if [[ ! -d "$VENV_DIR" ]]; then
    $SUDO -u "$SERVICE_USER" python3 -m venv "$VENV_DIR"
    info "虚拟环境已创建: $VENV_DIR"
fi

# 安装 web 依赖 + psycopg2
$SUDO -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install --upgrade pip -q
$SUDO -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install \
    flask flask-cors psycopg2-binary pyyaml requests -q
info "Python 依赖安装完成"

# 如果有 requirements_web.txt 也一并安装
if [[ -f "$APP_DIR/requirements_web.txt" ]]; then
    $SUDO -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install \
        -r "$APP_DIR/requirements_web.txt" -q 2>/dev/null || true
fi

# ─── 6. 修改监听地址为 0.0.0.0 ───────────────────────────
section "6. 调整监听配置"

# 将 web_dashboard.py 里 host='127.0.0.1' 改为允许外部访问
if grep -q "host='127.0.0.1'" "$APP_DIR/web_dashboard.py"; then
    $SUDO sed -i "s/host='127\.0\.0\.1'/host='${LISTEN_HOST}'/g" "$APP_DIR/web_dashboard.py"
    info "已将监听地址改为: ${LISTEN_HOST}:${LISTEN_PORT}"
fi

# ─── 7. 创建 systemd 服务 ─────────────────────────────────
section "7. 配置 systemd 服务"

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

$SUDO tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=MSPBots SQL Gateway Dashboard
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${VENV_DIR}/bin/python web_dashboard.py
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

# 资源限制
LimitNOFILE=65536

# 环境变量
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

$SUDO systemctl daemon-reload
$SUDO systemctl enable "$SERVICE_NAME"
info "systemd 服务已注册: $SERVICE_NAME"

# ─── 8. 配置防火墙 ────────────────────────────────────────
section "8. 防火墙配置"

if command -v ufw &>/dev/null; then
    $SUDO ufw allow "$LISTEN_PORT"/tcp 2>/dev/null && \
        info "UFW: 已开放端口 $LISTEN_PORT" || warn "UFW 规则添加失败，请手动开放端口 $LISTEN_PORT"
elif command -v firewall-cmd &>/dev/null; then
    $SUDO firewall-cmd --permanent --add-port="${LISTEN_PORT}/tcp" 2>/dev/null && \
    $SUDO firewall-cmd --reload 2>/dev/null && \
        info "firewalld: 已开放端口 $LISTEN_PORT" || warn "firewalld 规则添加失败，请手动开放端口 $LISTEN_PORT"
else
    warn "未检测到 UFW/firewalld，请手动确认端口 $LISTEN_PORT 已放行"
fi

# ─── 9. 启动服务 ──────────────────────────────────────────
section "9. 启动服务"

# 如果服务已在运行则重启
if $SUDO systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    $SUDO systemctl restart "$SERVICE_NAME"
    info "服务已重启"
else
    $SUDO systemctl start "$SERVICE_NAME"
    info "服务已启动"
fi

# 等待启动
sleep 3

if $SUDO systemctl is-active --quiet "$SERVICE_NAME"; then
    info "服务运行正常 ✓"
else
    warn "服务可能未正常启动，查看日志："
    $SUDO journalctl -u "$SERVICE_NAME" -n 20 --no-pager
fi

# ─── 10. 完成 ─────────────────────────────────────────────
section "部署完成"

# 获取本机 IP
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "YOUR_SERVER_IP")

echo ""
echo -e "${BOLD}访问地址：${NC}"
echo -e "  本机:   ${GREEN}http://localhost:${LISTEN_PORT}${NC}"
echo -e "  局域网: ${GREEN}http://${LOCAL_IP}:${LISTEN_PORT}${NC}"
echo ""
echo -e "${BOLD}常用命令：${NC}"
echo "  查看状态:  sudo systemctl status $SERVICE_NAME"
echo "  查看日志:  sudo journalctl -u $SERVICE_NAME -f"
echo "  重启服务:  sudo systemctl restart $SERVICE_NAME"
echo "  停止服务:  sudo systemctl stop $SERVICE_NAME"
echo ""
echo -e "${BOLD}配置文件：${NC} ${APP_DIR}/config.yaml"
echo ""
