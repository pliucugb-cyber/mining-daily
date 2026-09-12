// 回归测试：2026-09-10 P1/P2 移动端优化落地项
//   ① .mctab 对比度 token（源码级）
//   ② 8 个金属 chip 加 nf-chip-metal 类（DOM 保留，桌面不变；仅移动端 CSS 隐藏）
//   ③ 顶栏精简（2026-09-12）：收藏/历史常驻圆钮已移除，红点随之退役，死 CSS 已清理
//   ④ 入口下移：从独立「我的」页点击收藏/历史 → 关闭我的页并切换 body[data-filter-mode]
//   ⑤ 顶栏/页面已无 .md-badge 红点元素
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

  console.log('\n===== ③ 顶栏精简：收藏/历史常驻圆钮已移除（2026-09-12 用户要求）=====');
  ok('#mdFavBtn 已从顶栏移除', !d.getElementById('mdFavBtn'));
  ok('#mdHistBtn 已从顶栏移除', !d.getElementById('mdHistBtn'));
  ok('#mdFavBadge 红点元素已移除', !d.getElementById('mdFavBadge'));
  ok('#mdHistBadge 红点元素已移除', !d.getElementById('mdHistBadge'));
  ok('品牌行仍保留 品牌名 + 日期', !!d.querySelector('#mdTop .md-brand') && !!d.querySelector('#mdTop .md-date'));
  // 注意：断言必须锚定「规则体 [`/{`]」而不是裸类名 —— 源码注释里为说明本次删除会写到
  // `.md-fav-btn` / `.md-badge` 字样，裸 `/\.md-fav-btn/` 会被注释打红（上一轮已踩过一次）。
  ok('死 CSS 已清理：无 .md-fav-btn 规则', !/\.md-fav-btn\s*[,{]/.test(html));
  ok('死 CSS 已清理：无 .md-badge 规则', !/\.md-badge\s*[,{]/.test(html));
  ok('mdUpdateFavBadges 保留为空实现且不抛错',
    typeof w.mdUpdateFavBadges === 'function' && w.mdUpdateFavBadges() === undefined);

  console.log('\n===== ③b 品牌行重排：首页两端对齐 / 非首页居中 =====');
  ok('首页品牌行两端对齐（品牌左 / 日期右）',
    /body:not\(\.md-hide-catbar\) \.md-top-brand\{justify-content:space-between\}/.test(html));
  ok('非首页品牌行居中（分类栏隐藏后只剩 tab 名）',
    /body\.md-hide-catbar \.md-top-brand\{justify-content:center\}/.test(html));
  ok('品牌行高度改造：align-items:center + min-height:36px',
    /\.md-top-brand\{display:flex;align-items:center;[^}]*min-height:36px\}/.test(html));

  console.log('\n===== ④ 入口下移：从独立「我的」页切换 filter-mode =====');
  const sheet = d.getElementById('mineSheet');
  ok('#mineSheet 存在（独立全屏设置页）', !!sheet);
  const favEntry = sheet && sheet.querySelector('button[data-act="fav"]');
  const histEntry = sheet && sheet.querySelector('button[data-act="history"]');
  ok('「我的」页含收藏入口 button[data-act="fav"]', !!favEntry);
  ok('「我的」页含浏览记录入口 button[data-act="history"]', !!histEntry);
  // 先打开「我的」页
  const mineTab = d.querySelector('.mtab[data-go="mine"]');
  if (mineTab) mineTab.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  if (favEntry) {
    favEntry.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    ok('点「我的收藏」→ body[data-filter-mode]="fav"', d.body.getAttribute('data-filter-mode') === 'fav',
      '当前=' + d.body.getAttribute('data-filter-mode'));
    ok('点「我的收藏」后关闭我的页（md-mine-open 移除）', !d.body.classList.contains('md-mine-open'));
    ok('点「我的收藏」后 mineSheet 隐藏', sheet.hidden);
  } else ok('点收藏切换', false, '入口缺失');
  // 重新打开我的页再点历史
  if (mineTab) mineTab.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  if (histEntry) {
    histEntry.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    ok('点「浏览记录」→ body[data-filter-mode]="history"', d.body.getAttribute('data-filter-mode') === 'history',
      '当前=' + d.body.getAttribute('data-filter-mode'));
    ok('点「浏览记录」后关闭我的页（md-mine-open 移除）', !d.body.classList.contains('md-mine-open'));
    ok('点「浏览记录」后 mineSheet 隐藏', sheet.hidden);
  } else ok('点历史切换', false, '入口缺失');

  console.log('\n===== ⑤ 未读红点随按钮退役 =====');
  ok('顶栏内已无 .md-badge 元素', d.querySelectorAll('#mdTop .md-badge').length === 0);
  ok('整页已无 .md-badge 元素', d.querySelectorAll('.md-badge').length === 0);

  console.log('\n===== ⑥ 移动 CSS 规则齐备 =====');
  ok('news-summary 移动端 3 行截断', /news-summary\{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden\}/.test(html));
  ok('tag-chip 圆角改 --r-sm(4)', /\.tag-chip\{border-radius:var\(--r-sm\)\}/.test(html));
  ok('badge-new 去 pulse', /\.badge-new\{animation:none\}/.test(html));
  ok('已读圆点阴影用 --line-2 令牌', /\.news-item\.read \.dot\{box-shadow:inset 0 0 0 2px var\(--line-2\)\}/.test(html));
  ok('热榜 tab 隐藏会展卡', /body\[data-md-cat="hot"\] \.col-rail \.expo-mini\{display:none!important\}/.test(html));
  ok('顶栏 z-index 合并（搜索 225 在分类栏 230 下）', /\.news-filter-bar\{z-index:225\}/.test(html) && /#mdTop\{[^}]*z-index:230/.test(html));
  ok('移动块移除 body{font-size:15px}', /@media\(max-width:768px\)\{[\s\S]*?body\{line-height:1\.65\}/.test(html) && !/body\{font-size:15px;line-height:1\.65\}/.test(html));

  console.log('\n===== ⑦ 桌面不被破坏（DOM 层）=====');
  ok('#newsFilterBar 仍存在（桌面筛选条保留）', !!d.getElementById('newsFilterBar'));
  ok('金属 chip 仍在 DOM（桌面照常显示，仅 CSS 隐藏）', d.querySelectorAll('#nfChips .nf-chip-metal').length === 8);
  ok('0 致命 JS 错误', fatal.length === 0, fatal.length ? fatal.slice(0,3).join(' | ') : '无');

  console.log('\n===== 结果：' + pass + ' PASS / ' + fail + ' FAIL =====');
  process.exit(fail ? 1 : 0);
}, 1200);
