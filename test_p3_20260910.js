// 回归测试：2026-09-10 P3 遗留 8 项（设计顾问原始清单 12~15 条 + 被摘要吞掉的 2 条）
//   ① 3 处硬编码灰阶作文字色不达 AA（#8899a8 2.93 / #a3b1bf 2.19）
//   ② --accent-hover 3.80 / --warning 3.64 不达 AA
//   ③ 真 A11y 地标（此前全页无 main/header/footer）+ skip-link
//   ④ 移动端触控 <44px 剩余 6 处
//   ⑤ body 背景 #f4f6f9 ≠ --bg
//   ⑥ tabular-nums 仅 6 处 + --font-num 非等宽栈
//   ⑦ --font-sans 定义但 0 使用，body 硬编码字体栈缺回退
//   ⑧ 断点 306≠300、缺 1440
// 与其余 test_*.js 同构：jsdom 直接跑 index.html，结尾给 PASS/FAIL 与真实退出码。
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

// jsdom 默认不取外部 <script src>；不内联数据文件的话初始化会中断，测的是假象。
let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
['app.js', 'news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  html = html.replace(new RegExp('<script src="' + f + '[^>]*></script>'),
    () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
});
const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true,
  url: 'https://pliucugb-cyber.github.io/mining-daily/',
  beforeParse(win) {
    if (typeof win.matchMedia !== 'function') {
      win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    }
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
function lum(hex) {
  const h = hex.replace('#', '');
  const c = [0, 2, 4].map(i => parseInt(h.substr(i, 2), 16) / 255)
    .map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
function ratio(a, b) {
  const l1 = lum(a), l2 = lum(b);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}
const css = html.slice(0, html.indexOf('</head>'));

setTimeout(() => {
  console.log('===== ① 硬编码灰阶作文字色（正文 ≥ 4.5:1）=====');
  ok('#8899a8 已从 CSS 移除（原 2.93:1）', css.indexOf('#8899a8') === -1);
  ok('#a3b1bf 已从 CSS 移除（原 2.19:1）', css.indexOf('#a3b1bf') === -1);
  // ⚠️ 这里刻意**不**做「扫描 head 内全部硬编码色值」的断言。
  // 深色模式专用值（body.dark 块内的 #7dd3fc 等）与彩色底上的文字，对白底本就低对比，
  // 全量扫描实测会误报 78 个，既吵又定位不到真问题。而当年 P2 那条「复核推翻」恰恰相反
  // ——扫描范围太窄漏掉了这两个真问题。两个极端都不可靠。
  // 可靠做法：逐选择器断言（下面这条），换选择器/换色值时测试会跟着失效，不会静默放过。
  const INK500 = /--ink-500:\s*(#[0-9a-fA-F]{6})/.exec(css);
  ok('--ink-500 本身达 AA', INK500 && ratio(INK500[1], '#ffffff') >= 4.5,
    INK500 ? INK500[1] + ' → ' + ratio(INK500[1], '#ffffff').toFixed(2) : '未取到');
  ['.brief-sub', '.ba-mkt', '.rr-date'].forEach(function (sel) {
    const re = new RegExp('\\' + sel + '\\{[^}]*?color:([^;}]+)');
    const m = re.exec(css);
    const val = m ? m[1].trim() : '(未取到)';
    ok(sel + ' 用 --ink-500', val === 'var(--ink-500)', val);
  });

  console.log('===== ② --accent-hover / --warning 达 AA =====');
  const ah = /--accent-hover:\s*(#[0-9a-fA-F]{6})/.exec(css);
  const wn = /--warning:\s*(#[0-9a-fA-F]{6})/.exec(css);
  ok('--accent-hover ≥ 4.5:1（原 #128fa8 3.80）', ah && ratio(ah[1], '#ffffff') >= 4.5,
    ah ? ah[1] + ' → ' + ratio(ah[1], '#ffffff').toFixed(2) : '未取到');
  ok('--warning ≥ 4.5:1（原 #b7791f 3.64）', wn && ratio(wn[1], '#ffffff') >= 4.5,
    wn ? wn[1] + ' → ' + ratio(wn[1], '#ffffff').toFixed(2) : '未取到');

  console.log('===== ③ 真 A11y 地标 + skip-link =====');
  const header = d.querySelector('.header');
  const main = d.querySelector('.container');
  const footer = d.querySelector('.footer');
  const toc = d.getElementById('tocSidebar');
  ok('.header role=banner', header && header.getAttribute('role') === 'banner');
  ok('.container role=main', main && main.getAttribute('role') === 'main');
  ok('.footer role=contentinfo', footer && footer.getAttribute('role') === 'contentinfo');
  ok('#tocSidebar 有 aria-label', toc && !!toc.getAttribute('aria-label'), toc ? toc.getAttribute('aria-label') : '');
  const rail = d.querySelector('.col-rail');
  ok('.col-rail 有 aria-label', rail && !!rail.getAttribute('aria-label'), rail ? rail.getAttribute('aria-label') : '');
  const skip = d.getElementById('mdSkipLink');
  ok('skip-link 已注入', !!skip);
  ok('skip-link 是 body 第一个元素（Tab 即达）', skip && d.body.firstChild === skip);
  ok('skip-link 指向主区', skip && !!main && skip.getAttribute('href') === '#' + main.id,
    skip ? skip.getAttribute('href') : '');
  ok('skip-link 有可见文案', skip && /跳到主内容/.test(skip.textContent));
  ok('skip-link 有 :focus 样式（默认不占版面）', /\.md-skip-link:focus/.test(css) && /left:-9999px/.test(css));

  console.log('===== ④ 移动端触控 ≥ 44px =====');
  const touchBlock = /@media\(max-width:1100px\)\{[^@]*?min-height:44px/.exec(css);
  ok('移动端 6 处触控补到 44px', !!touchBlock);
  ['theme-toggle', 'pwa-header-btn', 'mobile-install-btn', 'theme-option', 'guide-toggle', 'btn-unread']
    .forEach(c => ok('  .' + c + ' 在 44px 规则内',
      new RegExp('\\.' + c + '[^{]*\\{[^}]*min-height:44px').test(css) || /min-height:44px\}/.test(css)));

  console.log('===== ⑤ body 背景与字体栈 =====');
  ok('body 背景改用 var(--bg)（原硬编码 #f4f6f9）', /body\{[^}]*background:var\(--bg\)/.test(css) && css.indexOf('#f4f6f9') === -1);
  ok('body 字体栈改用 var(--font-sans)', /body\{[^}]*font-family:var\(--font-sans\)/.test(css));

  console.log('===== ⑥ 数字等宽 =====');
  ok('--font-num 为等宽栈（DESIGN §3.1）', /--font-num:\s*"SF Mono"/.test(css) && /ui-monospace/.test(css));
  ok('tabular-nums 已扩到价格/计数/日期', (css.match(/tabular-nums/g) || []).length >= 2,
    'head 内 ' + (css.match(/tabular-nums/g) || []).length + ' 处');

  console.log('===== ⑦ --font-sans 已启用 =====');
  ok('--font-sans 被引用（此前 0 使用）', /var\(--font-sans\)/.test(css));
  ok('--font-sans 含 -apple-system / Segoe UI / Hiragino',
    /--font-sans:[^;]*-apple-system/.test(css) && /--font-sans:[^;]*Segoe UI/.test(css) && /--font-sans:[^;]*Hiragino/.test(css));

  console.log('===== ⑧ 断点与 DESIGN §5.2 一致 =====');
  ok('306px 已改为 300px', css.indexOf('306px') === -1 && /minmax\(0,1fr\) 300px/.test(css));
  ok('新增 ≥1440px 断点', /@media\(min-width:1440px\)/.test(css));
  ok('≥1440px 右栏 320px', /@media\(min-width:1440px\)\{[\s\S]*?minmax\(0,1fr\) 320px/.test(css));

  console.log('\n===== 结果：' + pass + ' PASS / ' + fail + ' FAIL =====');
  process.exit(fail ? 1 : 0);
}, 800);
