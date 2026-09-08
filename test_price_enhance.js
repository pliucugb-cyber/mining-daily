/**
 * 2026-09-08 价格区增强功能测试（jsdom）
 * 覆盖：① 今日异动排行条 ② 「昨」角标 ③ 按涨跌排序开关 ④ 热榜热度条
 * 运行：node test_price_enhance.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
['news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  html = html.replace(new RegExp('<script src="' + f + '"></script>'),
    '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
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
  if (cond) { pass++; console.log('  PASS  ' + name); }
  else { fail++; console.log('  FAIL  ' + name + (extra ? '  -> ' + extra : '')); }
}

setTimeout(() => {
  console.log('\n===== 价格区增强 =====');
  // 确保增强脚本已跑（价格数据异步渲染后需重跑）
  if (typeof window.__mdPriceEnhance === 'function') window.__mdPriceEnhance();
  const doc2 = window.document;

  // ① 异动排行条
  const tm = doc2.getElementById('priceTopMovers');
  check('① 排行条已生成', !!tm);
  if (tm) {
    const txt = tm.textContent || '';
    const pcts = txt.match(/[+-]\d+\.\d\d%/g) || [];
    check('① 含 2~3 个涨跌幅', pcts.length >= 2 && pcts.length <= 3, txt.trim().slice(0, 80));
    const ups = (tm.querySelectorAll('.mv.up') || []).length;
    const downs = (tm.querySelectorAll('.mv.down') || []).length;
    check('① 涨/跌方向类名正确（有涨有跌）', ups + downs === pcts.length && ups >= 1, 'up=' + ups + ' down=' + downs);
    // 数值正确性：最大涨幅应等于所有卡里的最大 pct
    const all = [];
    ['priceCardsShfe', 'priceCardsLme'].forEach(id => {
      const w = doc2.getElementById(id);
      if (!w) return;
      w.querySelectorAll('.price-card').forEach(c => {
        const m = ((c.querySelector('.pc-chg') || {}).textContent || '').match(/(-?\d+(?:\.\d+)?)\s*%/);
        if (m) all.push(parseFloat(m[1]));
      });
    });
    const maxPct = Math.max.apply(null, all);
    check('① 最大涨幅与卡内数据一致', txt.indexOf((maxPct > 0 ? '+' : '') + maxPct.toFixed(2) + '%') >= 0,
      'max=' + maxPct.toFixed(2) + '% | 条=' + txt.trim().slice(0, 60));
  }

  // ② 昨角标
  const stale = doc2.querySelectorAll('.price-card.stale');
  check('② 存在「昨」角标卡片', stale.length >= 1, 'count=' + stale.length);
  if (stale.length) {
    const nm = (stale[0].querySelector('.pc-name') || {}).textContent || '';
    const chg = (stale[0].querySelector('.pc-chg') || {}).textContent || '';
    check('② 角标卡片确实无当日涨跌幅', !/(-?\d+(\.\d+)?)\s*%/.test(chg), chg.slice(0, 30));
    check('② 角标不污染 textContent（CSV/预警安全）', !/昨/.test(nm + chg), nm.trim() + ' | ' + chg.trim());
  }

  // ③ 排序开关
  const bar = doc2.getElementById('priceSortBar');
  check('③ 排序条已生成', !!bar);
  const btns = bar ? bar.querySelectorAll('.sortbtn') : [];
  check('③ 两个排序按钮', btns.length === 2);
  const shfe = doc2.getElementById('priceCardsShfe');
  const before = Array.prototype.slice.call(shfe.querySelectorAll('.price-card'))
    .map(c => ((c.querySelector('.pc-chg') || {}).textContent || ''));
  if (btns.length === 2) {
    btns[1].dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    const after = Array.prototype.slice.call(shfe.querySelectorAll('.price-card'));
    const pcts = after.map(c => {
      const m = ((c.querySelector('.pc-chg') || {}).textContent || '').match(/(-?\d+(?:\.\d+)?)\s*%/);
      return m ? (c.classList.contains('down') ? -Math.abs(parseFloat(m[1])) : parseFloat(m[1])) : -999;
    });
    let sorted = true;
    for (let i = 1; i < pcts.length; i++) if (pcts[i] > pcts[i - 1] + 1e-9) sorted = false;
    check('③ 点击后按涨跌幅降序', sorted, pcts.join(','));
    check('③ 排序后带名次属性 data-rank', after[0].getAttribute('data-rank') === '1',
      'rank=' + after[0].getAttribute('data-rank'));
    check('③ 排序后卡片数不变', after.length === before.length, after.length + ' vs ' + before.length);
    btns[0].dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    const back = Array.prototype.slice.call(shfe.querySelectorAll('.price-card'))
      .map(c => ((c.querySelector('.pc-chg') || {}).textContent || ''));
    check('③ 切回默认顺序可还原', JSON.stringify(back) === JSON.stringify(before));
    check('③ 还原后无 data-rank', !shfe.querySelector('.price-card[data-rank]'));
  }

  // ⑤ 工具行布局（异动条/排序开关不得挤进标题行，防折行）
  const toolbar = doc2.querySelector('#priceStrip .price-toolbar');
  check('⑤ 工具行容器已生成', !!toolbar);
  if (toolbar) {
    check('⑤ 异动条在工具行内', toolbar.contains(doc2.getElementById('priceTopMovers')));
    check('⑤ 排序开关在工具行内', toolbar.contains(doc2.getElementById('priceSortBar')));
    const head = doc2.querySelector('#priceStrip .price-strip-head');
    check('⑤ 标题行内无异动条/排序开关', head && !head.querySelector('.top-movers') && !head.querySelector('.sortbar'));
  }

  // ④ 热榜热度条
  const bars = doc2.querySelectorAll('#hotListBody .hot-bar i');
  check('④ 热榜热度条已生成', bars.length >= 1, 'count=' + bars.length);
  if (bars.length >= 2) {
    const w1 = parseFloat(bars[0].style.width), w2 = parseFloat(bars[1].style.width);
    check('④ 热度条递减（首条最热）', w1 >= w2, w1 + '% -> ' + w2 + '%');
    check('④ 热度条宽度在 40~100%', w1 >= 40 && w1 <= 100, w1 + '%');
  }

  // 无阻塞性 JS 错误
  check('无阻塞性 JS 错误', errors.length === 0, errors.slice(0, 2).join(' | '));

  console.log('\n===== 汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 600);
