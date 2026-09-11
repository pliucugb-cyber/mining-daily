/**
 * 2026-09-10 手机端 UX 批量优化验证（jsdom）
 * 覆盖：① 热榜手机 10 条 / 桌面 5 条  ② 往期字号（CSS，字符串断言）
 *       ③+④ 推荐不显示价格、价格仅价格 tab  ⑤ 问按钮发光球（CSS 断言）
 *       ⑥ 问答全屏 + 返回箭头  ⑧ 我的面板内联安装卡 + 删阅读模式  ⑨ 会议 tab + 区块注入
 *       ⑩ 顶栏智能吸顶：隐藏只做 transform，不得折叠布局（2026-09-11 P0）
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

  console.log('\n===== ⑧ 我的面板：内联安装卡 + 删阅读模式 =====');
  const sheet = doc.getElementById('mineSheet');
  check('mineSheet 存在', !!sheet);
  check('阅读模式按钮已从我的面板删除', !!(sheet && !sheet.querySelector('[data-act="reading"]')));
  check('旧「安装到桌面」按钮已从我的面板删除', !!(sheet && !sheet.querySelector('[data-act="install"]')));
  const card = doc.getElementById('mineInstallCard');
  check('内联安装分步卡已注入', !!card, card ? ('内容片段=' + (card.textContent || '').slice(0, 18)) : '无');
  check('安装卡含系统识别提示', !!card && /主屏幕|安装/.test(card.textContent || ''));

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

  console.log('\n===== ⑫ 底部导航增强：记住 tab + 品牌行 tab 名 + 非首页隐藏搜索（2026-09-11 优化①②③）=====');
  function brandText(){ var b=doc.querySelector('#mdTop .md-brand'); return b?b.textContent:''; }
  function lsGet(k){ try{ return window.localStorage.getItem(k); }catch(e){ return null; } }
  clickGo('price');
  check('① 点价格 → 持久化 md_last_tab=price', lsGet('md_last_tab')==='price');
  check('③ 点价格 → 品牌行显示「价格」', brandText()==='价格', '实际「'+brandText()+'」');
  check('② 非首页隐藏搜索图标 CSS 规则存在', /body\.md-hide-catbar #mdSearchBtn\{display:none\}/.test(html));
  check('③ 非首页隐藏日期 CSS 规则存在', /body\.md-hide-catbar \.md-date\{display:none\}/.test(html));
  clickGo('rights');
  check('③ 点矿权 → 品牌行显示「矿权」', brandText()==='矿权', '实际「'+brandText()+'」');
  clickGo('home');
  check('③ 回首页 → 品牌行恢复含「矿业新闻日报」', brandText().indexOf('矿业新闻日报')>=0, '实际「'+brandText()+'」');
  check('① 回首页 → md_last_tab=home', lsGet('md_last_tab')==='home');
  check('② 搜索按钮结构仍在（display:none 由 CSS 控制）', !!doc.getElementById('mdSearchBtn'));

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

  console.log('\n===== JS 运行时错误 =====');
  const real = errors.filter(e => !/api\/hot-news|api\/ai-analyze|GoatCounter|gc\.zcounter|Failed to fetch|NetworkError/i.test(e));
  check('无阻塞性 JS 错误', real.length === 0, real.slice(0, 3).join(' | '));

  console.log('\n===== 汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 2500);
