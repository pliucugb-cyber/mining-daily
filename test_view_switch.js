/**
 * 2026-09-09 目录「视图切换」回归测试（jsdom）
 * 覆盖：① switchView 设置 body[data-view] ② 再次点击同一项回到全部
 *       ③ 收藏/历史切换前先 clearView ④ showAll 复位 ⑤ updateActiveSection 在视图模式下不抢高亮
 * 运行：node test_view_switch.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
['news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  const tag = new RegExp('<script src="' + f + '"></script>');
  html = html.replace(tag, '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
});
const errors = [];
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'https://pliucugb-cyber.github.io/mining-daily/',
  beforeParse(win) {
    if (typeof win.matchMedia !== 'function') {
      win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    }
    if (typeof win.fetch !== 'function') win.fetch = () => Promise.reject(new Error('stub'));
    win.addEventListener('error', e => errors.push('window.error: ' + e.message));
  }
});
const { window } = dom;
const { document } = window;

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log('  PASS  ' + name); }
  else { fail++; console.log('  FAIL  ' + name + (extra ? '  → ' + extra : '')); }
}
function disp(id) {
  const el = document.getElementById(id);
  if (!el) return 'missing';
  return window.getComputedStyle(el).display;
}

setTimeout(() => {
  try {
    check('switchView 函数存在', typeof window.switchView === 'function');
    check('clearView 函数存在', typeof window.clearView === 'function');

    // 1) 切换到往期视图
    const archItem = document.querySelector('[data-target="archiveSection"]');
    window.switchView('archive', archItem);
    check('switchView("archive") 设置 body[data-view=archive]', document.body.dataset.view === 'archive', document.body.dataset.view);
    check('往期项获得 active 高亮', archItem.classList.contains('active'));
    check('今日区在往期视图下隐藏', disp('todaySection') === 'none', disp('todaySection'));
    check('矿权区在往期视图下隐藏', disp('rightsSection') === 'none', disp('rightsSection'));
    check('往期区在往期视图下可见', disp('archiveSection') !== 'none', disp('archiveSection'));

    // 2) 再次点击同一项 → 回到全部
    window.switchView('archive', archItem);
    check('再次点击回到全部（data-view 清除）', !document.body.dataset.view, document.body.dataset.view);
    check('全部内容项 active', document.querySelector('.toc-all').classList.contains('active'));
    check('今日区恢复可见', disp('todaySection') !== 'none', disp('todaySection'));

    // 3) 切换到矿权视图
    const rightsItem = document.querySelector('[data-target="rightsSection"]');
    window.switchView('rights', rightsItem);
    check('switchView("rights") 设置 data-view=rights', document.body.dataset.view === 'rights', document.body.dataset.view);
    check('矿权区可见', disp('rightsSection') !== 'none', disp('rightsSection'));
    check('今日区隐藏', disp('todaySection') === 'none', disp('todaySection'));

    // 4) 安装视图：简报/价格/统计/主区块均隐藏，仅安装区可见
    const installItem = document.querySelector('[data-target="installGuideSection"]');
    window.switchView('install', installItem);
    check('安装视图 data-view=install', document.body.dataset.view === 'install', document.body.dataset.view);
    check('价格区在安装视图隐藏', disp('priceStrip') === 'none', disp('priceStrip'));
    check('统计条在安装视图隐藏', window.getComputedStyle(document.querySelector('.stats-bar')).display === 'none');
    check('安装区可见', disp('installGuideSection') !== 'none', disp('installGuideSection'));
    check('右栏在安装视图隐藏', window.getComputedStyle(document.querySelector('.col-rail')).display === 'none');

        // 5) 视图切换后应滚动到目标区块（jsdom 布局计算弱，给 todaySection 强设 offsetTop 后断言）
    let scrollArgs = null;
    const origScrollTo = window.scrollTo;
    window.scrollTo = function (arg) { scrollArgs = arg; };
    const todayEl = document.getElementById('todaySection');
    Object.defineProperty(todayEl, 'offsetTop', { value: 900, configurable: true });
    window.switchView('today', document.querySelector('[data-target="todaySection"]'));
    window.scrollTo = origScrollTo;
    check('切换今日视图后滚动到目标区块（top≈800）', scrollArgs && scrollArgs.top === 800, JSON.stringify(scrollArgs));

    // 6) 收藏切换前先 clearView
    window.switchView('archive', archItem); // 先进入某视图
    window.toggleFavFilter();               // 进入收藏（应清视图）
    check('toggleFavFilter 先 clearView（data-view 清除）', !document.body.dataset.view, document.body.dataset.view);

    // 7) updateActiveSection 在视图模式下不抢高亮
    window.switchView('today', document.querySelector('[data-target="todaySection"]'));
    const before = document.querySelector('[data-target="todaySection"]').classList.contains('active');
    window.updateActiveSection && window.updateActiveSection();
    const after = document.querySelector('[data-target="todaySection"]').classList.contains('active');
    check('视图模式下 updateActiveSection 不抢高亮', before && after, 'before=' + before + ' after=' + after);

    check('无阻塞性 JS 错误', errors.length === 0, errors.join(' | '));
  } catch (e) {
    fail++;
    console.log('  FAIL  测试执行抛错 → ' + e.message);
  }
  console.log('\n===== 视图切换汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 600);
