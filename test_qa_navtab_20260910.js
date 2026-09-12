// 回归测试：2026-09-10 问答入口移入底部导航栏（「问」固定 tab）
//   ① 底部导航栏含 data-go="qa" 的「问」tab，且顺序为 首页/价格/问/矿权/我的（居中）
//   ② 点「问」→ #qaFloat 进入 open（移动端扩为整页问答）
//   ③ 再点「问」→ 关闭（toggle）
//   ④ 在「问」打开时点内容 tab（如首页）→ 整页问答被关闭（qaFloatClose）
//   ⑤ 移动端 CSS：隐藏右下角悬浮球 #qaFab、#qaFloat 扩为整页（100dvh）
//   ⑥ 桌面不被破坏：#qaFab 元素仍在 DOM（桌面保留悬浮球）、0 致命 JS 错误
// 与 test_*.js 同构：jsdom 跑 index.html，结尾 PASS/FAIL + 真实退出码。
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
['app.js', 'news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  html = html.replace(new RegExp('<script src="' + f + '[^>]*></script>'),
    () => '<script>' + fs.readFileSync(p, 'utf8') + '</script>');
});

const fatal = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => {
  const msg = (e && (e.message || String(e))) || '';
  if (/Not implemented/i.test(msg)) return; // 良性：jsdom 未实现 scrollTo 等
  fatal.push(msg);
});
vc.on('error', (...a) => { fatal.push(a.map(String).join(' ')); });

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true,
  url: 'https://pliucugb-cyber.github.io/mining-daily/',
  virtualConsole: vc,
  beforeParse(win) {
    win.matchMedia = q => ({ matches: /max-width:\s*768px/.test(q), media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    if (typeof win.fetch !== 'function') win.fetch = () => Promise.reject(new Error('stub'));
  }
});
const w = dom.window;
const d = w.document;

let pass = 0, fail = 0;
function ok(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name + (detail ? '  → ' + detail : '')); }
  else { fail++; console.log('  FAIL  ' + name + (detail ? '  → ' + detail : '')); }
}

setTimeout(() => {
  console.log('===== ① 底部导航栏「问」tab 存在且居中 =====');
  const bar = d.getElementById('mobileTabBar');
  ok('#mobileTabBar 存在', !!bar);
  const qaBtn = bar && bar.querySelector('.mtab[data-go="qa"]');
  ok('存在 data-go="qa" 的「问」tab', !!qaBtn, qaBtn ? '文本=' + qaBtn.textContent.trim() : '缺失');
  // 2026-09-12：图标换成「渐变圆角方块 + <text>Ai</text>」（用户定夺），该字形是装饰性的
  //   （svg 带 aria-hidden="true"），但会混进 Element.textContent → 旧断言读到 "AiAI 搜" 而假 FAIL。
  //   标签文本应取**真正的标签 span**；同时把「图标必须装饰化」这条契约定下来。
  const qaLabel = qaBtn && (qaBtn.querySelector('span:last-child') || null);
  ok('「问」tab 文本为「AI 搜」（2026-09-12 方案 A 改名；取标签 span，图标不计入）',
    !!qaLabel && (qaLabel.textContent || '').trim() === 'AI 搜',
    'label=' + (qaLabel ? qaLabel.textContent.trim() : 'n/a'));
  const qaSvg = qaBtn && qaBtn.querySelector('.mi svg');
  ok('AI 搜图标对辅助技术隐藏（aria-hidden，装饰性）',
    !!qaSvg && qaSvg.getAttribute('aria-hidden') === 'true' && qaSvg.getAttribute('focusable') === 'false');
  ok('AI 搜 tab 有完整 aria-label（覆盖图标字形）',
    !!qaBtn && /AI 搜/.test(qaBtn.getAttribute('aria-label') || ''),
    qaBtn ? qaBtn.getAttribute('aria-label') : '');
  if (bar) {
    const seq = [...bar.querySelectorAll('.mtab')].map(b => b.getAttribute('data-go'));
    ok('tab 顺序 = 首页/价格/问/矿权/我的（居中）',
      JSON.stringify(seq) === JSON.stringify(['home', 'price', 'qa', 'rights', 'mine']),
      '实际 ' + JSON.stringify(seq));
  } else ok('tab 顺序', false, '无导航栏');

  console.log('\n===== ② 点「问」→ 整页问答打开 =====');
  const qaFloat = d.getElementById('qaFloat');
  ok('#qaFloat 存在', !!qaFloat);
  if (qaBtn && qaFloat) {
    qaBtn.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    ok('点「问」后 #qaFloat 进入 open（整页）', qaFloat.classList.contains('open'));
  } else ok('点「问」打开', false, '按钮或面板缺失');

  console.log('\n===== ③ 再点「问」→ 关闭（toggle）=====');
  if (qaBtn && qaFloat) {
    qaBtn.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    ok('再次点击 #qaFloat 退出 open', !qaFloat.classList.contains('open'));
  } else ok('再点关闭', false, '按钮或面板缺失');

  console.log('\n===== ④ 打开问答时点内容 tab → 关闭整页 =====');
  if (qaBtn && qaFloat) {
    qaBtn.dispatchEvent(new w.MouseEvent('click', { bubbles: true })); // 打开
    const opened = qaFloat.classList.contains('open');
    const home = bar.querySelector('.mtab[data-go="home"]');
    if (home) home.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    ok('打开状态下点「首页」→ 整页问答被关闭', opened && !qaFloat.classList.contains('open'),
      'opened=' + opened + ' 现=' + qaFloat.classList.contains('open'));
  } else ok('内容 tab 关问答', false, '按钮或面板缺失');

  console.log('\n===== ⑤ 移动端 CSS：隐藏悬浮球 + #qaFloat 整页 =====');
  ok('移动端隐藏右下角悬浮球 #qaFab', /#qaFab\{display:none!important\}/.test(html));
  ok('#qaFloat 移动端扩为整页（100dvh / top:0 / left:0）',
    /#qaFloat\{top:0;left:0;right:auto;bottom:auto;width:100vw;height:100dvh;max-height:none;border-radius:0;border:none;box-shadow:none\}/.test(html));
  ok('整页头部/底部留安全区',
    /\.qa-float-head\{padding-top:calc\(var\(--s3\) \+ env\(safe-area-inset-top,0px\)\)\}/.test(html)
    && /\.qa-float-foot\{padding-bottom:calc\(var\(--s3\) \+ env\(safe-area-inset-bottom,0px\)\)\}/.test(html));

  console.log('\n===== ⑥ 桌面不被破坏（DOM 层）=====');
  ok('#qaFab 元素仍在 DOM（桌面保留悬浮球）', !!d.getElementById('qaFab'));
  ok('qaFloatToggle 仍定义（共用问答逻辑）', typeof w.qaFloatToggle === 'function');
  ok('0 致命 JS 错误', fatal.length === 0, fatal.length ? fatal.slice(0, 3).join(' | ') : '无');

  console.log('\n===== 结果：' + pass + ' PASS / ' + fail + ' FAIL =====');
  process.exit(fail ? 1 : 0);
}, 1200);
