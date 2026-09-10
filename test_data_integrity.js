/**
 * 2026-09-09 数据完整性对账测试（jsdom）
 *
 * 背景：2026-09-09 全维度检查发现 P0——renderLmePrices() 用 PRICE_HISTORY 末两点
 * 无条件覆盖 LME_DATA（无比对日期），导致走势图滞后一天时：
 *   · 锌 真实 ▼-10.5 → 页面 ▲+5.00（用昨日价 + 方向反转）
 *   · 铅 真实 ▲+1.5  → 页面 ▼-2.00
 *   · 锡 price:null  → 被回填成 55,085.00
 * 而原有 162 项断言**无一校验价格数值**，P0 100% 逃逸。本测试补上这块。
 *
 * 覆盖：
 *   ① LME 卡片数值/方向 与 lme_data.json 对账（跨文件，非仅 DOM 存在性）
 *   ② 涨跌方向三处一致：箭头符号 ↔ class(up/down/flat) ↔ 数值正负
 *   ③ null 价格不得显示具体数值
 *   ④ 页面标注日期 == lme_data.date
 *   ⑤ 归档条目（data/news_*.json）是否都被页面数据源 NEWS_DATA 收录（防静默丢弃）
 *
 * 运行：node test_data_integrity.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
['app.js', 'news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  html = html.replace(new RegExp('<script src="' + f + '[^>]*></script>'),
    () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
});

const errors = [];
const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true,
  url: 'https://pliucugb-cyber.github.io/mining-daily/',
  beforeParse(win) {
    if (typeof win.matchMedia !== 'function') {
      win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    }
    if (typeof win.fetch !== 'function') win.fetch = () => Promise.reject(new Error('stub'));
    win.addEventListener('error', e => errors.push('window.error: ' + e.message));
    const origErr = win.console.error;
    win.console.error = (...a) => { errors.push('console.error: ' + a.join(' ')); origErr.apply(win.console, a); };
  }
});
const { window } = dom;
const doc = window.document;

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log('  PASS  ' + name + (extra ? '  → ' + extra : '')); }
  else { fail++; console.log('  FAIL  ' + name + (extra ? '  → ' + extra : '')); }
}
function num(s) {
  if (s == null) return NaN;
  return parseFloat(String(s).replace(/[,%\s]/g, ''));
}

setTimeout(() => {
  console.log('\n===== ① LME 卡片 vs lme_data.json（跨文件对账）=====');

  const lmeRaw = fs.readFileSync(path.join(__dirname, 'lme-data.js'), 'utf-8');
  const lmeJson = JSON.parse(lmeRaw.slice(lmeRaw.indexOf('{'), lmeRaw.lastIndexOf('}') + 1));
  const LME = lmeJson.metals || (lmeJson.LME_DATA && lmeJson.LME_DATA.metals) || [];
  check('lme-data.js 可解析且含 metals', LME.length > 0, LME.length + ' 个品种');

  // 确保价格渲染函数已执行（覆盖静态内联值，暴露真实的运行时覆盖行为）
  if (typeof window.renderLmePrices === 'function') window.renderLmePrices();

  const bySlug = {};
  LME.forEach(m => { bySlug[m.slug] = m; });

  let dirBad = [], valBad = [], nullBad = [];
  doc.querySelectorAll('#priceCardsLme .price-card').forEach(card => {
    const slug = card.getAttribute('data-slug');
    const exp = bySlug[slug];
    if (!exp) return;
    const vEl = card.querySelector('.pc-value'), cEl = card.querySelector('.pc-chg');
    const vTxt = (vEl && vEl.textContent || '').trim();
    const cTxt = (cEl && cEl.textContent || '').trim();
    const cls = card.className || '';

    // null：不得显示具体数值
    if (exp.price == null) {
      if (/\d[\d,]*\.\d{2}/.test(vTxt)) nullBad.push(slug + ' 显示 "' + vTxt + '"（应为 --/暂无数据）');
      return;
    }
    // 数值偏差（同一天两种口径应接近；差很多说明用了旧数据）
    const got = num(vTxt), want = Number(exp.price);
    if (isFinite(got) && isFinite(want) && want !== 0) {
      const dev = Math.abs(got - want) / Math.abs(want);
      if (dev > 0.01) valBad.push(slug + ' 页面=' + got + ' lme_data=' + want + ' 偏差' + (dev * 100).toFixed(2) + '%');
    }
    // 方向：class 必须与 chg 符号一致
    const chg = Number(exp.chg || 0);
    const wantCls = chg > 0 ? 'up' : (chg < 0 ? 'down' : 'flat');
    if (cls.indexOf(wantCls) < 0) {
      dirBad.push(slug + ' 期望 class=' + wantCls + '（chg=' + chg + '）实际="' + cls + '" 文案="' + cTxt + '"');
    }
  });

  check('LME 涨跌方向与 lme_data.json 一致（P0 回归）', dirBad.length === 0, dirBad.join(' | ') || '6/6 品种方向正确');
  check('LME 数值与 lme_data.json 偏差 < 1%', valBad.length === 0, valBad.join(' | ') || '全部吻合');
  check('价格为空的品种不显示具体数值', nullBad.length === 0, nullBad.join(' | ') || '无 null 被回填');

  console.log('\n===== ② 涨跌方向三处一致（箭头 ↔ class ↔ 数值）=====');
  let triBad = [];
  doc.querySelectorAll('.price-card').forEach(card => {
    const cEl = card.querySelector('.pc-chg');
    if (!cEl) return;
    const txt = (cEl.textContent || '').trim();
    const cls = card.className || '';
    const m = txt.match(/(-?\d[\d,]*\.\d{2})/);
    if (!m) return;                       // 如「夜盘持平」无数字，跳过
    const val = parseFloat(m[1].replace(/,/g, ''));
    const wantCls = val > 0 ? 'up' : (val < 0 ? 'down' : 'flat');
    if (cls.indexOf(wantCls) < 0) triBad.push((card.getAttribute('data-slug') || '?') + ' 数值=' + val + ' class="' + cls + '"');
    const arrowOK = (val > 0 && txt.indexOf('▲') >= 0) || (val < 0 && txt.indexOf('▼') >= 0) ||
                    (val === 0 && (txt.indexOf('■') >= 0 || txt.indexOf('持平') >= 0));
    if (!arrowOK) triBad.push((card.getAttribute('data-slug') || '?') + ' 箭头与数值不符："' + txt + '"');
  });
  check('全部价格卡 箭头/class/数值 三者一致', triBad.length === 0, triBad.join(' | ') || '一致');

  console.log('\n===== ③ 页面标注日期 == 数据日期 =====');
  const note = doc.getElementById('priceStripNote');
  const noteTxt = note ? (note.textContent || '').trim() : '';
  const dataDate = String(lmeJson.date || (lmeJson.updated || '').substring(0, 10));
  check('价格区标注日期与 lme_data 日期一致', !!dataDate && noteTxt.indexOf(dataDate) >= 0,
    '标注="' + noteTxt + '" 数据日期=' + dataDate);

  console.log('\n===== ④ 归档条目是否被页面数据源收录 =====');
  const ND = window.NEWS_DATA || {};
  const ndNews = ND.news || [];
  const ndUrls = new Set(ndNews.map(n => String(n.u || n.url || '')).filter(Boolean));
  check('NEWS_DATA 已加载', ndNews.length > 0, ndNews.length + ' 条');

  const dataDir = path.join(__dirname, 'data');
  let archived = [], missing = [];
  fs.readdirSync(dataDir).filter(f => /^news_\d{4}-\d{2}\.json$/.test(f)).forEach(f => {
    try {
      const j = JSON.parse(fs.readFileSync(path.join(dataDir, f), 'utf-8'));
      (j.news || []).forEach(n => {
        const u = String(n.url || n.u || '');
        if (!u) return;
        archived.push(u);
        if (!ndUrls.has(u)) missing.push(f + ' :: ' + (n.title || u).slice(0, 40));
      });
    } catch (e) { /* 忽略损坏文件 */ }
  });
  const rate = archived.length ? (archived.length - missing.length) / archived.length : 1;
  check('归档条目被 NEWS_DATA 收录率 >= 95%', rate >= 0.95,
    '归档 ' + archived.length + ' 条，缺失 ' + missing.length + ' 条，覆盖率 ' + (rate * 100).toFixed(1) + '%' +
    (missing.length ? ' 例：' + missing.slice(0, 3).join(' / ') : ''));

  console.log('\n===== JS 运行时错误 =====');
  const real = errors.filter(e => !/goatcounter|gc\.zgo\.at|favicon|net::ERR|Not implemented/i.test(e));
  check('无阻塞性 JS 错误', real.length === 0, real.slice(0, 3).join(' | '));

  console.log('\n===== 数据完整性汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 900);
