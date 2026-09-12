/**
 * 2026-09-10 手机端 UX 批量优化验证（jsdom）
 * 覆盖：① 热榜手机 10 条 / 桌面 5 条  ② 往期字号（CSS，字符串断言）
 *       ③+④ 推荐不显示价格、价格仅价格 tab  ⑤ 问按钮发光球（CSS 断言）
 *       ⑥ 问答全屏 + 返回箭头  ⑧ 我的面板独立全屏页（仅四项）  ⑨ 会议 tab + 区块注入
 *       ⑮ AI 搜面板：彩色 Ai 图标 / 窄屏全屏（形态隔离，清桌面内联记忆）/ 顶栏⋯菜单 / 空态推荐检索词
 *          —— 2026-09-12 用户定夺；同轮把 2026-09-11「禁止渐变」的旧约定作废（脉冲禁令保留）
 *       ⑩ 顶栏智能吸顶：隐藏只做 transform，不得折叠布局（2026-09-11 P0）
 *       ⑯ 顶栏瘦身(58->44px) / 输入区统一 38px 不折行 / 检索后滚动落点（2026-09-12 用户体验三条）
 *       ⑰ AI 搜六条体验增强（2026-09-12 用户续提）：① 取消保留已流式内容+重新生成 ② 返回补「我的」闭环
 *          ③ 手机顶栏下拉关闭 ④ 桌面 Esc 关闭+焦点归位 ⑤ 网络失败明确提示+重试 ⑥ 取消按钮无障碍 aria-label
 * 运行：node test_mobile_ux_batch.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
['news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  const tag = new RegExp('<script src="' + f + '"[^>]*></script>');
  html = html.replace(tag, () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
});
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
    if (typeof win.matchMedia !== 'function') {
      win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    }
    if (typeof win.fetch !== 'function') win.fetch = () => Promise.reject(new Error('jsdom: fetch stub'));
    // 手机视口（≤768 → 走移动端分支）
    try { Object.defineProperty(win, 'innerWidth', { value: 375, configurable: true, writable: true }); } catch (e) {}
    win.addEventListener('error', e => errors.push('window.error: ' + e.message));
    const oe = win.console.error;
    win.console.error = (...a) => { errors.push('console.error: ' + a.join(' ')); };
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
  console.log('===== ① 热榜：手机 10 条 / 桌面 5 条 =====');
  check('mdHotCount 在手机返回 10', window.mdHotCount() === 10, 'mdHotCount=' + window.mdHotCount());
  const hotMobile = doc.querySelectorAll('#hotListBody li.hot-item').length;
  check('手机热榜渲染 10 条', hotMobile === 10, '实际 ' + hotMobile + ' 条');
  // 切桌面重算
  Object.defineProperty(window, 'innerWidth', { value: 1280, configurable: true, writable: true });
  try { window.renderHotPage(); } catch (e) {}
  check('mdHotCount 在桌面返回 5', window.mdHotCount() === 5, 'mdHotCount=' + window.mdHotCount());
  const hotDesktop = doc.querySelectorAll('#hotListBody li.hot-item').length;
  check('桌面热榜渲染 5 条', hotDesktop === 5, '实际 ' + hotDesktop + ' 条');
  Object.defineProperty(window, 'innerWidth', { value: 375, configurable: true, writable: true });

  console.log('\n===== ② 往期/今日字号加大（CSS 字符串断言）=====');
  check('移动端 .news-title 字号上调到 16px', /\.news-title\{font-size:16px;line-height:1\.45\}/.test(html));
  check('移动端 .news-summary 字号上调到 14px', /\.news-summary\{font-size:14px;line-height:1\.55/.test(html));
  check('news-item 间距收紧（margin-bottom:--s2）', /\.news-item\{[^}]*margin-bottom:var\(--s2\)/.test(html));

  console.log('\n===== ③+④ 推荐不显示金属价格；价格仅价格 tab（CSS 断言）=====');
  // tuijian 展示规则中不应再包含 #priceStrip
  check('tuijian 展示规则已移除 #priceStrip', !/data-md-cat="tuijian"[^}]*#priceStrip/.test(html));
  check('price tab 展示规则保留 #priceStrip', /data-md-cat="price"[^}]*#priceStrip\{display:block!important\}/.test(html));
  check('安装引导整段在手机隐藏', /#installGuideSection\{display:none!important\}/.test(html));

  console.log('\n===== ⑤ 问按钮：与其它 tab 一致的平铺样式（无渐变/发光/脉冲）=====');
  check('问 tab 改为平铺一致样式（单一品牌色）', /\.mtab\[data-go="qa"\]\{color:var\(--brand\)\}/.test(html));
  check('问 tab 不再使用渐变发光球', !/\.mtab\[data-go="qa"\] \.mi\{[^}]*qaOrbPulse/.test(html));
  check('发光脉冲动画 keyframes 已移除', !/@keyframes qaOrbPulse\{/.test(html));

  console.log('\n===== ⑥ 问答全屏 + 返回箭头 =====');
  check('手机端问答面板 100vw/100dvh 全屏', /#qaFloat\{top:0;left:0;right:auto;bottom:auto;width:100vw;height:100dvh/.test(html));
  check('进入动画 keyframes 存在', /@keyframes qaFloatIn\{/.test(html));
  const cb = doc.querySelector('#qaFloat .pchart-close');
  check('手机端关闭按钮改为返回箭头 ‹', !!cb && cb.textContent === '‹', cb ? ('glyph=' + cb.textContent) : '无按钮');

  console.log('\n===== ⑧ 我的面板：独立全屏设置页（仅四项） =====');
  const sheet = doc.getElementById('mineSheet');
  check('mineSheet 存在', !!sheet);
  check('阅读模式按钮已从我的面板删除', !!(sheet && !sheet.querySelector('[data-act="reading"]')));
  check('旧「安装到桌面」按钮已从我的面板删除', !!(sheet && !sheet.querySelector('[data-act="install"]')));
  check('「返回顶部」按钮已从我的面板删除', !!(sheet && !sheet.querySelector('[data-act="top"]')));
  check('mineMeta 已从我的面板删除', !!(sheet && !sheet.querySelector('#mineMeta')));
  check('有独立页头 .mine-header', !!(sheet && sheet.querySelector('.mine-header')));
  check('页头标题为「我的"', !!(sheet && sheet.querySelector('.mine-title') && sheet.querySelector('.mine-title').textContent === '我的'));
  check('页头有关闭按钮 data-act="close"', !!(sheet && sheet.querySelector('.mine-close[data-act="close"]')));
  const items = sheet ? sheet.querySelectorAll('.mine-item') : [];
  check('设置项共 3 个（收藏/历史/主题）', items.length === 3, '实际 ' + items.length);
  check('第一项：我的收藏', !!(items[0] && items[0].getAttribute('data-act') === 'fav'));
  check('第二项：浏览记录', !!(items[1] && items[1].getAttribute('data-act') === 'history'));
  check('第三项：深色/浅色（带状态标签）', !!(items[2] && items[2].getAttribute('data-act') === 'theme' && items[2].querySelector('#mineThemeState')));
  const card = doc.getElementById('mineInstallCard');
  check('安装到主屏幕卡片已注入', !!card, card ? ('内容片段=' + (card.textContent || '').slice(0, 18)) : '无');
  check('安装卡含系统识别提示', !!card && /主屏幕|安装/.test(card.textContent || ''));
  // 2026-09-12：浏览记录「清空」快捷按钮（手机 Mine 面板 + 桌面左侧目录共用）
  check('浏览记录行含「清空」按钮 data-act="clear-history"', !!(sheet && sheet.querySelector('.mine-clear[data-act="clear-history"]')));
  check('桌面左侧目录含「清空浏览记录」按钮 .toc-clear', !!doc.querySelector('.toc-clear[data-act="clear-history"]'));
  // 功能：点「清空」应清掉浏览记录（localStorage HISTORY_KEY）
  try {
    window.localStorage.setItem('mining_daily_history', JSON.stringify([{url:'https://x.example/a',title:'测试条目',src:'X',time:new Date().toISOString()}]));
    const clr = sheet ? sheet.querySelector('.mine-clear[data-act="clear-history"]') : null;
    if (clr) {
      clr.dispatchEvent(new window.MouseEvent('click', { bubbles: true, cancelable: true }));
      const after = window.localStorage.getItem('mining_daily_history');
      check('点「清空」→ 浏览记录被清空（localStorage 已删除/空数组）', after === '[]' || after === null, 'after=' + after);
      const tc = doc.getElementById('tocHistoryCount');
      check('点「清空」→ 目录计数刷新为 0', !tc || tc.textContent === '0', tc ? ('count=' + tc.textContent) : '无计数');
    } else {
      check('点「清空」→ 浏览记录被清空', false, '找不到 .mine-clear');
    }
  } catch (e) {
    check('点「清空」→ 浏览记录被清空', false, '异常 ' + e.message);
  }
  // 行为：点底部「我的」tab 应添加 body.md-mine-open
  const mineTab = doc.querySelector('.mtab[data-go="mine"]');
  if (mineTab) {
    mineTab.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    check('点「我的」tab → body 添加 md-mine-open', doc.body.classList.contains('md-mine-open'));
    const closeBtn = sheet.querySelector('.mine-close');
    if (closeBtn) {
      closeBtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
      check('点关闭按钮 → body 移除 md-mine-open', !doc.body.classList.contains('md-mine-open'));
    }
  }

  console.log('\n===== ⑨ 会议 tab + 会议会展区块 =====');
  const mctabs = doc.querySelectorAll('#mdTop .mctab');
  check('顶部分类 Tab 共 4 个（含会议）', mctabs.length === 4, '实际 ' + mctabs.length);
  let hasMeeting = false;
  mctabs.forEach(t => { if (t.getAttribute('data-cat') === 'meeting') hasMeeting = true; });
  check('存在「会议」分类 tab', hasMeeting);
  check('会议会展区块已注入 DOM', !!doc.getElementById('meetingSection'));
  const rs = doc.getElementById('rightsSection');
  const ms = doc.getElementById('meetingSection');
  check('会议区块位于矿权区块之后（避开生成区）', !!(rs && ms && rs.compareDocumentPosition(ms) & window.Node.DOCUMENT_POSITION_FOLLOWING));
  const mItems = doc.querySelectorAll('#meetingSection .meeting-body .news-item').length;
  check('会议会展区块已抽取会展类新闻', mItems > 0, '实际 ' + mItems + ' 条');
  // 切到会议 tab
  try { window.mdSelectCat('meeting'); } catch (e) {}
  check('点击会议 tab 写入 body[data-md-cat=meeting]', doc.body.getAttribute('data-md-cat') === 'meeting');
  try { window.mdSelectCat('tuijian'); } catch (e) {}
  check('切回推荐写入 body[data-md-cat=tuijian]', doc.body.getAttribute('data-md-cat') === 'tuijian');

  console.log('\n===== ⑩ 顶栏智能吸顶：隐藏不得改动布局（2026-09-11 P0 修复）=====');
  const hidRule = (html.match(/body\.md-top-hidden #mdTop\{[^}]*\}/) || [''])[0];
  check('隐藏规则存在', hidRule.length > 0, hidRule.slice(0, 70));
  check('隐藏只做 transform 位移', /transform:translateY\(-100%\)/.test(hidRule));
  check('隐藏不再折叠布局（无 margin-bottom）', !/margin-bottom/.test(hidRule), hidRule.slice(0, 110));
  check('#mdTop 过渡不再含 margin-bottom', !/transition:[^;}]*margin-bottom/.test(html));
  check('隐藏时不可点（pointer-events:none）', /pointer-events\s*:\s*none/.test(hidRule));
  // 行为断言：滞后阈值 12px —— 小抖动不得来回切换
  let _sy = 0;
  try { Object.defineProperty(window, 'pageYOffset', { get: () => _sy, configurable: true }); } catch (e) {}
  try { Object.defineProperty(doc.documentElement, 'scrollHeight', { get: () => 3000, configurable: true }); } catch (e) {}
  try { Object.defineProperty(window, 'innerHeight', { value: 700, configurable: true, writable: true }); } catch (e) {}
  _sy = 0; window.mdTopOnScroll();
  const shownTop = !doc.body.classList.contains('md-top-hidden');
  _sy = 400; window.mdTopOnScroll();
  const hiddenDown = doc.body.classList.contains('md-top-hidden');
  _sy = 300; window.mdTopOnScroll();
  const shownUp = !doc.body.classList.contains('md-top-hidden');
  _sy = 295; window.mdTopOnScroll();
  const noFlick = !doc.body.classList.contains('md-top-hidden');
  check('顶部不隐藏', shownTop);
  check('下滚 400px 后隐藏', hiddenDown);
  check('上滑后重现', shownUp);
  check('5px 反向抖动不触发切换（12px 滞后）', noFlick);

  console.log('\n===== ⑪ 底部导航：首页改名 + 非首页 tab 隐藏顶部分类栏（2026-09-11 优化）=====');
  const homeTab = doc.querySelector('#mobileTabBar .mtab[data-go="home"]');
  check('底部主导航已注入（#mobileTabBar）', !!homeTab);
  const homeLabel = homeTab ? ((homeTab.querySelector('span:last-child') || {}).textContent || '') : '';
  check('底部首页 tab 标签为「首页」（原「推荐」已改名，避免与顶部分类重复）', homeLabel === '首页', '实际「' + homeLabel + '」');
  const topCats = doc.querySelectorAll('#mdTop .mctab');
  check('顶部分类栏仍有 4 个分类（推荐/热榜/往期/会议）', topCats.length === 4, '实际 ' + topCats.length);
  function clickGo(go){ const b = doc.querySelector('#mobileTabBar .mtab[data-go="' + go + '"]'); if (b) b.dispatchEvent(new window.Event('click', { bubbles: true })); }
  check('初始（首页）顶部分类栏可见（无 md-hide-catbar）', !doc.body.classList.contains('md-hide-catbar'));
  clickGo('price');
  check('点击价格 tab → 隐藏顶部分类栏（body.md-hide-catbar）', doc.body.classList.contains('md-hide-catbar'));
  check('隐藏规则 CSS 存在 body.md-hide-catbar .md-cat-bar{display:none}', /body\.md-hide-catbar \.md-cat-bar\{display:none\}/.test(html));
  clickGo('rights');
  check('点击矿权 tab → 隐藏顶部分类栏', doc.body.classList.contains('md-hide-catbar'));
  clickGo('qa');
  check('点击问 tab → 隐藏顶部分类栏', doc.body.classList.contains('md-hide-catbar'));
  clickGo('mine');
  check('点击我的 tab → 隐藏顶部分类栏', doc.body.classList.contains('md-hide-catbar'));
  clickGo('home');
  check('切回首页 tab → 恢复显示顶部分类栏', !doc.body.classList.contains('md-hide-catbar'));
  check('切回首页后 body[data-md-cat=tuijian]', doc.body.getAttribute('data-md-cat') === 'tuijian');

  console.log('\n===== ⑫ 底部导航增强：记住 tab + 品牌行 tab 名 + 检索统一进「AI 搜」面板（2026-09-11 优化①②③ / 09-12 决议）=====');
  function brandText(){ var b=doc.querySelector('#mdTop .md-brand'); return b?b.textContent:''; }
  function lsGet(k){ try{ return window.localStorage.getItem(k); }catch(e){ return null; } }
  clickGo('price');
  check('① 点价格 → 持久化 md_last_tab=price', lsGet('md_last_tab')==='price');
  check('③ 点价格 → 品牌行显示「价格」', brandText()==='价格', '实际「'+brandText()+'」');
  // 2026-09-12 检索统一（用户定夺）：顶栏搜索按钮已整体移除（DOM/绑定/mdOpenSearch/CSS 全清），
  //   检索能力统一由底部「AI 搜」面板承载 → 断言翻转为「必须不存在」。
  //   注意用 ^[ \t]* 锚定规则体行首，避开注释里提到的 .md-search-btn（曾两次踩到"匹配到注释"的坑）。
  check('② 顶栏搜索按钮 CSS 已清除（检索统一进「AI 搜」面板）', !/^[ \t]*\.md-search-btn\s*\{/m.test(html));
  check('③ 非首页隐藏日期 CSS 规则存在', /body\.md-hide-catbar \.md-date\{display:none\}/.test(html));
  clickGo('rights');
  check('③ 点矿权 → 品牌行显示「矿权」', brandText()==='矿权', '实际「'+brandText()+'」');
  clickGo('home');
  check('③ 回首页 → 品牌行恢复含「矿业新闻日报」', brandText().indexOf('矿业新闻日报')>=0, '实际「'+brandText()+'」');
  check('① 回首页 → md_last_tab=home', lsGet('md_last_tab')==='home');
  check('② 顶栏搜索按钮已从 DOM 移除', !doc.getElementById('mdSearchBtn'));
  check('② 未残留 md-search-open 生效规则', !/^[ \t]*body\.md-search-open\b/m.test(html));
  check('② 桌面检索条 #newsFilterBar 在移动端仍隐藏', /#newsFilterBar\{position:fixed/.test(html) && /#newsFilterBar\{position:fixed[^}]*display:none/.test(html));

  console.log('\n===== ⑬ 刷新红条误报修复：启动宽限期内不报整页降级（2026-09-11 体验修复）=====');
  check('mdDegraded 是函数', typeof window.mdDegraded === 'function');
  check('启动宽限标志 __mdBootGrace 已声明', 'undefined' !== typeof window.__mdBootGrace);
  // 模拟「app.js 尚未求值」的刷新加载窗口：宽限期内 mdDegraded 必须返回空串（不闪红条）
  var _ev = window.__mdAppEvaluated, _gr = window.__mdBootGrace;
  try { window.__mdAppEvaluated = false; window.__mdBootGrace = false; } catch (e) {}
  check('宽限期内（未求值）mdDegraded 返回空串 → 不挂红条', window.mdDegraded() === '', 'mdDegraded=' + JSON.stringify(window.mdDegraded()));
  // 宽限期内即便 mdSyncBanner 被 1.2s 自愈轮次调用，error 红条也不应出现
  try { window.mdSyncBanner(); } catch (e) {}
  var _warn = doc.getElementById('mdBootWarn');
  check('宽限期内 mdSyncBanner 不显示 error 红条', !(_warn && _warn.getAttribute('data-md-level') === 'error' && _warn.style.display === 'flex'));
  // 宽限期结束后仍为「未求值」才判整页降级（真实故障检测不丢）
  try { window.__mdBootGrace = true; } catch (e) {}
  check('宽限期后仍未求值 → 判定整页降级（app.js 未执行）', window.mdDegraded() === 'app.js 未执行', 'mdDegraded=' + JSON.stringify(window.mdDegraded()));
  // 还原：app 已求值 → 必为健康
  try { window.__mdAppEvaluated = _ev; window.__mdBootGrace = _gr; } catch (e) {}
  check('app 已求值 → mdDegraded 返回空串（健康）', window.mdDegraded() === '');

  console.log('\n===== ⑭ 区块宽限：加载窗口内不误报「部分区块未加载」（2026-09-11 二次体验修复）=====');
  check('区块宽限标志 __mdRegionGrace 已声明', 'undefined' !== typeof window.__mdRegionGrace);
  var _hotBody = doc.getElementById('hotListBody');
  var _hotHtml = _hotBody ? _hotBody.innerHTML : null;
  // 模拟「热榜异步渲染尚未完成」：容器仍是占位符（fetchHotNews 先 fetch 再退回本地，本就会晚于自愈轮次）
  try { if (_hotBody) _hotBody.textContent = '加载中…'; } catch (e) {}
  var _rg = window.__mdRegionGrace;
  try { window.__mdRegionGrace = false; } catch (e) {}
  check('宽限期内：区块未渲染也不判「卡住」（mdStuckRegions 为空）', window.mdStuckRegions().length === 0, 'len=' + window.mdStuckRegions().length);
  try { window.mdSyncBanner(); } catch (e) {}
  var _w2 = doc.getElementById('mdBootWarn');
  check('宽限期内 mdSyncBanner 不挂「部分区块未加载」info 条', !(_w2 && _w2.getAttribute('data-md-level') === 'info' && /部分区块未加载/.test(_w2.textContent)));
  try { window.__mdRegionGrace = true; } catch (e) {}
  check('宽限期后：仍未渲染 → 判为卡住（热榜）', window.mdStuckRegions().length >= 1, 'len=' + window.mdStuckRegions().length);
  // 还原
  try { window.__mdRegionGrace = _rg; if (_hotBody && _hotHtml !== null) _hotBody.innerHTML = _hotHtml; } catch (e) {}

  console.log('\n===== ⑮ 「AI 搜」面板：彩色 Ai 图标 / 窄屏全屏形态隔离 / 顶栏⋯菜单 / 空态推荐检索词（2026-09-12）=====');
  // ---- 图标：彩色渐变 Ai（用户定夺，作废 2026-09-11「单色描边」旧约定；脉冲禁令保留）----
  check('底栏 AI 搜图标改为彩色渐变 Ai（SVG 内置 linearGradient）', /<linearGradient id="qaAiGrad"/.test(html));
  check('渐变只作用于图标本身（方块 fill=url(#qaAiGrad)，不依赖 currentColor）', /<rect x="1" y="1" width="22" height="22" rx="6\.5" fill="url\(#qaAiGrad\)"\/>/.test(html));
  check('图标内含白色「Ai」字', /(?:text|tspan)[^>]*>Ai<\/text>/.test(html));
  check('底栏 AI 搜文字标签保留', /data-go="qa"[^>]*>[\s\S]{0,120}<span>AI 搜<\/span>/.test(html));
  check('呼吸脉冲 keyframes 仍不存在（旧禁令保留，不许回退）', !/@keyframes qaOrbPulse\{/.test(html));
  check('底栏 qa tab 仍持品牌色（色由文字标签承载）', /\.mtab\[data-go="qa"\]\{color:var\(--brand\)\}/.test(html));

  // ---- 顶栏三栏化：‹ 返回 / AI 搜 / ⋯（CSS 断言）----
  check('桌面：‹ 返回键默认隐藏', /\.qa-float-head \.qa-back\{display:none/.test(html));
  check('窄屏：‹ 返回键显示', /\.qa-float-head \.qa-back\{display:inline-flex\}/.test(html));
  check('桌面：⋯ 菜单键隐藏', /\.qa-float-head \.qa-head-menu-btn\{display:none/.test(html));
  check('窄屏：⋯ 菜单键显示', /\.qa-float-head \.qa-head-menu-btn\{display:inline-flex\}/.test(html));
  check('窄屏：导出/清空平铺按钮收起（收进 ⋯）', /\.qa-float-head \.qa-act-export,\.qa-float-head \.qa-act-clear\{display:none\}/.test(html));
  check('窄屏：原 ✕ 让位给 ‹（隐藏）', /\.qa-float-head \.pchart-close\{display:none\}/.test(html));
  check('窄屏：标题居中占满中间列', /\.qa-float-head \.qa-float-title\{flex:1;text-align:center/.test(html));
  check('⋯ 菜单列表 [hidden] 时不渲染', /\.qa-head-menu-list\[hidden\]\{display:none\}/.test(html));
  check('⋯ 菜单列表是绝对定位浮层（不挤压顶栏）', /\.qa-head-menu-list\{position:absolute/.test(html));
  check('⋯ 菜单有暗色适配', /body\.dark \.qa-head-menu-list\{/.test(html));

  // ---- 空态推荐检索词（CSS）----
  check('空态推荐词容器样式存在', /\.qa-sug-cards\{/.test(html) && /\.qa-sug-tip\{/.test(html));

  // ---- 形态隔离：窄屏全屏、桌面可拖拽（行为断言，这是「手机上打开是半屏卡片」的修复）----
  var _panel = doc.getElementById('qaFloat');
  check('qaFloatIsMobile / qaFloatSyncViewport / qaFloatClearInlineLayout 已导出',
        typeof window.qaFloatIsMobile === 'function' && typeof window.qaFloatSyncViewport === 'function' && typeof window.qaFloatClearInlineLayout === 'function');
  check('qaFloatIsMobile 在 375 宽为真', window.innerWidth === 375 && window.qaFloatIsMobile() === true, 'w=' + window.innerWidth);

  // 伪造「桌面拖拽/缩放留下的记忆」，再切桌面 → 应恢复内联尺寸/定位（桌面形态不被破坏）
  Object.defineProperty(window, 'innerWidth', { value: 1280, configurable: true, writable: true });
  check('qaFloatIsMobile 在 1280 宽为假', window.qaFloatIsMobile() === false);
  try {
    window.localStorage.setItem('qaFloatPos', JSON.stringify({ left: 40, top: 320 }));
    window.localStorage.setItem('qaFloatSize', JSON.stringify({ width: 440, height: 560 }));
  } catch (e) {}
  window.qaFloatSyncViewport();
  check('桌面：按记忆恢复内联尺寸', _panel.style.width === '440px' && _panel.style.height === '560px',
        'w=' + JSON.stringify(_panel.style.width) + ' h=' + JSON.stringify(_panel.style.height));
  var _expTop = Math.min(320, Math.max(window.innerHeight - 560, 0));
  check('桌面：按记忆恢复内联定位（越界时收敛在视口内）',
        _panel.style.left === '40px' && _panel.style.top === _expTop + 'px',
        'l=' + JSON.stringify(_panel.style.left) + ' t=' + JSON.stringify(_panel.style.top) + '  期望 top=' + _expTop + 'px');

  // 切回手机 → 必须清掉内联尺寸/定位，交还媒体查询的全屏规则（★ 本轮核心修复）
  Object.defineProperty(window, 'innerWidth', { value: 375, configurable: true, writable: true });
  window.qaFloatSyncViewport();
  check('★ 手机：清掉内联尺寸（修复「顶着屏幕中部的半屏卡片」）',
        _panel.style.width === '' && _panel.style.height === '',
        'w=' + JSON.stringify(_panel.style.width) + ' h=' + JSON.stringify(_panel.style.height));
  check('★ 手机：清掉内联定位（top/left/right/bottom/position 全清）',
        _panel.style.left === '' && _panel.style.top === '' && _panel.style.position === '' && _panel.style.right === '' && _panel.style.bottom === '',
        'l=' + JSON.stringify(_panel.style.left) + ' t=' + JSON.stringify(_panel.style.top) + ' pos=' + JSON.stringify(_panel.style.position));

  // 反向污染：手机全屏尺寸不得被写回桌面记忆（否则桌面打开又变全屏）
  window.qaFloatSaveSize(); window.qaFloatSavePos();
  var _szSaved = null, _posSaved = null;
  try { _szSaved = window.localStorage.getItem('qaFloatSize'); _posSaved = window.localStorage.getItem('qaFloatPos'); } catch (e) {}
  check('★ 手机：不写回桌面记忆（防反向污染）',
        _szSaved === JSON.stringify({ width: 440, height: 560 }) && _posSaved === JSON.stringify({ left: 40, top: 320 }),
        'size=' + _szSaved + ' pos=' + _posSaved);

  // 手机恒全屏 → 不挂缩放柄、缩放入口失效（否则全屏被拖坏）
  try { window.qaFloatAddResizeHandles(); } catch (e) {}
  check('★ 手机：不挂缩放柄', doc.querySelectorAll('#qaFloat .qa-resize-handle').length === 0,
        'n=' + doc.querySelectorAll('#qaFloat .qa-resize-handle').length);
  var _resizeBail = false;
  try { _resizeBail = (window.qaFloatStartResize({ target: { closest: function () { return null; } } }) === undefined); } catch (e) { _resizeBail = false; }
  check('★ 手机：缩放入口直接返回（不进入拖拽逻辑）', _resizeBail);
  try { window.localStorage.removeItem('qaFloatPos'); window.localStorage.removeItem('qaFloatSize'); } catch (e) {}

  // 跨断点监听已挂上（横竖屏切换 / 拖动窗口时会重新分流）
  check('已注册 resize → qaFloatSyncViewport', /addEventListener\('resize',\s*function\s*\(\)\s*\{\s*qaFloatSyncViewport\(\);\s*\}\)/.test(html));

  // ---- 顶栏 DOM 结构 ----
  var _back = doc.querySelector('#qaFloat .qa-back');
  check('顶栏 ‹ 返回键已注入 DOM', !!_back);
  check('‹ 返回键承载返回语义（onclick 调 qaFloatBack）', !!_back && /qaFloatBack/.test(_back.getAttribute('onclick') || ''));
  check('首次打开手机 AI 搜面板不自动聚焦输入框（源码含 innerWidth>768 才 focus）',
        /if\(i&&window\.innerWidth>768\)setTimeout\(function\(\)\{i\.focus\(\);\},80\)/.test(html));
  // 行为：从首页进 AI 搜，点返回应回到首页，而不是继续停在 AI 搜
  function activeGo(){ var b=doc.querySelector('#mobileTabBar .mtab.active'); return b?b.getAttribute('data-go'):null; }
  function clickGo(go){ var b=doc.querySelector('#mobileTabBar .mtab[data-go="'+go+'"]'); if(b) b.dispatchEvent(new window.Event('click',{bubbles:true})); }
  clickGo('home');
  var _beforeGo = activeGo()||'home';
  clickGo('qa');
  check('点 AI 搜 tab 打开面板并高亮 qa', _panel.classList.contains('open') && activeGo()==='qa');
  if(_back){ try{ _back.click(); }catch(e){} }
  check('点返回后回到之前的内容 tab（且恢复顶部分类栏）', activeGo()===_beforeGo && !doc.body.classList.contains('md-hide-catbar'),
        'before=' + _beforeGo + ' after=' + activeGo() + ' catbarHidden=' + doc.body.classList.contains('md-hide-catbar'));
  var _menu = doc.getElementById('qaHeadMenu');
  var _menuList = doc.getElementById('qaHeadMenuList');
  check('顶栏 ⋯ 菜单键已注入（id=qaHeadMenu）', !!_menu);
  check('⋯ 菜单键声明 aria-haspopup / aria-expanded', !!_menu && _menu.getAttribute('aria-haspopup') === 'true' && _menu.getAttribute('aria-expanded') === 'false');
  check('⋯ 菜单列表默认隐藏（hidden 属性）', !!_menuList && _menuList.hasAttribute('hidden'));
  check('⋯ 菜单含 2 项（导出全部对话 / 清空会话历史）', !!_menuList && _menuList.querySelectorAll('button').length === 2,
        '实际 ' + (_menuList ? _menuList.querySelectorAll('button').length : -1));
  check('⋯ 菜单项绑定 window.qaMenuExport / window.qaMenuClear',
        typeof window.qaMenuExport === 'function' && typeof window.qaMenuClear === 'function');
  var _a1 = (_menuList ? _menuList.querySelectorAll('button')[0].getAttribute('onclick') : '') || '';
  var _a2 = (_menuList ? _menuList.querySelectorAll('button')[1].getAttribute('onclick') : '') || '';
  check('菜单项 1 = 导出（qaMenuExport）', /qaMenuExport/.test(_a1), _a1);
  check('菜单项 2 = 清空（qaMenuClear）', /qaMenuClear/.test(_a2), _a2);

  // 展开 / 收起（含 aria 状态回写）
  window.qaHeadMenuToggle();
  check('qaHeadMenuToggle 展开菜单', !!_menuList && !_menuList.hasAttribute('hidden'));
  check('展开后 aria-expanded=true', !!_menu && _menu.getAttribute('aria-expanded') === 'true');
  window.qaHeadMenuClose();
  check('qaHeadMenuClose 收起菜单', !!_menuList && _menuList.hasAttribute('hidden'));
  check('收起后 aria-expanded=false', !!_menu && _menu.getAttribute('aria-expanded') === 'false');
  check('qaFloatToggle 打开面板时自动收起 ⋯ 菜单（避免残留浮层）', /if\(open\)\{[\s\S]{0,200}qaHeadMenuClose\(\);/.test(html));

  // ---- 空态推荐检索词（行为断言）----
  var _sugs = window.qaSuggestQueries();
  check('qaSuggestQueries 产出 3-5 个高命中词（不凭想象造词）', _sugs.length >= 3 && _sugs.length <= 5,
        'n=' + _sugs.length + ' → ' + _sugs.join('/'));
  var _body = doc.getElementById('qaFloatBody');
  try { _body.innerHTML = ''; } catch (e) {}
  window.qaFloatRenderSuggest();
  check('空态渲染出推荐检索词 chips', doc.querySelectorAll('#qaFloatBody .qa-sug').length >= 3,
        'n=' + doc.querySelectorAll('#qaFloatBody .qa-sug').length);
  check('推荐词带「试试这些检索词」引导', !!doc.querySelector('#qaFloatBody .qa-sug-tip'));
  var _chip = doc.querySelector('#qaFloatBody .qa-sug');
  check('推荐词 chip 可点（role=button + tabindex + onclick）',
        !!_chip && _chip.getAttribute('role') === 'button' && _chip.getAttribute('tabindex') === '0' && /qaSugQuery/.test(_chip.getAttribute('onclick') || ''));
  var _chipQ = _chip ? _chip.getAttribute('data-q') : null;
  var _nBefore = doc.querySelectorAll('#qaFloatBody .qa-msg.user').length;
  if (_chip) { try { window.qaSugQuery(_chip); } catch (e) {} }
  var _users = doc.querySelectorAll('#qaFloatBody .qa-msg.user');
  check('点推荐词 → 发起检索（生成用户消息）', _users.length === _nBefore + 1, 'userMsgs=' + _users.length);
  var _lastTxt = _users.length ? (_users[_users.length - 1].textContent || '') : '';
  check('检索词已作为检索条件提交', !!_chipQ && _lastTxt.indexOf(_chipQ) >= 0, 'chip=' + _chipQ + ' msg=' + _lastTxt.slice(0, 40));
  check('检索后收起推荐引导（不残留在答案下方）', doc.querySelectorAll('#qaFloatBody .qa-sug').length === 0,
        'left=' + doc.querySelectorAll('#qaFloatBody .qa-sug').length);
  check('清空会话后推荐词回归（qaClearHistory 末尾重渲染）', /function qaClearHistory\(\)\{[\s\S]{0,400}qaFloatRenderSuggest\(\);/.test(html));
  check('推荐词只在完全空态渲染（有历史时不打扰会话）', /if\(!fb\.children\.length\)\{[\s\S]{0,200}qaFloatRenderSuggest\(\);/.test(html));

  Object.defineProperty(window, 'innerWidth', { value: 375, configurable: true, writable: true });

  console.log('\n===== ⑯ 顶栏厚度 / 输入区形态 / 检索后滚动落点（2026-09-12）=====');
  // 用户反馈三条：① 顶栏太厚 ② 底部输入区折行、三种高度很难看 ③ 检索后跳到回答末尾要往回翻
  check('顶栏瘦身：竖向 padding 6px（整条 58px -> 44px）',
        /\.qa-float-head\{position:relative;display:flex;align-items:center;justify-content:space-between;padding:6px var\(--s3\);/.test(html));
  check('顶栏瘦身：窄屏顶部安全区同步为 6px',
        /\.qa-float-head\{padding-top:calc\(6px \+ env\(safe-area-inset-top,0px\)\)\}/.test(html));
  check('顶栏瘦身：‹ 返回键 32px（原 34px）',
        /\.qa-float-head \.qa-back\{display:none;[^}]*width:32px;height:32px;/.test(html));
  check('顶栏瘦身：⋯ 菜单键显式 height:32px（与返回键等高）',
        /\.qa-float-head \.qa-head-menu-btn\{display:none;[^}]*height:32px;padding:0 var\(--s2\)/.test(html));
  check('顶栏瘦身：桌面 ✕ 32px（压过 601px 断点的 34px）',
        /\.qa-float-head \.pchart-close\{width:32px;height:32px;/.test(html));

  check('输入区：foot 垂直居中（align-items:center）',
        /\.qa-float-foot\{position:relative;z-index:3;display:flex;align-items:center;gap:var\(--s2\);padding:var\(--s3\);/.test(html));
  check('输入区：输入框允许收缩 + 固定 38px + 胶囊圆角',
        /\.qa-float-input\{position:relative;z-index:4;flex:1 1 auto;min-width:0;height:38px;border:1px solid #dbe2ea;border-radius:19px;padding:0 var\(--s3\)/.test(html));
  check('输入区：按钮 flex:0 0 auto + nowrap + 38px（永不折成两行）',
        /\.qa-float-btn\{position:relative;z-index:4;flex:0 0 auto;[^}]*height:38px;white-space:nowrap;/.test(html));
  check('输入区：麦克风 38px 圆形（原 34px 方角）',
        /\.qa-mic\{padding:0;width:38px;height:38px;border-radius:50%\}/.test(html));
  check('输入区：AI 按钮 min-width 防「思考中…」抖动',
        /\.qa-float-btn\.primary\{background:var\(--tag-strategy\);color:#fff;min-width:78px\}/.test(html));
  var _qInp2 = doc.getElementById('qaFloatInput');
  check('输入区：占位提示已加（2026-09-12 反转「不放占位词」旧约定，<=12 字）',
        !!_qInp2 && !!_qInp2.getAttribute('placeholder') && _qInp2.getAttribute('placeholder').length <= 12,
        String(_qInp2 && _qInp2.getAttribute('placeholder')));
  check('输入区：仍保留 aria-label（可访问性不回退）',
        !!_qInp2 && !!_qInp2.getAttribute('aria-label'));
  check('筛选行：竖向 padding 收紧为 --s2（103px -> 95px）',
        /\.qa-float-filters\{display:flex;flex-wrap:wrap;gap:var\(--s2\);padding:var\(--s2\) var\(--s3\);/.test(html));

  console.log('  ---- 检索后滚动落点（问题 ③）----');
  check('落点：新增 qaFloatNearBottom / qaFloatFollow / qaFloatAnchorTop / qaFloatSettle 并导出',
        typeof window.qaFloatNearBottom === 'function' && typeof window.qaFloatFollow === 'function'
        && typeof window.qaFloatAnchorTop === 'function' && typeof window.qaFloatSettle === 'function'
        && typeof window.qaFloatAnchorLastQuestion === 'function');
  check('落点：★ qaFloatAdd 不再无条件滚到底（旧写法必须已删）',
        !/body\.appendChild\(d\);qaFloatScroll\(\);/.test(html)
        && /if\(opts\.anchorTop\)qaFloatAnchorTop\(d\);/.test(html)
        && /else if\(!opts\.keepScroll\)qaFloatFollow\(\);/.test(html));
  check('落点：检索/提问的「问题」带 anchorTop（钉到顶部）',
        (html.match(/anchorTop:true/g) || []).length >= 2,
        'n=' + (html.match(/anchorTop:true/g) || []).length);
  check('落点：答案/检索结果带 keepScroll（不把问题顶走）',
        /\{html:true,keepScroll:true\}/.test(html));
  check('落点：★ 答完不再甩到底部（收尾改 qaFloatSettle）',
        /qaFloatSettle\(\);qaSaveHistory\(\),?/.test(html) && !/qaFloatScroll\(\);qaSaveHistory\(\);/.test(html));
  check('落点：检索完成也走 qaFloatSettle',
        /qaFloatAdd\('ai',html,'全库 '\+QA_ROWS\.length\+' 条 · 检索于本地，不经任何服务',\{html:true,keepScroll:true\}\);\s*try\{qaFloatSettle\(\);\}/.test(html));
  check('落点：恢复历史后停在最后一条提问（与刚检索完一致）',
        /qaFloatAnchorLastQuestion\(\);\s*\}catch\(e\)\{\}/.test(html));
  check('落点：qaFloatScroll 仅剩「定义 + 空态引导」两处（其余已改跟随/锚定）',
        (html.match(/qaFloatScroll\(\)/g) || []).length === 2,
        'n=' + (html.match(/qaFloatScroll\(\)/g) || []).length);
  check('落点：qaFloatSettle 只在「问题落到下半屏」时才动（0.4*clientHeight）',
        /if\(off>h\*0\.4 && off<h\)qaFloatAnchorTop\(q\);/.test(html));

  console.log('\n===== ⑰ AI 搜六条体验增强（2026-09-12 用户续提）=====');
  check('① 取消：保留已流式内容 + 重新生成按钮（qa-cancel-foot / qaFloatReask）',
        html.includes("'qa-cancel-foot'") && html.includes("window.qaFloatReask&&window.qaFloatReask()") && html.includes("已取消生成"));
  check('② 返回：从「我的」进 AI 搜，返回重新打开「我的」覆盖层（mdQaReturn）',
        html.includes("var mdQaReturn='home'") && html.includes("md-mine-open') ? 'mine' : mdLastContentTab") && html.includes("if(_t==='mine'){ try{ activateTab('mine', true);"));
  check('③ 手势：手机顶栏下拉关闭面板（mdQaBindSwipe + translateY 反馈）',
        html.includes('function mdQaBindSwipe(') && html.includes('mdQaBindSwipe();') && html.includes("translateY('+Math.min(dy*0.4,40)+'px)'"));
  check('④ Esc：桌面端 Escape 关闭浮层并聚焦 #qaFab（mdQaBindKeys）',
        html.includes('function mdQaBindKeys(') && html.includes('mdQaBindKeys();') && html.includes("e.key!=='Escape'") && html.includes('fab.focus()'));
  check('⑤ 网络失败：明确失败条 + 重新生成（qaFloatShowNetFail / .qa-net-fail）',
        html.includes('function qaFloatShowNetFail(') && html.includes("'qa-net-fail'") && (html.match(/qaFloatShowNetFail\(msg,q\)/g)||[]).length >= 2 && /\.qa-net-fail\{/.test(html));
  check('⑥ 无障碍：取消按钮 aria-label 切换（取消生成 / AI 回答）',
        /id="qaFloatAi"[^>]*aria-label="AI 回答"/.test(html) && html.includes("btn.setAttribute('aria-label','取消生成')") && html.includes("btn.setAttribute('aria-label','AI 回答')"));

  console.log('\n===== ⑱ 收藏/浏览记录沉浸式视图（2026-09-12 用户反馈）=====');
  check('① 顶栏/右栏隐藏：fav/history 下 #mdTop 与 .col-rail 均 display:none!important',
        html.includes('body[data-filter-mode="fav"] #mdTop,') && html.includes('body[data-filter-mode="history"] #mdTop,') && html.includes('body[data-filter-mode="fav"] .col-rail,') && /\.col-rail\{display:none!important\}/.test(html));
  check('② 单栏：fav/history .news-grid 改为 minmax(0,1fr) 单列（右栏不再占位）',
        html.includes('body[data-filter-mode="history"] .news-grid{grid-template-columns:minmax(0,1fr);gap:var(--s5)}'));
  check('③ 沉浸式返回条：#favViewBar / #favViewTitle / data-act="fav-back" 存在',
        html.includes('id="favViewBar"') && html.includes('id="favViewTitle"') && html.includes('data-act="fav-back"'));
  check('④ 同步函数：mdSyncFavViewBar 定义且在 setFilter 内被调用',
        html.includes('function mdSyncFavViewBar(mode)') && html.includes('mdSyncFavViewBar(mode);'));
  check('⑤ 清空按钮：仅在浏览记录显示（.favview-clear + data-act="clear-history" 在返回条内）',
        html.includes('class="favview-clear" type="button" data-act="clear-history"'));
  let _syncOk=false,_tH='',_cH='',_tF='',_cF='';
  try{
    if(typeof window.setFilter==='function'){
      window.setFilter('history');
      var _bt=doc.getElementById('favViewTitle'); _tH=_bt?_bt.textContent:'';
      var _cl=doc.querySelector('#favViewBar .favview-clear'); _cH=_cl?(_cl.style.display||'(empty)'):'NA';
      window.setFilter('fav');
      var _bt2=doc.getElementById('favViewTitle'); _tF=_bt2?_bt2.textContent:'';
      var _cl2=doc.querySelector('#favViewBar .favview-clear'); _cF=_cl2?(_cl2.style.display||'(empty)'):'NA';
      window.setFilter('none');
      _syncOk=true;
    }
  }catch(e){ _syncOk=false; }
  check('⑥ 运行时：进入 history→标题「浏览记录」且清空可见；进入 fav→标题「我的收藏」且清空隐藏',
        _syncOk && _tH==='浏览记录' && _cH!=='none' && _cH!=='' && _tF==='我的收藏' && (_cF==='none'||_cF===''),
        'tH='+_tH+' cH='+_cH+' tF='+_tF+' cF='+_cF);

  // ⑦⑧⑨ 插画化空态（2026-09-12 续）：fav/history 为空时呈现 SVG 插画 + 引导按钮
  let _emptyOk=false,_eTitle='',_hasArt=false,_hasCta=false,_ctaAct='';
  try{
    if(typeof window.setFilter==='function'){
      window.setFilter('fav');
      var _list=doc.getElementById('archFavList');
      var _art=_list?_list.querySelector('.empty-art'):null;
      var _ti=_list?_list.querySelector('.empty-title'):null;
      var _cta=_list?_list.querySelector('.empty-cta'):null;
      _eTitle=_ti?_ti.textContent:'';
      _hasArt=!!_art;
      _hasCta=!!_cta;
      _ctaAct=_cta?(_cta.getAttribute('data-act')||''):'';
      window.setFilter('none');
      _emptyOk=true;
    }
  }catch(e){ _emptyOk=false; }
  check('⑦ 插画化空态：fav 为空渲染 SVG 插画(.empty-art)+标题「还没有收藏」+引导按钮(.empty-cta→fav-back)',
        _emptyOk && _hasArt && _eTitle==='还没有收藏' && _hasCta && _ctaAct==='fav-back',
        'art='+_hasArt+' title='+_eTitle+' cta='+_hasCta+' act='+_ctaAct);
  check('⑧ 插画化空态源码：.empty-art/.empty-cta/两套 SVG(星标+时钟)均已内置',
        html.includes('class="empty-art"') && html.includes('empty-cta') && html.includes('还没有收藏') && html.includes('还没有浏览记录') && html.includes('viewBox="0 0 128 128"'),
        '');
  check('⑨ 空态样式：.empty-art/.empty-cta 已在 index.html 定义',
        /\.aggregate-empty \.empty-art\{/.test(html) && /\.aggregate-empty \.empty-cta\{/.test(html),
        '');

  console.log('\n===== JS 运行时错误 =====');
  const real = errors.filter(e => !/api\/hot-news|api\/ai-analyze|GoatCounter|gc\.zcounter|Failed to fetch|NetworkError/i.test(e));
  check('无阻塞性 JS 错误', real.length === 0, real.slice(0, 3).join(' | '));

  console.log('\n===== 汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 2500);
