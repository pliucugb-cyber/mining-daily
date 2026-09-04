const fs = require('fs'), http = require('http'), https = require('https'), crypto = require('crypto');
const { JSDOM, VirtualConsole } = require('C:/Users/windows/.workbuddy/binaries/node/workspace/node_modules/jsdom');
const BASE = process.env.SMOKE_BASE || 'http://127.0.0.1:3005/';
const html = fs.readFileSync('index.html', 'utf8');
const vc = new VirtualConsole();
const errs = [];
vc.on('jsdomError', e => errs.push(e.message));
// 9/4 教训：index.html 突然变小（<50KB）通常是被自动化脚本误覆盖，第一时间报警
const _size = Buffer.byteLength(html);
const _sha = crypto.createHash('sha256').update(html).digest('hex').slice(0, 12);
console.error('[smoke] index.html size=', _size, 'bytes  sha256[:12]=', _sha, _size < 50000 ? '  ⚠️ 异常小，请确认是否被覆盖' : '');
const dom = new JSDOM(html, {
  url: BASE, runScripts: 'dangerously', resources: 'usable', virtualConsole: vc, pretendToBeVisual: true,
  beforeParse(w) {
    w.matchMedia = w.matchMedia || function () { return { matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }; };
    w.scrollTo = function () {};
    w.Element.prototype.scrollIntoView = w.Element.prototype.scrollIntoView || function () {};
    w.URL.createObjectURL = w.URL.createObjectURL || function () { return 'blob:mock'; };
    w.URL.revokeObjectURL = w.URL.revokeObjectURL || function () {};
    w.fetch = function (u, o) {
      return new Promise((res, rej) => {
        try {
          const U = new URL(u, w.location.href);
          const proto = U.protocol === 'https:' ? https : http;
          const r = proto.request(U.href, { method: (o && o.method) || 'GET', headers: (o && o.headers) || {} }, x => {
            const c = []; x.on('data', d => c.push(d)); x.on('end', () => {
              const b = Buffer.concat(c).toString();
              res({ ok: x.statusCode < 300, status: x.statusCode, json: () => Promise.resolve(JSON.parse(b)), text: () => Promise.resolve(b) });
            });
          });
          r.on('error', rej);
          if (o && o.body) r.write(o.body);
          r.end();
        } catch (e) { rej(e); }
      });
    };
  }
});
function q(sel) { return dom.window.document.querySelector(sel); }
function qa(sel) { return dom.window.document.querySelectorAll(sel); }
function txt(id) { const e = dom.window.document.getElementById(id); return e ? (e.textContent || '').trim() : null; }
const results = [];
function ok(name, cond, extra) { results.push({ name, pass: !!cond, extra: extra || '' }); }

function waitUntil(pred, timeout, step) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    (function loop() {
      let v = false; try { v = pred(); } catch (e) {}
      if (v) return resolve(true);
      if (Date.now() - t0 > timeout) return resolve(false);
      setTimeout(loop, step);
    })();
  });
}

// 等热榜经真实 API 异步渲染出列表（端到端）
waitUntil(() => { const items = dom.window.document.querySelectorAll('#hotListBody li.hot-item'); return items.length > 0; }, 25000, 300)
.then(() => {
  const w = dom.window, d = w.document;
  // ---------- 结构（DOM 已正确解析，此前 <style> 未闭合导致 body 空） ----------
  ok('DOM:<body>有子节点', d.body && d.body.children.length > 3, 'children=' + (d.body ? d.body.children.length : '-'));
  ok('价格条:priceStrip', !!q('#priceStrip'), 'p=' + !!q('#priceStrip'));
  ok('价格条:priceStripNote含沪期主力/SMM', /沪期主力|SMM/.test(txt('priceStripNote') || ''), (txt('priceStripNote') || '').slice(0, 30));
  ok('SHFE价格卡容器', !!q('#priceCardsShfe'), 'p=' + !!q('#priceCardsShfe'));
  ok('LME价格卡容器', !!q('#priceCardsLme'), 'p=' + !!q('#priceCardsLme'));
  const shfeCards = qa('#priceCardsShfe .price-card[data-slug]');
  ok('SHFE 6金属卡(data-slug)', shfeCards.length === 6, 'cnt=' + shfeCards.length);
  const lmeCards = qa('#priceCardsLme .price-card');
  ok('LME 6卡', lmeCards.length === 6, 'cnt=' + lmeCards.length);
  const lmeUnit0 = lmeCards.length ? (lmeCards[0].querySelector('.pc-unit') ? lmeCards[0].querySelector('.pc-unit').textContent.trim() : '') : '';
  ok('LME单位 USD/吨', /USD\/吨|美元\/吨/.test(lmeUnit0), 'unit=' + lmeUnit0);
  ok('问答输入:qaInput', !!q('#qaInput'), 'p=' + !!q('#qaInput'));
  // ---------- 矿业热榜 section ----------
  ok('热榜区块:hotListSection', !!q('#hotListSection'), 'p=' + !!q('#hotListSection'));
  ok('热榜容器:hotListBody', !!q('#hotListBody'), 'p=' + !!q('#hotListBody'));
  ok('热榜TOC入口', !!q('#tocSidebar .toc-main-item[data-target="hotListSection"]'), 'p=' + !!q('#tocSidebar .toc-main-item[data-target="hotListSection"]'));
  ok('热榜函数:fetchHotNews', typeof w.fetchHotNews === 'function', 'f=' + (typeof w.fetchHotNews));
  ok('热榜渲染函数:renderHotNews', typeof w.renderHotNews === 'function', 'f=' + (typeof w.renderHotNews));
  const styleTxt = Array.from(qa('style')).map(s => s.textContent || '').join('');
  ok('热榜CSS写入(list-style:none)', /\.hotlist-list\{[^}]*list-style:none/.test(styleTxt), 'css=' + /\.hotlist-list\{/.test(styleTxt));
  ok('热榜CSS写入(hot-rank渐变)', /\.hot-rank\{[^}]*border-radius/.test(styleTxt), 'css=' + /\.hot-rank\{/.test(styleTxt));
  // ---------- 实时渲染（端到端，来自 /api/hot-news） ----------
  const liveItems = qa('#hotListBody li.hot-item');
  ok('热榜实时渲染≥1项', liveItems.length >= 1, 'cnt=' + liveItems.length);
  ok('热榜实时渲染=3项', liveItems.length === 3, 'cnt=' + liveItems.length);
  const ranks = Array.from(liveItems).map(li => { const r = li.querySelector('.hot-rank'); return r ? r.textContent.trim() : ''; });
  ok('热榜编号01..03', ranks.join(',') === ['01','02','03'].join(','), ranks.join(','));
  const top1 = liveItems[0];
  ok('热榜Top1含🔥热标', !!(top1 && top1.querySelector('.hot-fire')), 'top1fire=' + !!(top1 && top1.querySelector('.hot-fire')));
  const links = qa('#hotListBody li.hot-item > div > a.hot-title[href^="http"][target="_blank"]');
  ok('热榜链接可点(http+新窗口)', links.length >= 3, 'cnt=' + links.length);

  // ---------- AI 深度解析（9-04 新增）----------
  const aiSec = q('#aiSection');
  ok('AI解析区块存在', !!aiSec, 'box=' + !!aiSec);
  const aiBody = q('#aiBody');
  ok('AI解析容器', !!aiBody, 'p=' + !!aiBody);
  const aiToc = q('#tocAiCount');
  ok('AI解析TOC入口', !!aiToc, 'p=' + !!aiToc);
  ok('AI解析函数:fetchAiAnalyze', typeof w.fetchAiAnalyze === 'function', 'f=' + typeof w.fetchAiAnalyze);
  ok('AI解析函数:renderAiAnalyze', typeof w.renderAiAnalyze === 'function', 'f=' + typeof w.renderAiAnalyze);
  const aiStyle = Array.from(d.querySelectorAll('style')).map(s => s.textContent || '').join('');
  ok('AI解析CSS写入(.ai-item)', /\.ai-item\{/.test(aiStyle), 'css=' + /\.ai-item\{/.test(aiStyle));
  ok('AI解析CSS写入(.ai-label)', /\.ai-label\{/.test(aiStyle), 'css=' + /\.ai-label\{/.test(aiStyle));
  // 单元：renderAiAnalyze 三种状态（未配置 / 加载失败 / 已加载）
  try {
    w.renderAiAnalyze({ enabled: false, reason: 'no key' });
    ok('AI解析单元:未配置提示', /AI\s*解析未配置|DEEPSEEK_API_KEY/.test((q('#aiBody') || {}).textContent || ''), 't=' + ((q('#aiBody') || {}).textContent || '').slice(0, 30));
    w.renderAiAnalyze({ enabled: true, items: [
      { url: 'https://example.com/x', title: '<b>XSS</b>突破', src: '自然资源部', summary: '一句话', insight: '<a>启示</a>', risk: '无' }
    ], quota_left: 25, quota_limit: 30 });
    const aiItems = qa('#aiBody .ai-item');
    ok('AI解析单元:1项', aiItems.length === 1, 'cnt=' + aiItems.length);
    const aiItem = aiItems[0];
    ok('AI解析单元:含要点/启示/风险', !!(aiItem && aiItem.querySelectorAll('.ai-row').length === 3), 'rows=' + (aiItem ? aiItem.querySelectorAll('.ai-row').length : 0));
    const aiTitle = aiItem && aiItem.querySelector('.ai-item-title');
    ok('AI解析单元:转义XSS(无元素注入)', !!(aiTitle && aiTitle.querySelector('*') === null && /<b>/.test(aiTitle.textContent)), 't=' + (aiTitle ? aiTitle.textContent.slice(0, 12) : 'null'));
  } catch (e) {
    ok('AI解析单元:执行', false, 'err=' + e.message);
  }
  // AI 解析 API 端点（无论 key 与否都能响应）；用 w.fetch shim（会按 BASE 解析相对 URL）
  const aiApiPromise = w.fetch('api/ai-analyze?v=' + Date.now(), { cache: 'no-store' })
    .then(r => r.ok ? r.json() : null)
    .then(j => {
      j = j || {};
      ok('AI解析API:连通性', true, 'via=w.fetch-shim');
      ok('AI解析API:date字段', !!j.date, 'd=' + j.date);
      ok('AI解析API:enabled字段', typeof j.enabled === 'boolean', 'e=' + j.enabled);
      ok('AI解析API:items数组', Array.isArray(j.items), 'cnt=' + (j.items || []).length);
      ok('AI解析API:quota字段', typeof j.quota_limit === 'number', 'ql=' + j.quota_limit);
      if (j.enabled === false) {
        ok('AI解析API:未配置reason', !!j.reason && /DEEPSEEK_API_KEY/.test(j.reason), 'r=' + (j.reason || '').slice(0, 20));
      } else if (j.items && j.items.length) {
        const it0 = j.items[0];
        ok('AI解析API:items[0]字段完整', !!(it0 && it0.title && it0.url && it0.summary && it0.insight && it0.risk), 'has=' + Object.keys(it0 || {}).join(','));
      }
    })
    .catch(e => ok('AI解析API:连通性', false, 'err=' + e.message));
  // ---------- 单元：renderHotNews 转义/编号/高亮 ----------
  try {
    w.renderHotNews({ hot: [
      { rank: 1, t: '<b>测试&XSS</b>突破', s: '自然资源部', d: '2026-09-03', u: 'https://example.com/a', hot: true },
      { rank: 2, t: '普通新闻', s: '中国地质调查局', d: '2026-09-02', u: 'https://example.com/b', hot: false }
    ] });
    const items2 = qa('#hotListBody li.hot-item');
    ok('renderHotNews单元:2项', items2.length === 2, 'cnt=' + items2.length);
    const a0 = items2[0].querySelector('a.hot-title');
    ok('renderHotNews单元:转义XSS(无元素注入)', !!(a0 && a0.querySelector('*') === null && a0.textContent.indexOf('<b>') > -1 && a0.getAttribute('href') === 'https://example.com/a'), 'txt=' + (a0 ? a0.textContent.slice(0, 12) : 'null'));
    ok('renderHotNews单元:rank=01', items2[0].querySelector('.hot-rank').textContent.trim() === '01', 'r=' + (items2[0].querySelector('.hot-rank') ? items2[0].querySelector('.hot-rank').textContent.trim() : 'null'));
    ok('renderHotNews单元:top1高亮类', items2[0].className.indexOf('top1') > -1, 'cls=' + items2[0].className);
    ok('renderHotNews单元:🔥热标', !!items2[0].querySelector('.hot-fire'), 'fire=' + !!items2[0].querySelector('.hot-fire'));
  } catch (e) { ok('renderHotNews单元', false, e.message); }
  // ---------- 后端确定性校验 /api/hot-news ----------
  return new Promise((resolve) => {
    const U = new URL('api/hot-news?v=' + Date.now(), BASE);
    const proto = U.protocol === 'https:' ? https : http;
    const r = proto.request(U.href, { method: 'GET' }, x => {
      const c = []; x.on('data', d2 => c.push(d2)); x.on('end', () => {
        try {
          const j = JSON.parse(Buffer.concat(c).toString());
          const arr = Array.isArray(j.hot) ? j.hot : [];
          ok('API:返回3项', arr.length === 3, 'cnt=' + arr.length);
          ok('API:rank 1-3', arr.length >= 2 && arr[0].rank === 1 && arr[arr.length-1].rank === arr.length, 'ranks=' + (arr.length >= 2 ? arr[0].rank + '..' + arr[arr.length-1].rank : 'n/a'));
          ok('API:rank1为🔥热', arr.length >= 1 && arr[0].hot === true && /突破|重大|战略|首次|新一轮|关键|世界第一/.test(arr[0].t || ''), 't=' + (arr[0] ? (arr[0].t || '').slice(0, 24) : 'null'));
          ok('API:链接http', arr.length >= 1 && /^https?:\/\//.test(arr[0].u || ''), 'u=' + (arr[0] ? (arr[0].u || '').slice(0, 24) : 'null'));
          ok('API:自然资源部常驻Top3', arr.slice(0, 3).some(x => x.s === '自然资源部'), 'top3=' + arr.slice(0, 3).map(x => (x.s || '').slice(0, 6)).join('|'));
        } catch (e) { ok('API解析', false, e.message); }
        // 等 AI 解析 API 断言也完成，避免 process.exit 提前截断
        Promise.resolve(aiApiPromise).then(() => resolve());
      });
    });
    r.on('error', e => { ok('API请求', false, e.message); resolve(); });
    r.end();
  });
}).then(() => {
  ok('零 jsdomError', errs.length === 0, errs.slice(0, 3).join(' | '));
  const fails = results.filter(r => !r.pass);
  console.log('==== 矿业日报 冒烟 SUMMARY ====');
  results.forEach(r => console.log((r.pass ? 'PASS' : 'FAIL') + '  ' + r.name + (r.extra ? '  [' + r.extra + ']' : '')));
  console.log('TOTAL=' + results.length + ' PASS=' + (results.length - fails.length) + ' FAIL=' + fails.length);
  dom.window.close();
  process.exit(fails.length ? 1 : 0);
}).catch(e => { console.error('FATAL', e); process.exit(2); });
