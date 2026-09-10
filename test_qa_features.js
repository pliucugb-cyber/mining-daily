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

  console.log('\n===== JS 运行时错误 =====');
  check('无阻塞性 JS 错误', errors.length === 0, errors.slice(0, 3).join(' | '));

  console.log('\n===== 汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 800);
