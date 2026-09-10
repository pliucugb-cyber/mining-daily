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
const appPath = path.join(__dirname, 'app.js');
const swSrc = fs.readFileSync(swPath, 'utf-8');
// 2026-09-10 性能优化：SW 注册调用已随应用逻辑外置到 app.js(defer)，注册 URL 断言改读 app.js
const htmlSrc = fs.readFileSync(htmlPath, 'utf-8');
const appSrc = fs.readFileSync(appPath, 'utf-8');

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
// 注册调用体已迁至 app.js：以下断言改读 appSrc
check('注册 URL 不再写死 ?v=11',
  !/register\(\s*'\.\/sw\.js\?v=11'\s*\)/.test(appSrc),
  '旧写死形式应已移除');
check('注册 URL 不再拼 build-version 动态查询串（根治死循环刷新）',
  !/register\(\s*'\.\/sw\.js\?v='\s*\+\s*_bv\s*\)/.test(appSrc) &&
  !/register\(\s*'\.\/sw\.js\?v='\s*\+/.test(appSrc),
  "应改为固定 register('./sw.js')");
check('注册 URL 为固定 ./sw.js（SW 脚本自身由浏览器 no-cache 校验更新）',
  /register\(\s*'\.\/sw\.js'\s*\)/.test(appSrc),
  "期望 register('./sw.js')");
check('无残留 _bv 动态 URL 引用',
  !/var _bv=/.test(htmlSrc),
  '_bv 取 build-version 的逻辑应已删除（index.html）');

console.log('\n===== ⑤ sw.js 必须能被真正解析 + 缓存名与 build-version 一致（2026-09-10 事故回归）=====');
// 事故：sw.js 第 10 行被写坏成 `const P260910-1900';`（SyntaxError）后原样上线 →
// SW 永远无法更新 → 用户卡在旧的/不完整的缓存 → 页面各区块一直停在「加载中…」。
// 此前本测试只把 sw.js 当字符串做正则匹配，语法错误完全测不出来。此处用 vm 真正编译。
let swParseOk = true, swParseErr = '';
try { new (require('vm').Script)(swSrc, { filename: 'sw.js' }); }
catch (e) { swParseOk = false; swParseErr = e.message; }
check('sw.js 可被真正解析（无语法错误）', swParseOk, swParseErr || 'vm.Script 编译通过');
const cnameMatch = swSrc.match(/const\s+CACHE_NAME\s*=\s*'([^']*)'/);
check('sw.js 存在合法 CACHE_NAME 声明', !!cnameMatch,
  'CACHE_NAME=' + (cnameMatch ? cnameMatch[1] : '(缺失)'));
check('CACHE_NAME === mining-daily-<build-version>',
  !!cnameMatch && cnameMatch[1] === 'mining-daily-' + bv,
  '期望 mining-daily-' + bv + ' 实际 ' + (cnameMatch ? cnameMatch[1] : '(缺失)'));

const installBlock = (swSrc.split("self.addEventListener('install'")[1] || '')
  .split("self.addEventListener('activate'")[0];
check('install 预缓存改为逐条容错（不再 addAll 整批原子失败）',
  installBlock.indexOf('addAll(') < 0 && installBlock.indexOf('urlsToCache.map(') >= 0,
  'addAll 遇到任一 404（如可选的 morning_report.json）会让整批预缓存失败');

console.log('\n===== ⑥ 刷新机制健壮性（app.js 运行时自愈 / 数据看门狗）=====');
check('_clearHtmlCache 只删非当前版本缓存（不再连当前缓存一起清空）',
  /name!==keep/.test(appSrc),
  '清掉当前缓存会留下「空缓存窗口」→ 数据取不到 → 停在加载中');
check('SW 注册失败有自愈（清理失效注册/缓存并重载一次，带会话级防抖）',
  /md_sw_selfheal/.test(appSrc) && /\.unregister\(\)/.test(appSrc),
  '卡在坏 SW 的用户需要能自动恢复');
check('存在数据看门狗：NEWS_DATA 缺失时给出可操作提示而非无限「加载中…」',
  /function mdDataWatchdog/.test(appSrc) && /mdDataWatchdog\(\)/.test(appSrc),
  '占位永不结束会让人以为是慢，而不是失败');

console.log('\n===== ⑦ 门禁覆盖：sw.js 已纳入语法校验（防止再次静默上线）=====');
const deploySrc = fs.readFileSync(path.join(__dirname, 'deploy_pages.py'), 'utf-8');
const preflightSrc = fs.readFileSync(path.join(__dirname, 'preflight_check.py'), 'utf-8');
check('deploy_pages.py 含 sw.js 语法/缓存名校验（validate_sw_js）',
  /def validate_sw_js/.test(deploySrc) && /'--check'/.test(deploySrc),
  '部署前必须真正解析 sw.js');
check('deploy_pages.py 找不到 CACHE_NAME 时 fail-fast（不再静默 return）',
  /raise RuntimeError/.test(deploySrc) && /找不到可改写的/.test(deploySrc),
  '旧实现匹配不到就打「已是最新」静默跳过 → 把坏 sw.js 推上线');
check('preflight_check.py 已加入 sw.js 语法检查项',
  /def check_sw_js/.test(preflightSrc) && /sw\.js 语法/.test(preflightSrc),
  '06:00 自动化闸门也要能拦');

console.log('\n===== ④ 运行时实际调用 register(固定 URL) =====');
let html = htmlSrc;
['app.js', 'news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  const tag = new RegExp('<script src="' + f + '[^>]*></script>');
  html = html.replace(tag, () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
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
