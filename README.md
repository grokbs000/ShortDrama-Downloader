# 🎬 ShortDrama Downloader v3.4

> 通用短劇搜尋、媒體偵測、HLS/MP4 下載與批次任務工具  
> Python + FastAPI + Playwright + SQLite + FFmpeg

---

## 1. 專案定位

ShortDrama Downloader v3.4 的目標不是只做「貼 MP4 URL → 下載」。

它把短劇下載流程拆成幾個獨立層：

```text
短劇頁面 / 影片 URL
        │
        ▼
   Provider Layer
        │
        ▼
 Media Resolver
   ├── Direct MP4/WebM
   ├── HLS .m3u8
   └── DASH 偵測
        │
        ▼
 Quality Selector
        │
        ▼
 Download Queue
   ├── Direct Downloader
   └── FFmpeg
        │
        ▼
 Downloads / Library
        │
        ▼
 SQLite + History + CSV
```

這個架構是為了讓未來新增網站來源時，不必重新改寫整個下載器。

---

# 2. v3.4 目前功能

## Web UI

啟動後可透過瀏覽器操作：

- 偵測短劇頁面
- Playwright 自動監聽 Network Response
- 顯示媒體候選
- 選擇 MP4 / HLS
- 加入下載 Queue
- 批次加入多個 URL
- 查看下載進度
- 查看下載歷史
- CSV 匯出

預設：

```text
http://127.0.0.1:8765
```

---

## Direct Video

目前可以處理正常可取得的：

- MP4
- WebM
- 其他 `video/*` 單檔媒體

下載時會檢查：

- HTTP Status
- Content-Type
- HTML / JSON 誤抓
- 暫存 `.part` 檔案
- 最終檔案

---

## HLS

支援：

```text
.m3u8
```

可以解析 Master Playlist，例如：

```text
1080p
720p
480p
```

並支援：

```text
Best
1080p
720p
480p
```

選擇。

實際封裝交給 FFmpeg。

---

## Playwright 自動偵測

當只有短劇頁面 URL 時：

```text
短劇頁面
   ↓
Playwright
   ↓
正常瀏覽器
   ↓
Network Response
   ↓
MP4 / WebM / m3u8 / mpd
   ↓
Candidate scoring
```

工具會嘗試排除：

```text
thumbnail
cover
avatar
logo
poster
preview
trailer
teaser
advertisement
```

避免把縮圖、預告片或廣告當成正式影片。

---

# 3. 安全與使用範圍

本專案只處理使用者在正常瀏覽網站時已可取得、且有權下載的媒體來源。

**不提供也不實作：**

- DRM 破解
- CAPTCHA 繞過
- 登入限制繞過
- Cookie 竊取
- Token 破解
- Signed URL 破解
- 存取控制繞過
- 付費牆繞過

如果網站需要正常登入：

1. Playwright 開啟瀏覽器。
2. 使用者自行登入。
3. 正常播放影片。
4. 工具只觀察瀏覽器產生的媒體 Network Response。

如果網站仍然回傳 401 / 403 或媒體受 DRM 保護，工具會停止，不會嘗試繞過。

---

# 4. macOS 安裝

## 4.1 進入專案

```bash
cd ShortDrama-Downloader-v3.4
```

---

## 4.2 建立 Python 虛擬環境

建議 Python 3.10 或更新版本。

```bash
python3 -m venv .venv
```

啟用：

```bash
source .venv/bin/activate
```

成功後 Terminal 通常會看到：

```text
(.venv)
```

---

## 4.3 安裝 Python 套件

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

## 4.4 安裝 Playwright Chromium

```bash
python -m playwright install chromium
```

---

## 4.5 安裝 FFmpeg

macOS 建議使用 Homebrew：

```bash
brew install ffmpeg
```

確認：

```bash
ffmpeg -version
```

如果能看到版本資訊，就完成。

---

# 5. 啟動 Web UI

最簡單：

```bash
source .venv/bin/activate
python app.py
```

看到類似：

```text
Uvicorn running on http://127.0.0.1:8765
```

後，在 Chrome 開：

```text
http://127.0.0.1:8765
```

---

## 也可以使用啟動腳本

```bash
./start.sh
```

如果沒有執行權限：

```bash
chmod +x start.sh
./start.sh
```

---

# 6. 第一次使用：推薦流程

## Step 1 — 開啟 Web UI

```bash
python app.py
```

Chrome：

```text
http://127.0.0.1:8765
```

---

## Step 2 — 貼上短劇 Episode URL

例如：

```text
https://example.com/episode/1
```

貼到：

```text
① 偵測短劇頁面
```

按：

```text
Playwright 自動偵測
```

---

## Step 3 — 瀏覽器會開啟

如果網站要求：

- 登入
- 正常驗證
- 播放影片

請在開啟的瀏覽器完成。

不要關閉瀏覽器。

---

## Step 4 — 等待媒體來源

工具會尋找：

```text
MP4
WebM
HLS
DASH
```

結果可能例如：

```text
#1 direct score=150 video/mp4
#2 hls    score=60 application/vnd.apple.mpegurl
```

通常優先選擇分數較高且符合正式影片特徵的來源。

---

# 7. HLS 使用方式

如果偵測結果是：

```text
hls
```

代表網站主要使用：

```text
.m3u8
```

可以使用 HLS resolver。

CLI：

```bash
python cli.py hls "https://example.com/master.m3u8" --quality best
```

指定 1080p：

```bash
python cli.py hls "https://example.com/master.m3u8" --quality 1080p
```

指定輸出：

```bash
python cli.py hls \
  "https://example.com/master.m3u8" \
  --quality best \
  -o downloads/Episode_001.mp4
```

---

# 8. Direct MP4 使用方式

如果已經知道 MP4 URL：

```bash
python cli.py direct "https://example.com/video.mp4"
```

指定檔名：

```bash
python cli.py direct \
  "https://example.com/video.mp4" \
  -o downloads/Episode_001.mp4
```

---

# 9. 自動偵測 CLI

不用 Web UI 也可以：

```bash
python cli.py detect "https://example.com/episode/1"
```

輸出會類似：

```text
[1] direct  score=150 type=video/mp4
[2] hls     score=60  type=application/vnd.apple.mpegurl
```

---

# 10. 批次下載

Web UI 的：

```text
③ 批次加入
```

每一行放一個來源：

```text
https://example.com/ep1.m3u8
https://example.com/ep2.m3u8
https://example.com/ep3.m3u8
```

設定：

```text
劇名：My Drama
起始集數：1
品質：Best
```

按：

```text
加入批次
```

Queue 會建立：

```text
Episode 001
Episode 002
Episode 003
```

---

# 11. Queue 狀態

目前任務狀態包括：

```text
queued
running
completed
failed
cancelled
```

例如：

```text
ID   劇名       集數   品質   狀態        進度
1    My Drama   001    Best   completed   100%
2    My Drama   002    Best   running      63%
3    My Drama   003    Best   queued        0%
```

下載成功後會寫入 History。

---

# 12. 檔案位置

預設下載：

```text
downloads/
```

例如：

```text
downloads/
└── My Drama/
    ├── Episode_001.mp4
    ├── Episode_002.mp4
    └── Episode_003.mp4
```

資料庫：

```text
data/shortdrama.db
```

---

# 13. SQLite 資料

v3.4 已經建立以下資料表：

## dramas

儲存短劇：

```text
title
source
source_id
detail_url
cover_url
```

## episodes

儲存集數：

```text
drama_id
episode_number
title
page_url
duration
```

## media_sources

儲存媒體來源：

```text
url
kind
content_type
quality
width
height
fps
bitrate
size
score
source
referer
```

## tasks

下載任務：

```text
url
title
episode
quality
status
progress
output
error
```

## history

下載歷史：

```text
task_id
title
episode
output
status
created_at
```

---

# 14. CSV

Web UI 可以直接匯出：

```text
Tasks CSV
Episodes CSV
```

也可以從瀏覽器存取：

```text
/api/export/tasks.csv
```

以及：

```text
/api/export/episodes.csv
```

---

# 15. Provider 架構

v3.4 不把所有網站寫在 `app.py`。

Provider 放在：

```text
providers/
```

目前：

```text
providers/
├── base.py
├── generic.py
└── dramabos.py
```

---

## Generic Provider

用途：

```text
任何正常 HTTP/HTTPS 短劇頁面
```

交給：

```text
Playwright
+
Media Resolver
```

進行偵測。

---

## DramaBos Provider

位置：

```text
providers/dramabos.py
```

它是「可選的外部 Provider」。

需要自行設定：

```text
DRAMABOS_API_URL
DRAMABOS_API_KEY
```

沒有設定時，其他功能仍可以使用。

---

# 16. 環境設定

複製：

```bash
cp .env.example .env
```

目前支援：

```text
SHORTDRAMA_HOST=127.0.0.1
SHORTDRAMA_PORT=8765
SHORTDRAMA_DOWNLOAD_DIR=./downloads
SHORTDRAMA_DB=./data/shortdrama.db
DRAMABOS_API_URL=
DRAMABOS_API_KEY=
```

注意：

目前 `.env.example` 是設定範例；如果需要自動載入 `.env`，可在後續版本加入 `python-dotenv`。

---

# 17. 常見問題

## Q1：Playwright 沒有啟動

執行：

```bash
python -m playwright install chromium
```

再重新：

```bash
python app.py
```

---

## Q2：顯示 FFmpeg 未安裝

執行：

```bash
brew install ffmpeg
```

確認：

```bash
which ffmpeg
ffmpeg -version
```

---

## Q3：HTTP 403

403 不代表程式一定壞掉。

常見原因：

- URL 已過期
- 來源有時間限制
- 網站要求特定正常瀏覽器上下文
- 網站拒絕目前請求
- 來源需要正常登入
- 來源受到存取控制

正確做法：

1. 回到瀏覽器重新播放。
2. 重新偵測。
3. 使用新的媒體來源。

不應該嘗試破解 URL。

---

## Q4：偵測不到影片

先確認影片真的有開始播放。

建議：

```text
開啟瀏覽器
↓
登入（如果網站要求）
↓
進入 Episode
↓
按播放
↓
等待 5～15 秒
↓
查看偵測結果
```

有些播放器只有真正開始播放後才建立媒體 Request。

---

## Q5：只有 DASH

v3.4 可以辨識：

```text
.mpd
```

但目前不自動執行完整 DASH downloader。

因此看到：

```text
DASH
```

代表網站可能使用 DASH。

後續版本可以加入：

```text
DASH Resolver
+
FFmpeg
```

---

## Q6：下載下來不是影片

如果伺服器回傳：

```text
text/html
```

或：

```text
application/json
```

v3.4 會拒絕寫成影片檔。

這通常表示：

- URL 已失效
- 需要授權
- 回傳錯誤頁
- Session 已失效

---

# 18. 專案架構

```text
ShortDrama-Downloader-v3.4/
│
├── app.py
├── cli.py
├── requirements.txt
├── pyproject.toml
├── README.md
├── .env.example
├── .gitignore
├── start.sh
│
├── core/
│   ├── config.py
│   ├── db.py
│   └── models.py
│
├── providers/
│   ├── base.py
│   ├── generic.py
│   └── dramabos.py
│
├── resolver/
│   ├── detector.py
│   └── hls.py
│
├── downloader/
│   ├── direct.py
│   ├── ffmpeg.py
│   └── queue.py
│
├── exports/
│   └── csv_export.py
│
├── services/
│   └── tasks.py
│
├── web/
│   └── index.html
│
├── tests/
│   └── test_core.py
│
├── data/
│   └── shortdrama.db
│
└── downloads/
```

---

# 19. 設計原則

### 原則 1：Provider 與 Downloader 分離

網站怎麼取得影片：

```text
Provider
```

影片怎麼下載：

```text
Downloader
```

兩者不要混在一起。

---

### 原則 2：Resolver 與 Provider 分離

Provider 可以知道：

```text
這是哪個網站
```

Resolver 負責：

```text
這是 MP4 / HLS / DASH？
```

---

### 原則 3：HLS 不應該寫死 1080p

應該先解析：

```text
Master Playlist
```

再依實際存在的：

```text
1080p
720p
480p
```

做選擇。

---

### 原則 4：所有下載都經過 Queue

不要讓 Web Request 直接卡住整個 API。

流程：

```text
Web UI
 ↓
Create Task
 ↓
Queue
 ↓
Worker
 ↓
Downloader
```

---

### 原則 5：失敗必須可追蹤

每個任務都保留：

```text
status
progress
output
error
```

方便後續加入：

- retry
- resume
- scheduling
- notification

---

# 20. 測試

目前專案有：

```text
tests/test_core.py
```

可以執行：

```bash
python -m pytest
```

如果尚未安裝 pytest：

```bash
python -m pip install pytest
```

---

# 21. v3.4 與下一階段

v3.4 已經建立：

```text
✅ Web UI
✅ SQLite
✅ Provider architecture
✅ Generic Provider
✅ Playwright detector
✅ MP4/WebM
✅ HLS
✅ HLS quality selection
✅ FFmpeg
✅ Download Queue
✅ Batch
✅ History
✅ CSV
✅ DramaBos Provider skeleton
```

下一階段建議：

```text
v3.5
├── Provider Manager
├── 更多網站 Adapter
└── Drama / Episode 詳細資料

v3.6
├── 搜尋中心
├── 短劇 ID
├── 全選 / 區間選集
└── 批次 Episode 建立

v3.7
├── FFmpeg 真實進度
├── Retry
├── Resume
└── 更完整 HLS

v3.8
├── Library
├── 收藏
├── 重複檔案判斷
└── Metadata

v4.0
└── 完整短劇管理與下載平台
```

---

# 22. Git 使用建議

第一次建立 Git：

```bash
git init
git add .
git commit -m "feat: initialize ShortDrama Downloader v3.4"
```

之後修改：

```bash
git status
git add .
git commit -m "feat: improve downloader"
```

`.gitignore` 已經排除：

```text
.venv
.env
SQLite database
下載影片
Python cache
macOS .DS_Store
```

因此不要把：

```text
.env
```

或大量影片檔案提交到 Git。

---

# 23. 一分鐘快速開始

如果只想最快測試：

```bash
cd ShortDrama-Downloader-v3.4

python3 -m venv .venv
source .venv/bin/activate

python -m pip install -r requirements.txt
python -m playwright install chromium

brew install ffmpeg

python app.py
```

然後開：

```text
http://127.0.0.1:8765
```

貼入短劇 Episode URL：

```text
↓
Playwright 自動偵測
↓
選擇影片來源
↓
加入 Queue
↓
等待下載
↓
downloads/劇名/
```

---

## License / 使用責任

本專案是一個技術工具。

使用者應自行確認：

1. 對目標內容具有下載權利。
2. 遵守網站服務條款。
3. 遵守所在地的著作權及相關法律。
4. 不利用本工具繞過 DRM 或其他技術存取控制。

本專案採用 [MIT License](LICENSE) 授權發布。
本專案的設計目標是協助管理與下載使用者正常可取得、且有權保存的媒體內容。
