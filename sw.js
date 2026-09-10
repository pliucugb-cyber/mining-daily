// mining-daily Service Worker
// 2026-09-04 修复：改为 network-first（HTML 永远优先拿线上最新版，离线才用缓存）
// + 缓存版本号 bump + activate 时清掉所有旧缓存 + 新 SW 激活后通知页面自动刷新
// 这样任何访客无需手动 Ctrl+F5 即可看到最新内容。
// 2026-09-04 二次修复：支持子路径部署（GitHub Pages 站点位于 /mining-daily/）。
//   原先写死 '/index.html' 这类绝对路径，在子路径下会指向站点根而 404。
//   改为以 SW 自身所在目录为基准推导 BASE，根路径部署（本地/沙箱）与子路径部署（Pages）均可。
// 2026-09-11 事故二次加固（原因见下）：
//   09-10 事故复盘发现「HTML/app.js 走 stale-while-revalidate」是长期卡死的放大器——
//   SWR 是 cache-first，只要缓存里躺着一份旧 HTML/旧 app.js，在线用户也会被一直喂旧版；
//   而 Ctrl+Shift+R 并不会清 Service Worker 缓存，用户无论如何刷新都出不来。
//   故本轮把 HTML 与 app.js 一并改成 **network-first + no-cache 再验证**（304 秒回，不变也快），
//   缓存只作离线兜底。牺牲一点点「秒开」，换「在线用户永不卡旧版」。
// ⚠️ CACHE_NAME 由 deploy_pages.py::sync_sw_cache_name() 依据 index.html 的 build-version
//    自动派生（mining-daily-<build-version>）。请勿手改本行的字面量：
//    2026-09-10 事故——本行被改写成 `const P260910-1900';`（语法错误），
//    导致 sw.js 无法解析 → SW 永远无法更新 → 用户卡在旧的/不完整缓存里，页面区块一直停在「加载中…」。
//    现 deploy_pages.py 与 preflight_check.py 都会对 sw.js 做语法校验，写坏即拒绝部署。
const CACHE_NAME = 'mining-daily-20260911-0140';

// 以 SW 自身位置推导站点基路径：
//   /sw.js              → BASE = '/'
//   /mining-daily/sw.js → BASE = '/mining-daily/'
const BASE = (function () {
  var p = self.location.pathname || '/';
  return p.replace(/[^/]*$/, '');
})();

// price-history.js（价格走势数据）预缓存
const urlsToCache = [
  BASE,
  BASE + 'index.html',
  BASE + 'news-data.js',
  BASE + 'lme-data.js',
  BASE + 'price-history.js',
  BASE + 'app.js',
  BASE + 'morning_report.json'
];
// 必须 network-first 的文件：每日更新的数据 + 每次发版都变的 app.js。
// 这些文件一旦被 cache-first 命中旧副本，页面就会长期停在旧内容/旧逻辑上
// （2026-09-11 事故根因之一：app.js 曾被 stale-while-revalidate 缓存持有，用户无法自愈）。
const DATA_FILES = [
  BASE + 'news-data.js',
  BASE + 'lme-data.js',
  BASE + 'price-history.js',
  BASE + 'morning_report.json',  // 2026-09-10 P1：晨报每日更新，此前只在 urlsToCache 里缓存一份，SWR 会一直喂昨天的
  BASE + 'app.js'                // 2026-09-11：每次发版都变，必须 network-first，否则旧逻辑常驻
];

// 2026-09-10 P1：离线兜底必须保持正确 MIME。
// 旧实现对所有取不到的请求一律回退 index.html —— 于是 fetch('morning_report.json')
// 拿到的是 HTML，.json() 直接抛错，页面表现成「简报区神秘隐藏」而看不出根因。
// 现在按扩展名给出正确类型的最小合法响应；只有导航请求才回退 index.html。
function offlineFallback(pathname) {
  if (/\.json$/i.test(pathname)) {
    return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
  }
  if (/\.js$/i.test(pathname)) {
    return new Response('', { status: 200, headers: { 'Content-Type': 'application/javascript; charset=utf-8' } });
  }
  return caches.match(BASE + 'index.html').then(function (c) {
    return c || new Response('<!DOCTYPE html><meta charset="utf-8"><p>离线且无可用缓存，请联网后重试。</p>', {
      status: 503,
      headers: { 'Content-Type': 'text/html; charset=utf-8' }
    });
  });
}

// network-first：先向网络要（no-cache 强制再验证，未变更时 304 秒回），
// 成功则顺手写缓存；网络失败才退回缓存/离线兜底。
// 注意：cache:'no-cache' 只会触发条件请求，不会像 'reload' 那样每次全量重下，
//      因此既保证「在线必拿新版」，又不会明显拖慢刷新。
function networkFirst(req, pathname) {
  return fetch(req, { cache: 'no-cache' }).then(function (res) {
    if (res && res.ok && res.type === 'basic') {
      var copy = res.clone();
      caches.open(CACHE_NAME).then(function (c) { return c.put(req, copy); }).catch(function () {});
    }
    return res;
  }).catch(function () {
    return caches.match(req).then(function (c) {
      return c || offlineFallback(pathname);
    });
  });
}

self.addEventListener('install', event => {
  // 强制新 SW 立即激活，不等旧标签页关闭
  self.skipWaiting();
  // 2026-09-10 修复：原先用 cache.addAll（一次性批量写入清单），只要清单里有一个 URL 不可用
  // （例如可选的 morning_report.json 在 Pages 上 404），addAll 会「整体原子失败」→
  // 一条都不预缓存 → 首屏秒开与离线兜底全部静默失效（.catch(()=>{}) 把原因也吞了）。
  // 改为逐条 add：单条失败只记录并跳过，其余照常预缓存。
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      Promise.all(urlsToCache.map(u =>
        cache.add(new Request(u, { cache: 'reload' })).catch(() => {
          console.warn('[sw] 预缓存跳过（该资源不可用）：' + u);
        })
      ))
    ).catch(() => {})
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    Promise.resolve()
      .then(() => caches.keys())
      .then(keys => Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())            // 立即接管所有打开的页面
      .then(() => self.clients.matchAll({ type: 'window' }))
      .then(clients => clients.forEach(c => {
        // 2026-09-10 优化：不再强制 clients.navigate()（会造成部署后重复/循环刷新——
        // 注册 URL 带 build-version 时，缓存 HTML 的版本戳与当前 SW 不一致会被当成新注册，
        // 触发 install→activate→navigate 的死循环，每次约 10s）。
        // 改为只通知页面「有新 SW」，由页面用一次性标志决定是否刷新（SW_UPDATED 处理），
        // 平时浏览零刷新；HTML/数据内容的新鲜度由 network-first 在每次加载时保证。
        try { c.postMessage({ type: 'SW_UPDATED' }); } catch (e) {}
      }))
  );
});

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  let url;
  try { url = new URL(req.url); } catch (e) { return; }
  if (url.origin !== self.location.origin) return;   // 只处理同源请求

  // 首页判断兼容子路径：根部署是 '/'，Pages 部署是 '/mining-daily/'
  const isHtml = req.mode === 'navigate' ||
                 url.pathname === BASE ||
                 url.pathname.endsWith('.html');

  // 2026-09-11：HTML 由 stale-while-revalidate 改为 network-first。
  // 旧版 SWR 是 cache-first：缓存里只要有一份旧 index.html，在线用户也会被喂旧页
  // （且旧页引用的 app.js 版本戳与线上不一致，新旧混装 → 区块永久停在「加载中…」）。
  // 现在改为向网络再验证后再返回；仅在完全取不到网络时才用缓存（离线可看）。
  if (isHtml) {
    event.respondWith(networkFirst(req, url.pathname));
    return;
  }
  if (DATA_FILES.indexOf(url.pathname) >= 0) {
    // 数据文件与 app.js：network-first（刷新即见最新）+ 写缓存（离线兜底）。
    // 去掉 cache:'reload' 改用 no-cache 条件验证：未变更时 304 秒回、变更时才下载新内容。
    event.respondWith(networkFirst(req, url.pathname));
    return;
  }

  // 其余静态资源（图标、manifest 等）：stale-while-revalidate（先用缓存秒开，后台静默更新）
  event.respondWith(
    caches.match(req).then(cached => {
      const network = fetch(req).then(res => {
        if (res && res.ok && res.type === 'basic') {
          const copy = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, copy)).catch(() => {});
        }
        return res;
      }).catch(() => cached);
      return cached || network;
    })
  );
});
