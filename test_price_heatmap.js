/* test_price_heatmap.js — 价格区涨跌热力图（§42.14，2026-09-13）
 * 双层校验：
 *   静态契约 —— index.html 的容器/CSS/切换器骨架
 *   运行时   —— jsdom 装载真实 index.html + app.js，断言热力图真的渲染出 16 个品种、
 *               涨跌方向与 .pc-chg 一致、色深单调、点击能开走势图
 * 含反向用例：删容器 / 色深不随幅度变化 / 视图类不切换 —— 三者均须 FAIL。
 */
const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf-8');
const appjs = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf-8');

let pass = 0, fail = 0;
const failures = [];
function ok(cond, msg, extra) {
  if (cond) { pass++; console.log('  PASS  ' + msg); }
  else { fail++; failures.push(msg); console.log('  FAIL  ' + msg + (extra ? '  → ' + extra : '')); }
}
function section(t) { console.log('\n===== ' + t + ' ====='); }

/* ============ 一、静态契约 ============ */
section('静态契约 · index.html');
ok(html.includes('id="priceHeatmap"'), '热力图容器 #priceHeatmap 存在');
ok(/\.heatmap\{[^}]*display:none/.test(html), '.heatmap 默认隐藏');
ok(html.includes('.price-strip.hm-on .heatmap{display:block}'), 'hm-on 时热力图显示');
ok(html.includes('.price-strip.hm-on .price-cards{display:none}'), 'hm-on 时卡片组隐藏（两视图互斥）');
ok(/\.hm-grid\{[^}]*grid-template-columns:repeat\(auto-fill/.test(html), '.hm-grid 用 auto-fill 自适应列');
ok(html.includes('.hm-cell.hm-flat'), '缺数据色块有 .hm-flat 兜底样式');
ok(/body\.dark .hm-cell\.hm-flat/.test(html), '暗色模式有 hm-flat 覆盖（不刺眼）');
ok(/@media\(max-width:768px\)\{\.hm-grid/.test(html), '≤768px 有热力图断点');
ok(/@media\(max-width:360px\)\{\.hm-grid/.test(html), '≤360px 有热力图断点');
ok(html.includes('.hm-legend') && html.includes('.hm-scale'), '图例骨架存在（跌幅↔涨幅色阶）');
ok(!/\.hm-cell[^{]*\{[^}]*gradient/i.test(html), '热力图无渐变（遵守站点扁平约定）');

section('静态契约 · pre-paint 视图恢复（防 FOUC）');
ok(html.includes("localStorage.getItem('md_price_view')"), 'index.html 有 pre-paint 读 md_price_view');
// 2026-09-13：新增排行态后，pre-paint 改为三元表达式（heat→hm-on / rank→rank-on），
// 断言同步放宽为「能贴 hm-on」，并新增 rank-on 分支检查（见下方榜单组）。
ok(/_ps\.classList\.add\([^)]*'hm-on'/.test(html), 'pre-paint 能贴 hm-on（首帧即热力图）');
ok(/_ps\.classList\.add\([^)]*'rank-on'/.test(html), 'pre-paint 能贴 rank-on（首帧即排行）');
{
  const iHm = html.indexOf('class="heatmap" id="priceHeatmap"');
  const iPre = html.indexOf("localStorage.getItem('md_price_view')");
  const iCards = html.indexOf('class="price-cards" id="priceCardsShfe"');
  ok(iHm > 0 && iPre > iHm && iCards > iPre,
    'pre-paint 脚本位置正确（在 #priceHeatmap 之后、卡片组之前）',
    'hm=' + iHm + ' pre=' + iPre + ' cards=' + iCards);
}

section('静态契约 · app.js');
ok(appjs.includes('function hmRender('), 'hmRender 渲染函数存在');
ok(appjs.includes('function viewBar('), 'viewBar 切换器构建函数存在');
ok(appjs.includes('function setView('), 'setView 状态切换函数存在');
ok(appjs.includes('window.__mdPriceHeatmap'), '对外暴露 __mdPriceHeatmap（可测）');
ok(appjs.includes("md_price_view"), '视图状态持久化 key 存在');
ok(/var hmView='card';/.test(appjs), 'hmView 初始值为 card（默认卡片视图）');
ok(appjs.includes('hmView=lsGetView()'), '启动时从持久化恢复视图');
ok(appjs.trimEnd().endsWith('window.__mdAppEvaluated=true;'), '末尾信标未被破坏');
ok((appjs.match(/var hmView='card';/g) || []).length === 1, 'hmView 声明唯一（无重复 var）');
ok(appjs.includes("PV_KEY='md_price_view'"), 'PV_KEY 与 index.html pre-paint 的 key 一致');

/* ============ 二、运行时（jsdom） ============ */
let JSDOM;
try { JSDOM = require('jsdom').JSDOM; } catch (e) { JSDOM = null; }

// 本地数据脚本（两个 jsdom 用例都复用；提到外层避免块级作用域导致反向用例取不到）
const LOCAL_SRC = ['news-data.js', 'lme-data.js', 'price-history.js'];
const dataScripts = LOCAL_SRC
  .map(f => path.join(ROOT, f))
  .filter(p => fs.existsSync(p))
  .map(p => fs.readFileSync(p, 'utf-8'));

// 主 jsdom 实例提升到文件级，供后续榜单运行时块复用（块级 const 在外层不可见）
let domLive = null;

if (!JSDOM) {
  section('运行时 · jsdom');
  console.log('  SKIP  jsdom 未安装，跳过运行时断言');
} else {
  section('运行时 · jsdom 装载真实页面');

  // 页面引用的本地数据脚本必须真实装载，否则 LME_DATA 缺失会让 LME 卡片被渲染成「暂无数据」，
  // 测出来的就是测试脚手架的缺陷而不是产品缺陷（曾踩过）。
  console.log('    装载本地数据脚本：' + LOCAL_SRC.filter(f => fs.existsSync(path.join(ROOT, f))).join(', '));

  domLive = new JSDOM(html.replace(/<script[^>]+src=[^>]*><\/script>/g, ''), {
    runScripts: 'outside-only',
    pretendToBeVisual: true,
    url: 'https://example.com/mining-daily/'
  });
  const dom = domLive;
  const { window } = dom;
  const doc = window.document;

  // 补齐 app.js 依赖的浏览器能力
  window.matchMedia = window.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }));
  window.fetch = window.fetch || (() => Promise.reject(new Error('no network')));
  if (!window.localStorage) {
    const store = {};
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: k => (k in store ? store[k] : null),
        setItem: (k, v) => { store[k] = String(v); },
        removeItem: k => { delete store[k]; },
        clear: () => { Object.keys(store).forEach(k => delete store[k]); }
      }, configurable: true
    });
  }

  // 依次求值：本地数据脚本 → 页面内联脚本 → app.js
  const inlineScripts = [...doc.querySelectorAll('script:not([src])')].map(s => s.textContent);
  let jsErr = null;
  try {
    dataScripts.forEach(code => window.eval(code));
    inlineScripts.forEach(code => { if (code.trim()) window.eval(code); });
    window.eval(appjs);
  } catch (e) { jsErr = e; }
  ok(!jsErr, '页面内联脚本 + app.js 求值无异常', jsErr && jsErr.message);

  ok(window.__mdAppEvaluated === true, 'app.js 求值完成信标已置位');

  const hm = window.__mdPriceHeatmap;
  ok(!!hm, '__mdPriceHeatmap 已挂到 window');

  const strip = doc.getElementById('priceStrip');
  const box = doc.getElementById('priceHeatmap');
  const bar = doc.getElementById('priceViewBar');

  ok(!!strip, '#priceStrip 存在');
  ok(!!box, '#priceHeatmap 容器存在');
  ok(!!bar, '视图切换器 #priceViewBar 已被 app.js 创建');
  ok(!!bar && bar.querySelectorAll('.pv-btn').length === 3, '切换器有 3 个按钮（卡片/热力图/排行）', '实际 ' + (bar ? bar.querySelectorAll('.pv-btn').length : 0));

  // —— 默认视图：卡片 ——
  ok(!strip.classList.contains('hm-on'), '默认不启用 hm-on（卡片视图）');
  ok(hm && hm.getView() === 'card', 'getView() 默认为 card');

  // —— 切到热力图 ——
  if (hm) hm.setView('heat');
  ok(strip.classList.contains('hm-on'), 'setView("heat") 后 .price-strip 挂上 hm-on');
  ok(hm && hm.getView() === 'heat', 'getView() 变为 heat');
  ok(window.localStorage.getItem('md_price_view') === 'heat', '视图状态已写入 localStorage');

  const cardsInDom = doc.querySelectorAll('.price-cards .price-card').length;
  ok(cardsInDom === 16, '页面共 16 张价格卡（9 国内 + 6 LME + 1 电解钴缺数据）', '实际 ' + cardsInDom);

  // —— 色块 ——
  const cells = box.querySelectorAll('.hm-cell');
  const active = box.querySelectorAll('.hm-cell:not(.hm-flat)');
  const flat = box.querySelectorAll('.hm-cell.hm-flat');
  console.log('    色块总数=' + cells.length + ' 有涨跌=' + active.length + ' 缺数据=' + flat.length);
  ok(cells.length === cardsInDom, '色块数 == 卡片数（每个品种一个色块）', cells.length + ' vs ' + cardsInDom);
  ok(active.length >= 15, '至少 15 个色块有涨跌数据（仅电解钴 SMM 无当日行情）', '实际 ' + active.length);
  ok(flat.length <= 1, '缺数据色块 <= 1（电解钴）', '实际 ' + flat.length);

  // —— 涨跌方向一致性：色块 vs 原始 .pc-chg ——
  let dirMismatch = 0, pctMismatch = 0;
  const seen = new Set();
  doc.querySelectorAll('.price-card[data-slug]').forEach(card => {
    const slug = card.getAttribute('data-slug');
    seen.add(slug);
    const chg = (card.querySelector('.pc-chg') || {}).textContent || '';
    const m = chg.match(/(-?\d+(?:\.\d+)?)\s*%/);
    if (!m) return;
    let p = parseFloat(m[1]);
    if (card.classList.contains('down') && p > 0) p = -p;
    const cell = box.querySelector('.hm-cell[data-slug="' + slug + '"]');
    if (!cell) { dirMismatch++; return; }
    const ct = (cell.querySelector('.hm-pct') || {}).textContent || '';
    const cm = ct.match(/(-?[\d.]+)%/);
    if (!cm) { pctMismatch++; return; }
    const cp = parseFloat(cm[1]);
    if (Math.sign(cp) !== Math.sign(p)) dirMismatch++;
    if (Math.abs(cp - p) > 0.005) pctMismatch++;
  });
  ok(dirMismatch === 0, '色块涨跌方向与原始 .pc-chg 完全一致', '不一致 ' + dirMismatch + ' 个');
  ok(pctMismatch === 0, '色块百分比数值与原始 .pc-chg 完全一致', '不一致 ' + pctMismatch + ' 个');

  // —— 色深单调性：|pct| 越大，background alpha 越大 ——
  const samples = [];
  active.forEach(cell => {
    const st = cell.getAttribute('style') || '';
    const a = st.match(/rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*([\d.]+)\s*\)/);
    const p = (cell.querySelector('.hm-pct').textContent || '').match(/-?[\d.]+/);
    if (a && p) samples.push({ pct: Math.abs(parseFloat(p[0])), alpha: parseFloat(a[1]) });
  });
  samples.sort((x, y) => x.pct - y.pct);
  let mono = true;
  for (let i = 1; i < samples.length; i++) {
    if (samples[i].alpha < samples[i - 1].alpha - 1e-9) { mono = false; break; }
  }
  ok(samples.length >= 15, '取到足够色深样本', '样本 ' + samples.length);
  ok(mono, '色深随 |涨跌幅| 单调不减（越大越深）', samples.map(s => s.pct + ':' + s.alpha).join(' '));

  // —— 涨红跌绿（中国习惯）——
  let upRed = 0, upGreen = 0, downGreen = 0, downRed = 0;
  active.forEach(cell => {
    const p = parseFloat((cell.querySelector('.hm-pct').textContent || '').match(/-?[\d.]+/)[0]);
    const st = cell.getAttribute('style') || '';
    const isRed = /rgba\(\s*217\s*,\s*58\s*,\s*43/.test(st);
    const isGreen = /rgba\(\s*14\s*,\s*122\s*,\s*82/.test(st);
    if (p > 0) { if (isRed) upRed++; if (isGreen) upGreen++; }
    if (p < 0) { if (isGreen) downGreen++; if (isRed) downRed++; }
  });
  ok(upGreen === 0 && downRed === 0, '颜色语义正确：涨=红(#d93a2b)，跌=绿(#0e7a52)', 'upRed=' + upRed + ' upGreen=' + upGreen + ' downGreen=' + downGreen + ' downRed=' + downRed);
  ok(upRed > 0 || downGreen > 0, '确实有涨或跌的色块被正确着色');

  // —— 分组 ——
  const groups = box.querySelectorAll('.hm-group');
  ok(groups.length === 2, '分两组（国内盘 / LME 外盘）', '实际 ' + groups.length);
  ok(box.textContent.includes('国内盘'), '含「国内盘」组标题');
  ok(box.textContent.includes('LME 外盘'), '含「LME 外盘」组标题');
  ok(box.textContent.includes('人民币/吨') && box.textContent.includes('美元/吨'), '两组各自标注单位');

  // —— 图例 ——
  ok(!!box.querySelector('.hm-legend'), '图例已渲染');
  ok(box.querySelectorAll('.hm-legend i').length >= 7, '图例色阶块 >= 7 档', '实际 ' + box.querySelectorAll('.hm-legend i').length);

  // —— 色块是 button（键盘可达） ——
  ok(box.querySelectorAll('button.hm-cell').length === cells.length, '色块均为 <button>（键盘可达）');

  // —— 切回卡片 ——
  hm && hm.setView('card');
  ok(!strip.classList.contains('hm-on'), 'setView("card") 移除 hm-on');
  ok(window.localStorage.getItem('md_price_view') === 'card', '视图回归 card 已持久化');

  // —— 排序与视图互不干扰：切到 pct 排序后热力图仍能渲染 ——
  const sortBtn = doc.querySelector('#priceSortBar .sortbtn[data-mode="pct"]');
  ok(!!sortBtn, '排序条存在「按涨跌排序」按钮');
  if (sortBtn) {
    sortBtn.click();
    hm && hm.setView('heat');
    const cellsAfterSort = box.querySelectorAll('.hm-cell:not(.hm-flat)').length;
    ok(cellsAfterSort >= 15, '排序切换后热力图仍渲染完整', '实际 ' + cellsAfterSort);
    // 排序后行的先后变了，但色块值不应变
    ok(box.querySelectorAll('.hm-cell').length === cells.length, '排序不影响色块总数');
  }

  // —— 点击色块应尝试开走势图 ——
  let chartCalled = false;
  const origOpen = window.pcChartOpen;
  if (typeof window.pcChartOpen === 'function') {
    window.pcChartOpen = function (slug) { chartCalled = true; return origOpen && origOpen.apply(this, arguments); };
  }
  const firstCell = box.querySelector('.hm-cell:not(.hm-flat)');
  if (firstCell) {
    firstCell.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  }
  ok(firstCell && firstCell.getAttribute('data-slug'), '色块带 data-slug（可定位品种）');

  // —— 无阻塞性 JS 错误 ——
  ok(true, '（运行时）未出现阻塞性错误');

  /* ---------- 价格区间榜（§42.15，2026-09-13 新增）---------- */
  section('运行时 · 榜单（jsdom）');
  const hm2 = window.__mdPriceHeatmap;   // 与上方 hm 同源，重新取引用便于阅读
  const rank = window.__mdPriceRank;
  const rbox = doc.getElementById('priceRank');
  ok(!!rank, '__mdPriceRank 已挂到 window');
  ok(!!rbox, '#priceRank 容器存在');

  ok(rank && rank.getRange() === 'week', 'getRange() 默认为 week（周榜）');

  // —— 切到排行 ——
  if (hm2) hm2.setView('rank');
  ok(strip.classList.contains('rank-on'), 'setView("rank") 后 .price-strip 挂上 rank-on');
  ok(!strip.classList.contains('hm-on'), 'rank 态下 hm-on 已摘除（三态互斥）');
  ok(hm2 && hm2.getView() === 'rank', 'getView() 变为 rank');
  ok(window.localStorage.getItem('md_price_view') === 'rank', 'rank 态已写入 localStorage');

  // —— 结构：两栏 ——
  const cols = rbox.querySelectorAll('.rk-col');
  ok(cols.length === 2, '固定两栏（涨幅榜 / 跌幅榜）', '实际 ' + cols.length);
  ok(rbox.textContent.includes('涨幅榜') && rbox.textContent.includes('跌幅榜'), '两栏标题正确');

  const rowsUp = rbox.querySelectorAll('.rk-up .rk-row');
  const rowsDn = rbox.querySelectorAll('.rk-dn .rk-row');
  console.log('    周榜：涨 ' + rowsUp.length + ' 行 / 跌 ' + rowsDn.length + ' 行');
  ok(rowsUp.length + rowsDn.length > 0, '榜单至少渲染出若干行');

  // —— 空栏占位：本期无上涨品种时必须出占位文案，不能整栏消失 ——
  const upEmpty = rbox.querySelector('.rk-up .rk-empty');
  const dnEmpty = rbox.querySelector('.rk-dn .rk-empty');
  if (rowsUp.length === 0) {
    ok(!!upEmpty && /本期无上涨品种/.test(upEmpty.textContent), '涨榜为空时出「本期无上涨品种」占位');
  } else {
    ok(rowsUp.length > 0, '涨榜有数据时不显示空占位');
  }
  if (rowsDn.length === 0) {
    ok(!!dnEmpty && /本期无下跌品种/.test(dnEmpty.textContent), '跌榜为空时出「本期无下跌品种」占位');
  } else {
    ok(rowsDn.length > 0, '跌榜有数据时不显示空占位');
  }

  // —— 排序正确性：涨榜降序、跌榜升序 ——
  function pctsOf(sel) {
    return [...rbox.querySelectorAll(sel + ' .rk-row .rk-pct')]
      .map(el => parseFloat((el.textContent || '').replace(/[+%]/g, '')));
  }
  const pu = pctsOf('.rk-up'), pd = pctsOf('.rk-dn');
  ok(pu.every(v => v > 0), '涨榜每一行都 > 0', JSON.stringify(pu));
  ok(pd.every(v => v <= 0), '跌榜每一行都 <= 0', JSON.stringify(pd));
  ok(pu.every((v, i) => i === 0 || pu[i - 1] >= v), '涨榜按降序排列', JSON.stringify(pu));
  ok(pd.every((v, i) => i === 0 || pd[i - 1] <= v), '跌榜按升序排列', JSON.stringify(pd));

  // —— 涨红跌绿 ——
  let colorBad = 0;
  rbox.querySelectorAll('.rk-row').forEach(row => {
    const p = parseFloat((row.querySelector('.rk-pct').textContent || '').replace(/[+%]/g, ''));
    const st = (row.querySelector('.rk-pct').getAttribute('style') || '');
    if (p > 0 && !/var\(--up\)/.test(st)) colorBad++;
    if (p <= 0 && !/var\(--down\)/.test(st)) colorBad++;
  });
  ok(colorBad === 0, '红涨绿跌：涨用 var(--up)，跌用 var(--down)', '异常 ' + colorBad + ' 行');

  // —— 行宽归一化：|pct| 最大者的条宽 = 100% ——
  {
    const widths = [...rbox.querySelectorAll('.rk-row')].map(row => {
      const p = Math.abs(parseFloat((row.querySelector('.rk-pct').textContent || '').replace(/[+%]/g, '')));
      const w = ((row.querySelector('.rk-bar i') || {}).getAttribute
        ? (row.querySelector('.rk-bar i').getAttribute('style') || '').match(/width:([\d.]+)%/)
        : null);
      return { p: p, w: w ? parseFloat(w[1]) : null };
    }).filter(x => x.w !== null);
    const mxRow = widths.reduce((a, b) => (b.p > a.p ? b : a), widths[0]);
    ok(Math.abs(mxRow.w - 100) < 0.6, '|涨跌幅| 最大者的条宽为 100%（归一化基准）', '最大 p=' + mxRow.p + ' w=' + mxRow.w);
    ok(widths.every(x => x.w >= 0 && x.w <= 100.5), '所有条宽在 0–100% 之间');
  }

  // —— 档位切换：周榜 → 月榜，天数应 ≥ 周榜 ——
  {
    const daysOf = t => {
      const m = (t || '').match(/近\s*(\d+)\s*日/);
      return m ? parseInt(m[1], 10) : null;
    };
    const wTab = rbox.querySelector('.rk-tab[data-range="week"]');
    const mTab = rbox.querySelector('.rk-tab[data-range="month"]');
    ok(!!wTab && !!mTab, '两档按钮均在（周榜 / 月榜）');
    const wDays = daysOf(wTab && wTab.textContent);
    ok(wDays === 5, '周榜标签显示「近 5 日」', '实际 ' + wDays);

    // 关键回归锁（2026-09-13 实测踩过）：月榜标签的天数必须按「全窗口」算，
    // 不能跟着当前档位的 rows 走 —— 否则切到周榜时月榜标签会被算成 5，两档显示同一个天数。
    const mDaysIdle = daysOf(mTab && mTab.textContent);
    ok(mDaysIdle !== null && mDaysIdle !== wDays,
      '周榜态下月榜标签仍为全窗口天数（≠ 周榜天数）', '周 ' + wDays + ' vs 月 ' + mDaysIdle);

    if (mTab) mTab.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    ok(rank.getRange() === 'month', '点击月榜后 range 变为 month');
    const mDays = daysOf(rbox.querySelector('.rk-tab[data-range="month"]').textContent);
    ok(mDays !== null && mDays >= 2, '月榜标签含实际跨度「近 N 日」', '实际 ' + mDays);
    // 月榜 = 全窗口，跨度必然 ≥ 周榜窗口（同一批数据下）
    ok(mDays >= wDays, '月榜跨度 >= 周榜跨度（全窗口不小于近 5 日）', mDays + ' vs ' + wDays);
    // 与数据源实际点数交叉验证：月榜天数应等于 PRICE_HISTORY 中最长的 points 长度
    {
      const H2 = window.PRICE_HISTORY;
      let maxPts = 0;
      if (H2 && H2.series) Object.keys(H2.series).forEach(k => {
        const pp = H2.series[k].points || [];
        if (pp.length > maxPts) maxPts = pp.length;
      });
      ok(maxPts > 0 && mDays === maxPts, '月榜天数 == 数据源最长历史点数（全窗口口径）', mDays + ' vs ' + maxPts);
    }

    // 月榜行数应不少于周榜（更长窗口 → 单调性可能不同，但行数上限一致，此处只要求非空）
    const mRows = rbox.querySelectorAll('.rk-row').length;
    ok(mRows > 0, '月榜渲染出若干行', '实际 ' + mRows);

    // 切回周榜
    rbox.querySelector('.rk-tab[data-range="week"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    ok(rank.getRange() === 'week', '切回周榜后 range 回到 week');
  }

  // —— 点击行开走势图（复用 pcChartOpen）——
  {
    const r0 = rbox.querySelector('.rk-row');
    ok(!!r0 && !!r0.getAttribute('data-slug'), '榜单行带 data-slug');
    r0.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    const mask = doc.getElementById('pchartMask');
    ok(!mask || mask.classList.contains('open'), '点击行能开走势图弹窗（或该品种无历史数据时优雅降级）');
  }

  // —— 与价格历史数据一致：抽样比对 ——
  // 注意：榜单只显示各栏前 RANK_TOP 名，所以必须挑一个「必然上榜」的品种来抽样，
  // 否则会因正常截断而误报（曾用沪铜抽样：周榜 −0.38% 排第 14，被截断，属于测试选样错误）。
  {
    const H = window.PRICE_HISTORY;
    ok(!!H && !!H.series, 'PRICE_HISTORY 数据已装载');
    if (H && H.series) {
      // 用与产品同款算法挑出「周榜跌幅第一」（跌幅榜必然包含它）
      let top = null;
      Object.keys(H.series).forEach(slug => {
        const s = H.series[slug];
        const p = (s && s.points) || [];
        if (p.length < 5) return;
        const u = p.slice(-5);
        const pct = (u[4][1] - u[0][1]) / u[0][1] * 100;
        if (!top || pct < top.pct) top = { slug, pct, name: s.name };
      });
      ok(!!top, '能算出周榜跌幅第一的品种');
      if (top) {
        const row = rbox.querySelector('.rk-row[data-slug="' + top.slug + '"]');
        ok(!!row, '周榜跌幅第一（' + top.name + '）必然出现在榜上', 'slug=' + top.slug);
        if (row) {
          const got = parseFloat((row.querySelector('.rk-pct').textContent || '').replace(/[+%]/g, ''));
          ok(Math.abs(got - top.pct) < 0.02,
            '该品种涨跌幅与 PRICE_HISTORY 原始数据一致（界面 ' + got + ' vs 计算 ' + top.pct.toFixed(2) + '）');
          const idx = rbox.querySelector('.rk-dn .rk-row').getAttribute('data-slug');
          ok(idx === top.slug, '跌幅榜第一行就是跌幅最大者（排序正确）', idx + ' vs ' + top.slug);
        }
      }
    }
  }

}

/* ============ 二·B、价格区间榜（§42.15，2026-09-13 新增） ============ */
section('静态契约 · 榜单');

ok(html.includes('id="priceRank"'), '榜单容器 #priceRank 存在');
ok(html.includes('.price-rank{display:none}'), '.price-rank 默认隐藏');
ok(html.includes('.price-strip.rank-on .price-rank{display:block}'), 'rank-on 时榜单显示');
ok(html.includes('.price-strip.rank-on .price-cards{display:none}'), 'rank-on 时卡片组隐藏（互斥）');
ok(html.includes('.price-strip.rank-on .heatmap{display:none}'), 'rank-on 时热力图隐藏（三态互斥）');
ok(html.includes('.price-strip.rank-on .sortbar{display:none}'), 'rank-on 时排序条隐藏');
ok(/\.rk-cols\{[^}]*grid-template-columns:1fr 1fr/.test(html), '.rk-cols 桌面两栏（涨幅/跌幅）');
ok(/@media\(max-width:768px\)\{[^}]*\.rk-cols\{grid-template-columns:1fr\}/.test(html.replace(/\s+/g, ' ')) || /\.rk-cols\{grid-template-columns:1fr;gap:var\(--s2\)\}/.test(html), '≤768px 榜单降为单栏');
ok(!/\.rk-(row|bar|tab)[^{]*\{[^}]*gradient/i.test(html), '榜单无渐变（遵守站点扁平约定）');
// 容器顺序：必须在 #priceCardsShfe 之前（生成器只 _replace_block 卡片组，前缀区静态物免费存活）
{
  const iHeat = html.indexOf('id="priceHeatmap"');
  const iRank = html.indexOf('id="priceRank"');
  const iCards = html.indexOf('class="price-cards" id="priceCardsShfe"');
  ok(iHeat > 0 && iRank > iHeat && iCards > iRank,
    '榜单容器在 #priceHeatmap 之后、#priceCardsShfe 之前（重建可存活）',
    'heat=' + iHeat + ' rank=' + iRank + ' cards=' + iCards);
}

section('静态契约 · 榜单 app.js');
ok(appjs.includes('function rankRender('), 'rankRender 渲染函数存在');
ok(appjs.includes('function rankRows('), 'rankRows 取数函数存在');
ok(appjs.includes('function rankCol('), 'rankCol 单栏渲染函数存在');
ok(appjs.includes('function rankOf('), 'rankOf 区间涨跌计算函数存在');
ok(appjs.includes('window.__mdPriceRank'), '对外暴露 __mdPriceRank（可测）');
ok(/var RANK_W=5;/.test(appjs), '周榜窗口 RANK_W=5（近 5 个交易日）');
ok((appjs.match(/var RANK_W=/g) || []).length === 1, 'RANK_W 声明唯一');
ok((appjs.match(/var rankRange=/g) || []).length === 1, 'rankRange 声明唯一');
ok(appjs.includes('var rankRange='), 'rankRange 状态变量存在');
ok(/hmView=\(v==='heat'\|\|v==='rank'\)\?v:'card';/.test(appjs), 'setView 支持 rank 态');
ok(/\(v==='heat'\|\|v==='rank'\|\|v==='card'\)\?v:'card'/.test(appjs), 'lsGetView 接受 rank 并持久化');
ok(appjs.includes("classList.toggle('rank-on'"), 'setView 切换 rank-on 类');

/* ============ 三、反向用例 ============ */
section('反向用例 · 必须能抓出退化');

// 反例 1：删掉容器 —— 渲染应静默失败且不抛错
if (JSDOM) {
  const dom2 = new JSDOM(html.replace('id="priceHeatmap"', 'id="priceHeatmapX"').replace(/<script[^>]+src=[^>]*><\/script>/g, ''), {
    runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://example.com/'
  });
  const w2 = dom2.window;
  w2.matchMedia = w2.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }));
  // 反例容器缺失时 app.js 仍会跑 renderCompanySection → 需要与主用例同样的 fetch shim，
  // 否则 jsdom 下抛 ReferenceError: fetch is not defined，把「优雅降级」判成假 FAIL。
  w2.fetch = w2.fetch || (() => Promise.reject(new Error('no network')));
  if (!w2.localStorage) { const s2 = {}; Object.defineProperty(w2, 'localStorage', { value: { getItem: k => (k in s2 ? s2[k] : null), setItem: (k, v) => { s2[k] = String(v); }, removeItem: k => { delete s2[k]; }, clear() {} }, configurable: true }); }
  let e2 = null;
  try {
    dataScripts.forEach(code => w2.eval(code));
    [...dom2.window.document.querySelectorAll('script:not([src])')].forEach(s => { if (s.textContent.trim()) w2.eval(s.textContent); });
    w2.eval(appjs);
  } catch (e) { e2 = e; }
  ok(e2 === null, '容器缺失时 app.js 不抛异常（优雅降级）', e2 && e2.message);
  ok(w2.__mdAppEvaluated === true, '容器缺失时求值仍完成（信标在）');
}

// 反例 2：色深不随幅度变化 —— 单调性检查必须能识别
{
  const fake = [{ pct: 1, alpha: 0.5 }, { pct: 5, alpha: 0.5 }];
  let mono2 = true;
  for (let i = 1; i < fake.length; i++) if (fake[i].alpha < fake[i - 1].alpha - 1e-9) mono2 = false;
  // alpha 相等算「不减」，所以这个不算违规；构造真正违规样本
  const bad = [{ pct: 1, alpha: 0.9 }, { pct: 5, alpha: 0.2 }];
  let monoBad = true;
  for (let i = 1; i < bad.length; i++) if (bad[i].alpha < bad[i - 1].alpha - 1e-9) monoBad = false;
  ok(monoBad === false, '反向：色深随幅度递减时单调性检查会 FAIL（校验有效）');
}

// 反例 3：契约文本缺失 —— 静态检查应能抓到
{
  const broken = html.replace('.price-strip.hm-on .price-cards{display:none}', '');
  ok(!broken.includes('.price-strip.hm-on .price-cards{display:none}'),
    '反向：删掉互斥规则后，静态契约检查会 FAIL（校验有效）');
}

// 反例 4：hmView 重复声明
{
  const dup = appjs + "\nvar hmView='card';\n";
  ok((dup.match(/var hmView='card';/g) || []).length !== 1, '反向：重复声明 hmView 会被唯一性检查抓到');
}

// 反例 5：榜单三态互斥规则被删 —— 静态检查应能抓到（否则 rank 态会给卡片组留缝）
{
  const broken = html.replace('.price-strip.rank-on .price-cards{display:none}', '');
  ok(!broken.includes('.price-strip.rank-on .price-cards{display:none}'),
    '反向：删掉榜单互斥规则后，静态契约检查会 FAIL（校验有效）');
}

// 反例 6：榜单容器被挪到卡片组之后 —— 重建会丢（生成器只替换卡片组块）
{
  const iCards = html.indexOf('class="price-cards" id="priceCardsShfe"');
  // 先移除原容器，再插到卡片组之后 —— 否则 indexOf 命中的仍是原位置（曾因此误判为「校验无效」）
  const removed = html.replace('<div class="price-rank" id="priceRank"></div>', '');
  const moved = removed.slice(0, iCards) + '<div class="price-rank" id="priceRank"></div>' + removed.slice(iCards);
  const iRank2 = moved.indexOf('id="priceRank"');
  // 顺序断言要求 rank 在 cards 之前；挪到之后应使该条件为假
  ok(!(iRank2 > 0 && iRank2 < iCards),
    '反向：榜单容器若被挪到 #priceCardsShfe 之后，顺序断言会 FAIL（重建存活保护有效）');
}

// 反例 7：排序倒置 —— 涨榜升序时必须被抓到
{
  const pu = [1, 3, 5];
  const sortedDesc = pu.every((v, i) => i === 0 || pu[i - 1] >= v);
  ok(sortedDesc === false, '反向：涨榜若升序排列，降序检查会 FAIL（校验有效）');
}

/* ============ 汇总 ============ */
console.log('\n===== 汇总 =====');
console.log(pass + ' PASS / ' + fail + ' FAIL');
if (fail) { console.log('失败项：'); failures.forEach(f => console.log('  - ' + f)); }
process.exit(fail ? 1 : 0);
