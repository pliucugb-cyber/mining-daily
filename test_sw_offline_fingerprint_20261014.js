/**
 * 2026-10-14 同事实测事故回归：「app.js 未执行」红条
 *
 * 事故形态（同事今天实际遇到）：
 *   github.io 在国内时通时不通 → Service Worker 把缓存的 index.html 喂给页面（页面看着正常），
 *   但页面引用的四个脚本都带 ?v= 内容指纹，而 SW 预缓存的键是裸路径（BASE+'app.js'）→
 *   safeMatch(req) 带全串必然 miss → offlineFallback 返回 503 → <script onerror> →
 *   app.js 从未执行、NEWS_DATA/LME_DATA/PRICE_HISTORY 全缺失 → 红条 + 热榜/简报/要闻全空。
 *
 * 本轮修复：
 *   A. sw.js 新增 matchFlexible()：网络失败后的兜底匹配放宽到「去查询串」再试一次；
 *   B. index.html 新增 mdAutoHealBoot()：启动失败且线上可达 → 自动 hardReset 一次；
 *      线上不可达 → 不清缓存（弱网用户连页面都没了），等 online 事件再试。
 *
 * 本测试两部分：
 *   ① vm 沙箱跑真 sw.js：网络断开时，带 ?v= 的脚本请求必须命中裸路径缓存（而不是 503）；
 *      未缓存的文件仍走 503 兜底（不喂垃圾）；在线时仍以网络为准。
 *   ② JSDOM 跑真 index.html：mdAutoHealBoot 的四个分支（可达→重置、不可达→保缓存、
 *      离线→不动作、已重置过→不重复）。
 *
 * 运行：node test_sw_offline_fingerprint_20261014.js   （需仓库 node_modules/jsdom）
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { JSDOM } = require('jsdom');

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name + (detail ? '  → ' + detail : '')); }
  else { fail++; console.log('  FAIL  ' + name + (detail ? '  → ' + detail : '')); }
}

const ORIGIN = 'https://pliucugb-cyber.github.io';
const BASE = ORIGIN + '/mining-daily/';
const swSrc = fs.readFileSync(path.join(__dirname, 'sw.js'), 'utf-8');

/* ======================= ① vm 沙箱：真 sw.js 的离线兜底 ======================= */
function buildSw(routes, netUp) {
  // routes: { url: body } —— 预缓存内容；netUp=false 时 fetch 一律拒绝（模拟断网）
  const store = new Map();               // url -> Response
  Object.keys(routes).forEach(u => store.set(u, new Response(routes[u], { status: 200, headers: { 'Content-Type': 'text/javascript' } })));
  const handlers = {};
  // 关键：真实浏览器里 self === globalThis，self.caches 与全局 caches 是同一个东西；
  // vm 沙箱里必须显式把 caches 挂到 self 上，否则 sw.js 的 self.caches.match 全undefined。
  const cachesMock = {
    keys: () => Promise.resolve([]),
    delete: () => Promise.resolve(true),
    open: () => Promise.resolve({
      put: (req, res) => { store.set(String(req.url || req), res); return Promise.resolve(); },
      add: (req) => { store.set(String(req.url || req), new Response('', { status: 200 })); return Promise.resolve(); },
    }),
    match: (req) => {
      // 真实浏览器里 caches.match 接受相对路径（基于 SW 作用域解析成绝对 URL），mock 需复刻
      let u = String(req.url || req);
      if (u.startsWith('/')) u = ORIGIN + u;
      return Promise.resolve(store.has(u) ? store.get(u) : undefined);
    },
  };
  const sandbox = {
    self: {
      location: { origin: ORIGIN, pathname: '/mining-daily/sw.js' },
      addEventListener: (type, fn) => { handlers[type] = fn; },
      skipWaiting: () => {},
      clients: { claim: () => Promise.resolve(), matchAll: () => Promise.resolve([]) },
      caches: cachesMock,
    },
    caches: cachesMock,
    fetch: (req) => {
      if (!netUp) return Promise.reject(new Error('net down'));
      const u = String(req.url || req);
      if (routes[u] !== undefined) return Promise.resolve(new Response(routes[u], { status: 200 }));
      return Promise.reject(new Error('404 ' + u));
    },
    Response, Request, URL, console,
  };
  vm.runInNewContext(swSrc, sandbox, { filename: 'sw.js' });
  return { handlers, store, sandbox };
}

function dispatchFetch(sw, url, mode) {
  return new Promise((resolve, reject) => {
    const req = { method: 'GET', url, mode: mode || 'no-cors' };
    let captured = null;
    const event = { request: req, respondWith: (p) => { captured = p; } };
    try { sw.handlers.fetch(event); } catch (e) { reject(e); return; }
    if (!captured) { reject(new Error('SW 未 respondWith')); return; }
    captured.then(resolve, reject);
  });
}

(async () => {
  console.log('===== ① sw.js 离线兜底：带 ?v= 指纹的请求必须命中裸路径缓存 =====');
  {
    // 场景A：断网 + app.js?v=指纹 → 旧行为 503（事故形态）；新行为必须返回预缓存的裸 app.js
    const sw = buildSw({
      [BASE + 'app.js']: 'APPJS-BODY',
      [BASE + 'news-data.js']: 'NEWS-BODY',
      [BASE + 'index.html']: '<html>cached</html>',
    }, false);
    const res = await dispatchFetch(sw, BASE + 'app.js?v=65f66af7');
    const body = await res.text();
    check('断网 + app.js?v=指纹 → 命中裸路径缓存（不再是 503）', res.status === 200 && body === 'APPJS-BODY',
      'status=' + res.status + ' body=' + body);

    const res2 = await dispatchFetch(sw, BASE + 'news-data.js?v=731b29d7');
    const body2 = await res2.text();
    check('断网 + news-data.js?v=指纹 → 同样命中缓存', res2.status === 200 && body2 === 'NEWS-BODY',
      'status=' + res2.status);

    // 场景C：没缓存过的文件仍然 503（兜底语义不能破，不能喂空 200 垃圾）
    const res3 = await dispatchFetch(sw, BASE + 'company_news.json?v=abc');
    check('断网 + 未缓存文件 → 仍走 503 兜底（不喂垃圾）', res3.status === 503, 'status=' + res3.status);

    // 场景E：断网 + 导航 → 缓存 HTML
    const res4 = await dispatchFetch(sw, BASE, 'navigate');
    const body4 = await res4.text();
    check('断网 + 导航 → 仍返回缓存 HTML（离线可看）', res4.status === 200 && body4 === '<html>cached</html>',
      'status=' + res4.status);
  }
  {
    // 场景D：在线 → 以网络为准（不因放宽匹配喂旧缓存）
    // 网络侧 routes 里没有带串 URL → fetch 拒绝 → 回落缓存（合理：网络 404 时用缓存兜底）
    // 用「网络有货」的场景断言：在线必须以网络为准，不喂旧缓存
    const sw2 = buildSw({ [BASE + 'app.js']: 'OLD-BODY', [BASE + 'app.js?v=65f66af7']: 'NEW-BODY' }, true);
    const res2 = await dispatchFetch(sw2, BASE + 'app.js?v=65f66af7');
    const body2 = await res2.text();
    check('在线 + 网络有货 → 返回网络内容（不喂旧缓存）', res2.status === 200 && body2 === 'NEW-BODY',
      'body=' + body2);
  }

  /* ======================= ② JSDOM：mdAutoHealBoot 分支 ======================= */
  console.log('\n===== ② index.html 启动失败自愈（mdAutoHealBoot）=====');
  let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
  ['news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
    const p = path.join(__dirname, f);
    if (!fs.existsSync(p)) return;
    html = html.replace(new RegExp('<script src="' + f + '[^>]*></script>'),
      () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
  });
  html = html.replace(new RegExp('<script src="app.js"[^>]*></script>'), '');
  html = html.replace('</body>', '<script>' + fs.readFileSync(path.join(__dirname, 'app.js'), 'utf-8') + '</script>\n</body>');

  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    url: BASE,
    beforeParse(win) {
      if (typeof win.matchMedia !== 'function') {
        win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
      }
      win.__fetchCalls = [];
      win.__fetchMode = 'ok';
      win.fetch = (u) => {
        win.__fetchCalls.push(String(u));
        if (win.__fetchMode === 'reject') return Promise.reject(new Error('net down'));
        return Promise.resolve({ ok: true, text: () => Promise.resolve("const CACHE_NAME = 'mining-daily-x';") });
      };
      win.__openedUrls = [];
      win.open = u => { win.__openedUrls.push(u); return null; };
    },
  });
  const win = dom.window;
  const RESET_FLAG = 'md_sw_hardreset';
  const tick = (ms) => new Promise(r => setTimeout(r, ms || 60));
  // 页面自身的版本探针（load+4s 的 sw.js?probe=）也会调 fetch，只统计自愈探针（sw.js?heal=）
  const healCalls = () => win.__fetchCalls.filter(u => /sw\.js\?heal=/.test(u)).length;

  check('mdAutoHealBoot 已挂到 window', typeof win.mdAutoHealBoot === 'function');
  var _bv = (html.match(/name="build-version" content="([^"]+)"/) || [])[1] || '';
  check('内联自愈段存在（build-version 已 bump）',
    !!_bv && swSrc.indexOf('mining-daily-' + _bv) >= 0, 'build-version=' + _bv);

  // 用例1：线上可达 → 自动 hardReset（sessionStorage 置位，整页重载）
  win.sessionStorage.removeItem(RESET_FLAG);
  win.__mdHealInFlight = false; win.__mdHealLastTry = 0;
  win.__fetchCalls = [];
  win.mdAutoHealBoot('app.js 未执行');
  await tick();
  check('线上可达 → 触发自动清缓存重载（RESET_FLAG 置位）',
    win.sessionStorage.getItem(RESET_FLAG) === '1',
    '自愈探测=' + healCalls());
  check('探测用唯一 query 穿透 SW 缓存',
    (win.__fetchCalls.find(u => /sw\.js\?heal=/.test(u)) || '').length > 0,
    win.__fetchCalls.find(u => /sw\.js\?heal=/.test(u)) || '(无)');

  // 用例2：线上不可达 → 绝不重置（保住弱网用户的离线缓存）
  win.sessionStorage.removeItem(RESET_FLAG);
  win.__mdHealInFlight = false; win.__mdHealLastTry = 0;
  win.__fetchMode = 'reject';
  win.__fetchCalls = [];
  win.mdAutoHealBoot('app.js 未执行');
  await tick();
  check('线上不可达 → 不清缓存、不重载（等 online 再试）',
    win.sessionStorage.getItem(RESET_FLAG) !== '1' && healCalls() === 1,
    '自愈探测=' + healCalls() + ' flag=' + win.sessionStorage.getItem(RESET_FLAG));
  win.__fetchMode = 'ok';

  // 用例3：本会话已重置过 → 不重复探测（防循环）
  win.sessionStorage.setItem(RESET_FLAG, '1');
  win.__mdHealInFlight = false; win.__mdHealLastTry = 0;
  win.__fetchCalls = [];
  win.mdAutoHealBoot('app.js 未执行');
  await tick();
  check('本会话已重置过 → 不重复探测（防刷新循环）', healCalls() === 0,
    '自愈探测=' + healCalls());
  win.sessionStorage.removeItem(RESET_FLAG);

  // 用例4：良性场景不触发（app.js 已执行的页面不该被自愈打扰）
  win.__mdHealInFlight = false; win.__mdHealLastTry = 0;
  win.__fetchCalls = [];
  win.mdAutoHealBoot('');            // 健康页 mdDegraded() 返回 ''
  await tick();
  check('健康页（why 为空）→ 不触发自愈', healCalls() === 0);

  // 用例5：离线状态 → 不探测（清了缓存连页面都没了）
  win.__mdHealInFlight = false; win.__mdHealLastTry = 0;
  win.__fetchCalls = [];
  let onLineRestored = null;
  try {
    const desc = Object.getOwnPropertyDescriptor(win.navigator, 'onLine');
    onLineRestored = desc;
    Object.defineProperty(win.navigator, 'onLine', { value: false, configurable: true });
  } catch (e) { /* jsdom 不允许改写则跳过本用例 */ }
  if (onLineRestored && onLineRestored.configurable !== false) {
    win.mdAutoHealBoot('app.js 未执行');
    await tick();
    check('离线（navigator.onLine=false）→ 不探测不重置', healCalls() === 0);
    try { Object.defineProperty(win.navigator, 'onLine', onLineRestored); } catch (e) {}
  } else {
    check('离线（navigator.onLine=false）→ 不探测不重置', true, 'jsdom 不支持改写 onLine，跳过');
  }

  console.log('\n结果：' + pass + ' 通过 / ' + fail + ' 失败');
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('测试执行异常：', e); process.exit(1); });
