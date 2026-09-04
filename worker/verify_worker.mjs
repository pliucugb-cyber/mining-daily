// verify_worker.mjs —— 验证 worker.js 逻辑（不依赖 wrangler/Cloudflare）
// 用 node 原生 fetch/Request/Response（node 18+ 全局可用）+ 手动 mock fetch(DeepSeek)
// 验证 worker.js 逻辑（不依赖 wrangler/Cloudflare）
// 用 node 原生 fetch/Request/Response（node 18+ 全局可用）+ 手动 mock fetch(DeepSeek)
// 读取 worker 源码并作为 ES module 动态执行，拿到 default 导出
const mod = await import('./worker.js');
const worker = mod.default;

let deepseekCalls = 0;
let lastDeepseekBody = null;
// mock DeepSeek
globalThis.fetch = async (url, opts) => {
  if (String(url).includes('api.deepseek.com')) {
    deepseekCalls++;
    lastDeepseekBody = JSON.parse(opts.body);
    return new Response(JSON.stringify({
      choices: [{ message: { content: '【模拟AI】关于「' + lastDeepseekBody.messages[1].content.slice(0, 20) + '…」的回答。' } }],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }
  throw new Error('unexpected fetch: ' + url);
};

function mkReq(pathname, { method = 'GET', body = null, origin = 'https://pliucugb-cyber.github.io' } = {}) {
  const url = 'https://mining-daily-qa.example.workers.dev' + pathname;
  const headers = { Origin: origin };
  const init = { method, headers };
  if (body !== null) { init.body = JSON.stringify(body); init.headers['Content-Type'] = 'application/json'; }
  return new Request(url, init);
}

const res = {};
const GH = 'https://pliucugb-cyber.github.io';

// 1) health 无 key
{
  const r = await worker.fetch(mkReq('/api/health', { origin: GH }), {});
  const j = await r.json();
  res.healthNoKey = { status: r.status, ok: j.ok, has_key: j.has_key, model: j.model,
    cors: r.headers.get('Access-Control-Allow-Origin') };
}

// 2) health 有 key
{
  const r = await worker.fetch(mkReq('/api/health', { origin: GH }), { DEEPSEEK_API_KEY: 'sk-test' });
  const j = await r.json();
  res.healthWithKey = { status: r.status, has_key: j.has_key, model: j.model };
}

// 3) qa 无 key → 关键词兜底
{
  const r = await worker.fetch(mkReq('/api/qa', { method: 'POST', body: { question: '铜价怎么样', context: [] }, origin: GH }), {});
  const j = await r.json();
  res.qaNoKey = { status: r.status, source: j.source, hasAnswer: !!j.answer, cited: j.cited };
}

// 4) qa 有 key + context → 走 DeepSeek
{
  const ctx = [{ d: '2026-09-03', t: '广西铝土矿勘查取得突破', s: '中国地质调查局', u: 'https://example.com/1' }];
  const r = await worker.fetch(mkReq('/api/qa', { method: 'POST', body: { question: '铝土矿最近有什么进展', context: ctx }, origin: GH }), { DEEPSEEK_API_KEY: 'sk-test' });
  const j = await r.json();
  res.qaWithKey = { status: r.status, source: j.source, hasAnswer: !!j.answer,
    cited: j.cited, refsCount: (j.refs || []).length,
    deepseekSawContext: !!lastDeepseekBody.messages[1].content.includes('广西铝土矿') };
}

// 5) CORS 拦截非白名单 origin
{
  const r = await worker.fetch(mkReq('/api/health', { origin: 'https://evil.example.com' }), {});
  res.corsBlocked = { allowOrigin: r.headers.get('Access-Control-Allow-Origin') };
}

// 6) 预检 OPTIONS
{
  const r = await worker.fetch(mkReq('/api/health', { method: 'OPTIONS', origin: GH }), {});
  res.options = { status: r.status };
}

// 7) 404
{
  const r = await worker.fetch(mkReq('/api/unknown', { origin: GH }), {});
  res.notFound = { status: r.status };
}

res.deepseekCalls = deepseekCalls;
res.PASS = res.healthNoKey.has_key === false && res.healthNoKey.cors === GH &&
           res.healthWithKey.has_key === true && res.healthWithKey.model === 'deepseek-chat' &&
           res.qaNoKey.source === 'keyword-fallback' && res.qaNoKey.hasAnswer &&
           res.qaWithKey.source === 'deepseek' && res.qaWithKey.cited === 1 && res.qaWithKey.refsCount === 1 &&
           res.qaWithKey.deepseekSawContext === true && res.corsBlocked.allowOrigin === 'null' &&
           res.options.status === 204 && res.notFound.status === 404 && deepseekCalls === 1;

console.log('WORKER_TEST=' + JSON.stringify(res, null, 2));
process.exit(res.PASS ? 0 : 1);
