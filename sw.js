// mining-daily Service Worker
// 2026-09-04 修复：改为 network-first（HTML 永远优先拿线上最新版，离线才用缓存）
// + 缓存版本号 bump + activate 时清掉所有旧缓存 + 新 SW 激活后通知页面自动刷新
// 这样任何访客无需手动 Ctrl+F5 即可看到最新内容。
// 2026-09-04 二次修复：支持子路径部署（GitHub Pages 站点位于 /mining-daily/）。
//   原先写死 '/index.html' 这类绝对路径，在子路径下会指向站点根而 404。
//   改为以 SW 自身所在目录为基准推导 BASE，根路径部署（本地/沙箱）与子路径部署（Pages）均可。
const CACHE_NAME = 'mining-daily-v6';

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
  BASE + 'price-history.js'
];
// 每日更新内容的数据文件：必须 network-first。
// 若走 stale-while-revalidate，当天首次打开会先渲染昨天缓存的新闻/行情，要刷新一次才更新
const DATA_FILES = [
  BASE + 'news-data.js',
  BASE + 'lme-data.js',
  BASE + 'price-history.js'
];

self.addEventListener('install', event => {
  // 强制新 SW 立即激活，不等旧标签页关闭
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache)).catch(() => {})
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

  // HTML 与每日数据文件：network-first —— 永远优先拿线上最新版，失败才用缓存（离线兜底）
  // 注意：index.html 成功时也不写入缓存，防止 Service Worker 把旧版 HTML 长期发给用户。
  if (isHtml || DATA_FILES.indexOf(url.pathname) >= 0) {
    event.respondWith(
      fetch(req).then(res => {
        if (isHtml) return res; // HTML 只走网络，避免旧版缓存
        if (res && res.ok && res.type === 'basic') {
          const copy = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, copy)).catch(() => {});
        }
        return res;
      }).catch(() => caches.match(req).then(r => r || caches.match(BASE + 'index.html')))
    );
    return;
  }

  // 静态资源：stale-while-revalidate（先用缓存秒开，后台静默更新）
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
