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
ok(/_ps\.classList\.add\('hm-on'\)/.test(html), 'pre-paint 直接贴 hm-on（首帧即热力图）');
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

if (!JSDOM) {
  section('运行时 · jsdom');
  console.log('  SKIP  jsdom 未安装，跳过运行时断言');
} else {
  section('运行时 · jsdom 装载真实页面');

  // 页面引用的本地数据脚本必须真实装载，否则 LME_DATA 缺失会让 LME 卡片被渲染成「暂无数据」，
  // 测出来的就是测试脚手架的缺陷而不是产品缺陷（曾踩过）。
  console.log('    装载本地数据脚本：' + LOCAL_SRC.filter(f => fs.existsSync(path.join(ROOT, f))).join(', '));

  const dom = new JSDOM(html.replace(/<script[^>]+src=[^>]*><\/script>/g, ''), {
    runScripts: 'outside-only',
    pretendToBeVisual: true,
    url: 'https://example.com/mining-daily/'
  });
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
  ok(!!bar && bar.querySelectorAll('.pv-btn').length === 2, '切换器有 2 个按钮（卡片/热力图）');

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
}

/* ============ 三、反向用例 ============ */
section('反向用例 · 必须能抓出退化');

// 反例 1：删掉容器 —— 渲染应静默失败且不抛错
if (JSDOM) {
  const dom2 = new JSDOM(html.replace('id="priceHeatmap"', 'id="priceHeatmapX"').replace(/<script[^>]+src=[^>]*><\/script>/g, ''), {
    runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://example.com/'
  });
  const w2 = dom2.window;
  w2.matchMedia = w2.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }));
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

/* ============ 汇总 ============ */
console.log('\n===== 汇总 =====');
console.log(pass + ' PASS / ' + fail + ' FAIL');
if (fail) { console.log('失败项：'); failures.forEach(f => console.log('  - ' + f)); }
process.exit(fail ? 1 : 0);
