/**
 * qa.js —— 矿业新闻日报 · AI 问答边缘代理（Netlify Edge Functions / Deno runtime）
 *
 * 为什么需要它：
 *   站点是 GitHub Pages 公开静态页，任何写进 index.html 的 Key 都等于公开（curl 即得）。
 *   本函数把 Key 存在 Netlify 环境变量里，浏览器只跟本函数通信，Key 永不出现在前端。
 *   同事打开页面直接用，无需自己填 Key。
 *
 * 接口（与前端 QA_API_BASE 约定一致）：
 *   GET  /api/health  → { ok, has_key, model }
 *   POST /api/qa      → { answer, question, source, cited, refs }
 *   请求体：{ question: string, context: [{d,t,s,u}] }  context 为前端本地检索到的相关新闻
 *
 * 部署：见 ../README-netlify.md
 */

// ── 允许的跨域来源（防 Key 被任意第三方站点盗用额度）──
function isAllowedOrigin(origin) {
  if (!origin) return false;
  if (/^https:\/\/[\w.-]+\.github\.io$/.test(origin)) return true;        // GitHub Pages
  if (/^https:\/\/[\w.-]+\.netlify\.app$/.test(origin)) return true;      // Netlify 自身
  if (/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)) return true; // 本地调试
  // 若日后绑了自定义域名，在此追加
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

// ── 无 Key / 调用失败时的关键词兜底，保证问答功能永远可用 ──
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

async function askDeepSeek(apiKey, question, context) {
  const system = ('你是资深矿业行业分析师，服务于「矿业新闻日报」产品。' +
    '回答要简洁专业、不啰嗦、用中文。' +
    '如果提供了相关新闻条目，请自然引用并注明来源与日期；' +
    '若没有相关新闻，请明确说明这是基于通用知识的回答，并建议用户查证官方信息。' +
    '不要编造数据、价格或政策细节。');

  let user = '用户问题：' + question + '\n\n';
  if (Array.isArray(context) && context.length) {
    user += '以下为前端检索到的相关本地新闻条目（仅供参考，请以公开权威信息为准）：\n';
    context.slice(0, 12).forEach((c, i) => {
      const d = c.d || '';
      const t = c.t || c.title || '';
      const s = c.s || c.source || '';
      user += `${i + 1}. [${d}] ${t}${s ? '（' + s + '）' : ''}\n`;
    });
    user += '\n';
  } else {
    user += '（前端未提供相关新闻，请基于通用知识回答。）\n\n';
  }
  user += '请直接给出回答，无需寒暄。';

  const resp = await fetch('https://api.deepseek.com/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + apiKey,
    },
    body: JSON.stringify({
      model: 'deepseek-chat',
      messages: [
        { role: 'system', content: system },
        { role: 'user', content: user },
      ],
      max_tokens: 800,
      temperature: 0.3,
      stream: false,
    }),
  });

  if (!resp.ok) {
    const txt = await resp.text().catch(() => '');
    throw new Error('DeepSeek HTTP ' + resp.status + ' ' + txt.slice(0, 200));
  }
  const data = await resp.json();
  const content = data && data.choices && data.choices[0] && data.choices[0].message &&
    data.choices[0].message.content;
  if (!content) throw new Error('DeepSeek 返回为空');
  return content.trim();
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
    const question = String(body.question || '').trim();
    const ctx = Array.isArray(body.context) ? body.context : [];

    if (!question) {
      return new Response(JSON.stringify({ answer: '请输入您要查询的矿业相关问题。' }),
        { status: 200, headers: corsHeaders(origin) });
    }

    const apiKey = Deno.env.get('DEEPSEEK_API_KEY');
    if (!apiKey) {
      return new Response(JSON.stringify({
        answer: keywordFallback(question),
        question: question,
        source: 'keyword-fallback',
        cited: 0,
        refs: [],
      }), { status: 200, headers: corsHeaders(origin) });
    }

    try {
      const answer = await askDeepSeek(apiKey, question, ctx);
      const refs = ctx.slice(0, 8).map((c) => ({
        d: c.d || '', t: c.t || c.title || '', u: c.u || c.url || '',
      })).filter((r) => r.u);
      return new Response(JSON.stringify({
        answer: answer,
        question: question,
        source: 'deepseek',
        cited: ctx.length,
        refs: refs,
      }), { status: 200, headers: corsHeaders(origin) });
    } catch (e) {
      // 上游失败时降级到关键词兜底，不让用户看到报错
      return new Response(JSON.stringify({
        answer: keywordFallback(question),
        question: question,
        source: 'keyword-fallback',
        cited: 0,
        refs: [],
        warning: (e && e.message) ? e.message : String(e),
      }), { status: 200, headers: corsHeaders(origin) });
    }
  }

  return new Response(JSON.stringify({ error: 'not found' }),
    { status: 404, headers: corsHeaders(origin) });
};

export const config = { path: '/api/*' };
