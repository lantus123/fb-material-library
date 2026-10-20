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
│   ├── 3_📋_貼文紀錄.py            # 歷史紀錄 + 回饋管理 + diff 分析
│   ├── 4_📊_統計儀表板.py          # 成效分析圖表 + 學習指標
│   ├── 5_📝_手動輸入.py            # 手動加入素材 + 寫法範本庫
│   └── 6_🧠_原則庫.py              # 修改原則庫 CRUD + 維護（階段 2）
├── apps-script/
│   └── Code.gs                     # Google Apps Script（素材庫 + 貼文紀錄）
├── config/
│   ├── sources.json                # 爬取來源清單（19 個來源）
│   └── brand.json                  # 品牌設定
├── prompts/
│   ├── analysis.md                 # 文章分析 prompt 模板
│   ├── copywriting.md              # 貼文生成 prompt 模板（含回饋注入）
│   └── diff_analysis.md            # 修改差異分析 prompt（萃取修改原則）
├── scripts/
│   ├── __init__.py
│   ├── sheets_api.py               # Google Sheets API 共用模組
│   ├── post_generator.py           # 貼文生成核心（含 few-shot 回饋 + diff 分析）
│   ├── metrics.py                  # 學習效果指標（每月 AI 初版→最終版 diff %）
│   ├── style_fingerprint.py        # 風格指紋（階段 3，量化特徵抽取）
│   ├── merge_principles.py         # 月度原則庫合併腳本（階段 2，cron 用）
│   ├── backup_sheets.sh            # 每週備份所有工作表為 CSV
│   ├── crawl.py                    # 爬取 + 分析腳本
│   ├── crawl_scheduled.sh          # 排程爬取（cron 用）
│   ├── generate_post.py            # CLI 貼文生成
│   ├── fb_api.py                   # Facebook Graph API 串接
│   ├── publish_ui.py               # 人工確認發布面板（生成頁／紀錄頁共用）
│   ├── start_web.sh                # 啟動 Streamlit 腳本
│   ├── test_model_compare.py       # 一次性：比較不同 Gemini model 的生成品質
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

### Facebook Graph API（`scripts/fb_api.py`）

- `POST /{page}/feed` — 發布文字貼文（可附連結）。
- `POST /{page}/photos` — 發布單張圖片（本機上傳或圖片網址）。
- 上述端點帶 `published=false`、`scheduled_publish_time` 可建立排程。
- `GET /{page}/scheduled_posts` — 列出排程中貼文。
- `DELETE /{post_id}` — 取消排程；網頁與 CLI 只允許取消 `scheduled` 紀錄。
- 既有 `GET /{page}/published_posts`、`GET /{post_id}` 與 `/insights` 維持成效讀取。

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

Streamlit Cloud 要在 secrets 加 `FB_PAGE_ID`、`FB_PAGE_ACCESS_TOKEN`。
設定於呼叫時讀取，優先使用 Streamlit secrets，再使用本專案 `.env` 環境設定；
Page Token 需具備 `pages_manage_posts` 權限。未設定時，發布面板只顯示設定提示。

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

### FB 成效更新與發布

```bash
python scripts/fb_api.py --refresh    # 批次更新所有 FB 成效
python scripts/fb_api.py --match      # 自動比對 FB 貼文
python scripts/fb_api.py --publish 12  # 預覽第 12 列並確認立即發布
python scripts/fb_api.py --publish 12 --at "2026-11-09 20:00" --image ./photo.jpg
python scripts/fb_api.py --publish 12 --image https://example.com/photo.png --yes
python scripts/fb_api.py --scheduled  # 列出排程中貼文（台北時間）
python scripts/fb_api.py --cancel 12  # 取消第 12 列的排程
```

網頁儲存後可立即發布或排程發布，支援單圖，必須先勾「我已看過內容，確認發布」。
CLI 先印出全文、時間與圖片；沒有 `--yes` 時，TTY 必須回答 `y`，非 TTY 直接以 exit code 2 拒絕。
排程採台北時間，限距現在 10 分鐘至 28 天（含邊界）；這是依實測採用的保守窗，
範例日期需依執行日調整。排程交由 Facebook 執行，沒有新增自動發布排程器。
發文成功但 Sheet 回寫失敗會顯示貼文 ID，請人工補登，不要重發。
取消排程保留原貼文 ID 與預定時間。發布寫入的 ID 可直接供 `--refresh` 更新成效。
發布狀態記錄本次操作結果，不會自動輪詢 Facebook 改寫狀態；排程時間已到時，
取消入口會拒絕刪除，避免把可能已公開的貼文當排程刪掉，請到粉專確認。

## 回饋系統

系統內建「生成 → 發佈 → 回饋 → 改善」閉環：

1. **生成時評分**：每篇貼文可打 1-5 星 + 備註
2. **FB 成效追蹤**：記錄按讚、留言、分享、觸及數
3. **自動學習**：生成新貼文時，自動將過去表現最好的 3 篇作為 few-shot 範例注入 prompt
4. **加權排序**：主觀評分 30% + 互動數據 70%
5. **Diff 學習（階段 1）**：貼文紀錄頁面保留 AI 原版，使用者編輯後可按「🔍 分析差異並學習」呼叫 Gemini 萃取一條「修改原則」存回 Sheet；亦可一鍵退回原版；並可勾選修改原因標籤讓分析更精準。
6. **原則庫回灌（階段 2）**：diff 分析萃取的原則會同時寫入獨立的「修改原則」工作表；生成新貼文時，`build_prompt` 自動拉取啟用中的原則注入 prompt（`{{principles}}` 區塊），形成閉環。機制：
   - 冷啟動門檻：啟用中原則 < 5 條時不注入（避免 AI 以為規則就這麼點）
   - Prompt 預算：單次最多注入 10 條
   - 主題優先：若當下 `post_type` 有相關原則，優先取同主題
   - 衰減：超過 90 天未被引用的自動標為 `archived`（lazy decay）
   - A/B 對照 few-shot：`get_top_posts` 若貼文有編輯版，會在 prompt 中並列顯示「AI 初版 ❌ → 最終版 ✅」
   - 迴音室防線：`get_top_posts` 權重改為「主觀評分 60% + 互動 40%」、強制每個 `post_type` 至少取 1 篇
   - 月度合併：`scripts/merge_principles.py` 透過 Gemini 自動合併相似原則，合併前快照到 `logs/principles_snapshots/`
7. **風格指紋 + TTL 快取（階段 3）**：
   - `scripts/style_fingerprint.py` 從「post_type + 評分 ≥4」的樣本抽取量化特徵（平均字數、emoji 密度、問句比例、開頭型態、hashtag 數、段落數、句長）
   - 樣本門檻：每主題 ≥3 篇才計算；`build_prompt` 依當下 `post_type` 注入對應指紋（`{{style_fingerprint}}` 區塊）
   - 指紋呈現為「統計趨勢」而非「硬性規則」，衝突時以內容為優先
   - `sheets_api.py` 新增 TTL cache（預設 60 秒）包住 `get_post_records` / `get_all_principles` / `get_style_examples`，寫入函式自動 invalidate；主要為避免 gspread 每分鐘配額爆掉
   - 儀表板新增「🎨 各主題風格指紋」區塊，顯示每個主題的量化特徵

### 貼文紀錄 Sheet 欄位

`貼文紀錄` 工作表在階段 1 新增三個欄位：
- `原始內容`（col 14）— AI 生成版本，不可變，作為 diff 分析基準
- `修改原因`（col 15）— 使用者勾選的標籤，以 `|` 分隔
- `修改原則`（col 16）— Gemini 分析 diff 後萃取的一條原則（原始 raw 輸出，同步寫入 `修改原則` 工作表）
- `發布狀態`（col 17）— 空白＝未發布；`published`／`scheduled`／`cancelled`／`failed`
- `發布時間`（col 18）— ISO 8601；立即發布為當下時間，排程為預定時間，取消保留原排程時間

既有 col 1–16 保持不變；`_get_or_create_sheet` 會在表頭不一致時擴欄並更新整列表頭，
不需另跑遷移腳本。Apps Script 的 `POST_HEADERS` 同步鏡像，發布邏輯由 Python 處理。

### 修改原則 Sheet 欄位（階段 2 新增）

`修改原則` 工作表 schema：
- col 1-4：建立時間 / 類型（正向/負向）/ 原則 / 理由
- col 5-6：來源貼文（貼文紀錄 row 號或「手動」）/ 主題
- col 7-8：使用次數（生成時被注入 +1）/ 最後引用時間
- col 9-10：狀態（active/disabled/archived）/ 備註

### 學習指標

`python3 scripts/metrics.py` 會計算每月「AI 初版 → 最終版」平均字數差異 %。若學習迴路有效，這個數字應隨月份下降。做任何 prompt 或 model 變動後，此為核心驗證指標。

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
7. AI 引擎使用 Google Gemini（免費方案），透過 `google-genai` SDK。**生成模型預設為 `gemini-2.5-pro`**（env var `GEMINI_MODEL`），flash 僅作為成本敏感備援
8. Streamlit 密碼存在 `.streamlit/secrets.toml`（已 .gitignore）
9. `prompts/copywriting.md` 頂端有**輸出格式鐵則**，禁止 AI 回應加「好的」「以下是」等 meta 前綴。修改 prompt 時切勿刪除此區塊
10. Google Sheet 備份：`scripts/backup_sheets.sh` 建議設 cron `0 3 * * 0` 每週日凌晨執行，保留最近 12 份備份於 `logs/backups/YYYY-MM-DD/`

## 待開發功能

- [x] 排程自動爬取（cron + shell wrapper + flock + email 通知）
- [x] 支援中文來源的爬取（親子天下、翻轉教育、未來Family、教育部、聯合報）
- [x] 素材去重機制（URL 正規化 + 標題相似度 + Apps Script 端防重複）
- [x] Web UI（Streamlit 管理介面 + 密碼保護）
- [x] 回饋系統（評分 + FB 成效追蹤 + few-shot 學習）
- [x] Facebook Graph API 串接（成效數據自動蒐集）
- [x] 階段 0/1：升級 Pro + meta 前綴禁止 + 保留原版 + diff 萃取修改原則 + 學習指標 + 備份腳本
- [x] 階段 2：修改原則庫（CRUD/衰減/月度合併）+ A/B 對照 few-shot + 冷啟動門檻 + prompt 預算 + 主題平衡
- [x] 階段 3：風格指紋量化特徵 + 主題分群注入 + TTL cache（避免 gspread 配額爆掉）
- [ ] 階段 4：Self-critique 迴圈 + 多版本生成 + 多樣性保護
- [x] 貼文排程發佈（Facebook Graph API publish）
- [ ] 圖片素材生成
