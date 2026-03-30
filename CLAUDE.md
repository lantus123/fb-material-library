# CLAUDE.md — FB素材庫 專案上下文

## 專案概述

「FB素材庫」是優見補習班的 Facebook 內容素材自動蒐集與管理系統。系統自動爬取國內外教育網站的優質文章，透過 Claude AI 分析其對目標受眾的價值，儲存至 Google Sheets 素材庫，並能根據素材自動生成符合品牌調性的 FB 貼文。

## 架構

```
Python 爬蟲腳本
    ↓ (爬取文章)
Claude API (分析文章)
    ↓ (結構化資料)
Google Apps Script API
    ↓ (儲存)
Google Sheets (素材庫)
    ↓ (讀取素材)
Claude API (生成貼文)
    ↓
FB 貼文輸出
```

## 目錄結構

```
fb-material-library/
├── apps-script/
│   └── Code.gs              # Google Apps Script（部署在 Google Sheets 上）
├── config/
│   ├── sources.json          # 爬取來源清單
│   └── brand.json            # 品牌設定（語氣、主題、hashtag）
├── prompts/
│   ├── analysis.md           # 文章分析 prompt 模板
│   └── copywriting.md        # 貼文生成 prompt 模板
├── scripts/
│   ├── crawl.py              # 爬取 + 分析腳本
│   └── generate_post.py      # 貼文生成腳本
├── .env.example              # 環境變數範本
├── .gitignore
├── requirements.txt          # Python 依賴
├── CLAUDE.md                 # 本檔案
└── README.md                 # 專案說明
```

## API 端點

### Apps Script Web App

Base URL 存在 `.env` 的 `APPS_SCRIPT_API_URL`

**GET 請求：**

- `?action=getMaterials` — 取得素材清單
  - 可選參數：`topic`（主題篩選）、`limit`（筆數限制，預設10）
  - 回傳：`{ materials: [...] }`

- `?action=getStats` — 取得統計資料
  - 回傳：`{ total, thisWeek, highRelevance, byTopic, lastUpdated }`

**POST 請求：**

- `action: "addMaterial"` — 新增素材
  - 欄位：title, summary, topics[], angles[], key_facts[], relevance_score, relevance_reason, source_url, source_title, raw_text
  - 回傳：`{ success: true, row: N, total: N }`

- `action: "markUsed"` — 標記素材為已使用
  - 欄位：row（列號）
  - 回傳：`{ success: true }`

## 如何執行

### 環境設定

```bash
cp .env.example .env
# 編輯 .env 填入 ANTHROPIC_API_KEY
pip install -r requirements.txt
```

### 自動爬取

```bash
# 爬取所有 RSS 來源（最近7天）
python scripts/crawl.py

# 指定天數
python scripts/crawl.py --days 14

# 手動爬取單一網址
python scripts/crawl.py --url https://example.com/article "來源名稱"
```

### 生成貼文

```bash
# 互動模式（選素材 → 選類型 → 生成）
python scripts/generate_post.py

# 快速模式（自動選最佳素材）
python scripts/generate_post.py --quick

# 指定主題快速生成
python scripts/generate_post.py --quick 親子教養

# 查看統計
python scripts/generate_post.py --stats
```

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

## 待開發功能

- [ ] 排程自動爬取（Cloud Scheduler 或 cron）
- [ ] 支援中文來源的爬取（親子天下等）
- [ ] 貼文排程發佈（Facebook Graph API）
- [ ] 素材去重機制（避免重複爬取同一篇文章）
- [ ] Web UI（用 Streamlit 或 Flask 做管理介面）
- [ ] 圖片素材生成
