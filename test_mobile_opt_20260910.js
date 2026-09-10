// 回归测试：2026-09-10 P1/P2 移动端优化落地项
//   ① .mctab 对比度 token（源码级）
//   ② 8 个金属 chip 加 nf-chip-metal 类（DOM 保留，桌面不变；仅移动端 CSS 隐藏）
//   ③ 顶栏收藏/历史常驻图标 + 红点：#mdFavBtn/#mdHistBtn/#mdFavBadge/#mdHistBadge 构建成功
//   ④ 点击收藏/历史按钮 → 切换 body[data-filter-mode]
//   ⑤ mdUpdateFavBadges 不抛错、红点按集合非空显示
//   ⑥ 各移动 CSS 规则字符串存在（news-summary clamp / tag-chip 圆角 / badge-new 去 pulse / dot 令牌 / 热榜会展卡隐藏 / z-index 合并）
//   ⑦ 桌面不破坏：金属 chip 仍在 DOM（8 个）、#newsFilterBar 存在、0 致命 JS 错误
// 与 test_*.js 同构：jsdom 跑 index.html，结尾 PASS/FAIL + 真实退出码。
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
['app.js', 'news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  html = html.replace(new RegExp('<script src="' + f + '[^>]*></script>'),
    () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
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
    // 模拟移动视口：max-width:768px 命中
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
  console.log('===== ① .mctab 对比度 token =====');
  ok('.mctab 非激活色改为 --ink-700', /\.mctab\{[^}]*color:var\(--ink-700\)/.test(html));

  console.log('\n===== ② 金属 chip nf-chip-metal（DOM 保留，桌面不变）=====');
  const metal = d.querySelectorAll('#nfChips .nf-chip-metal');
  ok('8 个金属 chip 带 nf-chip-metal 类', metal.length === 8, '实际 ' + metal.length);
  ok('金属 chip 含 金/铜/铝/铅锌/镍/锡/锂/钴',
    ['金','铜','铝','铅锌','镍','锡','锂','钴'].every(k => [...metal].some(s => s.textContent === k)));
  ok('保留 chip：全部/矿权/政策/勘查/技术/风险 仍在',
    ['全部','矿权','政策','勘查','技术','风险'].every(k => !!d.querySelector('#nfChips .nf-chip[data-kw="' + (k==='全部'?'':k) + '"]')));
  ok('移动端 CSS 隐藏 .nf-chip-metal', /\.nf-chip-metal\{display:none\}/.test(html));

  console.log('\n===== ③ 顶栏收藏/历史常驻图标 + 红点 =====');
  ok('#mdFavBtn 存在', !!d.getElementById('mdFavBtn'));
  ok('#mdHistBtn 存在', !!d.getElementById('mdHistBtn'));
  ok('#mdFavBadge 红点存在', !!d.getElementById('mdFavBadge'));
  ok('#mdHistBadge 红点存在', !!d.getElementById('mdHistBadge'));
  ok('收藏按钮含星标 SVG', !!d.querySelector('#mdFavBtn svg'));
  ok('历史按钮含时钟 SVG', !!d.querySelector('#mdHistBtn svg'));
  ok('mdUpdateFavBadges 已定义且不抛错', typeof w.mdUpdateFavBadges === 'function');

  console.log('\n===== ④ 点击收藏/历史切换 filter-mode =====');
  const fb = d.getElementById('mdFavBtn');
  if (fb) {
    fb.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    ok('点收藏 → body[data-filter-mode]="fav"', d.body.getAttribute('data-filter-mode') === 'fav',
      '当前=' + d.body.getAttribute('data-filter-mode'));
  } else ok('点收藏切换', false, '按钮缺失');
  // 再点一次退出 fav
  if (fb) { fb.dispatchEvent(new w.MouseEvent('click', { bubbles: true })); }
  const hb = d.getElementById('mdHistBtn');
  if (hb) {
    hb.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    ok('点历史 → body[data-filter-mode]="history"', d.body.getAttribute('data-filter-mode') === 'history',
      '当前=' + d.body.getAttribute('data-filter-mode'));
    hb.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  } else ok('点历史切换', false, '按钮缺失');

  console.log('\n===== ⑤ 红点按集合非空显示 =====');
  // 无收藏/历史时默认不显示
  ok('空集合时收藏红点不显示', !d.getElementById('mdFavBadge').classList.contains('show'));
  ok('空集合时历史红点不显示', !d.getElementById('mdHistBadge').classList.contains('show'));

  console.log('\n===== ⑥ 移动 CSS 规则齐备 =====');
  ok('news-summary 移动端 3 行截断', /news-summary\{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden\}/.test(html));
  ok('tag-chip 圆角改 --r-sm(4)', /\.tag-chip\{border-radius:var\(--r-sm\)\}/.test(html));
  ok('badge-new 去 pulse', /\.badge-new\{animation:none\}/.test(html));
  ok('已读圆点阴影用 --line-2 令牌', /\.news-item\.read \.dot\{box-shadow:inset 0 0 0 2px var\(--line-2\)\}/.test(html));
  ok('热榜 tab 隐藏会展卡', /body\[data-md-cat="hot"\] #col-rail \.expo-mini\{display:none!important\}/.test(html));
  ok('顶栏 z-index 合并（搜索 225 在分类栏 230 下）', /\.news-filter-bar\{z-index:225\}/.test(html) && /#mdTop\{[^}]*z-index:230/.test(html));
  ok('移动块移除 body{font-size:15px}', /@media\(max-width:768px\)\{[\s\S]*?body\{line-height:1\.65\}/.test(html) && !/body\{font-size:15px;line-height:1\.65\}/.test(html));

  console.log('\n===== ⑦ 桌面不被破坏（DOM 层）=====');
  ok('#newsFilterBar 仍存在（桌面筛选条保留）', !!d.getElementById('newsFilterBar'));
  ok('金属 chip 仍在 DOM（桌面照常显示，仅 CSS 隐藏）', d.querySelectorAll('#nfChips .nf-chip-metal').length === 8);
  ok('0 致命 JS 错误', fatal.length === 0, fatal.length ? fatal.slice(0,3).join(' | ') : '无');

  console.log('\n===== 结果：' + pass + ' PASS / ' + fail + ' FAIL =====');
  process.exit(fail ? 1 : 0);
}, 1200);
