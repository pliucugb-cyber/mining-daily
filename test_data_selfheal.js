// test_data_selfheal.js
// 2026-09-11 第三轮事故的**行为级**回归测试（不是静态断言，是真跑页面）。
//
// 复现的用户现象：
//   今日简报能出来，但今日要闻 / 热榜 / AI 检索全部空白，强制清缓存也没用。
//
// 机制：news-data.js 是一个 <script>，它提供 window.NEWS_DATA。
//   它只要没落地，读它的渲染函数就全部 `if(!window.NEWS_DATA) return` 静默返回；
//   而简报走的是 fetch('morning_report.json')，另一条路径 —— 所以「简报有、别的没有」。
//
// 本测试用一个本地 HTTP 服务**故意让 /news-data.js 第一次 404**（模拟脚本取不到），
// 然后检查页面内联自愈是否用 `news-data.js?_r=...` 重新取回并补渲染。
//
// 场景 A：news-data.js 首次 404 → 自愈后 要闻/热榜/NEWS_DATA 恢复正常
// 场景 B：app.js 404 → 至少横幅要弹出来（故障可见，不能静默）
//
// 运行：node test_data_selfheal.js
const fs = require('fs');
const path = require('path');
const http = require('http');
const { JSDOM } = require('jsdom');

const ROOT = __dirname;
const PORT = 8811;

let pass = 0, fail = 0;
function check(name, cond, why) {
  if (cond) { pass++; console.log('  PASS  ' + name + (why ? '  → ' + why : '')); }
  else { fail++; console.log('  FAIL  ' + name + (why ? '  → ' + why : '')); }
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.css': 'text/css; charset=utf-8'
};

function makeServer(opts) {
  return http.createServer((req, res) => {
    const u = new URL(req.url, 'http://127.0.0.1:' + PORT);
    const name = decodeURIComponent(u.pathname).replace(/^\/+/, '') || 'index.html';
    // 首次请求（无自愈用的一次性参数）直接 404，模拟「脚本取不到」
    if (name === 'news-data.js' && !u.searchParams.has('_r')) {
      res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end('<!DOCTYPE html><p>404</p>');
      return;
    }
    if (name === 'app.js' && opts.breakAppJs) {
      res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end('<!DOCTYPE html><p>404</p>');
      return;
    }
    const p = path.join(ROOT, name);
    if (!fs.existsSync(p) || !fs.statSync(p).isFile()) {
      res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end('<!DOCTYPE html><p>404</p>');
      return;
    }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(name)] || 'application/octet-stream' });
    fs.createReadStream(p).pipe(res);
  });
}

// jsdom 不实现 fetch；这里接到 node 原生 fetch，保证相对 URL 与查询串都真实走 HTTP。
function installFetch(win) {
  win.fetch = (u, o) => globalThis.fetch(new URL(String(u), win.location.href).toString(), o || {});
  if (typeof win.matchMedia !== 'function') {
    win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
  }
  win.HTMLElement.prototype.scrollTo = function () {};
  win.scrollTo = function () {};
}

function loadPage(opts) {
  return new Promise((resolve, reject) => {
    const server = makeServer(opts);
    server.listen(PORT, '127.0.0.1', () => {
      JSDOM.fromURL('http://127.0.0.1:' + PORT + '/index.html', {
        runScripts: 'dangerously',
        resources: 'usable',
        pretendToBeVisual: true,
        beforeParse: installFetch
      }).then(dom => resolve({ dom, server })).catch(err => {
        server.close();
        reject(err);
      });
    });
  });
}

function regionText(doc, sel) {
  const el = doc.querySelector(sel);
  return el ? (el.textContent || '') : '';
}

(async function main() {
  console.log('===== 场景 A：news-data.js 首次 404（用户遇到的形态）=====');
  {
    const { dom, server } = await loadPage({ breakAppJs: false });
    const { window } = dom;
    // 等首屏 + 自愈轮次（1200 / 3000ms）跑完
    await new Promise(r => setTimeout(r, 8000));
    const doc = window.document;

    const news = window.NEWS_DATA;
    check('自愈把 news-data.js 取回来了（NEWS_DATA 有数据）',
      !!(news && news.news && news.news.length > 0),
      'NEWS_DATA=' + (news && news.news ? news.news.length + ' 条' : String(news)));

    const hot = regionText(doc, '#hotListBody');
    check('热榜已渲染（不再是「加载中…」）',
      hot.trim().length > 0 && hot.indexOf('加载中') < 0 && hot.indexOf('加载失败') < 0,
      '热榜文本=' + hot.replace(/\s+/g, ' ').trim().slice(0, 60));

    const digest = regionText(doc, '#digestStrip');
    check('今日要闻已渲染（不再是「要闻提取中…」）',
      digest.trim().length > 0 && digest.indexOf('提取中') < 0 && digest.indexOf('获取中') < 0,
      '要闻文本=' + digest.replace(/\s+/g, ' ').trim().slice(0, 60));

    const brief = regionText(doc, '#briefMain');
    check('简报照常渲染（对照组：与 NEWS_DATA 无关）',
      brief.trim().length > 0 && brief.indexOf('加载中') < 0,
      '简报文本=' + brief.replace(/\s+/g, ' ').trim().slice(0, 40));

    check('自愈后看门狗不再误报（横幅不显示）',
      (() => { const b = doc.getElementById('mdBootWarn'); return !b || b.style.display === 'none'; })(),
      '全部区块就绪时不应再挂红条');

    dom.window.close();
    server.close();
  }

  console.log('\n===== 场景 B：app.js 完全取不到 =====');
  {
    const { dom, server } = await loadPage({ breakAppJs: true });
    const { window } = dom;
    await new Promise(r => setTimeout(r, 13000));
    const doc = window.document;
    const banner = doc.getElementById('mdBootWarn');
    check('app.js 取不到时横幅弹出（故障可见）',
      !!banner && banner.style.display !== 'none',
      '旧版是页面静默卡在「加载中…」，用户完全看不出是失败');
    check('横幅带诊断状态行',
      !!banner && !!doc.querySelector('.md-boot-diag') && (doc.querySelector('.md-boot-diag').textContent || '').indexOf('app.js=') >= 0,
      '诊断行=' + (doc.querySelector('.md-boot-diag') ? doc.querySelector('.md-boot-diag').textContent.slice(0, 80) : '(缺)'));
    check('诊断行明确写出 app.js 未执行',
      !!doc.querySelector('.md-boot-diag') && doc.querySelector('.md-boot-diag').textContent.indexOf('app.js=未执行') >= 0,
      '一眼看出是脚本没跑，而不是「网络慢」');
    check('提供了复制诊断信息入口',
      !!banner && (banner.textContent || '').indexOf('复制诊断信息') >= 0);
    dom.window.close();
    server.close();
  }

  console.log('\n===== 结果：' + pass + ' PASS / ' + fail + ' FAIL =====');
  process.exit(fail ? 1 : 0);
})().catch(e => {
  console.error('测试异常：', e && (e.stack || e.message || e));
  process.exit(1);
});
