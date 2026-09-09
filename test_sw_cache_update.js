/**
 * 2026-09-09 Service Worker 缓存更新根治测试（jsdom）
 * 守护「部署后普通刷新即见最新版，无需手动清缓存」：
 *   ① sw.js 对 HTML 导航用 network-first + cache:'reload'（绕过浏览器与 CDN 缓存回源）
 *   ② index.html 的 SW 注册 URL 带 build-version 动态变化（否则写死 ?v=11 时 CDN 缓存旧 sw.js，
 *     浏览器检测不到 SW 更新，新 SW 接不了管）
 *   ③ sw.js activate 内通过 clients.navigate() 强制已打开页面重新导航，由 SW 自己完成「第二次刷新」
 *   ④ 运行时确实调用了 register('./sw.js?v=<build-version>')
 * 运行：node test_sw_cache_update.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name + (detail ? '  → ' + detail : '')); }
  else { fail++; console.log('  FAIL  ' + name + (detail ? '  → ' + detail : '')); }
}

const swPath = path.join(__dirname, 'sw.js');
const htmlPath = path.join(__dirname, 'index.html');
const swSrc = fs.readFileSync(swPath, 'utf-8');
const htmlSrc = fs.readFileSync(htmlPath, 'utf-8');

console.log('===== ① sw.js HTML 策略：SWR（秒开缓存 + 后台 cache:\'reload\' 拉新）=====');
const isHtmlBlock = (swSrc.split('if (isHtml)')[1] || '').split('if (DATA_FILES)')[0];
check('sw.js HTML 块采用 SWR（先返回缓存秒开）',
  isHtmlBlock.indexOf('caches.match(req)') >= 0 && isHtmlBlock.indexOf('return cached || network') >= 0,
  'HTML 块应 caches.match + return cached || network 实现秒开');
check('sw.js HTML 后台更新用 cache:\'reload\'（绕过 HTTP 缓存拿最新）',
  isHtmlBlock.indexOf("cache: 'reload'") >= 0,
  '后台静默拉新仍强制回源，保证最终最新');
check('sw.js 仍保留 skipWaiting + clients.claim',
  /self\.skipWaiting\(\)/.test(swSrc) && /self\.clients\.claim\(\)/.test(swSrc));
check('sw.js activate 内通过 clients.navigate() 强制已打开页面重新导航',
  /c\.navigate\s*\(\s*c\.url\s*\)/.test(swSrc),
  '新 SW 接管后主动刷新，避免旧页面仍渲染旧版');

console.log('\n===== ② index.html SW 注册 URL 动态化 =====');
const bvMatch = htmlSrc.match(/<meta name="build-version" content="([^"]+)"/);
const bv = bvMatch ? bvMatch[1] : '';
check('build-version meta 存在', !!bv, 'build-version=' + bv);
check('注册 URL 不再写死 ?v=11',
  !/register\(\s*'\.\/sw\.js\?v=11'\s*\)/.test(htmlSrc),
  '旧写死形式应已移除');
check('注册 URL 改为 ?v=<build-version> 动态拼接',
  /register\(\s*'\.\/sw\.js\?v='\s*\+\s*_bv\s*\)/.test(htmlSrc),
  "期望 register('./sw.js?v='+_bv)");
check('动态 URL 引用的 _bv 来自 build-version meta',
  /var _bv=\([^;]*getAttribute\('content'\)\)\|\|'1'/.test(htmlSrc));

console.log('\n===== ③ 运行时实际调用 register(动态 URL) =====');
// 复用 smoke 的加载骨架：内联数据文件，桩 matchMedia/fetch
let html = htmlSrc;
['news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  const tag = new RegExp('<script src="' + f + '"></script>');
  html = html.replace(tag, '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
});
const errors = [];
let captured = null;
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'https://pliucugb-cyber.github.io/mining-daily/',
  beforeParse(win) {
    if (typeof win.matchMedia !== 'function') {
      win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    }
    if (typeof win.fetch !== 'function') {
      win.fetch = () => Promise.reject(new Error('jsdom: fetch stub'));
    }
    // 桩 serviceWorker.register，捕获实际调用的 URL
    try {
      Object.defineProperty(win.navigator, 'serviceWorker', {
        configurable: true,
        value: {
          register(url) { captured = url; return Promise.resolve({ update() {} }); },
          addEventListener() {},
          getRegistration() { return Promise.resolve(null); }
        }
      });
    } catch (e) {}
    win.addEventListener('error', e => errors.push('window.error: ' + e.message));
    const origErr = win.console.error;
    win.console.error = (...a) => { errors.push('console.error: ' + a.join(' ')); origErr.apply(win.console, a); };
  }
});
const { window } = dom;

setTimeout(() => {
  // 若 load 事件未触发 register，手动补一次
  if (!captured) {
    try { window.dispatchEvent(new window.Event('load')); } catch (e) {}
  }
  setTimeout(() => {
    check('register 被实际调用', !!captured, 'captured=' + captured);
    if (captured) {
      check('注册 URL 含 ./sw.js?v= 前缀', captured.indexOf('./sw.js?v=') === 0, captured);
      check('注册 URL 包含当前 build-version',
        captured === './sw.js?v=' + bv,
        '期望 ./sw.js?v=' + bv + ' 实际 ' + captured);
    }
    check('无阻塞性 JS 错误', errors.length === 0, errors.slice(0, 3).join(' | '));
    console.log('\n===== 结果：' + pass + ' PASS / ' + fail + ' FAIL =====');
    process.exit(fail === 0 ? 0 : 1);
  }, 100);
}, 200);
