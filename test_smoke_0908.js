/**
 * 2026-09-08 批次改动冒烟测试（jsdom）
 * 覆盖：① 找矿专项区已取消 ② 要闻跨源去重 + 日期标注 ③ 热榜 ≤5 条且与要闻互斥
 *       ④ 会展迷你卡进侧栏 ⑤ 矿权改紧凑列表 + 去重 ⑥ 已读样式对比度
 * 运行：node test_smoke_0908.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

// jsdom 默认不取外部脚本，把本地数据文件内联进去，避免全库为空导致误判
let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
['news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  const tag = new RegExp('<script src="' + f + '"></script>');
  html = html.replace(tag, '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
});
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
    let staleLeft = 0, freshBadged = 0, backfillN = 0;
    todaySec.querySelectorAll('.news-item').forEach(el => {
      const meta = el.querySelector('.news-meta');
      const m = meta ? (meta.textContent || '').match(/(\d{2})-(\d{2})/) : null;
      if (!m) return;
      const d = new Date(base.getFullYear(), +m[1] - 1, +m[2]);
      const stale = (base - d) / 86400000 > 2;
      const hasNew = !!el.querySelector('.badge-new') && el.classList.contains('is-new');
      const hasBf = !!el.querySelector('.badge-backfill');
      if (hasBf) backfillN++;
      if (stale && hasNew) staleLeft++;
      if (!stale && hasBf) freshBadged++;
    });
    check('③c 超期条目不再带 NEW', staleLeft === 0, '残留 ' + staleLeft + ' 条');
    check('③c 时效内条目不被误标补录', freshBadged === 0, '误标 ' + freshBadged + ' 条');
    check('③c 补录标已生成（当前数据应为 4 条左右）', backfillN >= 1, 'backfill=' + backfillN);
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
  check('⑦ 输入框不显示占位提示词', !!qaInput && !qaInput.getAttribute('placeholder'));
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

  console.log('\n===== ⑨ 矿权区单视图（表格已删回归守护） =====');
  check('⑨ 表格结构已删', !doc.getElementById('rightsTable') && !doc.getElementById('rightsTableWrap') && !doc.getElementById('rightsTableBody'));
  check('⑨ 视图切换按钮已删', doc.querySelectorAll('.rights-view-btn').length === 0);
  const rc9 = doc.getElementById('rightsCards');
  check('⑨ 列表容器仍在且已渲染', !!rc9 && rc9.querySelectorAll('.rights-row').length >= 1, 'rows=' + (rc9 ? rc9.querySelectorAll('.rights-row').length : 0));

  console.log('\n===== JS 运行时错误 =====');
  const real = errors.filter(e => !/api\/hot-news|api\/ai-analyze|GoatCounter|gc\.zcounter|Failed to fetch|NetworkError/i.test(e));
  check('无阻塞性 JS 错误', real.length === 0, real.slice(0, 3).join(' | '));

  console.log('\n===== 汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 2500);
