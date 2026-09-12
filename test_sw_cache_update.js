/**
 * 2026-09-10 Service Worker 缓存更新测试（jsdom）
 * 守护「部署后普通刷新即见最新版，且无循环/双重刷新」：
 *   ① sw.js 对 HTML/app.js 用 network-first（在线必拿新版，缓存仅离线兜底）
 *   ② index.html 的 SW 注册 URL 固定为 './sw.js'（不再拼 build-version 查询串）——避免缓存 HTML
 *      的版本戳与当前 SW 不一致时被浏览器当成「不同注册」而反复 install→activate 形成 ~10s 刷新死循环
 *   ③ sw.js activate 内只 postMessage('SW_UPDATED') 通知页面，由页面用一次性标志决定是否刷新
 *      （不再 clients.navigate() 强制整页重新导航，否则会叠加成循环/双重刷新）
 *   ④ 运行时确实调用了 register('./sw.js')（固定 URL）
 * 运行：node test_sw_cache_update.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

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

console.log('===== ① sw.js HTML/app.js 策略：network-first（在线必拿新版，缓存仅离线兜底）=====');
const isHtmlBlock = (swSrc.split('if (isHtml)')[1] || '').split('if (DATA_FILES')[0];
const dataListBlock = (swSrc.split('const DATA_FILES')[1] || '').split(']')[0];
// 2026-09-11 事故二次加固：HTML 由 SWR（cache-first）改为 network-first。
// 旧实现的 `return cached || network` 本质是 cache-first：缓存里只要躺着一份旧 index.html，
// 在线用户就会被一直喂旧页；而 Ctrl+Shift+R 并不会清 Service Worker 缓存，用户无论如何刷新
// 都出不来，只能永久停在「加载中…」。故改为向网络再验证（未变更 304 秒回）。
check('sw.js HTML 块不再是 cache-first（不再 return cached || network）',
  isHtmlBlock.indexOf('return cached || network') < 0,
  'cache-first 会让在线用户长期停留旧页，是 09-10/09-11 两次卡死的放大器');
check('sw.js HTML 走 network-first（先向网络再验证）',
  isHtmlBlock.indexOf('networkFirst(req') >= 0,
  '在线必须拿到线上最新 HTML；缓存只作离线兜底');
check('network-first 使用 no-cache 再验证（304 秒回，不全量重下）',
  swSrc.indexOf("cache: 'no-cache'") >= 0,
  'no-cache 触发条件请求：未变更 304 秒回、变更才下载，兼顾新鲜度与速度');
check('app.js 纳入 network-first 清单（防止旧逻辑常驻）',
  dataListBlock.indexOf("BASE + 'app.js'") >= 0,
  'app.js 每次发版都变；被 cache 持有会让用户永远拿不到修复');
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
  /application\/json/.test(swSrc) && /text\/javascript/.test(swSrc) &&
  !/caches\.match\(req\)\.then\(r => r \|\| caches\.match\(BASE \+ 'index\.html'\)\)/.test(swSrc),
  '旧实现会让 fetch(\'*.json\') 拿到 HTML，.json() 抛错');
// 2026-09-11 第三轮加固：离线兜底不得对 .js 回「空的 200」
check('离线兜底不再对 .js/.json 回空的 200，改 503',
  /status:\s*503/.test(swSrc) && swSrc.indexOf("new Response('', { status: 200") < 0,
  '空 200 会让 <script>「加载成功但没有数据」：连 onerror 都不触发，'
  + 'NEWS_DATA 静默变 undefined → 动态区块整片空白却查不到任何错误');
check('缓存读取统一走 safeMatch（respondWith 不会连拒绝）',
  /function safeMatch/.test(swSrc) && swSrc.indexOf('safeMatch(req)') >= 0
  && (swSrc.match(/caches\.match\(req\)/g) || []).length === 1,
  '直接读缓存只允许出现在 safeMatch 内部这一处；其余一律走兜底版，'
  + '否则 Cache Storage 抛错会让 respondWith 一并拒绝，浏览器只给出一个没有 message 的 '
  + 'error 事件（[object Event]），定位不到是哪一层坏了');

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

// ===== ⑧ 首次安装不得触发自动刷新（2026-09-12 用户实测：手机上「过 1 分钟左右又刷一次」）=====
// 根因：sw.js activate 无条件广播 SW_UPDATED；首装 SW 也会走到这条分支 → 页面 reload。
// 而首装时 install 要预缓存约 1MB（index.html+app.js+数据，且 cache:'reload' 绕过 HTTP 缓存），
// 弱网手机上耗时几十秒 —— 这就是那「1 分钟」的来源。修法：页面侧快照「本页是否已被 SW 接管」，
// controller 为空（= 首装）则跳过刷新；真·版本更新仍照刷。
// 真 Chrome 复现证据（%TEMP%\md_nav_reload_probe.js）：修复前首访主文档导航 2 次（第 2 次在
// install 跑完之后，预缓存加 10s 延迟则第 2 次从 +21.6s 推迟到 +51.4s）；修复后 1 次。
console.log('\n===== ⑧ 首装不得自动刷新（手机「过 1 分钟又刷一次」根因）=====');
check('app.js 在文档加载期快照「本页是否已被 SW 接管」',
  /var\s+__swCtlAtLoad\s*=\s*!!\s*navigator\.serviceWorker\.controller\s*;/.test(appSrc),
  '快照必须取在 claim 之前（脚本执行期）；若取在 load 之后，首装时读到的已是 true，守卫失效');
const swMsgBlock = (appSrc.split("addEventListener('message'")[1] || '').split('});')[0];
check('SW_UPDATED 分支：controller 为空（首装）直接 return，不 reload',
  /if\s*\(\s*!__swCtlAtLoad\s*\)\s*\{[\s\S]*?return;/.test(swMsgBlock),
  '首装时页面内容本来就是最新（HTML/app.js 走 network-first），这一刷纯属白刷');
check('首装守卫位于写版本戳/清缓存之前',
  swMsgBlock.indexOf('if(!__swCtlAtLoad)') >= 0 &&
  swMsgBlock.indexOf('if(!__swCtlAtLoad)') < swMsgBlock.indexOf('_clearHtmlCache()'),
  '顺序颠倒会把「页面正在看的这一版」记成已自愈，反而多触发一次硬刷新');
check('真·版本更新仍然会自动刷新（未把 reload 一并删掉）',
  swMsgBlock.indexOf('location.reload()') >= 0,
  '只有首装这一种情况该跳过；新版本上线后仍必须刷新到新版');

// app.js 之外还有第二条 SW 注册路径：index.html 内联兜底（app.js 不可用时也要能更新 SW）。
// ⚠️ 2026-09-12 教训：上一条守卫只改 app.js 时刷新依旧 —— 真元凶就是这里的 controllerchange。
//    它同样在首装 claim 时触发。查 SW/刷新类代码必须 **同时扫 index.html 内联脚本**（别只 grep *.js）。
const ctlBlock = (htmlSrc.split("addEventListener('controllerchange'")[1] || '').split('});')[0];
check('index.html 存在内联 controllerchange 守卫段',
  ctlBlock.length > 0 && /__swReloaded/.test(ctlBlock),
  '这段内联脚本是 app.js 之外的第二条注册路径，不能只看 app.js');
check('内联 controllerchange 也做「首装不刷新」判定',
  /var\s+__mdSwCtlAtStart\s*=\s*!!\s*navigator\.serviceWorker\.controller\s*;/.test(htmlSrc) &&
  /if\s*\(\s*!__mdSwCtlAtStart\s*\)\s*return;/.test(ctlBlock),
  '首装时 clients.claim() 也会触发 controllerchange；漏了它页面照样会在 SW 装好后自动刷一次');
check('内联守卫位于该段 location.reload 之前',
  ctlBlock.indexOf('if(!__mdSwCtlAtStart)return;') >= 0 &&
  ctlBlock.indexOf('if(!__mdSwCtlAtStart)return;') < ctlBlock.indexOf('location.reload()'),
  '顺序颠倒等于没修');
check('内联路径的换版刷新仍在（只拦首装，不拦真更新）',
  ctlBlock.indexOf('location.reload()') >= 0,
  '换版场景（开始时已被旧 SW 接管）必须继续刷新到新版');

// 行为双例：用 jsdom 跑真实 app.js，派发 SW_UPDATED，看它到底有没有去 navigate。
// jsdom 的 location.reload() 会以 jsdomError「Not implemented: navigation」暴露出来，据此计数。
function mdSwCase(controllerValue, cb) {
  let h = htmlSrc;
  ['app.js', 'news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
    const p = path.join(__dirname, f);
    if (!fs.existsSync(p)) return;
    h = h.replace(new RegExp('<script src="' + f + '[^>]*></script>'), () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
  });
  const nav = { n: 0 }, listeners = { message: [], controllerchange: [] };
  const vc = new VirtualConsole();
  vc.on('jsdomError', e => { if (/navigation/i.test(String(e && e.message))) nav.n++; });
  const dom = new JSDOM(h, {
    runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc,
    url: 'https://pliucugb-cyber.github.io/mining-daily/',
    beforeParse(win) {
      if (typeof win.matchMedia !== 'function') {
        win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
      }
      if (typeof win.fetch !== 'function') win.fetch = () => Promise.reject(new Error('jsdom: fetch stub'));
      try {
        Object.defineProperty(win.navigator, 'serviceWorker', {
          configurable: true,
          value: {
            controller: controllerValue,
            register() { return Promise.resolve({ update() {} }); },
            addEventListener(type, fn) { if (listeners[type]) listeners[type].push(fn); },
            getRegistration() { return Promise.resolve(null); }
          }
        });
      } catch (e) {}
    }
  });
  const t0 = Date.now();
  const ready = () => listeners.message.length > 0;
  (function wait() {
    if (ready() || Date.now() - t0 > 6000) {
      try { if (!ready()) dom.window.dispatchEvent(new dom.window.Event('load')); } catch (e) {}
      const t1 = Date.now();
      (function wait2() {
        if (ready() || Date.now() - t1 > 3000) {
          // 先派发 controllerchange（= SW 接管本页那一刻，index.html 内联守卫在这里），
          // 再派发 SW_UPDATED（app.js 的分支）。两次都记 navigation 次数。
          listeners.controllerchange.slice(0, 2).forEach(fn => { try { fn(); } catch (e) {} });
          setTimeout(() => {
            const nCtl = nav.n;
            listeners.message.slice(0, 2).forEach(fn => { try { fn({ data: { type: 'SW_UPDATED' } }); } catch (e) {} });
            setTimeout(() => {
              cb({ ctl: nCtl, msg: nav.n - nCtl, total: nav.n,
                   m: listeners.message.length, c: listeners.controllerchange.length }, dom);
            }, 150);
          }, 150);
          return;
        }
        setTimeout(wait2, 50);
      })();
      return;
    }
    setTimeout(wait, 50);
  })();
}

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

    // ⑧ 行为双例：① 首装（controller 为空）不得刷新 ② 已被旧 SW 接管时，换版仍须刷新
    mdSwCase(null, (a) => {
      check('行为①：首装（controller 为空）接管 + SW_UPDATED 都不得触发刷新',
        a.total === 0,
        '导航次数=' + a.total + '（controllerchange ' + a.ctl + ' / message ' + a.msg + '），'
        + '监听器 ' + a.c + 'c/' + a.m + 'm');
      mdSwCase({ scriptURL: 'https://pliucugb-cyber.github.io/mining-daily/sw.js' }, (b) => {
        check('行为②：已被旧 SW 接管时 controllerchange 仍会刷新（换版不会被一并吞掉）',
          b.ctl >= 1,
          '导航次数=' + b.total + '（controllerchange ' + b.ctl + ' / message ' + b.msg + '），'
          + '监听器 ' + b.c + 'c/' + b.m + 'm');
        console.log('\n===== 结果：' + pass + ' PASS / ' + fail + ' FAIL =====');
        process.exit(fail === 0 ? 0 : 1);
      });
    });
  }, 100);
}, 200);
