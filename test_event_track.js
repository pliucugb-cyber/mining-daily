/**
 * 2026-10-25 「事件跟踪」模块回归测试（右栏卡片 + 移动端「事件」tab + 数据契约 + 建议精度）
 *
 * 背景：ChatGPT 站审「最建议增加事件跟踪」。方案见 docs/event-track-plan.md，范式复刻「会议日程」：
 *   data/events.json（manual 人工 + review 待审核）→ fetch_events.py 生成 event-data.js
 *   （window.EVENT_DATA）→ app.js 事件 IIFE 渲染右栏 #eventTrack 与移动端 #eventSection。
 *
 * 与会议日程的三个本质差异（本测试的重点守护对象）：
 *   ① 无 14 天闸门：事件是长生命周期叙事，active（进行中/观察中）按 started 倒序常驻，
 *      已达成/已终止 只降级到后面，不因过期下线（2026-01-05 的旧事件也必须渲染）。
 *   ② 关联新闻主键是 URL 不是 id：news-data.js 是 slim schema（d/t/s/u/g/c/m/n），没有 id 字段，
 *      前端只能按 URL 现查 window.NEWS_DATA；全库 data/news_YYYY-MM.json 的 id = md5(url)[:12]，
 *      由 D 组校验（防臆造：URL 必须真实存在于新闻库）。
 *   ③ 自动建议有「强命中资格」：泛词（探矿权/伦铜/收购/花旗…）只参与排序、永不给资格。
 *      2026-10-25 踩坑：仅凭「探矿权」把辽宁闹沟里金铜矿转让公示挂到江西安远铂矿事件上；
 *      凭「收购」把 34 条并购新闻挂到新铝时代事件上（46 条误配 → 0 条）。
 *
 * 断言分组：
 *   A 桌面卡片：渲染条数/排序/状态色点/计数徽标/脚注/关联新闻链接（含解析不到的 URL 优雅跳过）、
 *     时间线默认只显示 1 节点、展开收起互不影响、单节点事件无展开按钮、无 14 天闸门。
 *   B 空态：items 为空或缺字段 → 卡片整块隐藏，不白屏不报错。
 *   C 移动端「事件」tab：#eventSection 注入位置/同源渲染/计数/高亮；index.html 与 app.js 静态契约
 *     （含「.et-title 不可点击故不得有 hover 变色」这条死交互修复）。
 *   D 数据契约：data/events.json 结构合法、status 合法、news 是 URL、每个 URL 都能在新闻库里
 *     按 md5(url)[:12] 对上号；event-data.js 语法合法且条目数 = manual 数（逗号红线）；
 *     deploy_pages.py 的 REQUIRED 与 BUST_FILES 都登记了 event-data.js。
 *   E 建议精度（跑真实 fetch_events.py --suggest --dry-run）：泛词用例强命中=0、正对照≥2、
 *     所有候选 score≥2、dry-run 不落盘。
 *
 * 运行：node test_event_track.js   （需仓库 node_modules/jsdom）
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');
const { JSDOM } = require('jsdom');

const ROOT = __dirname;
const APPJS = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf-8');
const INDEX = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf-8');
const PY = process.env.PYTHON || 'python';

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name + (detail ? '  → ' + detail : '')); }
  else { fail++; console.log('  FAIL  ' + name + (detail ? '  → ' + detail : '')); }
}

// ──  fixtures ────────────────────────────────────────────────────────────────
const NEWS = [
  { d: '2026-10-20', t: '甲相关新闻标题', s: '测试源', u: 'https://example.com/news-a', g: ['铜'], c: '矿权交易', m: '摘要a', n: '2026-10-20' },
  { d: '2026-09-10', t: '乙相关新闻标题', s: 'SMM 国际站', u: 'https://example.com/news-b', g: ['铜'], c: '市场与价格', m: '摘要b', n: '2026-09-10' }
];

const EVENTS = [
  { id: 'evt_a', title: '测试事件甲·进行中', summary: '甲摘要', category: '矿权交易', status: '进行中', priority: 'normal', started: '2026-10-20',
    timeline: [
      { date: '2026-10-20', title: '甲节点一', detail: '细节一', news: ['https://example.com/not-in-news-data'], source: '测试源', milestone: true },
      { date: '2026-10-24', title: '甲节点二', news: [NEWS[0].u], source: '测试源', milestone: false }
    ] },
  { id: 'evt_b', title: '测试事件乙·观察中', summary: '乙摘要', category: '政策与法规', status: '观察中', priority: 'high', started: '2026-09-10',
    timeline: [
      { date: '2026-09-10', title: '乙节点一', news: [NEWS[1].u], source: 'SMM 国际站', milestone: true },
      { date: '2026-10-01', title: '乙节点二', news: [NEWS[1].u], source: 'SMM 国际站', milestone: false },
      { date: '2026-10-06', title: '乙节点三', news: ['https://example.com/not-in-news-data'], source: 'SMM 国际站', milestone: false },
      { date: '2026-10-24', title: '乙节点四', news: [NEWS[1].u], source: 'SMM 国际站', milestone: false }
    ] },
  { id: 'evt_old', title: '测试旧事件·无14天闸门', summary: '旧摘要', category: '并购与投资', status: '观察中', priority: 'normal', started: '2026-01-05',
    timeline: [{ date: '2026-01-05', title: '旧节点', news: [], source: '测试源', milestone: true }] },
  { id: 'evt_c', title: '测试事件丙·已达成', summary: '丙摘要', category: '并购与投资', status: '已达成', priority: 'normal', started: '2026-08-28',
    timeline: [{ date: '2026-08-28', title: '丙节点', news: [], source: '公司公告', milestone: true }] }
];

function buildDom(eventData, opts) {
  opts = opts || {};
  const evScript = eventData === null ? '' :
    '<script>window.EVENT_DATA = ' + JSON.stringify(eventData) + ';</script>';
  const newsScript = opts.noNews ? '' :
    '<script>window.NEWS_DATA = ' + JSON.stringify({ updated: '2026-10-25 06:10', schema: '1.2-slim', total: NEWS.length, news: NEWS }) + ';</script>';
  const html = '<!DOCTYPE html><html><head></head><body>'
    + '<div class="stats-bar"><span id="newCount"></span><span id="unreadCount"></span></div>'
    + '<div class="section" id="todaySection"></div>'
    + '<div class="section" id="archiveSection"><span id="todayCount"></span><span id="archiveCount"></span></div>'
    + '<div class="section" id="rightsSection"></div>'
    + '<div class="section" id="meetingSection" style="display:none"></div>'
    + '<div class="news-grid"><div class="col-main"></div><aside class="col-rail">'
    + '<div class="event-track" id="eventTrack" style="display:none">'
    + '<div class="event-track-head">事件跟踪<span class="et-count" id="eventTrackCount"></span></div>'
    + '<ul class="event-track-list" id="eventTrackList"></ul>'
    + '<div class="event-track-foot" id="eventTrackFoot"></div>'
    + '</div></aside></div>'
    + evScript + newsScript
    + '<script>' + APPJS + '</script>'
    + '</body></html>';
  const errors = [];
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    url: 'https://pliucugb-cyber.github.io/mining-daily/',
    beforeParse(win) {
      win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
      win.fetch = () => Promise.reject(new Error('jsdom: fetch stub'));
      try { Object.defineProperty(win, 'innerWidth', { value: 1280, configurable: true, writable: true }); } catch (e) {}
      win.addEventListener('error', e => errors.push('window.error: ' + (e && e.message)));
      win.console.error = (...a) => { errors.push('console.error: ' + a.join(' ')); };
    }
  });
  return { dom, window: dom.window, doc: dom.window.document, errors };
}

const EV = (extra) => Object.assign({ updated: '2026-10-25', source: '人工维护（data/events.json 的 manual 区）', items: EVENTS }, extra || {});

function waitFor(fn, timeout) {
  return new Promise((resolve, reject) => {
    const t0 = Date.now();
    (function poll() {
      let v = null;
      try { v = fn(); } catch (e) { v = null; }
      if (v) return resolve(v);
      if (Date.now() - t0 > (timeout || 5000)) return resolve(null);
      setTimeout(poll, 50);
    })();
  });
}

const titlesOf = (doc, sel) => Array.prototype.map.call(doc.querySelectorAll(sel), e => e.textContent.trim());

// ===== A 桌面卡片 =====
async function runA() {
  console.log('===== A 桌面卡片（4 条 fixture：进行中/观察中×2/已达成）=====');
  const { doc, errors } = buildDom(EV());
  await waitFor(() => doc.querySelectorAll('#eventTrackList li.et-item').length > 0);

  const box = doc.getElementById('eventTrack');
  check('[A1] 卡片可见', box && box.style.display !== 'none', 'display=' + (box ? box.style.display : 'n/a'));

  const items = doc.querySelectorAll('#eventTrackList li.et-item');
  check('[A2] 渲染 4 条事件', items.length === 4, 'actual=' + items.length);

  const titles = titlesOf(doc, '#eventTrackList li.et-item .et-title');
  check('[A3] 排序：active 在前且按 started 倒序，closed 垫后',
    titles[0] === '测试事件甲·进行中' && titles[1] === '测试事件乙·观察中'
    && titles[2] === '测试旧事件·无14天闸门' && titles[3] === '测试事件丙·已达成', titles.join(' | '));

  const dots = Array.prototype.map.call(doc.querySelectorAll('#eventTrackList li.et-item .et-dot'),
    e => Array.prototype.filter.call(e.classList, c => c !== 'et-dot')[0]);
  check('[A4] 状态色点 class 正确（ongoing/watch/watch/done）',
    dots.join(',') === 'ongoing,watch,watch,done', dots.join(','));

  const cnt = doc.getElementById('eventTrackCount');
  check('[A5] 计数徽标＝active 件数（进行中+观察中）', cnt && cnt.textContent === '· 3 件追踪中', cnt ? cnt.textContent : 'n/a');

  const foot = doc.getElementById('eventTrackFoot');
  check('[A6] 脚注含数据截至/总件数/人工维护',
    !!foot && /数据截至 2026-10-25/.test(foot.textContent) && /共 4 件/.test(foot.textContent) && /人工维护/.test(foot.textContent),
    foot ? foot.textContent : 'n/a');

  // 关联新闻：URL 现查 NEWS_DATA（隐藏的时间线节点也在 DOM 里，故可见/总数分开断言）
  const visLinks = doc.querySelectorAll('#eventTrackList .et-tl li:not(.et-tl-extra) .et-tl-news a');
  const allLinks = doc.querySelectorAll('#eventTrackList .et-tl-news a');
  const hrefs = Array.prototype.map.call(allLinks, a => a.getAttribute('href'));
  check('[A7] 可见节点的关联链接＝2（时间线倒序，默认显示最新节点）', visLinks.length === 2, 'visible=' + visLinks.length);
  check('[A7b] 全部节点共 4 个可解析链接（另 2 个不可解析 URL 被优雅跳过）',
    allLinks.length === 4 && hrefs.indexOf(NEWS[0].u) >= 0 && hrefs.indexOf(NEWS[1].u) >= 0, 'n=' + allLinks.length);
  const a0 = Array.prototype.filter.call(allLinks, a => a.getAttribute('href') === NEWS[0].u)[0];
  check('[A8] 链接文案取自 NEWS_DATA 的 t（不臆造）', !!a0 && a0.textContent === '甲相关新闻标题', a0 ? a0.textContent : 'n/a');
  check('[A9] 链接 target=_blank + rel=noopener', !!a0 && a0.getAttribute('target') === '_blank' && a0.getAttribute('rel') === 'noopener');
  check('[A10] 解析不到的 URL 不产生链接也不抛错',
    Array.prototype.filter.call(allLinks, a => /not-in-news-data/.test(a.getAttribute('href'))).length === 0);

  // 时间线折叠
  const evA = Array.prototype.filter.call(items, li => /甲/.test(li.querySelector('.et-title').textContent))[0];
  const evB = Array.prototype.filter.call(items, li => /乙/.test(li.querySelector('.et-title').textContent))[0];
  const evOld = Array.prototype.filter.call(items, li => /旧事件/.test(li.querySelector('.et-title').textContent))[0];
  const btnA = evA.querySelector('.et-more-btn'), btnB = evB.querySelector('.et-more-btn');
  check('[A11] 多节点事件有展开按钮（甲 2 节点、乙 4 节点）', !!btnA && !!btnB);
  check('[A12] 单节点事件无展开按钮（旧事件、丙）', !evOld.querySelector('.et-more-btn') && !items[3].querySelector('.et-more-btn'));
  check('[A13] 默认只显示 1 个节点，其余 hidden',
    evA.querySelectorAll('.et-tl li:not(.et-tl-extra)').length === 1 && evA.querySelectorAll('.et-tl-extra[hidden]').length === 1
    && evB.querySelectorAll('.et-tl li:not(.et-tl-extra)').length === 1 && evB.querySelectorAll('.et-tl-extra[hidden]').length === 3,
    'A-extra-hidden=' + evA.querySelectorAll('.et-tl-extra[hidden]').length + ' B-extra-hidden=' + evB.querySelectorAll('.et-tl-extra[hidden]').length);

  btnA.onclick();
  check('[A14] 点甲的按钮只展开甲，不影响乙',
    evA.querySelectorAll('.et-tl-extra[hidden]').length === 0 && evB.querySelectorAll('.et-tl-extra[hidden]').length === 3
    && btnA.textContent === '收起时间线 ▴', 'btnA=' + btnA.textContent);
  btnA.onclick();
  check('[A15] 再点收起，文案还原', evA.querySelectorAll('.et-tl-extra[hidden]').length === 1 && btnA.textContent === '展开时间线 ▾', 'btnA=' + btnA.textContent);

  const upd = evA.querySelector('.et-updated');
  check('[A16] 「更新于 X 前」文案（与运行日期无关的正则）', !!upd && /^(今天更新|昨天更新|\d+ 天前更新)$/.test(upd.textContent.trim()),
    upd ? upd.textContent.trim() : 'n/a');

  check('[A17] 无 14 天闸门：2026-01-05 的旧事件仍渲染', /旧事件/.test(titles[2] || ''));
  check('[A18] 空 detail 不产生 .et-tl-detail', evA.querySelectorAll('.et-tl-detail').length === 1,
    'n=' + evA.querySelectorAll('.et-tl-detail').length);
  check('[A19] 无未捕获错误', errors.length === 0, errors.slice(0, 2).join(' ; '));
}

// ===== B 空态 =====
async function runB() {
  console.log('===== B 空态（items 空 / 缺 items / EVENT_DATA 未定义）=====');
  {
    const { doc } = buildDom(EV({ items: [] }));
    await new Promise(r => setTimeout(r, 250));
    const box = doc.getElementById('eventTrack');
    check('[B1] items 为空 → 卡片隐藏', box && box.style.display === 'none', 'display=' + (box ? box.style.display : 'n/a'));
    check('[B2] items 为空 → 列表清空', doc.getElementById('eventTrackList').children.length === 0);
  }
  {
    const { doc } = buildDom({ updated: '2026-10-25' });   // 缺 items 字段
    await new Promise(r => setTimeout(r, 250));
    const box = doc.getElementById('eventTrack');
    check('[B3] 缺 items 字段 → 卡片隐藏不报错', box && box.style.display === 'none', 'display=' + (box ? box.style.display : 'n/a'));
  }
}

// ===== C 移动端 tab + 静态契约 =====
async function runC() {
  console.log('===== C 移动端「事件」tab 与静态契约 =====');
  const { doc } = buildDom(EV());
  await waitFor(() => doc.querySelectorAll('#eventTrackList li.et-item').length > 0);

  const w = doc.defaultView;
  check('[C1] mdSelectCat 可用', typeof w.mdSelectCat === 'function');
  w.mdSelectCat('event');
  await new Promise(r => setTimeout(r, 120));

  const sec = doc.getElementById('eventSection');
  check('[C2] #eventSection 已注入', !!sec);
  check('[C3] 注入位置在 #meetingSection 之后（与会议/矿权区块同级）',
    !!sec && sec.previousElementSibling && sec.previousElementSibling.id === 'meetingSection',
    sec && sec.previousElementSibling ? 'prev=' + sec.previousElementSibling.id : 'n/a');
  check('[C4] body[data-md-cat=event]', doc.body.getAttribute('data-md-cat') === 'event', doc.body.getAttribute('data-md-cat'));
  const tabBtn = doc.querySelector('.mctab[data-cat="event"]');
  check('[C5] 顶部分类栏有「事件」tab 且选中', !!tabBtn && tabBtn.classList.contains('active') && tabBtn.textContent === '事件',
    tabBtn ? tabBtn.textContent + '/' + tabBtn.className : 'n/a');
  const tabItems = doc.querySelectorAll('#eventTabList li.et-item');
  check('[C6] 移动端与右栏同源渲染 4 条', tabItems.length === 4, 'actual=' + tabItems.length);
  const ec = doc.getElementById('eventCount');
  check('[C7] 移动端计数 4件', !!ec && ec.textContent === '4件', ec ? ec.textContent : 'n/a');

  // 静态契约（index.html）
  check('[C8] index.html 有 #eventTrack 卡片', INDEX.indexOf('id="eventTrack"') >= 0);
  check('[C9] index.html 引用 event-data.js（defer）', /<script src="event-data\.js" defer><\/script>/.test(INDEX));
  check('[C10] #eventSection 默认隐藏', INDEX.indexOf('#eventSection{display:none}') >= 0);
  check('[C11] event tab 下显示 #eventSection', INDEX.indexOf('body[data-md-cat="event"]:not([data-filter-mode]) #eventSection{display:block!important}') >= 0);
  check('[C12] 事件卡 CSS 存在', INDEX.indexOf('.event-track{') >= 0);
  check('[C13] 暗色覆盖存在', INDEX.indexOf('body.dark .et-dot.ongoing') >= 0);
  check('[C14] .et-title 不可点击 → 不得有 hover 变色（死交互修复）', INDEX.indexOf('.et-title:hover') < 0);

  // 静态契约（app.js）
  check('[C15] cats 数组含 event tab', APPJS.indexOf("['event','事件']") >= 0);
  check('[C16] app.js 用 URL 现查（newsByUrl）', APPJS.indexOf('function newsByUrl(') >= 0);
  check('[C17] app.js 不再有按 id 现查的旧实现', APPJS.indexOf('function newsById(') < 0);
  check('[C18] 暴露 window.__mdEvent 供测试/调试', APPJS.indexOf('window.__mdEvent = {') >= 0);
}

// ===== D 数据契约（真实文件） =====
async function runD() {
  console.log('===== D 数据契约（data/events.json / event-data.js / deploy_pages.py）=====');
  const ev = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'events.json'), 'utf-8'));
  check('[D1] events.json 有 manual 与 review 两区', Array.isArray(ev.manual) && Array.isArray(ev.review));
  check('[D2] manual 非空', ev.manual.length >= 1, 'n=' + ev.manual.length);

  const VALID_STATUS = ['进行中', '观察中', '已达成', '已终止'];
  let structOk = true, statusOk = true, dateOk = true, urlOk = true, tlOk = true;
  const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
  ev.manual.forEach(e => {
    if (!e.id || !e.title || !e.summary || !e.category || !e.status || !e.started) structOk = false;
    if (VALID_STATUS.indexOf(e.status) < 0) statusOk = false;
    if (!DATE_RE.test(e.started || '')) dateOk = false;
    (e.timeline || []).forEach(n => {
      if (!DATE_RE.test(n.date || '') || !n.title) tlOk = false;
      (n.news || []).forEach(u => { if (!/^https?:\/\//.test(u)) urlOk = false; });
    });
  });
  check('[D3] 每条事件字段完整（id/title/summary/category/status/started）', structOk);
  check('[D4] status 合法', statusOk, ev.manual.map(e => e.status).join(','));
  check('[D5] started 为 YYYY-MM-DD', dateOk);
  check('[D6] 时间线节点有 date/title', tlOk);
  check('[D7] 关联 news 均为 http(s) URL（不用 id：slim schema 无 id 字段）', urlOk);

  // 防臆造：每个 URL 必须真实存在于新闻库，且 md5(url)[:12] === 该库条目的 id
  const lib = {};
  fs.readdirSync(path.join(ROOT, 'data')).filter(f => /^news_2026-.*\.json$/.test(f)).forEach(f => {
    const d = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', f), 'utf-8'));
    (d.news || []).forEach(n => { if (n.url) lib[n.url] = n.id; });
  });
  let miss = [], mismatch = [], checked = 0;
  ev.manual.forEach(e => (e.timeline || []).forEach(n => (n.news || []).forEach(u => {
    checked++;
    if (!lib[u]) { miss.push(u); return; }
    if (lib[u] !== crypto.createHash('md5').update(u, 'utf8').digest('hex').slice(0, 12)) mismatch.push(u);
  })));
  check('[D8] 关联新闻 URL 全部真实存在于新闻库（防臆造）', miss.length === 0, 'checked=' + checked + ' miss=' + miss.length + (miss[0] ? ' → ' + miss[0] : ''));
  check('[D9] URL 与全库 id（md5(url)[:12]）对得上', mismatch.length === 0, 'mismatch=' + mismatch.length);

  // 生成物：语法 + 逗号红线（条目数 = manual 数）
  try {
    execFileSync(process.execPath, ['--check', path.join(ROOT, 'event-data.js')], { cwd: ROOT, stdio: 'pipe' });
    check('[D10] event-data.js 语法合法（node --check）', true);
  } catch (e) { check('[D10] event-data.js 语法合法（node --check）', false, String(e.message).slice(0, 120)); }
  const gen = fs.readFileSync(path.join(ROOT, 'event-data.js'), 'utf-8');
  // 用 vm 真求值（比正则数条目更强：同时证明语法合法 + items 长度正确）
  let genItems = -1;
  try {
    const vm = require('vm');
    const ctx = { window: {} };
    vm.createContext(ctx);
    vm.runInContext(gen, ctx);
    genItems = (ctx.window.EVENT_DATA && ctx.window.EVENT_DATA.items || []).length;
  } catch (e) { genItems = -1; }
  check('[D11] event-data.js 可求值且条目数 = manual 数（逗号红线的实质守护）',
    genItems === ev.manual.length, 'items=' + genItems + ' manual=' + ev.manual.length);
  check('[D12] 生成物标注「自动生成勿直接改」', gen.indexOf('【自动生成，勿直接改】') >= 0);

  // 部署接入
  const dep = fs.readFileSync(path.join(ROOT, 'deploy_pages.py'), 'utf-8');
  const reqBlock = dep.slice(dep.indexOf('REQUIRED = ['), dep.indexOf(']', dep.indexOf('REQUIRED = [')));
  const bustLine = (dep.match(/BUST_FILES = \[[^\]]*\]/) || [''])[0];
  check('[D13] deploy REQUIRED 登记 event-data.js', reqBlock.indexOf("'event-data.js'") >= 0);
  check('[D14] deploy BUST_FILES 登记 event-data.js（否则 ?v= 指纹缺失，改内容不生效）', bustLine.indexOf("'event-data.js'") >= 0);
  const fet = fs.readFileSync(path.join(ROOT, 'fetch_events.py'), 'utf-8');
  check('[D15] fetch_events.py 有泛词表与强命中资格机制', fet.indexOf('GENERIC_TOKENS') >= 0 && fet.indexOf('QUALIFY_STRONG') >= 0);
  check('[D16] fetch_events.py 支持 --suggest --dry-run（测试不污染数据源）', fet.indexOf('dry=dry') >= 0);
}

// ===== E 建议精度（真实跑 fetch_events.py） =====
async function runE() {
  console.log('===== E 建议精度（python fetch_events.py --suggest --dry-run）=====');
  const probe = [
    'import json, io, os, sys',
    'sys.path.insert(0, sys.argv[1])',
    'import fetch_events as fe',
    'data = fe.load_json(fe.DATA_FILE)',
    'before = io.open(fe.DATA_FILE, encoding="utf-8").read()',
    'fe.suggest(data, dry=True)',
    'after = io.open(fe.DATA_FILE, encoding="utf-8").read()',
    'def strong(ev, title):',
    '    toks = [str(x).lower() for x in (ev.get("entities") or []) + (ev.get("keywords") or [])]',
    '    return fe._strong_hits(toks, title)[0]',
    'byid = dict((e["id"], e) for e in data["manual"])',
    'rv = data.get("review") or []',
    'out = {',
    '  "node": len([r for r in rv if r["type"] == "node_suggestion"]),',
    '  "new": len([r for r in rv if r["type"] == "new_event"]),',
    '  "min_score": min([r["score"] for r in rv if r["type"] == "node_suggestion"] or [99]),',
    '  "unchanged": before == after,',
    '  "g_liaoning": strong(byid["evt_anyuan_pt"], "辽宁省岫岩县闹沟里金铜矿普查探矿权转让公示"),',
    '  "g_duotou": strong(byid["evt_anyuan_pt"], "洛阳双海矿业有限公司嵩县草宝山(含前岭)金矿采矿权转让公示"),',
    '  "g_lunco": strong(byid["evt_us_copper_tariff"], "伦铜 12 周内第 11 次周线上涨 中国洋山铜溢价创近四年新高"),',
    '  "g_citic": strong(byid["evt_us_copper_tariff"], "花旗重申未来三个月铜价目标 15,000 美元/吨"),',
    '  "p_anyuan": strong(byid["evt_anyuan_pt"], "江西省安远县甲水铂矿详查探矿权转让公示"),',
    '  "p_xinlv": strong(byid["evt_xinlv_honglian"], "新铝时代收购东莞宏联电子 100% 股权完成过户"),',
    '}',
    'sys.stdout.write("@@JSON@@" + json.dumps(out, ensure_ascii=False))'
  ].join('\n');
  let out = null;
  try {
    const txt = execFileSync(PY, ['-c', probe, ROOT], { cwd: ROOT, encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] });
    const i = txt.indexOf('@@JSON@@');
    if (i >= 0) out = JSON.parse(txt.slice(i + 8));
  } catch (e) { /* 落到下面 check 报错 */ }
  if (!out) { check('[E0] 成功跑通 python 探针', false, 'python 探针无输出（PYTHON=' + PY + '）'); return; }
  check('[E0] 成功跑通 python 探针', true, 'node=' + out.node + ' new=' + out.new);

  check('[E1] 泛词不给资格：辽宁闹沟里金铜矿 vs 安远铂矿 → 强命中 0', out.g_liaoning === 0, 'strong=' + out.g_liaoning);
  check('[E2] 泛词不给资格：洛阳草宝山金矿 vs 安远铂矿 → 强命中 0', out.g_duotou === 0, 'strong=' + out.g_duotou);
  check('[E3] 泛词不给资格：伦铜周线上涨 vs 铜关税 → 强命中 0', out.g_lunco === 0, 'strong=' + out.g_lunco);
  check('[E4] 泛词不给资格：花旗铜价目标 vs 铜关税 → 强命中 0', out.g_citic === 0, 'strong=' + out.g_citic);
  check('[E5] 正对照：真实安远新闻 → 强命中 ≥2', out.p_anyuan >= 2, 'strong=' + out.p_anyuan);
  check('[E6] 正对照：真实新铝时代新闻 → 强命中 ≥2', out.p_xinlv >= 2, 'strong=' + out.p_xinlv);
  check('[E7] 所有节点候选 score ≥ 2（资格线）', out.min_score >= 2, 'min_score=' + out.min_score);
  check('[E8] --dry-run 不落盘（events.json 字节不变）', out.unchanged === true);
  check('[E9] 人工闸门：review 不进 event-data.js（只渲染 manual）',
    (function () {
      const gen = fs.readFileSync(path.join(ROOT, 'event-data.js'), 'utf-8');
      const ev = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'events.json'), 'utf-8'));
      return gen.indexOf(ev.manual[0].id) >= 0 && gen.indexOf('"review"') < 0;
    })());
}

// ===== 汇总 =====
(async () => {
  await runA();
  await runB();
  await runC();
  await runD();
  await runE();
  console.log('\n===== 汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('测试脚本异常:', e); process.exit(2); });
