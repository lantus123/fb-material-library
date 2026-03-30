# FB素材庫 — 優見補習班 Facebook 內容素材管理系統

自動蒐集教育文章、AI 分析篩選、一鍵生成 FB 貼文。

## 專案簡介

「FB素材庫」幫助優見補習班（天母/士林）自動化 Facebook 內容行銷流程：

1. **自動爬取**：定時從 Edutopia、MindShift 等 10+ 個國際教育網站蒐集最新文章
2. **AI 分析**：透過 Claude AI 分析每篇文章對國小國中家長的實用性，評分並分類
3. **素材庫管理**：分析結果自動存入 Google Sheets，方便查看與管理
4. **貼文生成**：從素材庫挑選文章，AI 自動生成符合品牌調性的 FB 貼文

## 快速開始

### 1. 安裝

```bash
git clone https://github.com/lantus123/fb-material-library.git
cd fb-material-library
pip install -r requirements.txt
```

### 2. 設定環境變數

```bash
cp .env.example .env
```

編輯 `.env` 檔案，填入：
- `ANTHROPIC_API_KEY`：你的 Claude API Key
- `APPS_SCRIPT_API_URL`：Google Apps Script Web App 的網址

### 3. 設定 Google Sheets

1. 建立一個新的 Google Sheets
2. 進入「擴充功能 → Apps Script」
3. 將 `apps-script/Code.gs` 的內容貼入
4. 部署為「網頁應用程式」，存取權限設為「任何人」
5. 將部署後的 URL 填入 `.env` 的 `APPS_SCRIPT_API_URL`

### 4. 執行

```bash
# 自動爬取文章並分析
python scripts/crawl.py

# 生成 FB 貼文（互動模式）
python scripts/generate_post.py

# 快速生成（自動選最佳素材）
python scripts/generate_post.py --quick
```

## 指令說明

### 爬取腳本 (crawl.py)

| 指令 | 說明 |
|------|------|
| `python scripts/crawl.py` | 自動爬取所有來源（最近7天） |
| `python scripts/crawl.py --days 14` | 自動爬取（最近14天） |
| `python scripts/crawl.py --url <URL>` | 手動爬取單一網址 |
| `python scripts/crawl.py --url <URL> 來源名稱` | 手動爬取並指定來源 |

### 貼文生成 (generate_post.py)

| 指令 | 說明 |
|------|------|
| `python scripts/generate_post.py` | 互動模式 |
| `python scripts/generate_post.py --quick` | 快速生成 |
| `python scripts/generate_post.py --quick 親子教養` | 指定主題快速生成 |
| `python scripts/generate_post.py --list` | 列出素材 |
| `python scripts/generate_post.py --stats` | 查看統計 |

## 爬取來源

### 自動爬取（RSS）

| 來源 | 焦點 |
|------|------|
| Edutopia | 教學方法、學習方法 |
| Parenting Science | 親子教養、學習方法 |
| Big Life Journal | 親子教養、成長心態 |
| The Learning Scientists | 學習科學 |
| MindShift (KQED) | 學習方法、教育趨勢 |
| Cult of Pedagogy | 教學方法 |
| TeachThought | 教學方法、教育趨勢 |
| Janet Lansbury | 親子教養 |
| Maggie Dent | 親子教養、學習方法 |
| Kimchi Mamas | 親子教養、亞洲觀點 |

### 手動輸入

支援 PTT、Facebook、X/Twitter、Threads、新聞網站等來源的手動輸入。

## 技術架構

```
Python 爬蟲 → Claude API 分析 → Apps Script API → Google Sheets
                                                        ↓
                   FB 貼文 ← Claude API 生成 ← 讀取素材庫
```

## 授權

MIT License
