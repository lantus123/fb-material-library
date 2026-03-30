const SHEET_NAME = '素材庫';
const HEADERS = [
  '收錄時間', '標題', '摘要', '主題標籤', '可用角度', '關鍵事實',
  '相關性分數', '相關性原因', '來源URL', '來源標題', '原文摘錄', '已使用'
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
    default:
      result = { error: 'Unknown action', availableActions: ['getMaterials', 'getStats'] };
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
    default:
      result = { success: false, error: 'Unknown action' };
  }
  return ContentService
    .createTextOutput(JSON.stringify(result))
    .setMimeType(ContentService.MimeType.JSON);
}

function handleAddMaterial(data) {
  try {
    const sheet = initSheet();
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
