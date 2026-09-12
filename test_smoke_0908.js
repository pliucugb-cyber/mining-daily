/**
 * 2026-09-08 批次改动冒烟测试（jsdom）
 * 覆盖：① 找矿专项区已取消 ② 要闻跨源去重 + 日期标注 ③ 热榜 ≤5 条且与要闻互斥
 *       ④ 会展迷你卡进侧栏 ⑤ 矿权改紧凑列表 + 去重（09-12 起桌面恢复「卡片/列表」双视图） ⑥ 已读样式对比度
 * 运行：node test_smoke_0908.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

// jsdom 默认不取外部脚本，把本地数据文件内联进去，避免全库为空导致误判
let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
// 数据脚本：内联到原位即可（仅定义全局变量，不依赖 DOM 就绪）
['news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  const tag = new RegExp('<script src="' + f + '[^>]*></script>');
  html = html.replace(tag, () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
});
// 2026-09-10 性能优化：app.js 生产用 defer（全文档解析完成后才执行），其初始化 IIFE 依赖 #qaFloatBody
// 已存在。jsdom 内联到标签原位会丢失 defer 语义、在 #qaFloat 之前执行 → 欢迎语不渲染。
// 故把 app.js 移到 </body> 前，等价模拟 defer 的「DOM 解析完成后执行」。
{
  const p = path.join(__dirname, 'app.js');
  if (fs.existsSync(p)) {
    html = html.replace(new RegExp('<script src="app.js"[^>]*></script>'), '');
    html = html.replace('</body>', '<script>' + fs.readFileSync(p, 'utf-8') + '</script>\n</body>');
  }
}
const errors = [];

const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'https://pliucugb-cyber.github.io/mining-daily/',
  beforeParse(win) {
    // jsdom 未实现 matchMedia：补一个「桌面宽屏」桩，让会展迷你卡走桌面分支
    if (typeof win.matchMedia !== 'function') {
      win.matchMedia = q => ({ matches: /max-width:\s*1100px/.test(q) ? false : false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    }
    // jsdom 无 fetch：不补会让 fetchHotNews 同步抛错，中断后续初始化（QA_ROWS 等拿不到）
    if (typeof win.fetch !== 'function') {
      win.fetch = () => Promise.reject(new Error('jsdom: fetch stub'));
    }
    win.addEventListener('error', e => errors.push('window.error: ' + e.message));
    const origErr = win.console.error;
    win.console.error = (...a) => { errors.push('console.error: ' + a.join(' ')); origErr.apply(win.console, a); };
  }
});

const { window } = dom;
const doc = window.document;

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name + (detail ? '  → ' + detail : '')); }
  else { fail++; console.log('  FAIL  ' + name + (detail ? '  → ' + detail : '')); }
}

setTimeout(() => {
  console.log('===== ① 找矿专项区已取消 =====');
  check('主区 #specialSection 已移除', doc.querySelectorAll('#specialSection').length === 0);
  check('侧栏「找矿专项」目录项已移除',
    doc.querySelectorAll('.toc-main-item[data-target="specialSection"]').length === 0);
  const strategyBadges = doc.querySelectorAll('.badge-strategy').length;
  check('「战略」徽章仍在（条目留原位，未丢失标记）', strategyBadges >= 0, '徽章数=' + strategyBadges);
  const spList = doc.querySelectorAll('.sp-list').length;
  check('专项子类容器 sp-list 已清空', spList === 0, 'sp-list 数=' + spList);

  console.log('\n===== ② 今日要闻：跨源去重 + 日期标注 =====');
  const digest = doc.querySelectorAll('#digestList li');
  check('要闻条数 1~4', digest.length >= 1 && digest.length <= 4, '实际 ' + digest.length + ' 条');
  const titles = [...digest].map(li => (li.querySelector('.digest-link') || {}).textContent || '');
  console.log('       要闻标题：');
  titles.forEach(t => console.log('         - ' + t.slice(0, 46)));
  let maxSim = 0, dupPair = null;
  const sim = window.mdTitleSim;
  check('mdTitleSim 已挂到 window', typeof sim === 'function');
  if (typeof sim === 'function') {
    for (let i = 0; i < titles.length; i++) {
      for (let j = i + 1; j < titles.length; j++) {
        const v = sim(titles[i], titles[j]);
        if (v > maxSim) { maxSim = v; dupPair = [titles[i], titles[j]]; }
      }
    }
    check('要闻内无跨源重复（最高相似度 < 0.5）', maxSim < 0.5,
      'maxSim=' + maxSim.toFixed(3) + (dupPair ? '  (' + dupPair[0].slice(0, 20) + ' vs ' + dupPair[1].slice(0, 20) + ')' : ''));
  }
  const dtag = doc.querySelectorAll('#digestList .digest-dtag').length;
  console.log('       非当日条目标注日期数：' + dtag);

  console.log('\n===== ③ 矿业热榜：≤5 条 + 与要闻互斥 =====');
  const hot = doc.querySelectorAll('#hotListBody li.hot-item');
  check('热榜条数 1~5', hot.length >= 1 && hot.length <= 5, '实际 ' + hot.length + ' 条');
  const hotTitles = [...hot].map(li => (li.querySelector('.hot-title') || {}).textContent || '');
  console.log('       热榜标题：');
  hotTitles.forEach(t => console.log('         - ' + t.slice(0, 46)));
  if (typeof sim === 'function') {
    let cross = 0, worst = 0;
    hotTitles.forEach(ht => titles.forEach(dt => {
      const v = sim(ht, dt);
      if (v >= 0.5) { cross++; if (v > worst) worst = v; }
    }));
    check('热榜与要闻无重复条目', cross === 0, '重叠 ' + cross + ' 对' + (worst ? ' maxSim=' + worst.toFixed(2) : ''));
  }

  // ③b 换一换（2026-09-08 晚新增：头条式轮换）
  const rbtn = doc.getElementById('hotRefreshBtn');
  check('③b 换一换按钮存在且可见', !!rbtn && rbtn.style.display !== 'none');
  const beforeTitles = [...doc.querySelectorAll('#hotListBody .hot-title')].map(a => a.textContent);
  if (rbtn) {
    rbtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    const afterTitles = [...doc.querySelectorAll('#hotListBody .hot-title')].map(a => a.textContent);
    check('③b 点击换一换后条目变化', JSON.stringify(beforeTitles) !== JSON.stringify(afterTitles));
    const hotAfter = doc.querySelectorAll('#hotListBody li.hot-item');
    check('③b 换一换后仍 1~5 条', hotAfter.length >= 1 && hotAfter.length <= 5, '实际 ' + hotAfter.length);
    let cycled = false;
    const pages = Math.ceil(((window.__hotPool || []).length) / 5) || 1;
    for (let i = 1; i <= pages; i++) {
      rbtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
      const cur = [...doc.querySelectorAll('#hotListBody .hot-title')].map(a => a.textContent);
      if (JSON.stringify(cur) === JSON.stringify(beforeTitles)) { cycled = true; break; }
    }
    check('③b 连点可循环回绕到第一页', cycled, 'pool=' + (window.__hotPool || []).length + ' pages=' + pages);
  }

  // ③c 旧闻补录降级（2026-09-08 晚：发布日期距报告日>2天的今日区条目，NEW -> 灰色「补录」）
  const todaySec = doc.getElementById('todaySection');
  check('③c 今日区存在', !!todaySec);
  if (todaySec) {
    const now = new Date();
    let anchor = '';
    try { anchor = (typeof window.qaReportDate === 'function') ? (window.qaReportDate() || '') : ''; } catch (e) {}
    if (!anchor) anchor = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0') + '-' + String(now.getDate()).padStart(2, '0');
    const base = new Date(+anchor.slice(0, 4), +anchor.slice(5, 7) - 1, +anchor.slice(8, 10));
    let staleLeft = 0, freshBadged = 0, backfillN = 0, staleCount = 0;
    todaySec.querySelectorAll('.news-item').forEach(el => {
      const meta = el.querySelector('.news-meta');
      const m = meta ? (meta.textContent || '').match(/(\d{2})-(\d{2})/) : null;
      if (!m) return;
      const d = new Date(base.getFullYear(), +m[1] - 1, +m[2]);
      const stale = (base - d) / 86400000 > 2;
      if (stale) staleCount++;
      const hasNew = !!el.querySelector('.badge-new') && el.classList.contains('is-new');
      const hasBf = !!el.querySelector('.badge-backfill');
      if (hasBf) backfillN++;
      if (stale && hasNew) staleLeft++;
      if (!stale && hasBf) freshBadged++;
    });
    check('③c 超期条目不再带 NEW', staleLeft === 0, '残留 ' + staleLeft + ' 条');
    check('③c 时效内条目不被误标补录', freshBadged === 0, '误标 ' + freshBadged + ' 条');
    // 数据相关：今日区若存在>2天旧闻则必须生成补录标；若数据本身无超期条目（降级逻辑正确 no-op）则 backfill=0
    if (staleCount > 0) {
      check('③c 补录标已生成（超期 ' + staleCount + ' 条应降级）', backfillN >= 1, 'backfill=' + backfillN);
    } else {
      check('③c 今日区无超期条目→降级逻辑正确 no-op', backfillN === 0, 'backfill=' + backfillN + '（数据无>2天旧闻）');
    }
    // 2026-09-08 晚追加：补录条目不保留 is-special 底色强调
    let spLeft = 0;
    todaySec.querySelectorAll('.news-item .badge-backfill').forEach(b => {
      const el = b.closest('.news-item');
      if (el && el.classList.contains('is-special')) spLeft++;
    });
    check('③c 补录条目无 is-special 底色', spLeft === 0, '残留 ' + spLeft + ' 条');
  }

  console.log('\n===== ④ 会展预告迁至侧栏迷你卡 =====');
  const mini = doc.getElementById('expoMini');
  check('侧栏迷你卡容器存在', !!mini);
  check('迷你卡在右栏 col-rail 内', !!(mini && mini.closest('.col-rail')));
  // 2026-09-08 晚：全量展示 + 限高滚动，「另有 N 场」死文本已删
  const miniItems = [...doc.querySelectorAll('#expoMiniList li')];
  check('迷你卡无「另有 N 场」残留行', doc.querySelectorAll('#expoMiniList .expo-mini-more').length === 0);
  check('迷你卡条目全部带链接（可点击）', miniItems.every(li => li.querySelector('a[href]')));
  const vaultAll = doc.querySelectorAll('#expoVault .news-item').length;
  check('迷你卡条目数 = 移入 vault 条数（无截断）', miniItems.length === vaultAll, 'list=' + miniItems.length + ' vault=' + vaultAll);
  let expoDup = 0;
  const expoTitles = miniItems.map(li => (li.querySelector('a') || {}).textContent || '').filter(Boolean);
  for (let i = 0; i < expoTitles.length; i++)
    for (let j = i + 1; j < expoTitles.length; j++)
      if (typeof sim === 'function' && sim(expoTitles[i], expoTitles[j]) >= 0.5) expoDup++;
  check('迷你卡内无跨源重复会议', expoDup === 0, '重复 ' + expoDup + ' 对');
  console.log('       会展条目：');
  [...miniItems].forEach(li => console.log('         - ' + (li.textContent || '').trim().slice(0, 46)));
  check('主区不再生成 #expoSection', doc.querySelectorAll('#expoSection').length === 0);
  const vault = doc.getElementById('expoVault');
  check('会展条目已移入隐藏容器（仍在 DOM 可搜索）', !!vault, vault ? ('条数=' + vault.querySelectorAll('.news-item').length) : '');

  console.log('\n===== ⑤ 矿权：紧凑列表 + 同宗去重 =====');
  const rows = doc.querySelectorAll('#rightsCards .rights-row');
  const oldCards = doc.querySelectorAll('#rightsCards .rights-card');
  check('渲染为紧凑行 .rights-row', rows.length > 0, '行数=' + rows.length);
  check('旧大卡片 .rights-card 已不再渲染', oldCards.length === 0);
  const rTitles = [...rows].map(r => (r.querySelector('.rr-title') || {}).textContent || '');
  const uniq = new Set(rTitles.map(t => t.replace(/[^一-龥A-Za-z0-9]/g, '')));
  check('矿权列表内无重复标题', uniq.size === rTitles.length, rTitles.length + ' 行 / ' + uniq.size + ' 个唯一标题');
  check('CSV 导出数据源 __rightsFullList 存在', Array.isArray(window.__rightsFullList), '长度=' + (window.__rightsFullList || []).length);
  const sum = doc.querySelector('.news-item[data-rights-summary="1"]');
  if (sum) {
    const links = [...sum.querySelectorAll('.rr-link')].map(a => a.textContent.trim().replace(/[^一-龥A-Za-z0-9]/g, ''));
    check('聚合条内链接无重复', new Set(links).size === links.length, links.length + ' 个链接 / ' + new Set(links).size + ' 唯一');
    const ts = doc.getElementById('todaySection');
    check('聚合条位于今日新增末尾', ts && ts.lastElementChild === sum);
  } else {
    console.log('       （今日无矿权结果聚合条，跳过）');
  }

  console.log('\n===== ⑥ 已读样式对比度 =====');
  const css = html;
  // 2026-09-08 step3 修订：禁用 opacity 做已读态（13px 中文会发灰糊），改用 --ink-300 文字色
  check('已读改用文字色（非 opacity）', /\.news-item\.read \.news-title\{color:var\(--ink-300\)/.test(css)
    && /\.news-item\.read \.news-summary\{color:var\(--ink-300\)/.test(css));
  check('已读不再整块降透明度', !/\.news-item\.read\{opacity/.test(css));
  check('已读圆点改空心灰环', /\.news-item\.read \.dot\{background:transparent;box-shadow:inset 0 0 0 2px/.test(css));
  check('未读圆点仍为实心品牌色', /\.dot\{width:9px;height:9px;border-radius:\s*50%;background:(#2980b9|var\(--brand\))/.test(css));

  console.log('\n===== ⑦ 新闻问答面板 =====');
  const qaInput = doc.getElementById('qaFloatInput');
  // 2026-09-12 反转：原「输入框不显示占位提示词」——用户反馈底部输入区「看着很别扭」，
  //   空框没有任何提示是主要原因之一。改为「有简短占位词（<=12 字）」，aria-label 仍保留。
  check('⑦ 输入框有简短占位提示（2026-09-12 由「不放占位词」反转，<=12 字）',
    !!qaInput && !!qaInput.getAttribute('placeholder') && qaInput.getAttribute('placeholder').length <= 12,
    qaInput && qaInput.getAttribute('placeholder'));
  check('⑦ 输入框保留 aria-label（可访问性）', !!qaInput && !!qaInput.getAttribute('aria-label'));
  const qaBody = doc.getElementById('qaFloatBody');
  const firstMsg = qaBody ? qaBody.querySelector('.qa-msg.ai .qa-msg-bubble') : null;
  const welcome = firstMsg ? firstMsg.textContent : '';
  check('⑦ 欢迎语含库条数', /本地新闻库共 \d+ 条/.test(welcome), welcome.slice(0, 40));
  check('⑦ 欢迎语含检索/AI 引导', welcome.includes('检索') && welcome.includes('AI'));
  const qaAiBtn = doc.getElementById('qaFloatAi');
  check('⑦ AI 按钮不误标「AI 本地」（代理可用）', !!qaAiBtn && qaAiBtn.textContent !== '✨ AI 本地', qaAiBtn ? qaAiBtn.textContent : '无按钮');
  check('⑦ 检索/AI 按钮存在', !!doc.getElementById('qaFloatSearch') && !!qaAiBtn);

  console.log('\n===== ⑧ 本地持久化链路（lsSet 回归守护） =====');
  // 2026-09-08 晚：lsSet 曾写成 window.lsSet 自调用（无限递归被吞），09-06 起所有本地存储静默失效
  try {
    doc.defaultView.lsSet('md_test_key', 'v1');
    check('⑧ lsSet 真实写入 localStorage', doc.defaultView.localStorage.getItem('md_test_key') === 'v1');
  } catch (e) {
    check('⑧ lsSet 真实写入 localStorage', false, e.message);
  }
  try {
    doc.defaultView.markAllRead();
    const readN = doc.querySelectorAll('.news-item.read').length;
    check('⑧ markAllRead 后已读条数 > 0', readN > 0, 'read=' + readN);
  } catch (e) {
    check('⑧ markAllRead 后已读条数 > 0', false, e.message);
  }

  console.log('\n===== ⑨ 矿权区双视图（2026-09-12 改版：卡片/列表；表格视图仍禁复活） =====');
  // 沿革：09-08 曾删掉「卡片/表格」双视图（内容 80% 重复）。09-12 按用户要求在桌面恢复双视图，
  // 但现行形态是「卡片（默认，自适应多列网格）/ 列表（紧凑行）」——旧的表格视图与 .rights-view-btn 仍严禁复活。
  check('⑨ 旧表格视图未复活（无 #rightsTable 系列 / .rights-view-btn）',
    !doc.getElementById('rightsTable') && !doc.getElementById('rightsTableWrap') && !doc.getElementById('rightsTableBody')
    && doc.querySelectorAll('.rights-view-btn').length === 0);
  const rc9 = doc.getElementById('rightsCards');
  check('⑨ 列表容器仍在且已渲染', !!rc9 && rc9.querySelectorAll('.rights-row').length >= 1, 'rows=' + (rc9 ? rc9.querySelectorAll('.rights-row').length : 0));

  // 切换器：两态按钮，默认卡片
  const rvBtns = doc.querySelectorAll('.rights-views .rv-btn');
  check('⑨ 切换器在位（卡片/列表 两态）', rvBtns.length === 2, 'n=' + rvBtns.length);
  check('⑨ 默认卡片视图（#rightsCards 带 rv-cards 且卡片键 is-on）',
    !!rc9 && rc9.classList.contains('rv-cards') && !!doc.querySelector('.rv-btn[data-rv="cards"].is-on'));
  // 运行时切换：点「列表」→ 去掉 rv-cards 且按钮态互换；再点回「卡片」复原
  try {
    const listBtn = doc.querySelector('.rv-btn[data-rv="list"]');
    const cardsBtn = doc.querySelector('.rv-btn[data-rv="cards"]');
    listBtn.dispatchEvent(new window.Event('click', { bubbles: true }));
    const toList = !rc9.classList.contains('rv-cards') && listBtn.classList.contains('is-on');
    cardsBtn.dispatchEvent(new window.Event('click', { bubbles: true }));
    const backToCards = rc9.classList.contains('rv-cards') && cardsBtn.classList.contains('is-on');
    check('⑨ 点「列表」切紧凑行 / 点「卡片」切回（含按钮态与 aria-pressed）',
      toList && backToCards, 'list→' + toList + ' cards→' + backToCards);
  } catch (e) { check('⑨ 点「列表」切紧凑行 / 点「卡片」切回（含按钮态与 aria-pressed）', false, e.message); }

  // 列表态截止期：每条带 deadline 的行都渲染 .rr-due（与卡片 badge 同源文案，避免两个口径）
  const dueRows = rc9 ? rc9.querySelectorAll('.rights-row').length : 0;
  const dueN = rc9 ? rc9.querySelectorAll('.rr-due').length : 0;
  check('⑨ 列表态截止期元素 .rr-due 随行渲染', dueN > 0 && dueN <= dueRows, 'due=' + dueN + ' rows=' + dueRows);
  // CSS 契约：卡片态自适应多列网格 / 列表态显示 .rr-due / 手机隐藏切换器
  check('⑨ CSS：桌面卡片态为自适应多列网格',
    /#rightsCards\.rv-cards\{display:grid;grid-template-columns:repeat\(auto-fill,minmax\(330px,1fr\)\)/.test(html));
  check('⑨ CSS：列表态显示 .rr-due、手机隐藏切换器',
    /#rightsCards:not\(\.rv-cards\) \.rr-due\{display:inline-block\}/.test(html)
    && /@media\(max-width:768px\)\{\.rights-views\{display:none\}\}/.test(html));

  // 列表排序条（2026-09-12：把原本无入口的死代码 rightsSort 接上）
  const cols9 = rc9 ? rc9.querySelector('.rights-cols') : null;
  const sortBtns = rc9 ? rc9.querySelectorAll('.rc-sort') : [];
  check('⑨ 列表排序条在位（默认/到期日/成交价 三个 chip）', !!cols9 && sortBtns.length === 3, 'chips=' + sortBtns.length);
  check('⑨ 默认激活「默认·紧迫度」chip',
    !!rc9.querySelector('.rc-sort[data-sk=""].is-on') && !rc9.querySelector('.rc-sort.is-on[data-sk="price"]'));
  const amtEls = () => rc9.querySelectorAll('.rights-row .rr-amount');
  check('⑨ 金额列 .rr-amount 随行渲染', amtEls().length === dueRows, 'amount=' + amtEls().length + ' rows=' + dueRows);
  const amtNums = () => [...amtEls()].map(el => el.classList.contains('na') ? null : parseFloat((el.textContent || '').replace(/[^\d.]/g, '')));
  // 注意：点 chip 会 renderRightsSection() 重建 innerHTML，旧节点引用会脱离 DOM——每次点击后重新查询。
  const sortBtn = (sk) => rc9.querySelector('.rc-sort[data-sk="' + sk + '"]');
  const clickSort = (sk) => { const b = sortBtn(sk); b.dispatchEvent(new window.Event('click', { bubbles: true })); };
  try {
    clickSort('price');
    const d1 = amtNums(); const nn1 = d1.filter(v => v != null);
    const desc = nn1.every((v, i) => i === 0 || nn1[i - 1] >= v);
    const nullTail = d1.slice(nn1.length).every(v => v == null);
    check('⑨ 点「成交价」→ 按金额降序、缺值沉底',
      sortBtn('price').classList.contains('is-on') && desc && nullTail,
      'n=' + nn1.length + ' 降序=' + desc + ' 沉底=' + nullTail);
    clickSort('price');
    const nn2 = amtNums().filter(v => v != null);
    const asc = nn2.every((v, i) => i === 0 || nn2[i - 1] <= v);
    check('⑨ 再点「成交价」→ 反向为升序（按钮带方向箭头）',
      asc && /[↑↓]/.test(sortBtn('price').textContent),
      '升序=' + asc + ' 文案=' + (sortBtn('price').textContent || '').trim());
    clickSort('deadline');
    check('⑨ 点「到期日」→ 切换维度（按截止日升序）',
      sortBtn('deadline').classList.contains('is-on') && !sortBtn('price').classList.contains('is-on'));
    clickSort('');
    check('⑨ 点「默认·紧迫度」→ 排序复位',
      sortBtn('').classList.contains('is-on') && !sortBtn('deadline').classList.contains('is-on')
      && !sortBtn('price').classList.contains('is-on'));
    check('⑨ 排序状态不写 localStorage（刷新即回默认紧迫度）',
      !doc.defaultView.localStorage.getItem('mdRightsSort'));
  } catch (e) { check('⑨ 排序交互（点 chip 重排 / 反向 / 复位）', false, e.message); }
  check('⑨ CSS：列表态开排序条与金额列、默认隐藏',
    /#rightsCards:not\(\.rv-cards\) \.rights-cols\{display:flex\}/.test(html)
    && /#rightsCards:not\(\.rv-cards\) \.rr-amount\{display:inline-block\}/.test(html)
    && /\.rights-cols\{display:none/.test(html));

  console.log('\n===== ⑩ 计数口径一致（2026-09-08 深夜） =====');
  // 子分类「N条新增」原是生成脚本写死的静态值，会展条目被收纳/旧闻降级后不再更新，
  // 出现「3+16+13=32」与顶部「28 今日新增」对不上。现由 syncSubCounts() 按 DOM 重算。
  try {
    const newTotal = parseInt((doc.getElementById('newCount') || {}).textContent || '0', 10);
    let sum = 0;
    doc.querySelectorAll('#todaySection .sub-cat').forEach(c => {
      const t = (c.querySelector('.sub-count') || {}).textContent || '';
      const m = t.match(/(\d+)/);
      if (m) sum += parseInt(m[1], 10);
    });
    check('⑩ 今日区子分类「新增」之和 = 顶部今日新增', sum === newTotal, '子分类=' + sum + ' 顶部=' + newTotal);
  } catch (e) { check('⑩ 今日区子分类「新增」之和 = 顶部今日新增', false, e.message); }
  try {
    const titleN = parseInt(((doc.getElementById('todayCount') || {}).textContent || '').replace(/\D/g, ''), 10);
    const realN = doc.querySelectorAll('#todaySection .news-item:not(.arch-fav)').length;
    check('⑩ 区块标题条数 = 今日区实际条数', titleN === realN, '标题=' + titleN + ' 实际=' + realN);
  } catch (e) { check('⑩ 区块标题条数 = 今日区实际条数', false, e.message); }
  // 专项区取消后遗留：GoatCounter 后台未开通（403），默认隐藏避免常驻「累计访问 - 次」
  const gcLine = doc.getElementById('gcStatLine');
  check('⑩ 累计访问行默认隐藏（取到数字才显示）', !!gcLine && gcLine.style.display === 'none');
  check('⑩ 矿权区标题不再自称「结构化卡片」', !/结构化卡片/.test((doc.getElementById('rightsSection') || {}).textContent || ''));

  console.log('\n===== \u246a \u6536\u85cf/\u5386\u53f2\u7b5b\u9009\u5b9a\u4f4d\uff082026-09-09 \u51cc\u6668\uff09 =====');
  // \u80cc\u666f\uff1a\u76ee\u5f55\u91cc\u7684\u300c\u6211\u7684\u6536\u85cf / \u6d4f\u89c8\u8bb0\u5f55\u300d\u539f onclick \u5c3e\u5df2\u6302\u4e86 window.scrollTo({top:0})\uff0c
  // \u70b9\u5b8c\u6c38\u8fdc\u88ab\u5f39\u56de\u9876\u90e8\uff1b\u4e14\u5f80\u671f\u533a\u65e5\u7ec4\u6298\u53e0\u4f1a\u8ba9\u547d\u4e2d\u9879\u85cf\u5728\u5185\u8054 display:none \u91cc\u3002
  try {
    const tocFav = doc.getElementById('tocFavItem');
    const tocHis = doc.getElementById('tocHistoryItem');
    check('\u246a \u76ee\u5f55\u300c\u6211\u7684\u6536\u85cf\u300d\u4e0d\u518d\u5f3a\u5236\u6eda\u56de\u9876\u90e8', !!tocFav && !/scrollTo/.test(tocFav.getAttribute('onclick') || ''));
    check('\u246a \u76ee\u5f55\u300c\u6d4f\u89c8\u8bb0\u5f55\u300d\u4e0d\u518d\u5f3a\u5236\u6eda\u56de\u9876\u90e8', !!tocHis && !/scrollTo/.test(tocHis.getAttribute('onclick') || ''));
    check('\u246a \u65e5\u7ec4\u81ea\u52a8\u5c55\u5f00 / \u547d\u4e2d\u6536\u96c6 / \u7a7a\u6001\u63d0\u793a\u51fd\u6570\u9f50\u5907',
      typeof window.mdAutoExpandDayGroups === 'function' &&
      typeof window.collectVisibleMatches === 'function' &&
      typeof window.mdShowFilterEmpty === 'function');

    // jsdom \u65e0\u5e03\u5c40\uff1a\u624b\u5de5\u6253\u6869\uff08\u7b2c i \u4e2a\u6761\u76ee top = i*100\uff09\uff0c\u628a rAF \u540c\u6b65\u5316\uff0c\u65b9\u80fd\u6821\u9a8c\u771f\u5b9e\u5750\u6807
    const all = Array.from(doc.querySelectorAll('.news-item')).filter(e => e.dataset && e.dataset.url);
    all.forEach((el, i) => { el.getBoundingClientRect = () => ({ top: i * 100, bottom: i * 100 + 90, height: 90, left: 0, right: 600, width: 600 }); });
    Object.defineProperty(window, 'innerHeight', { value: 800, configurable: true });
    Object.defineProperty(window, 'pageYOffset', { value: 0, configurable: true, writable: true });
    Object.defineProperty(doc.documentElement, 'scrollHeight', { value: all.length * 100 + 2000, configurable: true });
    const _scrolls = [];
    window.scrollTo = function () { _scrolls.push(arguments.length === 1 ? arguments[0] : [arguments[0], arguments[1]]); };
    const _raf = window.requestAnimationFrame;
    window.requestAnimationFrame = cb => { cb(Date.now()); return 0; };

    try { window.lsSet('mining_daily_favorites', '[]'); } catch (e) {}
    const farIdx = 60;
    window.toggleFav(all[farIdx].dataset.url);
    _scrolls.length = 0;
    window.toggleFavFilter();
    const got = _scrolls.length ? (_scrolls[0].top != null ? _scrolls[0].top : _scrolls[0][1]) : null;
    // 2026-09-09 晚：收藏改为沉浸式聚合视图，命中条目集中在 #archivedFavSection 顶部，
    // 因此滚动目标不再是原归档区深处的条目，而是顶部列表区域（<=100）。
    check('\u246a \u6536\u85cf\u7b5b\u9009\u6eda\u5230\u5217\u8868\u9876\u90e8', got != null && got <= 100, 'got=' + got);

    _scrolls.length = 0;
    window.toggleFavFilter();
    const back = _scrolls.length ? (_scrolls[0].top != null ? _scrolls[0].top : _scrolls[0][1]) : null;
    check('\u246a \u9000\u51fa\u7b5b\u9009\u8fd8\u539f\u4f4d\u7f6e\u800c\u975e\u8df3\u9876', back === 0, 'back=' + back);

    // 0 \u547d\u4e2d\uff1a\u5e94\u7ed9\u7a7a\u6001\u63d0\u793a\u4e14\u4e0d\u4e71\u8df3
    try { window.lsSet('mining_daily_favorites', '[]'); } catch (e) {}
    _scrolls.length = 0;
    window.toggleFavFilter();
    const tip = doc.getElementById('mdFilterEmptyTip');
    check('\u246a 0 \u547d\u4e2d\u65f6\u7ed9\u7a7a\u6001\u63d0\u793a\u4e14\u4e0d\u4e71\u8df3', !!tip && tip.classList.contains('show') === true);

    window.requestAnimationFrame = _raf;
    try { window.lsSet('mining_daily_favorites', '[]'); } catch (e) {}
  } catch (e) { check('\u246a \u6536\u85cf/\u5386\u53f2\u7b5b\u9009\u5b9a\u4f4d', false, e.message); }

  console.log('\n===== ⑫ 往期日组点击 + 今日新增计数口径（2026-09-09） =====');
  // ⑫a 往期日组点击只展开该日组、不误折叠父分类（事件冒泡修复）
  try {
    const arch = doc.getElementById('archiveSection');
    const dgs = arch ? arch.querySelectorAll('.day-group') : [];
    if (dgs.length) {
      const dg = dgs[0];
      const cat = dg.closest('.sub-cat') || dg.parentElement;
      const catBefore = cat.getAttribute('data-collapsed');
      const dgBefore = dg.getAttribute('data-collapsed');
      dg.dispatchEvent(new window.MouseEvent('click', { bubbles: true, cancelable: true }));
      const dgAfter = dg.getAttribute('data-collapsed');
      const catAfter = cat.getAttribute('data-collapsed');
      check('⑫ 日组点击切换自身折叠态', dgAfter !== dgBefore, 'before=' + dgBefore + ' after=' + dgAfter);
      check('⑫ 日组点击不误折叠父分类', catAfter === catBefore, 'cat before=' + catBefore + ' after=' + catAfter);
    } else {
      check('⑫ 日组点击切换自身折叠态', true, '当前数据无日组，跳过');
      check('⑫ 日组点击不误折叠父分类', true, '当前数据无日组，跳过');
    }
  } catch (e) { check('⑫ 日组点击', false, e.message); }
  // ⑫b 矿权结果摘要不计入「今日新增」：顶部 newCount 须等于 NEWS_DATA.stats.new_count
  try {
    const newCountEl = doc.getElementById('newCount');
    const newCount = newCountEl ? parseInt(newCountEl.textContent, 10) : -1;
    const rsItems = doc.querySelectorAll('#todaySection .news-item[data-rights-summary]');
    let rsHasNew = 0;
    rsItems.forEach(el => { if (el.classList.contains('is-new')) rsHasNew++; });
    check('⑫ 矿权摘要条不带 is-new 角标', rsHasNew === 0, '误带=' + rsHasNew + ' 条');
    const statNew = (window.NEWS_DATA && window.NEWS_DATA.stats) ? window.NEWS_DATA.stats.new_count : null;
    if (typeof statNew === 'number') {
      check('⑫ 顶部今日新增数 = 简报收录数（new_count）', newCount === statNew, '顶部=' + newCount + ' 简报=' + statNew);
    } else {
      const isNew = doc.querySelectorAll('#todaySection .news-item.is-new:not([data-rights-summary])').length;
      check('⑫ 今日新增数 = 今日区 is-new（不含矿权摘要）', newCount === isNew, '顶部=' + newCount + ' is-new=' + isNew);
    }
  } catch (e) { check('⑫ 今日新增计数口径', false, e.message); }

  console.log('\n===== JS 运行时错误 =====');
  const real = errors.filter(e => !/api\/hot-news|api\/ai-analyze|GoatCounter|gc\.zcounter|Failed to fetch|NetworkError/i.test(e));
  check('无阻塞性 JS 错误', real.length === 0, real.slice(0, 3).join(' | '));

  console.log('\n===== 汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 2500);
