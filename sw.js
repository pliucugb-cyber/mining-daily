// mining-daily Service Worker
// 2026-09-04 修复：改为 network-first（HTML 永远优先拿线上最新版，离线才用缓存）
// + 缓存版本号 bump + activate 时清掉所有旧缓存 + 新 SW 激活后通知页面自动刷新
// 这样任何访客无需手动 Ctrl+F5 即可看到最新内容。
const CACHE_NAME = 'mining-daily-v3';
const urlsToCache = ['/', '/index.html', '/news-data.js', '/lme-data.js'];

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

  const isHtml = req.mode === 'navigate' ||
                 url.pathname === '/' ||
                 url.pathname.endsWith('.html');

  if (isHtml) {
    // HTML：network-first —— 永远优先拿线上最新版，失败才用缓存（离线兜底）
    event.respondWith(
      fetch(req).then(res => {
        if (res && res.ok && res.type === 'basic') {
          const copy = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, copy)).catch(() => {});
        }
        return res;
      }).catch(() => caches.match(req).then(r => r || caches.match('/index.html')))
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
