/**
 * qa.js —— 矿业资讯速览 · AI 问答边缘代理（Netlify Edge Functions / Deno runtime）
 *
 * 为什么需要它：
 *   站点是 GitHub Pages 公开静态页，任何写进 index.html 的 Key 都等于公开（curl 即得，
 *   混淆不是加密）。本函数把 Key 存在 Netlify 环境变量里，浏览器只跟本函数通信，
 *   Key 永不出现在前端代码或页面里。同事打开页面直接用，无需自己填 Key。
 *
 * 接口：
 *   GET  /api/health   → { ok, has_key, model }
 *   GET  /api/balance  → 账号余额（告警监控用；只回数字，不回 Key）
 *   POST /api/qa       → 透传模式返回 DeepSeek 原始 JSON；简化模式返回 {answer, refs}
 *
 * 两种调用约定：
 *   ① 透传模式（前端默认）：{ messages:[{role,content}...], max_tokens, temperature }
 *      —— 前端已构造好完整对话（含 system prompt 与检索到的新闻上下文），
 *         本函数只负责加 Key 转发，并原样返回 DeepSeek 响应，前端解析逻辑无需改动。
 *   ② 简化模式：{ question, context:[{d,t,s,u}] } —— 供脚本/调试使用。
 *
 * 部署：见 ../README.md
 */

// ── 允许的跨域来源（2026-10-25 A01：精确到本站，不再放行任意子域）──
// 旧实现两条正则放行**任意** GitHub 用户 Pages 与**任意** Netlify 子域——
// 攻击者自建一个 *.github.io 页面即可持本站 AI 额度；且 isAllowedOrigin 此前
// 只用于构造 CORS 响应头，POST 本身不拒绝，而非浏览器客户端（curl/脚本）
// 根本不受 CORS 约束。CORS 不是鉴权：① 白名单精确到站点 ② 消耗额度的
// POST 加来源闸门 ③ 无 Origin 头一律拒绝（浏览器跨站/同源 POST 必带 Origin）。
const ALLOWED_ORIGINS = [
  'https://pliucugb-cyber.github.io',      // GitHub Pages 主站（本站唯一正式入口）
  'https://mining-daily-qa.netlify.app',   // Netlify 边缘函数自身（前端 QA_API_BASE 指向它）
  // 若日后绑定自定义域名，在此追加完整 origin（不要再用通配子域）
];
function isAllowedOrigin(origin) {
  if (!origin) return false;
  if (ALLOWED_ORIGINS.indexOf(origin) >= 0) return true;
  if (/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)) return true; // 本地调试
  return false;
}

// 来源闸门：不合法/缺失 Origin 的请求直接 403，不触达上游、不消耗额度。
function originGate(request) {
  const origin = request.headers.get('Origin');
  if (!isAllowedOrigin(origin)) {
    return new Response(JSON.stringify({ error: 'origin not allowed' }),
      { status: 403, headers: corsHeaders(origin) });
  }
  return null;
}

// ── 请求体资源上限与参数约束（2026-10-25 A02）──
// 旧实现对 body 零校验：体积/条数/字符/角色均无限制，max_tokens/temperature
// 客户端直传（可传负数或超大值），上游 fetch 无超时。
const MAX_BODY_BYTES = 64 * 1024;    // 请求体上限 64KB（正常提问远小于此）
const MAX_MESSAGES = 30;             // 对话条数上限
const MAX_MSG_CHARS = 4000;          // 单条消息字符上限
const MAX_TOTAL_CHARS = 24000;       // 全部消息字符总上限
const ALLOWED_ROLES = ['system', 'user', 'assistant'];
const MAX_TOKENS_CAP = 4000;         // max_tokens 服务端钳制上限
const MIN_TOKENS_CAP = 1;
const TEMP_MIN = 0, TEMP_MAX = 2;    // temperature 服务端钳制范围
const UPSTREAM_TIMEOUT_MS = 30000;   // 非流式上游超时
const UPSTREAM_STREAM_TIMEOUT_MS = 90000;  // 流式上游超时（SSE 长回答需放宽，仍防永久悬挂）

function validateBody(body, rawText) {
  /** 返回 null 表示通过，否则返回错误原因字符串（调用方转 400/413）。 */
  const bytes = new TextEncoder().encode(rawText).length;
  if (bytes > MAX_BODY_BYTES) {
    return '请求体过大（' + bytes + ' 字节 > ' + MAX_BODY_BYTES + '）';
  }
  const msgs = Array.isArray(body.messages) ? body.messages : null;
  const q = String(body.question || '').trim();
  if (!msgs && !q) return '缺少 messages 或 question 字段';
  if (msgs) {
    if (msgs.length > MAX_MESSAGES) {
      return '消息条数超限（' + msgs.length + ' > ' + MAX_MESSAGES + '）';
    }
    let total = 0;
    for (const m of msgs) {
      if (!m || typeof m.content !== 'string') return '消息格式非法（缺少字符串 content）';
      if (ALLOWED_ROLES.indexOf(m.role) < 0) {
        return '非法消息角色：' + String(m.role).slice(0, 20);
      }
      if (m.content.length > MAX_MSG_CHARS) {
        return '单条消息过长（' + m.content.length + ' > ' + MAX_MSG_CHARS + ' 字符）';
      }
      total += m.content.length;
    }
    if (total > MAX_TOTAL_CHARS) {
      return '消息总长超限（' + total + ' > ' + MAX_TOTAL_CHARS + ' 字符）';
    }
  }
  if (q && q.length > MAX_MSG_CHARS) return '问题过长';
  return null;
}

function clampParams(body) {
  /** max_tokens/temperature 钳制到服务端合法区间（不因越界报错，夹取即可）。 */
  let mt = parseInt(body.max_tokens, 10);
  if (!isFinite(mt)) mt = 1000;
  mt = Math.min(Math.max(mt, MIN_TOKENS_CAP), MAX_TOKENS_CAP);
  let tp = parseFloat(body.temperature);
  if (!isFinite(tp)) tp = 0.3;
  tp = Math.min(Math.max(tp, TEMP_MIN), TEMP_MAX);
  return { max_tokens: mt, temperature: tp };
}

function corsHeaders(origin) {
  const allow = isAllowedOrigin(origin);
  return {
    'Access-Control-Allow-Origin': allow ? origin : 'null',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  };
}

// ── 无 Key / 调用失败时的关键词兜底，保证问答永远有回应 ──
const QA_TEMPLATES = [
  [['铜', 'Cu'], '铜（Cu）是有色金属中的重要品种，广泛应用于电力、建筑、交通等领域。'],
  [['铝', 'Al'], '铝（Al）具有轻质、耐腐蚀等特性，广泛应用于航空航天、汽车制造、包装容器等领域。'],
  [['锌', 'Zn'], '锌（Zn）主要用于镀锌钢板、合金制造和电池。'],
  [['铅', 'Pb'], '铅（Pb）主要用于铅酸蓄电池、辐射防护材料。'],
  [['镍', 'Ni'], '镍（Ni）是不锈钢和动力电池的关键金属，新能源车带动需求快速增长。'],
  [['锡', 'Sn'], '锡（Sn）主要用于焊锡和电子封装，半导体景气度直接影响其需求。'],
  [['锂', 'Li'], '锂（Li）被称为"白色石油"，是新能源动力电池的核心原材料。中国是全球最大锂消费国。'],
  [['稀土'], '稀土是 17 种金属元素的统称，中国是全球最大的稀土生产国和供应国。'],
  [['金', '黄金'], '黄金兼具商品、货币、避险三重属性，央行购金、地缘冲突是金价的核心驱动。'],
  [['铁矿', '铁矿石'], '铁矿石是钢铁工业的核心原料，中国是全球最大进口国，对外依存度高。'],
  [['新一轮', '找矿', '突破', '战略'], '新一轮找矿突破战略行动已取得阶段性成果：铜、铝、锂、钴、镍等关键矿产新增资源量稳步提升。'],
  [['关键矿产', '战略性矿产'], '关键矿产对国家经济安全和国防至关重要，中国"十四五"明确将 24 种矿产列为战略性矿产。'],
  [['勘查', '勘探'], '矿产勘查分为预查、普查、详查、勘探 4 个阶段，铝土矿等矿种勘查深度按 DZ/T 0202-2020 等规范执行。'],
  [['矿权', '采矿权', '探矿权'], '矿业权包括探矿权和采矿权，出让方式分招拍挂与协议出让。'],
  [['DZ/T', '规范', '标准'], '地质矿产领域现行重要标准：DZ/T 0202-2020（铝土矿）、DZ/T 0204-2020（铜铅锌银）、DZ/T 0205-2020（稀有金属）等。'],
];

function keywordFallback(q) {
  for (const [kws, ans] of QA_TEMPLATES) {
    if (kws.some((k) => q.includes(k))) return ans;
  }
  return ('关于「' + q + '」，我暂未匹配到精确答案。' +
    '可尝试关键词：铜/铝/锌/铅/镍/锡/锂/稀土/找矿/矿权。' +
    '（当前为无密钥兜底模式，代理端配置 DEEPSEEK_API_KEY 后可获得 AI 深度解答）');
}

// DeepSeek 兼容的降级响应：即使走兜底，也返回与真实响应同构的 JSON，
// 前端按 choices[0].message.content 解析即可，无需分支处理。
function fallbackResponse(text, warning) {
  return {
    choices: [{ message: { role: 'assistant', content: text }, finish_reason: 'stop' }],
    _fallback: true,
    _warning: warning || '',
  };
}

async function callDeepSeek(apiKey, payload) {
  const body = Object.assign({
    model: 'deepseek-chat',
    max_tokens: 1000,
    temperature: 0.3,
    stream: false,
  }, payload || {});

  const resp = await fetch('https://api.deepseek.com/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + apiKey,
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),   // 2026-10-25 A02：上游超时可控退出
  });

  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const msg = (data && data.error && data.error.message) || ('HTTP ' + resp.status);
    throw new Error(msg);
  }
  return data;
}

// 流式版本：返回 DeepSeek 的 SSE 原始流（不 json 转换），由前端边收边渲染
async function callDeepSeekStream(apiKey, payload) {
  const body = Object.assign({
    model: 'deepseek-chat',
    max_tokens: 1000,
    temperature: 0.3,
    stream: true,
  }, payload || {});

  const resp = await fetch('https://api.deepseek.com/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + apiKey,
      'Accept': 'text/event-stream',
    },
    body: JSON.stringify(body),
    // 2026-10-25 A02：流式超时放宽到 90s——SSE 是长连接，超时按整个流计时，
    // 取「覆盖绝大多数完整回答、又能防永久悬挂」的折中；前端另有 35s AbortController。
    signal: AbortSignal.timeout(UPSTREAM_STREAM_TIMEOUT_MS),
  });
  return resp;
}

export default async (request, context) => {
  const url = new URL(request.url);
  const origin = request.headers.get('Origin');

  if (request.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: corsHeaders(origin) });
  }

  if (url.pathname === '/api/health') {
    const key = Deno.env.get('DEEPSEEK_API_KEY');
    return new Response(JSON.stringify({
      ok: true,
      has_key: !!key,
      model: key ? 'deepseek-chat' : 'disabled',
      time: new Date().toISOString(),
    }), { status: 200, headers: corsHeaders(origin) });
  }

  if (url.pathname === '/api/balance') {
    // 2026-10-25 余额告警：供每日定时任务查询账号余额。
    // 设计约定：① 与 /api/qa 同样过来源闸门（余额数字不公开暴露，自动化请求需带合法 Origin 头）；
    // ② 只透出告警需要的字段，Key 与多余信息不回传；③ HTTP 层一律 200，
    //    业务状态放 ok 字段——监控端区分「接口可达」与「查不到余额」两种失败。
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return new Response(JSON.stringify({ error: 'method not allowed' }),
        { status: 405, headers: corsHeaders(origin) });
    }
    const gate = originGate(request);
    if (gate) return gate;

    const balKey = Deno.env.get('DEEPSEEK_API_KEY');
    if (!balKey) {
      return new Response(JSON.stringify({ ok: false, reason: 'no_key' }),
        { status: 200, headers: corsHeaders(origin) });
    }
    try {
      const resp = await fetch('https://api.deepseek.com/user/balance', {
        headers: { 'Authorization': 'Bearer ' + balKey, 'Accept': 'application/json' },
        signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        const msg = (data && data.error && data.error.message) || ('HTTP ' + resp.status);
        return new Response(JSON.stringify({ ok: false, reason: msg }),
          { status: 200, headers: corsHeaders(origin) });
      }
      const infos = Array.isArray(data.balance_infos) ? data.balance_infos : [];
      const cny = infos.find((b) => b.currency === 'CNY') || infos[0] || {};
      return new Response(JSON.stringify({
        ok: true,
        is_available: !!data.is_available,
        currency: cny.currency || 'CNY',
        total_balance: cny.total_balance != null ? cny.total_balance : null,
        topped_up_balance: cny.topped_up_balance != null ? cny.topped_up_balance : null,
        granted_balance: cny.granted_balance != null ? cny.granted_balance : null,
        time: new Date().toISOString(),
      }), { status: 200, headers: corsHeaders(origin) });
    } catch (e) {
      return new Response(JSON.stringify({ ok: false, reason: (e && e.message) ? e.message : String(e) }),
        { status: 200, headers: corsHeaders(origin) });
    }
  }

  if (url.pathname === '/api/qa') {
    if (request.method !== 'POST') {
      return new Response(JSON.stringify({ error: 'method not allowed' }),
        { status: 405, headers: corsHeaders(origin) });
    }

    // 2026-10-25 A01：来源闸门先于一切解析（不合法来源不读 body、不触达上游）
    const gate = originGate(request);
    if (gate) return gate;

    // 2026-10-25 A02：读原始文本做字节级体积校验，再解析 JSON
    let rawText = '';
    try {
      rawText = await request.text();
    } catch (e) {
      return new Response(JSON.stringify({ error: '无法读取请求体' }),
        { status: 400, headers: corsHeaders(origin) });
    }
    let body = {};
    try {
      body = JSON.parse(rawText);
    } catch (e) {
      return new Response(JSON.stringify({ error: 'JSON 解析失败' }),
        { status: 400, headers: corsHeaders(origin) });
    }
    const vErr = validateBody(body, rawText);
    if (vErr) {
      const tooBig = vErr.indexOf('过大') >= 0;
      return new Response(JSON.stringify({ error: vErr }),
        { status: tooBig ? 413 : 400, headers: corsHeaders(origin) });
    }
    const safeParams = clampParams(body);

    // 取出「用户问题」用于兜底文案（透传模式下从最后一条 user 消息里取）
    let question = String(body.question || '').trim();
    const msgs = Array.isArray(body.messages) ? body.messages : [];
    if (!question && msgs.length) {
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i] && msgs[i].role === 'user') { question = String(msgs[i].content || ''); break; }
      }
    }
    if (!question) {
      return new Response(JSON.stringify(fallbackResponse('请输入您要查询的矿业相关问题。')),
        { status: 200, headers: corsHeaders(origin) });
    }

    const apiKey = Deno.env.get('DEEPSEEK_API_KEY');
    if (!apiKey) {
      // 未配置环境变量：降级关键词兜底，不让用户看到报错
      return new Response(JSON.stringify(
        fallbackResponse(keywordFallback(question), 'DEEPSEEK_API_KEY 未配置')),
        { status: 200, headers: corsHeaders(origin) });
    }

    try {
      let data;
      if (msgs.length) {
        // ① 透传模式：前端已构造完整对话
        if (body.stream) {
          // Phase B：流式转发 DeepSeek SSE，前端边收边渲染
          const dsResp = await callDeepSeekStream(apiKey, {
            messages: msgs,
            max_tokens: safeParams.max_tokens,
            temperature: safeParams.temperature,
          });
          if (!dsResp.ok) {
            const d = await dsResp.json().catch(() => ({}));
            const msg = (d && d.error && d.error.message) || ('HTTP ' + dsResp.status);
            return new Response(JSON.stringify(fallbackResponse(keywordFallback(question), msg)),
              { status: 200, headers: corsHeaders(origin) });
          }
          const sseHeaders = Object.assign({}, corsHeaders(origin), {
            'Content-Type': 'text/event-stream; charset=utf-8',
            'Cache-Control': 'no-store',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
          });
          return new Response(dsResp.body, { status: 200, headers: sseHeaders });
        }
        data = await callDeepSeek(apiKey, {
          messages: msgs,
          max_tokens: safeParams.max_tokens,
          temperature: safeParams.temperature,
        });
      } else {
        // ② 简化模式：question + context
        const ctx = Array.isArray(body.context) ? body.context : [];
        let user = '用户问题：' + question + '\n\n';
        if (ctx.length) {
          user += '以下为本地检索到的相关新闻条目（仅供参考，请以公开权威信息为准）：\n';
          ctx.slice(0, 12).forEach((c, i) => {
            const d = c.d || '', t = c.t || c.title || '', s = c.s || c.source || '';
            user += `${i + 1}. [${d}] ${t}${s ? '（' + s + '）' : ''}\n`;
          });
          user += '\n';
        }
        user += '请直接给出回答，无需寒暄。';
        data = await callDeepSeek(apiKey, {
          messages: [
            { role: 'system', content: '你是资深矿业行业分析师。回答简洁专业、用中文，不编造数据。' },
            { role: 'user', content: user },
          ],
          max_tokens: safeParams.max_tokens,
          temperature: safeParams.temperature,
        });
      }
      return new Response(JSON.stringify(data), { status: 200, headers: corsHeaders(origin) });
    } catch (e) {
      // 上游失败：降级兜底（同构响应），前端无需特殊处理
      return new Response(JSON.stringify(
        fallbackResponse(keywordFallback(question), (e && e.message) ? e.message : String(e))),
        { status: 200, headers: corsHeaders(origin) });
    }
  }

  return new Response(JSON.stringify({ error: 'not found' }),
    { status: 404, headers: corsHeaders(origin) });
};

export const config = { path: '/api/*' };
