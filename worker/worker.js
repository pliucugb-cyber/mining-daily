/**
 * worker.js —— 矿业新闻日报 · 轻后端（仅 /api/qa + /api/health）
 *
 * 设计目标（与用户约定）：
 *  - 无状态：不读任何数据文件，前端把"问题 + 本地已检索到的相关新闻"一起 POST 过来，
 *    本函数只负责调 DeepSeek 生成答案（key 存在 wrangler secret，不落代码）。
 *  - 最省心：Cloudflare Workers，免费额度大、全球边缘、原生 CORS。
 *  - 换电脑可恢复：本文件 + wrangler.toml 都进 git；key 是平台 secret；
 *    换机只需 `wrangler login` → `wrangler deploy` 即可。
 *
 * 部署：
 *   cd worker
 *   npm i -g wrangler      # 或 npx wrangler
 *   wrangler login          # 绑定你的 Cloudflare 账号（换电脑重做这步即可）
 *   wrangler secret put DEEPSEEK_API_KEY   # 把 key 存为 secret，绝不写进代码
 *   wrangler deploy
 *   把输出的 worker URL（https://<name>.<subdomain>.workers.dev）填回
 *   index.html 的 QA_API_BASE 常量。
 */

// ── 允许的跨域来源（防 key 被任意第三方站点滥用）──
//    GitHub Pages 站点 + 本地调试（无 TLS 的 localhost/127.0.0.1 任意端口）。
function isAllowedOrigin(origin) {
  if (!origin) return false;
  if (/^https:\/\/[\w.-]+\.github\.io$/.test(origin)) return true;        // 任意 github.io 子域
  if (/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)) return true; // 本地调试
  return false;
}

// ── CORS 头（仅对白名单来源放行，预检也受控）──
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

// ── 无 key 时的本地关键词兜底（搬运自原 server.py QA_TEMPLATES）──
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
    '（当前为无密钥兜底模式，配置 DEEPSEEK_API_KEY 后可获得 AI 深度解答）');
}

// ── 调用 DeepSeek 生成答案 ──
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

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get('Origin');

    // 预检
    if (request.method === 'OPTIONS') {
      const h = corsHeaders(origin);
      return new Response(null, { status: 204, headers: h });
    }

    // /api/health —— 健康检查 + AI 配置状态
    if (url.pathname === '/api/health') {
      const hasKey = !!env.DEEPSEEK_API_KEY;
      return new Response(JSON.stringify({
        ok: true,
        has_key: hasKey,
        model: hasKey ? 'deepseek-chat' : 'disabled',
        time: new Date().toISOString(),
      }), { status: 200, headers: corsHeaders(origin) });
    }

    // /api/qa —— 仅接受 POST
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
      const context = Array.isArray(body.context) ? body.context : [];

      if (!question) {
        return new Response(JSON.stringify({ answer: '请输入您要查询的矿业相关问题。' }),
          { status: 200, headers: corsHeaders(origin) });
      }

      // 无 key：关键词兜底（仍可用，不报错）
      if (!env.DEEPSEEK_API_KEY) {
        return new Response(JSON.stringify({
          answer: keywordFallback(question),
          question: question,
          source: 'keyword-fallback',
          cited: 0,
          refs: [],
        }), { status: 200, headers: corsHeaders(origin) });
      }

      // 有 key：调 DeepSeek（含前端传来的相关新闻作为 RAG 上下文）
      try {
        const answer = await askDeepSeek(env.DEEPSEEK_API_KEY, question, context);
        const refs = context.slice(0, 8).map((c) => ({
          d: c.d || '', t: c.t || c.title || '', u: c.u || c.url || '',
        })).filter((r) => r.u);
        return new Response(JSON.stringify({
          answer: answer,
          question: question,
          source: 'deepseek',
          cited: context.length,
          refs: refs,
        }), { status: 200, headers: corsHeaders(origin) });
      } catch (e) {
        return new Response(JSON.stringify({
          error: 'AI 服务调用失败：' + (e && e.message ? e.message : String(e)),
        }), { status: 502, headers: corsHeaders(origin) });
      }
    }

    return new Response(JSON.stringify({ error: 'not found' }),
      { status: 404, headers: corsHeaders(origin) });
  },
};
