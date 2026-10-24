#!/bin/bash
# ==============================================================
# 🎬 ShortDrama Downloader v3.4 - 啟動腳本
# ==============================================================

# 切換到腳本所在目錄
cd "$(dirname "$0")"

# 終端文字色彩
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${CYAN}${BOLD}"
echo "=========================================================="
echo "    🎬 ShortDrama Downloader v3.4 - 正在啟動服務...       "
echo "=========================================================="
echo -e "${NC}"

# 檢查虛擬環境
if [ -d ".venv" ] && [ -f ".venv/bin/activate" ]; then
    echo -e "${BLUE}ℹ️ 正在啟用本地虛擬環境 (.venv)...${NC}"
    source .venv/bin/activate
    PYTHON_CMD="python"
else
    PYTHON_CMD="python3"
fi

# 檢查是否已在運行
PORT=8765
RUNNING_PID=$(lsof -ti :$PORT 2>/dev/null)

if [ -n "$RUNNING_PID" ]; then
    echo -e "${YELLOW}⚠️ 發現短劇下載器已在背景運行 (PID: $RUNNING_PID, Port: $PORT)${NC}"
    echo -e "${GREEN}🌐 正在為您打開瀏覽器介面...${NC}"
    open "http://127.0.0.1:$PORT"
    echo ""
    echo -e "${BLUE}💡 若要停止服務，請雙擊運行「停止短劇下載器.command」${NC}"
    echo ""
    read -n 1 -s -r -p "按任意鍵關閉此視窗..."
    echo ""
    exit 0
fi

# 延遲 1.5 秒自動在瀏覽器打開網頁
(sleep 1.5 && open "http://127.0.0.1:$PORT") &

echo -e "${GREEN}🚀 服務即將啟動於: ${BOLD}http://127.0.0.1:$PORT${NC}"
echo -e "${BLUE}💡 提示：按下 ${YELLOW}Ctrl + C${BLUE} 即可安全停止服務，或直接關閉此視窗${NC}"
echo "----------------------------------------------------------"
echo ""

# 執行主程式
exec $PYTHON_CMD app.py
