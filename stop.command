#!/bin/bash
# ==============================================================
# 🛑 ShortDrama Downloader v3.4 - 中止腳本
# ==============================================================

cd "$(dirname "$0")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${CYAN}${BOLD}"
echo "=========================================================="
echo "    🛑 ShortDrama Downloader v3.4 - 正在停止服務...       "
echo "=========================================================="
echo -e "${NC}"

PORT=8765
KILLED=0

# 1. 根據 Port 8765 尋找佔用行程
PORT_PIDS=$(lsof -ti :$PORT 2>/dev/null)
if [ -n "$PORT_PIDS" ]; then
    for PID in $PORT_PIDS; do
        echo -e "${YELLOW}🔍 發現佔用 Port $PORT 的進程 (PID: $PID)，正在優雅關閉...${NC}"
        kill "$PID" 2>/dev/null
        KILLED=1
    done
fi

# 2. 根據命令名稱尋找 app.py 行程
APP_PIDS=$(pgrep -f "python.*app\.py" 2>/dev/null)
if [ -n "$APP_PIDS" ]; then
    for PID in $APP_PIDS; do
        echo -e "${YELLOW}🔍 發現正在執行的 app.py 進程 (PID: $PID)，正在終止...${NC}"
        kill "$PID" 2>/dev/null
        KILLED=1
    done
fi

if [ $KILLED -eq 0 ]; then
    echo -e "${GREEN}✨ 目前沒有正在運行的 ShortDrama Downloader 服務。${NC}"
else
    # 等待 1.5 秒讓進程完整完成 WAL Checkpoint
    sleep 1.5
    
    # 再次檢查是否已完全關閉
    RECHECK=$(lsof -ti :$PORT 2>/dev/null)
    if [ -n "$RECHECK" ]; then
        echo -e "${RED}⚠️ 進程仍在運行，執行強制終止 (kill -9)...${NC}"
        kill -9 $RECHECK 2>/dev/null
    fi
    echo -e "${GREEN}${BOLD}✅ ShortDrama Downloader 服務已成功完全終止！${NC}"
fi

echo ""
echo "----------------------------------------------------------"
echo -e "${CYAN}💡 3 秒後自動關閉視窗...${NC}"
sleep 3
exit 0
