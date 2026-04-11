# CLAUDE.md — FB素材庫 專案上下文

## 專案概述

「FB素材庫」是優見補習班的 Facebook 內容素材自動蒐集與管理系統。系統自動爬取國內外教育網站的優質文章，透過 Gemini AI 分析其對目標受眾的價值，儲存至 Google Sheets 素材庫，並能根據素材自動生成符合品牌調性的 FB 貼文。內建回饋系統，讓生成品質隨使用越來越好。

## 架構

```
Python 爬蟲腳本
    ↓ (爬取文章)
Gemini API (分析文章)
    ↓ (結構化資料)
Google Apps Script API
    ↓ (儲存)
Google Sheets (素材庫 + 貼文紀錄)
    ↓ (讀取素材 + 歷史回饋)
Gemini API (生成貼文，含 few-shot 範例)
    ↓
Streamlit Web UI (瀏覽/生成/回饋/統計)
    ↓
FB 貼文輸出
```

## 目錄結構

```
fb-material-library/
├── app.py                          # Streamlit Web UI 入口（含密碼驗證）
├── pages/
│   ├── auth.py                     # 共用密碼驗證模組
│   ├── 1_📚_素材庫瀏覽.py          # 瀏覽/篩選素材
│   ├── 2_✏️_貼文生成.py            # 生成/編輯/評分/儲存貼文
│   ├── 3_📋_貼文紀錄.py            # 歷史紀錄 + 回饋管理
│   └── 4_📊_統計儀表板.py          # 成效分析圖表
├── apps-script/
│   └── Code.gs                     # Google Apps Script（素材庫 + 貼文紀錄）
├── config/
│   ├── sources.json                # 爬取來源清單（19 個來源）
│   └── brand.json                  # 品牌設定
├── prompts/
│   ├── analysis.md                 # 文章分析 prompt 模板
│   └── copywriting.md              # 貼文生成 prompt 模板（含回饋注入）
├── scripts/
│   ├── __init__.py
│   ├── sheets_api.py               # Google Sheets API 共用模組
│   ├── post_generator.py           # 貼文生成核心（含 few-shot 回饋）
│   ├── crawl.py                    # 爬取 + 分析腳本
│   ├── crawl_scheduled.sh          # 排程爬取（cron 用）
│   ├── generate_post.py            # CLI 貼文生成
│   ├── fb_api.py                   # Facebook Graph API 串接
│   ├── start_web.sh                # 啟動 Streamlit 腳本
│   └── fb-material-streamlit.service # systemd 服務檔（備用）
├── .streamlit/
│   ├── config.toml                 # Streamlit 設定
│   └── secrets.toml                # 密碼（.gitignore）
├── logs/                           # 排程 log + Streamlit log
├── .env                            # 環境變數（.gitignore）
├── .env.example                    # 環境變數範本
├── .gitignore
├── requirements.txt                # Python 依賴
├── CLAUDE.md                       # 本檔案
└── README.md                       # 專案說明
```

## API 端點

### Apps Script Web App

Base URL 存在 `.env` 的 `APPS_SCRIPT_API_URL`

**GET 請求（素材庫）：**
- `?action=getMaterials` — 取得素材清單（可選：topic、limit）
- `?action=getStats` — 取得統計資料
- `?action=getExistingUrls` — 取得已存 URL 和標題（重複偵測用）

**GET 請求（貼文紀錄）：**
- `?action=getPostRecords` — 取得貼文紀錄（可選：limit）
- `?action=getTopPosts` — 取得表現最好的貼文（加權排序，可選：limit）

**POST 請求（素材庫）：**
- `action: "addMaterial"` — 新增素材
- `action: "markUsed"` — 標記素材為已使用
- `action: "sendReport"` — 寄送爬取報告 email

**POST 請求（貼文紀錄）：**
- `action: "addPostRecord"` — 儲存生成的貼文
- `action: "updatePostMetrics"` — 更新 FB 成效數據
- `action: "updatePostRating"` — 更新評分和備註

## 如何執行

### 環境設定

```bash
cp .env.example .env
# 編輯 .env 填入 GEMINI_API_KEY
pip install -r requirements.txt
```

### Web UI（主要使用方式）

```bash
# 啟動 Streamlit
bash scripts/start_web.sh

# 或手動啟動
streamlit run app.py
```

部署入口：

- **Streamlit Cloud（主要）**：https://fb-material-library.streamlit.app
- **自架 GCP VM**：http://35.201.163.220:8501

兩者都需要密碼登入。

### 自動爬取

```bash
# 爬取所有來源（最近7天）
python scripts/crawl.py

# 排程模式（完成後寄 email 報告）
python scripts/crawl.py --scheduled

# 手動爬取單一網址
python scripts/crawl.py --url https://example.com/article "來源名稱"
```

### 排程設定

```bash
# 每週一、四早上 8 點自動爬取
crontab -e
0 8 * * 1,4 /home/r19911219/fb-material-library/scripts/crawl_scheduled.sh
```

### CLI 貼文生成（備用）

```bash
python scripts/generate_post.py              # 互動模式
python scripts/generate_post.py --quick      # 快速生成
python scripts/generate_post.py --stats      # 查看統計
```

### FB 成效更新

```bash
python scripts/fb_api.py --refresh    # 批次更新所有 FB 成效
python scripts/fb_api.py --match      # 自動比對 FB 貼文
```

## 回饋系統

系統內建「生成 → 發佈 → 回饋 → 改善」閉環：

1. **生成時評分**：每篇貼文可打 1-5 星 + 備註
2. **FB 成效追蹤**：記錄按讚、留言、分享、觸及數
3. **自動學習**：生成新貼文時，自動將過去表現最好的 3 篇作為 few-shot 範例注入 prompt
4. **加權排序**：主觀評分 30% + 互動數據 70%

## 品牌指南

- **品牌名稱**：優見補習班
- **位置**：天母/士林
- **對象**：國小國中學生的家長
- **語氣**：親切專業，像鄰居大姊姊聊天
- **五大主題**：升學資訊、親子教養、學習方法、教育政策趨勢、在地學區資訊
- **禁忌**：簡體中文、恐嚇式行銷、過度推銷、太學術化

## 開發注意事項

1. **所有面向使用者的文字必須使用繁體中文**
2. Python 腳本的 print 訊息使用繁體中文 + emoji
3. 爬取時注意 rate limiting，每篇文章間隔至少 2 秒
4. 相關性分數 < 5 的文章不會自動存入素材庫
5. Apps Script 部署方式：在 Google Sheets 的 Extensions → Apps Script 中貼入 Code.gs，部署為 Web App
6. 部署時權限選「Anyone」才能讓外部腳本呼叫
7. AI 引擎使用 Google Gemini（免費方案），透過 `google-genai` SDK
8. Streamlit 密碼存在 `.streamlit/secrets.toml`（已 .gitignore）

## 待開發功能

- [x] 排程自動爬取（cron + shell wrapper + flock + email 通知）
- [x] 支援中文來源的爬取（親子天下、翻轉教育、未來Family、教育部、聯合報）
- [x] 素材去重機制（URL 正規化 + 標題相似度 + Apps Script 端防重複）
- [x] Web UI（Streamlit 管理介面 + 密碼保護）
- [x] 回饋系統（評分 + FB 成效追蹤 + few-shot 學習）
- [x] Facebook Graph API 串接（成效數據自動蒐集）
- [ ] 貼文排程發佈（Facebook Graph API publish）
- [ ] 圖片素材生成
