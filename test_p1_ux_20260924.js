/**
 * 2026-09-24 P1 UX 批处理回归（#6/#7 优化清单落地）
 * 覆盖：A1 全局回到顶部 / F5 焦点轮廓 / D1 视图淡入 / D4 更新时间+刷新 / A4 深链 / B3 关键词订阅 / E2 窄屏日期
 * 校验两类契约：
 *   ① index.html <style> 内的 CSS 规则文本存在；
 *   ② app.js 内新增函数 / 调用点 / 嵌入片段存在；
 *   ③ jsdom 实跑抽取出的 P1 函数块（mdP1UXInit），确认 DOM 真实产物（#mdTopBtn / .md-update-time / 关键词订阅入口）。
 * 运行：node test_p1_ux_20260924.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log('  ✓ ' + name); }
  else { fail++; console.log('  ✗ ' + name + (extra ? ' — 实际：' + extra : '')); }
}

const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
const appjs = fs.readFileSync(path.join(__dirname, 'app.js'), 'utf-8');
const cssAll = (html.match(/<style[^>]*>([\s\S]*?)<\/style>/g) || [])
  .map(s => s.replace(/<\/?style[^>]*>/g, '')).join('\n');

console.log('===== ① CSS 规则契约 =====');
check('A1 #mdTopBtn 样式规则存在', /#mdTopBtn\{/.test(cssAll));
check('A1 #mdTopBtn.show 显现规则存在', /#mdTopBtn\.show\{opacity:1;pointer-events:auto\}/.test(cssAll));
check('F5 全局 :focus-visible 轮廓存在', /:focus-visible\{outline:2px solid var\(--brand\)/.test(cssAll));
check('D1 @keyframes mdViewFade 存在', /@keyframes mdViewFade\{from\{opacity:0\}to\{opacity:1\}\}/.test(cssAll));
check('D1 .md-view-enter 淡入类存在', /\.md-view-enter\{animation:mdViewFade/.test(cssAll));
check('D4 .md-update-time 存在', /\.md-update-time\{/.test(cssAll));
check('D4 .md-refresh-btn 存在', /\.md-refresh-btn\{/.test(cssAll));
check('B3 .md-watch 命中高亮存在（无发光）', /\.md-watch\{box-shadow:inset 3px 0 0 var\(--brand\);background:var\(--brand-soft\)\}/.test(cssAll));
check('B3 .mine-watch-editor 编辑器样式存在', /\.mine-watch-editor\{/.test(cssAll));
check('深链 .md-flash 闪烁类存在', /\.md-flash\{animation:mdFlash/.test(cssAll));
check('reduced-motion 覆盖不影响新动画（既有规则）', /prefers-reduced-motion/.test(cssAll));

console.log('===== ② app.js 代码契约 =====');
check('入口函数 mdP1UXInit 已定义', /function mdP1UXInit\(\)/.test(appjs));
check('A1 mdInitTopButton 已定义', /function mdInitTopButton\(\)/.test(appjs));
check('D4 mdInitUpdateTime 已定义', /function mdInitUpdateTime\(\)/.test(appjs));
check('D4 mdManualRefresh 已定义', /function mdManualRefresh\(\)/.test(appjs));
check('A4 mdInitDeepLink 已定义', /function mdInitDeepLink\(\)/.test(appjs));
check('B3 mdInitWatchWords 已定义', /function mdInitWatchWords\(\)/.test(appjs));
check('B3 mdApplyWatch 已定义', /function mdApplyWatch\(\)/.test(appjs));
check('mdP1UXInit() 已在 DOMContentLoaded 调用（唯一）', (appjs.match(/mdP1UXInit\(\);/g) || []).length === 1);
check('E2 窄屏日期短格式（MM-DD 周X）片段存在', /E2：窄屏日期短格式 MM-DD 周X/.test(appjs));
check('D1 switchView 内对已切视图区块加 .md-view-enter', /targetEl\.classList\.remove\('md-view-enter'\)/.test(appjs));
check('A4 深链视图映射 today/archive/rights/company 存在', /viewMap=\{'todaySection':'today'/.test(appjs));
check('B3 我的面板刷新入口 data-act="refresh" 已注入', /data-act="refresh"/.test(appjs));
check('B3 关键词订阅本地存储键 mdWatchWords 使用', /var KEY='mdWatchWords'/.test(appjs));

console.log('===== ③ jsdom 实跑 P1 函数块 =====');
try {
  const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://example.com/' });
  const w = dom.window;
  // 构造 P1 函数依赖的最小 DOM 片段（#mineSheet 由运行时注入，测试里补一个 theme 项）
  let mine = w.document.getElementById('mineSheet');
  if (!mine) { mine = w.document.createElement('div'); mine.id = 'mineSheet'; w.document.body.appendChild(mine); }
  if (!mine.querySelector('[data-act="theme"]')) {
    const ti = w.document.createElement('button'); ti.setAttribute('data-act', 'theme'); mine.appendChild(ti);
  }
  if (!w.document.querySelector('.date-badge')) {
    const db = w.document.createElement('span'); db.className = 'date-badge'; db.textContent = '2026-09-24 周四'; w.document.body.appendChild(db);
  }
  // 抽取并执行业务函数块（含全部 md* 定义），再调用入口
  // 本次一并切掉块尾的 window.addEventListener('DOMContentLoaded', …)：见 ④ 的同类说明。
  // （本文件结束前是不再立即 exit 的异步段，该监听器会在 jsdom load 事件里刷无关报错。）
  const i = appjs.indexOf('// ===== 2026-09-24 P1 UX');
  const j = appjs.indexOf('// ===== 版本戳记录');
  if (i < 0 || j < 0) throw new Error('未定位 P1 函数块边界');
  const cutI = appjs.indexOf("window.addEventListener('DOMContentLoaded'", i);
  const block = appjs.slice(i, cutI > i ? cutI : j);
  w.eval(block);
  w.eval('mdP1UXInit()');
  check('A1 运行时创建 #mdTopBtn', !!w.document.getElementById('mdTopBtn'));
  // 期望值由页面 build-version 现算，不再写死日期（写死会在换日后天天假 FAIL）
  const _bv = html.match(/name="build-version" content="(\d{4})(\d{2})(\d{2})/);
  const _bvDay = _bv ? _bv[1] + '-' + _bv[2] + '-' + _bv[3] : '';
  check('D4 运行时注入 .md-update-time（解析 build ' + _bvDay + '）', (w.document.querySelector('.md-update-time') || {}).textContent === '更新于 ' + _bvDay.slice(5));
  check('D4 运行时注入 .md-refresh-btn', !!w.document.querySelector('.md-refresh-btn'));
  check('B3 我的面板注入「关键词订阅」入口（data-act=watch）', !!w.document.querySelector('[data-act="watch"]'));
  check('B3 关键词订阅编辑器 #mineWatchEditor 已注入', !!w.document.getElementById('mineWatchEditor'));
} catch (e) {
  check('③ jsdom 实跑未抛异常（' + e.message + '）', false);
}

// ===== ④ 2026-09-28「打开一律回首页·全部内容」冷启动回归（REFERENCE.md §42.44）=====
// 复现用户场景：URL 残留 #/companySection（浏览器书签/历史/地址栏自动补全里由 09-27
// 「目录项点击写 hash」留下的旧 hash，以及已装 PWA 快捷方式里带的 start_url）→
// 新打开不得再被劫持到矿业公司视图；同时【内容级深链 #/news-<id>】必须仍然生效。
(async function () {
  console.log('\n===== ④ 冷启动不再被 URL 残留分类 hash 劫持（2026-09-28 §42.44）=====');
  const b = appjs.indexOf('// ===== 2026-09-24 P1 UX');
  const e = appjs.indexOf('// ===== 版本戳记录');
  check('④ 定位 P1 函数块边界', b >= 0 && e > b, 'b=' + b + ' e=' + e);
  // 只取「函数定义」段：切掉块尾的 window.addEventListener('DOMContentLoaded', …)
  // —— 本段是异步等待（800ms），若把该监听器一起 eval 进来，它会在 jsdom 的 load 事件里
  //    调用 mdMobileTopTabs()/scrollTo() 等本段未定义的函数，刷一屏无关报错、淹没断言输出。
  const cut = appjs.indexOf("window.addEventListener('DOMContentLoaded'", b);
  const block = appjs.slice(b, cut > b ? cut : e);

  function boot(url) {
    const d = new JSDOM('<!doctype html><html><body><div id="news-n1"></div></body></html>',
      { runScripts: 'outside-only', pretendToBeVisual: true, url: url });
    const w = d.window;
    // jsdom 未实现 scrollIntoView：补空实现，避免深链定位分支抛错干扰断言
    try { w.HTMLElement.prototype.scrollIntoView = function () {}; } catch (e2) {}
    const calls = [];
    w.mdSelectCat = function (c) { calls.push('cat:' + c); };
    w.switchView = function (v) { calls.push('view:' + v); };
    w.eval(block);
    w.mdInitDeepLink();
    return { w: w, calls: calls };
  }

  const c1 = boot('https://example.com/#/companySection');
  await new Promise(function (r) { setTimeout(r, 800); });
  check('④ 残留 #/companySection 冷启动不再切矿业公司视图', c1.calls.length === 0, JSON.stringify(c1.calls));
  check('④ 残留分类 hash 已清洗（不再传染下次打开）', c1.w.location.hash === '', JSON.stringify(c1.w.location.hash));

  const c2 = boot('https://example.com/#/news-n1');
  await new Promise(function (r) { setTimeout(r, 800); });
  check('④ 内容级深链 #/news-<id> 冷启动仍生效（未被清洗）',
        c2.calls.length === 0 && c2.w.location.hash === '#/news-n1', JSON.stringify(c2.w.location.hash));

  const c3 = boot('https://example.com/#/rightsSection');
  await new Promise(function (r) { setTimeout(r, 800); });
  check('④ 其它分类 hash（#/rightsSection）同样不再劫持',
        c3.calls.length === 0 && c3.w.location.hash === '', JSON.stringify(c3.calls) + ' hash=' + JSON.stringify(c3.w.location.hash));

  console.log('\n===== 结果 =====');
  console.log('通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
})();
