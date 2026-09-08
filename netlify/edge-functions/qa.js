/**
 * qa.js —— 矿业新闻日报 · AI 问答边缘代理（Netlify Edge Functions / Deno runtime）
 *
 * 为什么需要它：
 *   站点是 GitHub Pages 公开静态页，任何写进 index.html 的 Key 都等于公开（curl 即得，
 *   混淆不是加密）。本函数把 Key 存在 Netlify 环境变量里，浏览器只跟本函数通信，
 *   Key 永不出现在前端代码或页面里。同事打开页面直接用，无需自己填 Key。
 *
 * 接口：
 *   GET  /api/health  → { ok, has_key, model }
 *   POST /api/qa      → 透传模式返回 DeepSeek 原始 JSON；简化模式返回 {answer, refs}
 *
 * 两种调用约定：
 *   ① 透传模式（前端默认）：{ messages:[{role,content}...], max_tokens, temperature }
 *      —— 前端已构造好完整对话（含 system prompt 与检索到的新闻上下文），
 *         本函数只负责加 Key 转发，并原样返回 DeepSeek 响应，前端解析逻辑无需改动。
 *   ② 简化模式：{ question, context:[{d,t,s,u}] } —— 供脚本/调试使用。
 *
 * 部署：见 ../README.md
 */

// ── 允许的跨域来源（防 Key 被任意第三方站点盗用额度）──
function isAllowedOrigin(origin) {
  if (!origin) return false;
  if (/^https:\/\/[\w.-]+\.github\.io$/.test(origin)) return true;        // GitHub Pages
  if (/^https:\/\/[\w.-]+\.netlify\.app$/.test(origin)) return true;      // Netlify 自身
  if (/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)) return true; // 本地调试
  // 若日后绑定自定义域名，在此追加
  return false;
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
  });

  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const msg = (data && data.error && data.error.message) || ('HTTP ' + resp.status);
    throw new Error(msg);
  }
  return data;
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

  if (url.pathname === '/api/qa') {
    if (request.method !== 'POST') {
      return new Response(JSON.stringify({ error: 'method not allowed' }),
        { status: 405, headers: corsHeaders(origin) });
    }

    let body = {};
    try {
      body = await request.json();
    } catch (e) {
      body = {};
    }

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
        data = await callDeepSeek(apiKey, {
          messages: msgs,
          max_tokens: body.max_tokens || 1000,
          temperature: body.temperature == null ? 0.3 : body.temperature,
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
          max_tokens: body.max_tokens || 800,
          temperature: body.temperature == null ? 0.3 : body.temperature,
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
