// 回归测试：2026-09-10 P2 落地项
//   ① 收藏星标三态对比度（非文本图形 ≥ 3:1）
//   ② 键盘可达：目录 / 返回顶部 / 展开更早（div+onclick，此前完全不可 Tab）
//   ③ 标题层级与区块标签（无 main/header 地标，157 条新闻无法跳转导航）
//   ④ 断点 760/768 并存（761–768px 矿权行不换行）
//   ⑤ 移动端：会展恢复显示 + 安装指引移到栅格末尾（跨栏 order 无效，只能挪 DOM）
//   ⑥ 筛选态全局指示与出口 / 全部标为已读可撤销 / 简报加载超时兜底
// 与其余 test_*.js 同构：jsdom 直接跑 index.html，结尾给 PASS/FAIL 与真实退出码。
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

// jsdom 默认不取外部 <script src>；不内联数据文件的话初始化会中断，测的是假象。
let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
['app.js', 'news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  html = html.replace(new RegExp('<script src="' + f + '[^>]*></script>'),
    () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
});
const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true,
  url: 'https://pliucugb-cyber.github.io/mining-daily/',
  beforeParse(win) {
    if (typeof win.matchMedia !== 'function') {
      win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    }
    if (typeof win.fetch !== 'function') win.fetch = () => Promise.reject(new Error('stub'));
  }
});
const w = dom.window;
const d = w.document;

let pass = 0, fail = 0;
function ok(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name + (detail ? '  → ' + detail : '')); }
  else { fail++; console.log('  FAIL  ' + name + (detail ? '  → ' + detail : '')); }
}
function lum(hex) {
  const h = hex.replace('#', '');
  const c = [0, 2, 4].map(i => parseInt(h.substr(i, 2), 16) / 255)
    .map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
function ratio(a, b) {
  const l1 = lum(a), l2 = lum(b);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

setTimeout(() => {
  console.log('===== ① 收藏星标三态对比度（非文本 ≥ 3:1）=====');
  const star = /\.btn-star\{[^}]*color:\s*(#[0-9a-fA-F]{6})/.exec(html);
  const hover = /\.btn-star:hover\{color:\s*(#[0-9a-fA-F]{6})/.exec(html);
  const fav = /\.news-item\.favorited \.btn-star\{color:\s*(#[0-9a-fA-F]{6})/.exec(html);
  ok('默认态 ≥ 3:1', star && ratio(star[1], '#ffffff') >= 3, star ? star[1] + ' → ' + ratio(star[1], '#ffffff').toFixed(2) : '未取到');
  ok('hover 态 ≥ 3:1', hover && ratio(hover[1], '#ffffff') >= 3, hover ? hover[1] + ' → ' + ratio(hover[1], '#ffffff').toFixed(2) : '未取到');
  ok('收藏态 ≥ 3:1', fav && ratio(fav[1], '#ffffff') >= 3, fav ? fav[1] + ' → ' + ratio(fav[1], '#ffffff').toFixed(2) : '未取到');

  console.log('\n===== ② 键盘可达（div + onclick）=====');
  ok('mdEnhanceKeyboard 已定义', typeof w.mdEnhanceKeyboard === 'function');
  const toc = [...d.querySelectorAll('.toc-main-item')];
  ok('目录条目存在', toc.length > 0, toc.length + ' 个');
  w.mdEnhanceKeyboard();
  const kbOk = toc.filter(el => el.getAttribute('role') === 'button' && el.getAttribute('tabindex') === '0');
  ok('目录条目已补 role=button + tabindex=0', kbOk.length === toc.length, kbOk.length + '/' + toc.length);
  const backTop = d.querySelector('.toc-back-top');
  ok('返回顶部已补键盘可达', backTop && backTop.getAttribute('tabindex') === '0');
  // Enter 真的能触发点击（而不是只挂了属性）
  let clicked = 0;
  const probe = toc[0];
  const origClick = probe.click;
  probe.click = function () { clicked++; };
  probe.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  probe.click = origClick;
  ok('回车键触发点击', clicked === 1, 'clicked=' + clicked);

  console.log('\n===== ③ 标题层级与区块标签 =====');
  ok('mdA11yLandmarks 已定义', typeof w.mdA11yLandmarks === 'function');
  w.mdA11yLandmarks();
  const secs = [...d.querySelectorAll('.section')];
  const labelled = secs.filter(s => s.getAttribute('aria-label'));
  ok('区块已补 aria-label', labelled.length > 0, labelled.length + '/' + secs.length);
  const h2 = [...d.querySelectorAll('.section-title')].filter(t => t.getAttribute('role') === 'heading' && t.getAttribute('aria-level') === '2');
  ok('section-title 挂 role=heading aria-level=2', h2.length > 0, h2.length + ' 个');
  const h3 = [...d.querySelectorAll('.sub-cat')].filter(t => t.getAttribute('aria-level') === '3');
  ok('sub-cat 挂 aria-level=3', h3.length > 0, h3.length + ' 个');

  console.log('\n===== ④ 断点 760 / 768 并存 =====');
  ok('不再有 760px 断点', !/max-width:\s*760px/.test(html));
  ok('矿权行换行规则统一到 768px', /@media\(max-width:768px\)\{\s*\.rights-row\{flex-wrap:wrap\}/.test(html));

  console.log('\n===== ⑤ 移动端右栏 =====');
  // ⑤ 移动端会展卡：默认显示；仅「热榜」tab（body[data-md-cat="hot"]）隐藏会展卡，突出矿业热榜。
  //   故允许热榜-tab 作用域内的 .expo-mini{display:none!important}，但禁止任何全局/无作用域的强制隐藏。
  const expoNone = (html.match(/\.expo-mini\{display:none!important\}/g) || []);
  // 2026-09-11 视觉规范评审修复 A1：锚点由 #col-rail 更正为 .col-rail（页面元素是 class 无 id）
  const hotScoped = /body\[data-md-cat="hot"\] \.col-rail \.expo-mini\{display:none!important\}/.test(html);
  ok('会展仅热榜 tab 隐藏（移动端默认显示，无全局强制隐藏）', expoNone.length === (hotScoped ? 1 : 0) && hotScoped,
    'display:none 规则数=' + expoNone.length + '，热榜作用域=' + hotScoped);
  ok('mdMobileRailOrder 已定义', typeof w.mdMobileRailOrder === 'function');
  const grid = d.querySelector('.news-grid');
  const guide = d.getElementById('installGuideSection');
  if (grid && guide) {
    w.matchMedia = q => ({ matches: /max-width:\s*1100px/.test(q), media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    w.mdMobileRailOrder();
    ok('窄屏时安装指引移到栅格末尾（热榜/会展在其之前）', guide.parentNode === grid,
      'parent=' + (guide.parentNode && guide.parentNode.className));
    w.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    w.mdMobileRailOrder();
    ok('宽屏时还原回原栏位', guide.parentNode !== grid, 'parent=' + (guide.parentNode && guide.parentNode.className));
  } else {
    ok('.news-grid / #installGuideSection 存在', false);
  }

  console.log('\n===== ⑥ 筛选态指示与出口 =====');
  ok('mdSyncFilterState 已定义', typeof w.mdSyncFilterState === 'function');
  if (typeof w.setFilter === 'function') {
    w.setFilter('unread');
    w.applyFilter();
    const bar = d.getElementById('mdFilterState');
    ok('筛选态显示全局指示条', bar && bar.style.display !== 'none');
    ok('指示条说明当前筛选条件', bar && /只看未读/.test(bar.textContent || ''), bar ? (bar.textContent || '').trim().slice(0, 30) : '');
    const clear = d.getElementById('mdFilterClear');
    ok('指示条带清除出口', !!clear);
    if (clear) {
      clear.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
      const bar2 = d.getElementById('mdFilterState');
      ok('点清除后指示条隐藏', bar2 && bar2.style.display === 'none');
    }
  } else {
    ok('setFilter 可用（无法做运行时校验）', false);
  }

  console.log('\n===== ⑦ 全部标为已读可撤销 =====');
  ok('mdUndoToast 已定义', typeof w.mdUndoToast === 'function');
  ok('markAllRead 会保存快照用于撤销', /function markAllRead\(\)\{[\s\S]{0,200}\[?\.\.\.\]?getReadSet\(\)/.test(html));
  if (typeof w.getReadSet === 'function' && typeof w.markAllRead === 'function') {
    const before = w.getReadSet().size;
    w.markAllRead();
    const after = w.getReadSet().size;
    const toast = d.getElementById('mdToast');
    ok('全部标为已读后条数增加', after >= before, before + ' → ' + after);
    ok('弹出可撤销提示', !!toast && /撤销/.test(toast.textContent || ''));
    if (toast) {
      toast.querySelector('.md-undo').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
      ok('点撤销后已读集合回滚', w.getReadSet().size === before, '回滚后 ' + w.getReadSet().size + '（原 ' + before + '）');
    }
  }

  console.log('\n===== ⑧ 简报加载超时兜底 =====');
  ok('loadBrief 带 8 秒超时兜底', /_briefTimer[\s\S]{0,400}8000/.test(html));
  ok('超时文案给了可行动提示', /简报加载较慢/.test(html));

  console.log('\n===== 结果：' + pass + ' PASS / ' + fail + ' FAIL =====');
  process.exit(fail ? 1 : 0);
}, 1200);
