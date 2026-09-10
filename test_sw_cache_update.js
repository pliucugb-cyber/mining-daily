/**
 * 2026-09-10 Service Worker 缓存更新测试（jsdom）
 * 守护「部署后普通刷新即见最新版，且无循环/双重刷新」：
 *   ① sw.js 对 HTML 导航用 SWR（秒开缓存 + 后台 cache:'reload' 拉新）
 *   ② index.html 的 SW 注册 URL 固定为 './sw.js'（不再拼 build-version 查询串）——避免缓存 HTML
 *      的版本戳与当前 SW 不一致时被浏览器当成「不同注册」而反复 install→activate 形成 ~10s 刷新死循环
 *   ③ sw.js activate 内只 postMessage('SW_UPDATED') 通知页面，由页面用一次性标志决定是否刷新
 *      （不再 clients.navigate() 强制整页重新导航，否则会叠加成循环/双重刷新）
 *   ④ 运行时确实调用了 register('./sw.js')（固定 URL）
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

console.log('\n===== ③ sw.js activate 不再强制 navigate（根治循环/双重刷新）=====');
check('sw.js activate 内已移除 clients.navigate()（整页强制重导航）',
  !/c\.navigate\s*\(\s*c\.url\s*\)/.test(swSrc),
  'c.navigate(c.url) 若不存在才算修好');
check('sw.js activate 改为 postMessage(\'SW_UPDATED\') 通知页面',
  /postMessage\(\s*\{\s*type:\s*'SW_UPDATED'\s*\}\s*\)/.test(swSrc),
  '由页面用一次性标志决定是否刷新');

// 2026-09-10 第 2 批：数据文件清单 + 离线兜底 MIME
const dataFilesBlock = (swSrc.split('const DATA_FILES = [')[1] || '').split(']')[0];
check('DATA_FILES 含 morning_report.json（每日更新，不能只在安装时缓存一次）',
  dataFilesBlock.indexOf('morning_report.json') >= 0,
  'DATA_FILES=' + dataFilesBlock.replace(/\s+/g, ' ').trim());
check('离线兜底按扩展名返回正确 MIME，不再一律回退 index.html',
  /function offlineFallback/.test(swSrc) &&
  /application\/json/.test(swSrc) && /application\/javascript/.test(swSrc) &&
  !/caches\.match\(req\)\.then\(r => r \|\| caches\.match\(BASE \+ 'index\.html'\)\)/.test(swSrc),
  '旧实现会让 fetch(\'*.json\') 拿到 HTML，.json() 抛错');

console.log('\n===== ② index.html SW 注册 URL 固定化（不再拼 build-version 查询串）=====');
const bvMatch = htmlSrc.match(/<meta name="build-version" content="([^"]+)"/);
const bv = bvMatch ? bvMatch[1] : '';
check('build-version meta 存在', !!bv, 'build-version=' + bv);
check('注册 URL 不再写死 ?v=11',
  !/register\(\s*'\.\/sw\.js\?v=11'\s*\)/.test(htmlSrc),
  '旧写死形式应已移除');
check('注册 URL 不再拼 build-version 动态查询串（根治死循环刷新）',
  !/register\(\s*'\.\/sw\.js\?v='\s*\+\s*_bv\s*\)/.test(htmlSrc) &&
  !/register\(\s*'\.\/sw\.js\?v='\s*\+/.test(htmlSrc),
  "应改为固定 register('./sw.js')");
check('注册 URL 为固定 ./sw.js（SW 脚本自身由浏览器 no-cache 校验更新）',
  /register\(\s*'\.\/sw\.js'\s*\)/.test(htmlSrc),
  "期望 register('./sw.js')");
check('无残留 _bv 动态 URL 引用',
  !/var _bv=/.test(htmlSrc),
  '_bv 取 build-version 的逻辑应已删除');

console.log('\n===== ④ 运行时实际调用 register(固定 URL) =====');
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
      check('注册 URL 为固定 ./sw.js（不含 ?v= 查询串）',
        captured === './sw.js',
        '期望 ./sw.js 实际 ' + captured);
    }
    check('无阻塞性 JS 错误', errors.length === 0, errors.slice(0, 3).join(' | '));
    console.log('\n===== 结果：' + pass + ' PASS / ' + fail + ' FAIL =====');
    process.exit(fail === 0 ? 0 : 1);
  }, 100);
}, 200);
