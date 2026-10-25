/**
 * 2026-10-25 A01/A02：Netlify AI 代理加固测试（vm 沙箱 + mock 上游，零真实额度）
 * 守护：
 *   ① origin 白名单精确到本站；异常来源/缺失 Origin 的 POST → 403 且不触达上游
 *   ② 请求体字节/条数/字符/角色校验 → 413/400 且不触达上游
 *   ③ max_tokens/temperature 服务端 clamp（客户端传超大值被夹住）
 *   ④ 上游 fetch 带 AbortSignal.timeout
 *   ⑤ 上游失败 → 200 + _fallback:true（B06 前端识别的依据）
 *   ⑥ 合法 origin + 正常请求 → 200 + 上游收到 clamp 后的参数
 * 运行：node test_qa_proxy.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name + (detail ? '  → ' + detail : '')); }
  else { fail++; console.log('  FAIL  ' + name + (detail ? '  → ' + detail : '')); }
}

// ── 加载 qa.js：ESM export 语法在 vm 里不可用，替换为全局赋值 ──
const qaSrc = fs.readFileSync(path.join(__dirname, 'netlify/edge-functions/qa.js'), 'utf8')
  .replace(/export default async \(request, context\) =>/, 'globalThis.__handler = async (request, context) =>')
  .replace(/export const config = .*?;\s*$/, '');

const upstreamCalls = [];
let upstreamMode = 'ok';   // ok | fail | http500

function makeSandbox() {
  const sandbox = {
    console: { log() {}, warn() {}, error() {} },
    Deno: { env: { get: (k) => (k === 'DEEPSEEK_API_KEY' ? 'test-key-not-real' : '') } },
    TextEncoder, URL, Request, Response, Headers,
    AbortController, AbortSignal, ReadableStream,
    setTimeout, clearTimeout,
    fetch: (url, opts) => {
      upstreamCalls.push({ url: String(url), body: opts && opts.body ? JSON.parse(opts.body) : null,
                           signal: !!(opts && opts.signal) });
      if (upstreamMode === 'fail') {
        return Promise.reject(Object.assign(new Error('The operation was aborted due to timeout'),
          { name: 'TimeoutError' }));
      }
      if (upstreamMode === 'http500') {
        return Promise.resolve({ ok: false, status: 500,
          json: () => Promise.resolve({ error: { message: 'upstream 500' } }) });
      }
      return Promise.resolve({
        ok: true, status: 200,
        json: () => Promise.resolve({ choices: [{ message: { role: 'assistant', content: 'AI 回答：铜广泛应用于电力行业。' }, finish_reason: 'stop' }] }),
        body: new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode('data: {"x":1}\n\n')); c.close(); } }),
      });
    },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(qaSrc, sandbox);
  return sandbox;
}

const mkReq = (origin, payload, opts) => new Request('https://mining-daily-qa.netlify.app/api/qa', {
  method: 'POST',
  headers: origin === null ? { 'Content-Type': 'application/json' }
                        : { 'Content-Type': 'application/json', Origin: origin },
  body: typeof payload === 'string' ? payload : JSON.stringify(payload),
  ...(opts || {}),
});
const OK_MSGS = [{ role: 'system', content: '你是矿业分析师' }, { role: 'user', content: '铜的用途？' }];

(async () => {
  const sandbox = makeSandbox();
  const call = (req) => sandbox.__handler(req, {});

  console.log('===== A01：来源闸门（异常来源不触达上游）=====');
  upstreamCalls.length = 0; upstreamMode = 'ok';
  let r = await call(mkReq('https://evil-user.github.io', { messages: OK_MSGS }));
  check('攻击者自建 *.github.io → 403', r.status === 403, 'status=' + r.status);
  check('被拒请求未触达上游', upstreamCalls.length === 0, 'upstream=' + upstreamCalls.length);

  r = await call(mkReq(null, { messages: OK_MSGS }));
  check('无 Origin（curl/服务端直连）→ 403', r.status === 403, 'status=' + r.status);
  check('无 Origin 请求未触达上游', upstreamCalls.length === 0);

  r = await call(mkReq('https://attacker.netlify.app', { messages: OK_MSGS }));
  check('他人 Netlify 子域 → 403', r.status === 403, 'status=' + r.status);

  console.log('===== A01：合法来源放行 =====');
  r = await call(mkReq('https://pliucugb-cyber.github.io', { messages: OK_MSGS }));
  check('本站 Pages origin → 200', r.status === 200, 'status=' + r.status);
  let d = await r.json();
  check('返回上游 AI 内容', !!(d.choices && d.choices[0].message.content.indexOf('铜') >= 0));
  check('合法请求触达上游 1 次', upstreamCalls.length === 1, 'upstream=' + upstreamCalls.length);

  r = await call(mkReq('http://localhost:8080', { messages: OK_MSGS }));
  check('本地调试 origin → 200', r.status === 200, 'status=' + r.status);

  console.log('===== A02：请求体校验（超限不触达上游）=====');
  upstreamCalls.length = 0;
  // 单条 5000 字符（>4000 上限）但总体 <64KB → 应命中单条长度校验（400），
  // 若误撞字节上限会返回 413，说明校验顺序/语义不对
  r = await call(mkReq('https://pliucugb-cyber.github.io', { messages: OK_MSGS.map(m => ({ ...m, content: 'x'.repeat(5000) })) }));
  check('单条消息 5000 字符（总体<64KB）→ 400', r.status === 400, 'status=' + r.status);
  check('超限未触达上游', upstreamCalls.length === 0);

  r = await call(mkReq('https://pliucugb-cyber.github.io', { messages: Array.from({ length: 50 }, () => ({ role: 'user', content: 'hi' })) }));
  check('50 条消息 → 400', r.status === 400, 'status=' + r.status);

  r = await call(mkReq('https://pliucugb-cyber.github.io', { messages: [{ role: 'admin', content: 'hack' }] }));
  check('非法角色 admin → 400', r.status === 400, 'status=' + r.status);

  const bigBody = JSON.stringify({ messages: OK_MSGS, pad: 'y'.repeat(70000) });
  r = await call(mkReq('https://pliucugb-cyber.github.io', bigBody));
  check('>64KB 请求体 → 413', r.status === 413, 'status=' + r.status);

  r = await call(mkReq('https://pliucugb-cyber.github.io', 'not-json{{'));
  check('非法 JSON → 400', r.status === 400, 'status=' + r.status);
  check('以上全部未触达上游', upstreamCalls.length === 0, 'upstream=' + upstreamCalls.length);

  console.log('===== A02：参数 clamp =====');
  upstreamCalls.length = 0;
  r = await call(mkReq('https://pliucugb-cyber.github.io', { messages: OK_MSGS, max_tokens: 999999, temperature: 99 }));
  check('超大 max_tokens/temperature → 仍 200（夹取不报错）', r.status === 200, 'status=' + r.status);
  const sent = upstreamCalls[0] && upstreamCalls[0].body;
  check('上游收到 clamp 后 max_tokens=4000', !!(sent && sent.max_tokens === 4000), 'got=' + (sent && sent.max_tokens));
  check('上游收到 clamp 后 temperature=2', !!(sent && Math.abs(sent.temperature - 2) < 1e-9), 'got=' + (sent && sent.temperature));
  check('上游 fetch 带中止信号（超时保护）', !!(upstreamCalls[0] && upstreamCalls[0].signal));

  console.log('===== A02/B06：上游失败 → 同构兜底 + _fallback 标记 =====');
  upstreamCalls.length = 0; upstreamMode = 'fail';
  r = await call(mkReq('https://pliucugb-cyber.github.io', { messages: OK_MSGS }));
  d = await r.json();
  check('上游超时 → HTTP 200（不把错误抛给用户）', r.status === 200, 'status=' + r.status);
  check('兜底响应带 _fallback:true（前端识别依据）', d._fallback === true);
  check('兜底响应带 _warning（原因）', typeof d._warning === 'string' && d._warning.length > 0);
  upstreamMode = 'http500';
  r = await call(mkReq('https://pliucugb-cyber.github.io', { messages: OK_MSGS }));
  d = await r.json();
  check('上游 500 → 200 + _fallback', r.status === 200 && d._fallback === true);

  console.log('===== 简化模式与健康检查不受影响 =====');
  upstreamCalls.length = 0; upstreamMode = 'ok';
  r = await call(new Request('https://mining-daily-qa.netlify.app/api/qa', {
    method: 'POST', headers: { 'Content-Type': 'application/json', Origin: 'https://pliucugb-cyber.github.io' },
    body: JSON.stringify({ question: '铜的用途', context: [{ d: '2026-10-25', t: '某铜矿投产', s: '中国有色网', u: 'http://x/1' }] }),
  }));
  check('简化模式（question+context）→ 200', r.status === 200, 'status=' + r.status);
  r = await call(new Request('https://mining-daily-qa.netlify.app/api/health', { headers: { Origin: 'https://pliucugb-cyber.github.io' } }));
  d = await r.json();
  check('/api/health → has_key=true（不消耗额度的探测放行）', r.status === 200 && d.has_key === true);

  console.log('\nQA-PROXY ' + pass + ' PASS / ' + fail + ' FAIL');
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error('FATAL', e); process.exit(2); });
