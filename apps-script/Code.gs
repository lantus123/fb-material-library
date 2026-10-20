const SHEET_NAME = '素材庫';
const HEADERS = [
  '收錄時間', '標題', '摘要', '主題標籤', '可用角度', '關鍵事實',
  '相關性分數', '相關性原因', '來源URL', '來源標題', '原文摘錄', '已使用'
];

const POST_SHEET_NAME = '貼文紀錄';
const POST_HEADERS = [
  '生成時間', '素材標題', '素材列號', '貼文類型', '貼文內容',
  '主觀評分', '備註', 'FB貼文ID', '按讚數', '留言數',
  '分享數', '觸及人數', '最後更新',
  '原始內容', '修改原因', '修改原則',
  '發布狀態', '發布時間'
];

const STYLE_SHEET_NAME = '寫法範本';
const STYLE_HEADERS = [
  '收錄時間', '標題', '原文內容', '寫法亮點', '來源URL', '標籤'
];

function initSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
  }
  const firstRow = sheet.getRange(1, 1, 1, HEADERS.length).getValues()[0];
  if (firstRow[0] !== HEADERS[0]) {
    sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
    sheet.getRange(1, 1, 1, HEADERS.length).setFontWeight('bold');
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function initPostSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(POST_SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(POST_SHEET_NAME);
  }
  const firstRow = sheet.getRange(1, 1, 1, POST_HEADERS.length).getValues()[0];
  if (firstRow[0] !== POST_HEADERS[0]) {
    sheet.getRange(1, 1, 1, POST_HEADERS.length).setValues([POST_HEADERS]);
    sheet.getRange(1, 1, 1, POST_HEADERS.length).setFontWeight('bold');
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function initStyleSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(STYLE_SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(STYLE_SHEET_NAME);
  }
  const firstRow = sheet.getRange(1, 1, 1, STYLE_HEADERS.length).getValues()[0];
  if (firstRow[0] !== STYLE_HEADERS[0]) {
    sheet.getRange(1, 1, 1, STYLE_HEADERS.length).setValues([STYLE_HEADERS]);
    sheet.getRange(1, 1, 1, STYLE_HEADERS.length).setFontWeight('bold');
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function doGet(e) {
  const action = e.parameter.action;
  let result;
  switch (action) {
    case 'getMaterials':
      result = handleGetMaterials(e.parameter);
      break;
    case 'getStats':
      result = handleGetStats();
      break;
    case 'getExistingUrls':
      result = handleGetExistingUrls();
      break;
    case 'getPostRecords':
      result = handleGetPostRecords(e.parameter);
      break;
    case 'getTopPosts':
      result = handleGetTopPosts(e.parameter);
      break;
    case 'getStyleExamples':
      result = handleGetStyleExamples(e.parameter);
      break;
    default:
      result = { error: 'Unknown action', availableActions: ['getMaterials', 'getStats', 'getExistingUrls', 'getPostRecords', 'getTopPosts', 'getStyleExamples'] };
  }
  return ContentService
    .createTextOutput(JSON.stringify(result))
    .setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  let data;
  try {
    data = JSON.parse(e.postData.contents);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ success: false, error: 'Invalid JSON' }))
      .setMimeType(ContentService.MimeType.JSON);
  }
  let result;
  switch (data.action) {
    case 'addMaterial':
      result = handleAddMaterial(data);
      break;
    case 'markUsed':
      result = handleMarkUsed(data.row);
      break;
    case 'sendReport':
      result = handleSendReport(data);
      break;
    case 'addPostRecord':
      result = handleAddPostRecord(data);
      break;
    case 'updatePostMetrics':
      result = handleUpdatePostMetrics(data);
      break;
    case 'updatePostRating':
      result = handleUpdatePostRating(data);
      break;
    case 'updatePostContent':
      result = handleUpdatePostContent(data);
      break;
    case 'addStyleExample':
      result = handleAddStyleExample(data);
      break;
    default:
      result = { success: false, error: 'Unknown action' };
  }
  return ContentService
    .createTextOutput(JSON.stringify(result))
    .setMimeType(ContentService.MimeType.JSON);
}

// ─── 素材庫 handlers ──────────────────────────────────────

function handleAddMaterial(data) {
  try {
    const sheet = initSheet();
    // 重複偵測：檢查 source_url 是否已存在
    const sourceUrl = (data.source_url || '').replace(/\/+$/, '');
    if (sourceUrl) {
      const lastRow = sheet.getLastRow();
      if (lastRow > 1) {
        const existingUrls = sheet.getRange(2, 9, lastRow - 1, 1).getValues().flat();
        const normalizedExisting = existingUrls.map(u => (u || '').toString().replace(/\/+$/, ''));
        if (normalizedExisting.includes(sourceUrl)) {
          return { success: false, error: 'duplicate', message: '此 URL 已存在素材庫中' };
        }
      }
    }
    const row = [
      data.curated_at || new Date().toISOString(),
      data.title || '',
      data.summary || '',
      (data.topics || []).join(', '),
      (data.angles || []).join(' | '),
      (data.key_facts || []).join(' | '),
      data.relevance_score || 0,
      data.relevance_reason || '',
      data.source_url || '',
      data.source_title || '',
      (data.raw_text || '').substring(0, 500),
      'N'
    ];
    sheet.appendRow(row);
    const lastRow = sheet.getLastRow();
    const score = data.relevance_score || 0;
    if (score >= 9) {
      sheet.getRange(lastRow, 7).setBackground('#c6efce');
    } else if (score >= 7) {
      sheet.getRange(lastRow, 7).setBackground('#ffeb9c');
    } else if (score <= 3) {
      sheet.getRange(lastRow, 7).setBackground('#ffc7ce');
    }
    return { success: true, row: lastRow, total: lastRow - 1 };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

function handleGetMaterials(params) {
  try {
    const sheet = initSheet();
    const lastRow = sheet.getLastRow();
    if (lastRow <= 1) return { materials: [] };
    const data = sheet.getRange(2, 1, lastRow - 1, HEADERS.length).getValues();
    const topic = params.topic || null;
    const limit = parseInt(params.limit) || 10;
    let materials = data.map((row, idx) => ({
      row_number: idx + 2,
      curated_at: row[0],
      title: row[1],
      summary: row[2],
      topics: row[3] ? row[3].split(', ') : [],
      angles: row[4] ? row[4].split(' | ') : [],
      key_facts: row[5] ? row[5].split(' | ') : [],
      relevance_score: row[6],
      relevance_reason: row[7],
      source_url: row[8],
      source_title: row[9],
      used: row[11] === 'Y'
    }));
    if (topic) {
      materials = materials.filter(m =>
        m.topics.some(t => t.includes(topic))
      );
    }
    materials.sort((a, b) => {
      if (a.used !== b.used) return a.used ? 1 : -1;
      return (b.relevance_score || 0) - (a.relevance_score || 0);
    });
    return { materials: materials.slice(0, limit) };
  } catch (error) {
    return { materials: [], error: error.message };
  }
}

function handleGetStats() {
  try {
    const sheet = initSheet();
    const lastRow = sheet.getLastRow();
    if (lastRow <= 1) {
      return { total: 0, thisWeek: 0, highRelevance: 0, byTopic: {}, lastUpdated: 'N/A' };
    }
    const data = sheet.getRange(2, 1, lastRow - 1, HEADERS.length).getValues();
    const now = new Date();
    const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    let thisWeek = 0;
    let highRelevance = 0;
    const byTopic = {};
    let lastDate = '';
    data.forEach(row => {
      const date = new Date(row[0]);
      if (date >= weekAgo) thisWeek++;
      if (row[6] >= 8) highRelevance++;
      const topics = row[3] ? row[3].split(', ') : [];
      topics.forEach(t => {
        byTopic[t] = (byTopic[t] || 0) + 1;
      });
      if (row[0]) lastDate = row[0];
    });
    return { total: data.length, thisWeek, highRelevance, byTopic, lastUpdated: lastDate };
  } catch (error) {
    return { error: error.message };
  }
}

function handleMarkUsed(rowNumber) {
  try {
    const sheet = initSheet();
    sheet.getRange(rowNumber, 12).setValue('Y');
    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

function handleGetExistingUrls() {
  try {
    const sheet = initSheet();
    const lastRow = sheet.getLastRow();
    if (lastRow <= 1) return { urls: [], titles: [] };
    const data = sheet.getRange(2, 1, lastRow - 1, HEADERS.length).getValues();
    const urls = data.map(row => (row[8] || '').toString());
    const titles = data.map(row => (row[1] || '').toString());
    return { urls: urls, titles: titles };
  } catch (error) {
    return { urls: [], titles: [], error: error.message };
  }
}

function handleSendReport(data) {
  try {
    const recipient = data.email || 'r19911219@gmail.com';
    const subject = data.subject || 'FB素材庫 — 爬取報告';
    const body = data.body || '（無內容）';
    MailApp.sendEmail({
      to: recipient,
      subject: subject,
      htmlBody: body,
    });
    return { success: true, message: '報告已寄出' };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

// ─── 貼文紀錄 handlers ──────────────────────────────────────

function handleAddPostRecord(data) {
  try {
    const sheet = initPostSheet();
    const row = [
      data.generated_at || new Date().toISOString(),
      data.material_title || '',
      data.material_row || '',
      data.post_type || '一般',
      data.post_content || '',
      data.rating || 0,
      data.notes || '',
      data.fb_post_id || '',
      data.likes || 0,
      data.comments || 0,
      data.shares || 0,
      data.reach || 0,
      ''
    ];
    sheet.appendRow(row);
    const lastRow = sheet.getLastRow();
    // 評分顏色標記
    const rating = data.rating || 0;
    if (rating >= 4) {
      sheet.getRange(lastRow, 6).setBackground('#c6efce');
    } else if (rating <= 2 && rating > 0) {
      sheet.getRange(lastRow, 6).setBackground('#ffc7ce');
    }
    return { success: true, row: lastRow, total: lastRow - 1 };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

function handleGetPostRecords(params) {
  try {
    const sheet = initPostSheet();
    const lastRow = sheet.getLastRow();
    if (lastRow <= 1) return { records: [] };
    const data = sheet.getRange(2, 1, lastRow - 1, POST_HEADERS.length).getValues();
    const limit = parseInt(params.limit) || 50;
    let records = data.map((row, idx) => ({
      row_number: idx + 2,
      generated_at: row[0],
      material_title: row[1],
      material_row: row[2],
      post_type: row[3],
      post_content: row[4],
      rating: row[5],
      notes: row[6],
      fb_post_id: row[7],
      likes: row[8],
      comments: row[9],
      shares: row[10],
      reach: row[11],
      last_updated: row[12]
    }));
    // 最新的排前面
    records.reverse();
    return { records: records.slice(0, limit) };
  } catch (error) {
    return { records: [], error: error.message };
  }
}

function handleGetTopPosts(params) {
  try {
    const sheet = initPostSheet();
    const lastRow = sheet.getLastRow();
    if (lastRow <= 1) return { posts: [] };
    const data = sheet.getRange(2, 1, lastRow - 1, POST_HEADERS.length).getValues();
    const limit = parseInt(params.limit) || 3;
    let posts = data.map((row, idx) => ({
      row_number: idx + 2,
      material_title: row[1],
      post_type: row[3],
      post_content: row[4],
      rating: row[5] || 0,
      likes: row[8] || 0,
      comments: row[9] || 0,
      shares: row[10] || 0,
      reach: row[11] || 0
    }));
    // 只考慮有評分的貼文
    posts = posts.filter(p => p.rating > 0);
    if (posts.length === 0) return { posts: [] };
    // 計算互動總分的最大值（用於正規化）
    const maxEngagement = Math.max(1, ...posts.map(p => p.likes + p.comments * 2 + p.shares * 3));
    // 加權排序：主���評分 30% + 互���數據 70%
    posts.forEach(p => {
      const engagementScore = (p.likes + p.comments * 2 + p.shares * 3) / maxEngagement * 5;
      // 如果沒有 FB 數據，純用主觀評分
      if (p.likes === 0 && p.comments === 0 && p.shares === 0) {
        p.composite_score = p.rating;
      } else {
        p.composite_score = p.rating * 0.3 + engagementScore * 0.7;
      }
    });
    posts.sort((a, b) => b.composite_score - a.composite_score);
    return { posts: posts.slice(0, limit) };
  } catch (error) {
    return { posts: [], error: error.message };
  }
}

function handleUpdatePostMetrics(data) {
  try {
    const sheet = initPostSheet();
    const row = data.row;
    if (!row) return { success: false, error: '缺少 row 參數' };
    if (data.fb_post_id !== undefined) sheet.getRange(row, 8).setValue(data.fb_post_id);
    if (data.likes !== undefined) sheet.getRange(row, 9).setValue(data.likes);
    if (data.comments !== undefined) sheet.getRange(row, 10).setValue(data.comments);
    if (data.shares !== undefined) sheet.getRange(row, 11).setValue(data.shares);
    if (data.reach !== undefined) sheet.getRange(row, 12).setValue(data.reach);
    sheet.getRange(row, 13).setValue(new Date().toISOString());
    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

function handleUpdatePostRating(data) {
  try {
    const sheet = initPostSheet();
    const row = data.row;
    if (!row) return { success: false, error: '缺少 row 參數' };
    if (data.rating !== undefined) {
      sheet.getRange(row, 6).setValue(data.rating);
      // 評分顏色標記
      if (data.rating >= 4) {
        sheet.getRange(row, 6).setBackground('#c6efce');
      } else if (data.rating <= 2) {
        sheet.getRange(row, 6).setBackground('#ffc7ce');
      } else {
        sheet.getRange(row, 6).setBackground(null);
      }
    }
    if (data.notes !== undefined) sheet.getRange(row, 7).setValue(data.notes);
    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

function handleUpdatePostContent(data) {
  try {
    const sheet = initPostSheet();
    const row = data.row;
    if (!row) return { success: false, error: '缺少 row 參數' };
    if (data.post_content !== undefined) sheet.getRange(row, 5).setValue(data.post_content);
    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

// ─── 寫法範本 handlers ──────────────────────────────────────

function handleAddStyleExample(data) {
  try {
    const sheet = initStyleSheet();
    const row = [
      data.created_at || new Date().toISOString(),
      data.title || '',
      data.content || '',
      data.highlights || '',
      data.source_url || '',
      (data.tags || []).join(', ')
    ];
    sheet.appendRow(row);
    const lastRow = sheet.getLastRow();
    return { success: true, row: lastRow, total: lastRow - 1 };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

function handleGetStyleExamples(params) {
  try {
    const sheet = initStyleSheet();
    const lastRow = sheet.getLastRow();
    if (lastRow <= 1) return { examples: [] };
    const data = sheet.getRange(2, 1, lastRow - 1, STYLE_HEADERS.length).getValues();
    const limit = parseInt(params.limit) || 20;
    let examples = data.map((row, idx) => ({
      row_number: idx + 2,
      created_at: row[0],
      title: row[1],
      content: row[2],
      highlights: row[3],
      source_url: row[4],
      tags: row[5] ? row[5].split(', ') : []
    }));
    examples.reverse();
    return { examples: examples.slice(0, limit) };
  } catch (error) {
    return { examples: [], error: error.message };
  }
}
