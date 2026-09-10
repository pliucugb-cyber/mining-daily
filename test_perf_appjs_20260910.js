// 性能优化回归：验证内联 JS 外置为 app.js(defer) 后页面仍能正确加载运行。
// 关键风险：抽取可能破坏语法 / 加载顺序 / 全局符号。本测试从 git HEAD 权威对象取文件，
// 规避沙箱 overlay 漂移，内联 app.js + 数据脚本（顺序 news->lme->price->app），
// 模拟 defer 执行后检查：0 致命 JS 错误、关键函数存在、问答「问」tab 正常工作、内容渲染。
const { execSync } = require('child_process');
const { JSDOM, VirtualConsole } = require('jsdom');

function blob(p) {
  return execSync(`git show HEAD:${p}`, { cwd: __dirname, encoding: 'utf8' });
}

let html = blob('index.html');
const files = ['app.js', 'news-data.js', 'lme-data.js', 'price-history.js'];
let replaced = {};
for (const f of files) {
  const content = blob(f);
  const re = new RegExp('<script src="' + f + '"[^>]*></script>');
  if (re.test(html)) {
    // 用函数式替换，避免 content 中的 $& / $1 等被 String.replace 误当成特殊序列
    html = html.replace(re, () => '<script>' + content + '</script>');
    replaced[f] = true;
  }
}

const fatal = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => {
  const msg = (e && (e.message || String(e))) || '';
  if (/Not implemented/i.test(msg)) return;
  fatal.push(msg);
});
vc.on('error', (...a) => { fatal.push(a.map(String).join(' ')); });

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true,
  url: 'https://pliucugb-cyber.github.io/mining-daily/',
  virtualConsole: vc,
  beforeParse(win) {
    win.matchMedia = q => ({ matches: /max-width:\s*768px|prefers-color-scheme:\s*dark/.test(q), media: q,
      addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    if (typeof win.fetch !== 'function') win.fetch = () => Promise.reject(new Error('stub'));
  }
});
const w = dom.window, d = w.document;

let pass = 0, fail = 0;
function ok(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name + (detail ? '  → ' + detail : '')); }
  else { fail++; console.log('  FAIL  ' + name + (detail ? '  → ' + detail : '')); }
}

setTimeout(() => {
  console.log('===== 性能优化：app.js 外置后功能回归 =====');
  ok('app.js 已内联进测试 DOM', !!replaced['app.js']);
  ok('news/lme/price 数据脚本已内联', replaced['news-data.js'] && replaced['lme-data.js'] && replaced['price-history.js']);
  ok('0 致命 JS 错误', fatal.length === 0, fatal.slice(0, 3).join(' | '));

  ok('qaFloatToggle 已定义', typeof w.qaFloatToggle === 'function');
  ok('mdMobileTopTabs 已定义', typeof w.mdMobileTopTabs === 'function');
  ok('renderLmePrices 已定义', typeof w.renderLmePrices === 'function');
  // renderRightsSection 为 IIFE 内部作用域（非全局），其正确性由下方矿权区渲染断言覆盖

  ok('window.NEWS_DATA 已加载（问答全库）', !!w.NEWS_DATA);

  const bar = d.getElementById('mobileTabBar');
  ok('#mobileTabBar 存在', !!bar);
  const qaBtn = bar && bar.querySelector('.mtab[data-go="qa"]');
  ok('存在「问」tab', !!qaBtn);
  if (bar) {
    const seq = [...bar.querySelectorAll('.mtab')].map(b => b.getAttribute('data-go'));
    ok('tab 顺序 首页/价格/问/矿权/我的',
      JSON.stringify(seq) === JSON.stringify(['home', 'price', 'qa', 'rights', 'mine']),
      '实际 ' + JSON.stringify(seq));
  }
  const qaFloat = d.getElementById('qaFloat');
  if (qaBtn && qaFloat) {
    qaBtn.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    ok('点「问」→ #qaFloat.open（整页问答）', qaFloat.classList.contains('open'));
  } else ok('点「问」打开', false, '按钮/面板缺失');

  // 内容渲染（DOMContentLoaded 后由 app.js 填充）
  const today = d.getElementById('todaySection');
  ok('今日新增区已渲染内容', !!today && today.childElementCount > 0,
    today ? 'children=' + today.childElementCount : '缺失');
  const rights = d.getElementById('rightsSection');
  ok('矿权区已渲染内容', !!rights && rights.childElementCount > 0,
    rights ? 'children=' + rights.childElementCount : '缺失');

  // 防刷新闪白：主题初始化内联块已执行（dark 模式给 body 加 .dark）
  ok('主题初始化内联块已执行（body.dark）', d.body.classList.contains('dark'),
    'body.class=' + d.body.className);

  console.log(`\n结果：${pass} PASS / ${fail} FAIL`);
  process.exit(fail ? 1 : 0);
}, 600);
