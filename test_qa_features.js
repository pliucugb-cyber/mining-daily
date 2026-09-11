/**
 * 新闻问答子系统回归测试（jsdom）
 * 守护五大优化维度不回退：
 *   A 检索：qaHi 高亮 / qaSnippet 摘要片段
 *   B 流式：qaTryStreamOrJson / qaFinishAnswer / qaStreamPump / qaApplyJson 存在且 qaDeepseekCall 已接线
 *   C 引用+追问：qaInlineRefs 内联引用 / qaFollowUps 追问 chips
 *   D 语音：qaToggleMic / qaGetRec 存在（不支持时安全降级，不抛）
 *   E 行情：qaPriceBrief 本地价格快照注入
 * 运行：node test_qa_features.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
['app.js', 'news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  const tag = new RegExp('<script src="' + f + '[^>]*></script>');
  html = html.replace(tag, () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
});

const errors = [];
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'https://pliucugb-cyber.github.io/mining-daily/',
  beforeParse(win) {
    if (typeof win.matchMedia !== 'function') {
      win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    }
    if (typeof win.fetch !== 'function') {
      win.fetch = () => Promise.reject(new Error('jsdom: fetch stub'));
    }
    win.addEventListener('error', e => errors.push('window.error: ' + e.message));
    const origErr = win.console.error;
    win.console.error = (...a) => { errors.push('console.error: ' + a.join(' ')); origErr.apply(win.console, a); };
  }
});

const { window } = dom;
let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name + (detail ? '  → ' + detail : '')); }
  else { fail++; console.log('  FAIL  ' + name + (detail ? '  → ' + detail : '')); }
}

setTimeout(() => {
  console.log('===== Phase B 流式输出接线 =====');
  check('qaTryStreamOrJson 已定义', typeof window.qaTryStreamOrJson === 'function');
  check('qaFinishAnswer 已定义', typeof window.qaFinishAnswer === 'function');
  check('qaStreamPump 已定义', typeof window.qaStreamPump === 'function');
  check('qaApplyJson 已定义', typeof window.qaApplyJson === 'function');
  // 2026-09-10 性能优化：应用逻辑已外置为 app.js(defer)，qaDeepseekCall/qaTryStreamOrJson 现位于 app.js
  const src = fs.readFileSync(path.join(__dirname, 'app.js'), 'utf-8');
  check('qaDeepseekCall 已切换为流式入口', /qaDeepseekCall[\s\S]{0,400}qaTryStreamOrJson/.test(src) || src.indexOf('qaTryStreamOrJson') >= 0);

  console.log('\n===== Phase A 检索体验 =====');
  let hi = '';
  try { hi = window.qaHi('铜矿价格大涨铜矿', ['铜矿']); } catch (e) { hi = 'ERR:' + e.message; }
  check('qaHi 关键词高亮', hi.indexOf('<mark>铜矿</mark>') >= 0, hi.slice(0, 40));
  let sn = '';
  try { sn = window.qaSnippet('x'.repeat(200)); } catch (e) { sn = 'ERR:' + e.message; }
  check('qaSnippet 超长截断（≤60 字）', sn.length <= 60 && sn.length > 0, 'len=' + sn.length);

  console.log('\n===== Phase C 内联引用 + 追问 =====');
  let ir = '';
  try { ir = window.qaInlineRefs('据媒体报道（SMM，2026-09-08）铜价上行', [{ s: 'SMM', d: '2026-09-08', u: 'https://www.smm.cn/' }]); } catch (e) { ir = 'ERR:' + e.message; }
  check('qaInlineRefs 生成可点引用', ir.indexOf('qa-inref') >= 0, ir.slice(0, 60));
  let fu = [];
  try { fu = window.qaFollowUps('铜价为什么大跌', { r: [] }); } catch (e) { fu = ['ERR:' + e.message]; }
  check('qaFollowUps 产出 ≥2 条追问', Array.isArray(fu) && fu.length >= 2, 'chips=' + fu.length);

  console.log('\n===== Phase E 实时行情快照 =====');
  let pb = '';
  try { pb = window.qaPriceBrief('铜价现在多少'); } catch (e) { pb = 'ERR:' + e.message; }
  check('qaPriceBrief 识别价格意图并返回快照', typeof pb === 'string' && pb.length > 0 && pb.indexOf('铜') >= 0, pb.slice(0, 40));
  let pb2 = '';
  try { pb2 = window.qaPriceBrief('今天有什么并购消息'); } catch (e) { pb2 = 'ERR:' + e.message; }
  check('qaPriceBrief 非价格问题返回空串', pb2 === '');

  console.log('\n===== Phase D 语音输入 =====');
  check('qaGetRec 已定义', typeof window.qaGetRec === 'function');
  check('qaToggleMic 已定义', typeof window.qaToggleMic === 'function');

  console.log('\n===== 渲染工具 =====');
  let md = '';
  try { md = window.qaMdRender('# 标题\n\n正文 **粗体** 与 `代码`'); } catch (e) { md = 'ERR:' + e.message; }
  check('qaMdRender 解析标题/粗体/代码', md.indexOf('<h1') >= 0 && md.indexOf('<strong') >= 0 && md.indexOf('<code') >= 0);

  console.log('\n===== Phase F P0：表格渲染 / 相对时间窗 / 格式契约 =====');
  // F1 模型按提示词给的 Markdown 表格必须渲染成真表格（此前是裸竖线）
  let tb = '';
  try {
    tb = window.qaMdRender('|类型|数量|涉及矿种|\n|---|---|---|\n|探矿权出让结果公示|4|铜、金、铁多金属|\n|探矿权转让公示|3|金多金属、钼铌|\n');
  } catch (e) { tb = 'ERR:' + e.message; }
  check('qaMdRender 输出真表格（table/thead/th/td）',
    tb.indexOf('<table>') >= 0 && tb.indexOf('<thead>') >= 0 &&
    tb.indexOf('<th>类型</th>') >= 0 && tb.indexOf('<td>4</td>') >= 0 &&
    tb.indexOf('<td>铜、金、铁多金属</td>') >= 0, tb.slice(0, 120));
  check('分隔行不再漏成裸文本', tb.indexOf('---') < 0, tb.slice(0, 120));
  check('表格被 .qa-table-wrap 包裹（窄面板横向滚动）', tb.indexOf('class="qa-table-wrap"') >= 0);
  check('3 列表格恰好 3 个表头单元格', (tb.match(/<th[ >]/g) || []).length === 3, 'th=' + (tb.match(/<th[ >]/g) || []).length);

  // F2 分隔行对齐语法
  let ta = '';
  try { ta = window.qaMdRender('|矿种|数量|\n|:---:|---:|\n|金|3|'); } catch (e) { ta = 'ERR:' + e.message; }
  check('分隔行对齐解析（居中 / 右对齐）',
    ta.indexOf('text-align:center') >= 0 && ta.indexOf('text-align:right') >= 0, ta.slice(0, 140));

  // F3 正文里的单个竖线不能被误判成表格
  let nt = '';
  try { nt = window.qaMdRender('铜价上涨 | 铝价下跌\n这是第二行'); } catch (e) { nt = 'ERR:' + e.message; }
  check('无分隔行时不误判为表格', nt.indexOf('<table>') < 0, nt.slice(0, 80));

  // F4 相对时间窗解析（此前「近三天」根本不是日期意图 → 全库 Top-20 → 模型自编时间窗）
  const ri = q => { try { return window.qaDetectRangeIntent(q); } catch (e) { return { err: e.message }; } };
  check('「近三天」→ 3 天', ((ri('近三天矿权交易') || {}).days === 3), JSON.stringify(ri('近三天矿权交易')));
  check('「近3天」→ 3 天', ((ri('近3天有什么矿权交易') || {}).days === 3));
  check('「最近一周」→ 7 天', ((ri('最近一周的并购新闻') || {}).days === 7));
  check('「近一个月」→ 30 天', ((ri('近一个月铜价走势') || {}).days === 30));
  check('「近十日」→ 10 天', ((ri('近十日矿权') || {}).days === 10));
  check('「本周」→ week 标记', !!(ri('本周有什么新闻') || {}).week);
  check('「本月」→ month 标记', !!(ri('本月的并购动态') || {}).month);
  check('普通问题不误判（返回 null）',
    ri('铜价为什么大跌') === null && ri('今天有什么新闻') === null && ri('紫金矿业怎么样') === null);
  check('qaRangeDays(本周, 2026-09-11 周五) → 5', window.qaRangeDays({ week: true }, '2026-09-11') === 5);
  check('qaRangeDays(本月, 2026-09-11) → 11', window.qaRangeDays({ month: true }, '2026-09-11') === 11);

  // F5 格式契约 + 条目日期范围 + 采样参数（拦 fetch 看真实请求体）
  let cap = null;
  window.fetch = (url, opts) => { cap = { url: String(url), body: opts && opts.body }; return new Promise(() => {}); };
  const ctx2 = [
    { d: '2026-09-09', t: '某矿权出让结果公示', s: '矿业权市场', u: 'https://x.test/a' },
    { d: '2026-09-11', t: '某金矿普查新发现', s: '中国有色金属报', u: 'https://x.test/b' }
  ];
  try { window.qaDeepseekCall('近三天矿权交易', ctx2, null, null, [], false, '2026-09-11'); }
  catch (e) { cap = { err: e.message }; }
  let sent = null;
  try { sent = JSON.parse(cap.body); } catch (e) {}
  const sys = sent ? sent.messages[0].content : '';
  const usr = sent ? sent.messages[sent.messages.length - 1].content : '';
  check('请求已发出（走代理 /api/qa）', !!sent && /api\/qa/.test(cap.url), (cap && cap.url) || JSON.stringify(cap));
  check('系统提示含【输出格式（硬性要求）】', sys.indexOf('【输出格式（硬性要求）】') >= 0);
  check('格式契约要求计数类问题用 Markdown 表格', sys.indexOf('Markdown 表格') >= 0);
  check('格式契约要求以【条目日期范围】为准', sys.indexOf('【条目日期范围】') >= 0);
  check('用户消息注入条目日期范围 2026-09-09 至 2026-09-11',
    usr.indexOf('2026-09-09 至 2026-09-11') >= 0, usr.slice(-180));
  check('temperature=0（跨机可复现）+ max_tokens=1500',
    !!sent && sent.temperature === 0 && sent.max_tokens === 1500,
    sent ? 'temperature=' + sent.temperature + ' max_tokens=' + sent.max_tokens : '');

  // F6 端到端：问「近三天」必须真的按日期收窄（窗口起点 = 数据最新日期往前 3 天）
  let cap2 = null;
  window.fetch = (url, opts) => { cap2 = { url: String(url), body: opts && opts.body }; return new Promise(() => {}); };
  const qInp = window.document.getElementById('qaFloatInput');
  const rows = window.QA_ROWS || [];
  const allD = rows.map(r => r.d).filter(Boolean).sort();
  const maxD = allD[allD.length - 1] || '';
  if (qInp) { qInp.value = '近三天矿权交易'; try { window.qaFloatAsk(); } catch (e) { cap2 = { err: e.message }; } }
  let sent2 = null;
  try { sent2 = JSON.parse(cap2.body); } catch (e) {}
  const usr2 = sent2 ? sent2.messages[sent2.messages.length - 1].content : '';
  const win2 = usr2.match(/【条目日期范围（唯一可引用的时间范围）】(\d{4}-\d{2}-\d{2}) 至 (\d{4}-\d{2}-\d{2})/);
  let minAllowed = '';
  if (maxD) { const dd = new Date(maxD + 'T00:00:00'); dd.setDate(dd.getDate() - 2); minAllowed = dd.toISOString().slice(0, 10); }
  check('「近三天」问句已按日期收窄到最近 3 天（起点 ≥ ' + minAllowed + '）',
    !!win2 && !!maxD && win2[1] >= minAllowed && win2[2] <= maxD,
    win2 ? win2[1] + ' ~ ' + win2[2] + '（数据最新 ' + maxD + '）' : usr2.slice(-200));

  // F7 日期回退必须走本地日期字段（不用 toISOString，否则 UTC+8 下「近N天」多算一天）
  const sd = (a, b) => { try { return window.qaShiftDate(a, b); } catch (e) { return 'ERR:' + e.message; } };
  check('qaShiftDate 同日不偏移', sd('2026-09-11', 0) === '2026-09-11', sd('2026-09-11', 0));
  check('qaShiftDate 近7天起点 = 09-05（时区 off-by-one 回归）', sd('2026-09-11', 6) === '2026-09-05', sd('2026-09-11', 6));
  check('qaShiftDate 跨月边界 03-01 回退 1 天 = 02-28', sd('2026-03-01', 1) === '2026-02-28', sd('2026-03-01', 1));
  check('qaShiftDate 跨年边界 01-01 回退 1 天 = 上年 12-31', sd('2026-01-01', 1) === '2025-12-31', sd('2026-01-01', 1));
  check('_from 已改走 qaShiftDate（源级防回退）',
    /if\(_rg>0&&_max\)\{_from=qaShiftDate\(_max,_rg-1\);\}/.test(src) && !/_from=_dt\.toISOString/.test(src));

  // F8 结构：<style> 标签必须配平，且表格规则能真被 CSSOM 解析
  // （曾踩坑：新增的 <style> 把上一个块的 </style> 吃掉了，于是新块里第一条规则
  //   .qa-table-wrap 被浏览器当成非法选择器整条丢弃，窄面板横向滚动静默失效）
  const rawIdx = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
  const soN = (rawIdx.match(/^<style/gm) || []).length, scN = (rawIdx.match(/^<\/style>/gm) || []).length;
  check('index.html 行首 <style>/</style> 配平', soN === scN && soN >= 11, soN + ' / ' + scN);
  const cssHit = { wrap: false, th: false, darkTh: false, darkTd: false };
  Array.prototype.forEach.call(window.document.styleSheets, ss => {
    let rules = [];
    try { rules = ss.cssRules || []; } catch (e) { return; }
    Array.prototype.forEach.call(rules, r => {
      const sel = String(r.selectorText || '');
      if (sel.indexOf('.qa-table-wrap') >= 0) cssHit.wrap = true;
      if (sel.indexOf('.qa-msg-bubble th') >= 0) { cssHit.th = !/^body\.dark/.test(sel) ? true : cssHit.th; if (/^body\.dark/.test(sel)) cssHit.darkTh = true; }
      if (/^body\.dark/.test(sel) && sel.indexOf('.qa-msg-bubble td') >= 0) cssHit.darkTd = true;
    });
  });
  check('.qa-table-wrap 规则可被 CSSOM 解析（未被整条丢弃）', cssHit.wrap, JSON.stringify(cssHit));
  check('.qa-msg-bubble th 亮/暗两套规则均可解析', cssHit.th && cssHit.darkTh, JSON.stringify(cssHit));

  // F9 单元格内行内代码含竖线不得被拆列
  let tc2 = '';
  try { tc2 = window.qaMdRender('|表达式|结果|\n|---|---|\n|`x|y`|1|'); } catch (e) { tc2 = 'ERR:' + e.message; }
  check('单元格内行内代码含竖线不被拆列',
    tc2.indexOf('<code>x|y</code>') >= 0 && (tc2.match(/<td/g) || []).length === 2,
    'td=' + (tc2.match(/<td/g) || []).length + ' → ' + tc2.slice(0, 160));
  // F10 超宽行（单元格数多于表头）应结束表格、留给正文，而不是截断丢字
  let tc3 = '';
  try { tc3 = window.qaMdRender('|类型|数量|\n|---|---|\n|出让|4|\n铜价上涨 | 铝价下跌 | 锂价持平'); } catch (e) { tc3 = 'ERR:' + e.message; }
  check('超宽行结束表格且不丢字（正文仍可见）',
    tc3.indexOf('<td>4</td>') >= 0 && tc3.indexOf('锂价持平') >= 0 && (tc3.match(/<td/g) || []).length === 2,
    'td=' + (tc3.match(/<td/g) || []).length + ' → ' + tc3.slice(0, 200));

  console.log('\n===== JS 运行时错误 =====');
  check('无阻塞性 JS 错误', errors.length === 0, errors.slice(0, 3).join(' | '));

  console.log('\n===== 汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 800);
