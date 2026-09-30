#!/usr/bin/env bash
# =============================================================================
# build_mac.sh — Air Mouse macOS 一键构建脚本
# 运行方式：在终端中 cd 到 "Air Mouse Python APP" 文件夹，执行：
#   chmod +x build_mac.sh && ./build_mac.sh
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/../AirMouse"
VENV="$HERE/.venv"
DIST="$HERE/dist"
APP_PATH="$DIST/Air Mouse.app"
DMG_PATH="$DIST/Air Mouse.dmg"

# ── 颜色输出 ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}▸ $*${NC}"; }
success() { echo -e "${GREEN}✓ $*${NC}"; }
warn()    { echo -e "${YELLOW}⚠ $*${NC}"; }
error()   { echo -e "${RED}✗ $*${NC}"; exit 1; }

echo ""
echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   Air Mouse macOS 打包构建工具       ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

# ── 检查前置条件 ──────────────────────────────────────────────────────────────
info "检查运行环境..."

# 必须在 macOS 上运行
if [[ "$(uname)" != "Darwin" ]]; then
    error "此脚本只能在 macOS 上运行。"
fi
success "macOS $(sw_vers -productVersion)"

# Python 3.9+
if ! command -v python3 &>/dev/null; then
    error "未找到 python3。请先安装 Python 3.11（推荐）：https://www.python.org/downloads/"
fi
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 9 ]]; then
    error "需要 Python 3.9 或更高版本（当前：$PY_VER）"
fi
success "Python $PY_VER"

# 检查 AirMouse 源码存在
if [[ ! -d "$SRC/airmouse" ]]; then
    error "找不到 AirMouse 源码目录：$SRC/airmouse\n请确保 'AirMouse' 文件夹与 'Air Mouse Python APP' 在同一目录下。"
fi
success "AirMouse 源码目录已找到"

# ── 虚拟环境 ──────────────────────────────────────────────────────────────────
info "配置 Python 虚拟环境..."
if [[ ! -d "$VENV" ]]; then
    python3 -m venv "$VENV"
    success "虚拟环境已创建：$VENV"
else
    success "复用已有虚拟环境"
fi
source "$VENV/bin/activate"

# ── 安装依赖 ──────────────────────────────────────────────────────────────────
info "更新 pip..."
pip install --upgrade pip --quiet

info "安装项目依赖（首次可能需要几分钟）..."
pip install -r "$SRC/requirements.txt" --quiet
success "项目依赖安装完成"

info "安装 PyInstaller..."
pip install "pyinstaller>=6.0" --quiet
success "PyInstaller 已就绪"

# ── 生成应用图标 ──────────────────────────────────────────────────────────────
info "生成应用图标..."
mkdir -p "$HERE/assets"
if python3 "$HERE/create_icon.py"; then
    success "图标生成完成"
else
    warn "图标生成失败，将使用系统默认图标（不影响功能）"
fi

# ── 清理上次构建产物 ──────────────────────────────────────────────────────────
info "清理旧构建文件..."
rm -rf "$HERE/build" "$HERE/dist"
success "清理完成"

# ── 运行 PyInstaller ──────────────────────────────────────────────────────────
info "运行 PyInstaller 打包（这一步需要较长时间，请耐心等待）..."
cd "$HERE"
pyinstaller AirMouse.spec --clean --noconfirm
success "PyInstaller 打包完成"

# 验证 .app 存在
if [[ ! -d "$APP_PATH" ]]; then
    error "打包失败：未找到 $APP_PATH"
fi

# ── 代码签名 ──────────────────────────────────────────────────────────────────
info "尝试对应用进行签名（临时签名，无需开发者账号）..."
if codesign \
    --force \
    --deep \
    --sign - \
    --entitlements "$HERE/entitlements.plist" \
    --options runtime \
    "$APP_PATH" 2>/dev/null; then
    success "临时签名完成"
else
    warn "签名失败，跳过。首次运行时 macOS 会显示「未知开发者」提示，请右键→打开来绕过。"
fi

# ── 打包 DMG ──────────────────────────────────────────────────────────────────
info "制作 DMG 安装镜像..."
[[ -f "$DMG_PATH" ]] && rm "$DMG_PATH"

hdiutil create \
    -volname "Air Mouse" \
    -srcfolder "$APP_PATH" \
    -ov \
    -format UDZO \
    "$DMG_PATH" \
    > /dev/null

success "DMG 制作完成"

# ── 完成 ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          🎉  构建成功！               ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "  📦 App 包：${CYAN}$APP_PATH${NC}"
echo -e "  💿 DMG 文件：${CYAN}$DMG_PATH${NC}"
echo ""
echo -e "  ${YELLOW}安装方法：${NC}"
echo -e "  1. 双击打开 Air Mouse.dmg"
echo -e "  2. 将 Air Mouse.app 拖入「应用程序」文件夹"
echo -e "  3. 首次打开时右键点击 → 打开（绕过未知开发者提示）"
echo -e "  4. 在「系统设置 → 隐私与安全性 → 辅助功能」中授权 Air Mouse"
echo ""
