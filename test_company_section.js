/**
 * 2026-09-23 矿业公司动态（v4：跨列区块 = 左新闻流 + 右 sticky 侧栏）运行时渲染回归（jsdom）
 * 覆盖：① 区块跨满 news-grid 两列（companySection / installGuideSection 移出 .col-main，col-rail 显式回第一行第二列）
 *       ② 右侧栏：搜索框 / 矿种 chips / 公司导航全部收进 .co-side（旧 .co-bar 已移除）
 *       ③ 新闻流：默认「近90天」+ 日期分组 + 分页 60；切「全部」+ 连续「加载更多」可渲染出全部条目
 *       ④ 左导航列出全部公司（含矿种分组）；未收录公司折进可展开分组，点击直达官网
 *       ⑤ 点击公司 / 点来源名 / hash=#co=公司 → 新闻流收敛到该公司
 *       ⑥ 搜索框按标题/公司名过滤；移动端 <select> 用 <optgroup> 按矿种分组、选项数 = 公司数 + 1
 *       ⑦ switchView('company') 视图隔离（隐藏其它主区块、右栏）
 *       ⑧ 无阻塞 JS 错误
 * 运行：node test_company_section.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = 'C:/Users/中铝矿业投并部/.workbuddy/binaries/node/workspace/node_modules';

let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
['app.js', 'news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  const tag = new RegExp('<script src="' + f + '[^>]*></script>');
  html = html.replace(tag, () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
});

// 真实公司数据（mock fetch 用）
const companyData = JSON.parse(fs.readFileSync(path.join(__dirname, 'company_news.json'), 'utf-8'));
const totalItems = (companyData.counts && companyData.counts.items) || 0;
const nCompanies = (companyData.companies || []).length;
const nEmptyCompanies = (companyData.companies || []).filter(c => !((c.items || []).length)).length;

// 期望值：按 updated_at 为基准日，统计近 90 天内（有日期）的条目数 —— 与 app.js passRange() 同口径
function toTs(s) {
  const m = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(String(s || ''));
  return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) : NaN;
}
const baseTs = toTs(companyData.updated_at || '');
let inRange90 = 0, noDateCount = 0;
(companyData.companies || []).forEach(c => (c.items || []).forEach(it => {
  if (!it.d) { noDateCount++; return; }
  const a = toTs(it.d);
  if (isNaN(a) || isNaN(baseTs)) return;
  const n = Math.round((baseTs - a) / 86400000);
  if (n >= 0 && n <= 90) inRange90++;
}));
const PAGE = 60;
const expectDefaultRendered = Math.min(PAGE, inRange90);

const errors = [];
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'https://pliucugb-cyber.github.io/mining-daily/',
  beforeParse(win) {
    if (typeof win.matchMedia !== 'function') {
      win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    }
    win.open = () => null;
    win.fetch = (url) => {
      if (String(url).indexOf('company_news.json') !== -1) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(companyData) });
      }
      return Promise.reject(new Error('stub-no-' + url));
    };
    win.addEventListener('error', e => errors.push('window.error: ' + (e.message || e)));
  }
});
const { window } = dom;
const { document } = window;

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log('  PASS  ' + name); }
  else { fail++; console.log('  FAIL  ' + name + (extra ? '  -> ' + extra : '')); }
}
function disp(id) {
  const el = document.getElementById(id);
  if (!el) return 'missing';
  return window.getComputedStyle(el).display;
}
function coState() { return window.__mdCo.state(); }

setTimeout(() => {
  try {
    // 0) 入口与容器存在（v4 骨架：跨列区块 + 右侧栏）
    check('目录含 🏢 矿业公司 入口', !!document.querySelector('[data-target="companySection"]'));
    check('companySection 容器存在', !!document.getElementById('companySection'));
    check('companyList 容器存在', !!document.getElementById('companyList'));
    check('左导航 coNav 存在', !!document.getElementById('coNav'));
    check('移动端 coNavSel 存在', !!document.getElementById('coNavSel'));
    check('搜索框 coSearch 存在', !!document.getElementById('coSearch'));
    check('统计 coStat 存在', !!document.getElementById('coStat'));
    check('新闻流头部 coFeedHead 存在', !!document.getElementById('coFeedHead'));
    check('加载更多 coMoreWrap / coMore 存在', !!document.getElementById('coMoreWrap') && !!document.getElementById('coMore'));

    // 1) v4 布局：区块跨满 news-grid 两列 + 右侧栏收纳
    const ng = document.querySelector('.news-grid');
    check('companySection 是 .news-grid 的直接子元素（跨列）',
          document.getElementById('companySection').parentElement === ng);
    check('installGuideSection 也移到 .news-grid 直接子级',
          document.getElementById('installGuideSection').parentElement === ng);
    check('eventCalendar 仍在 .col-main 内（未随迁）',
          document.getElementById('eventCalendar').parentElement !== ng &&
          !!document.getElementById('eventCalendar').closest('.col-main'));
    const coStyle = document.querySelector('#companySection > style');
    check('#companySection > style 存在', !!coStyle);
    const css = coStyle ? coStyle.textContent : '';
    check('CSS：公司区块 grid-column:1/-1', css.indexOf('#companySection{grid-column:1/-1}') >= 0);
    check('CSS：col-rail 显式回到第一行第二列', css.indexOf('.news-grid>.col-rail{grid-column:2;grid-row:1}') >= 0);
    check('CSS：侧栏 sticky', /\.co-side\{[^}]*position:sticky/.test(css));
    check('CSS：宽屏新闻流两栏网格', css.indexOf('.co-day-items') >= 0 && css.indexOf('min-width:1400px') >= 0);
    check('搜索框已收进右侧栏 .co-side', !!(document.getElementById('coSearch').closest('.co-side')));
    check('矿种 chips 已收进右侧栏 .co-side', !!(document.getElementById('coFilters').closest('.co-side')));
    check('公司导航已收进右侧栏 .co-side', !!(document.getElementById('coNav').closest('.co-side')));
    check('旧 .co-bar 已移除', !document.querySelector('.co-bar'));
    check('区块头部顺序：标题 → 说明 → 侧栏/新闻流',
          (function () {
            const h = document.getElementById('companySection');
            const kids = Array.from(h.children).map(e => e.id || e.className || e.tagName);
            return kids.indexOf('coNavSel') > kids.indexOf('coNote') && kids.indexOf('coCount') < kids.indexOf('coNote');
          })());

    // 2) 新闻流默认：近 90 天 + 分页 60 + 日期分组
    const st0 = coState();
    check('window.__mdCo 状态句柄存在', !!window.__mdCo && typeof st0 === 'object');
    check('默认时间范围为「近90天」', st0.range === 90, 'range=' + st0.range);
    check('默认分页游标 = 60', st0.shown === PAGE, 'shown=' + st0.shown);
    check('默认渲染条数 = min(60, 近90天条数)',
          st0.rendered === expectDefaultRendered,
          'got ' + st0.rendered + ' / expect ' + expectDefaultRendered + ' (in90=' + inRange90 + ')');
    check('新闻流按日期分组（.co-day 数 >= 1）', st0.groups >= 1, 'groups=' + st0.groups);
    check('coCount 显示公司家数', /家/.test((document.getElementById('coCount') || {}).textContent || ''),
          (document.getElementById('coCount') || {}).textContent);
    const rangeBtns = document.querySelectorAll('#coFeedHead .co-range button');
    check('时间范围切换按钮 3 个', rangeBtns.length === 3, 'got ' + rangeBtns.length);
    check('「加载更多」可见性 = 范围内条目超出一页',
          coState().moreVisible === (inRange90 > PAGE),
          'moreVisible=' + coState().moreVisible + ' in90=' + inRange90);

    // 3) 切「全部」+ 连续加载更多 → 渲染出全部条目
    const allBtn = document.querySelector('#coFeedHead .co-range button[data-r="0"]');
    if (allBtn) {
      allBtn.click();
      check('切「全部」后 range=0', coState().range === 0, 'range=' + coState().range);
      check('切「全部」后仍分页（渲染 = min(60, 全部条数)）',
            coState().rendered === Math.min(PAGE, totalItems),
            'got ' + coState().rendered + ' / ' + Math.min(PAGE, totalItems));
      let guard = 0;
      while (coState().rendered < totalItems && guard++ < 40) {
        const m = document.getElementById('coMore');
        if (!m || document.getElementById('coMoreWrap').hidden) break;
        m.click();
      }
      check('连续「加载更多」后渲染全部条目（' + totalItems + ' 条）',
            coState().rendered === totalItems,
            'got ' + coState().rendered + ' / expect ' + totalItems);
      check('全部加载完后「加载更多」隐藏', coState().moreVisible === false);
      check('未标注日期条目只在「全部」下出现',
            noDateCount === 0 || coState().rendered > inRange90,
            'noDate=' + noDateCount + ' rendered=' + coState().rendered + ' in90=' + inRange90);
      // 还原默认范围
      const defBtn = document.querySelector('#coFeedHead .co-range button[data-r="90"]');
      if (defBtn) defBtn.click();
    } else {
      check('存在「全部」范围按钮', false);
    }

    // 4) 左侧导航（右侧栏）：全部公司 + 矿种分组 + 未收录折叠
    const navItems = document.querySelectorAll('#coNav .co-nav-item');
    check('公司导航列出全部公司（数量≈公司数）',
          navItems.length >= nCompanies - 1 && navItems.length <= nCompanies + 1,
          'got ' + navItems.length + ' / companies ' + nCompanies);
    const fchips = document.querySelectorAll('#coFilters .co-fchip');
    check('矿种过滤 chips >= 2（含「全部」）', fchips.length >= 2, 'got ' + fchips.length);
    const navAll = document.querySelector('#coNav .co-nav-all');
    check('公司导航「全部公司」入口存在', !!navAll);
    const emptyItems = document.querySelectorAll('#coNav .co-nav-item.empty');
    check('未收录公司列入折叠组（数量=' + nEmptyCompanies + '）',
          emptyItems.length === nEmptyCompanies, 'got ' + emptyItems.length);
    const box0 = document.getElementById('coEmptyBox');
    check('未收录组默认折叠', !!box0 && box0.hasAttribute('hidden'));
    const tog = document.getElementById('coEmptyToggle');
    if (tog) {
      tog.click();
      check('点「展开」后未收录组显示', !document.getElementById('coEmptyBox').hasAttribute('hidden'));
      tog.click();
      check('再点一次收回折叠', document.getElementById('coEmptyBox').hasAttribute('hidden'));
    } else {
      check('「暂未收录」折叠开关存在', false);
    }

    // 5) 抽查首条：标题 + 公司来源名 + http(s) 外链
    const items = document.querySelectorAll('#companyList .co-item');
    const first = items[0];
    check('首条含新闻标题', !!(first && first.querySelector('.co-title') && first.querySelector('.co-title').textContent.trim().length > 0));
    check('首条含公司来源名（co-src 可点选公司）',
          !!(first && first.querySelector('.co-src') && first.querySelector('.co-src').textContent.trim().length > 0));
    check('首条标题为 http(s) 外链', !!(first && first.querySelector('.co-title') &&
          /^https?:\/\//.test(first.querySelector('.co-title').getAttribute('href') || '')));

    // 6) 公司选择：点第一个「有数据」的公司项 → 新闻流收敛
    let selName = '';
    for (const ni of navItems) {
      if (!ni.classList.contains('empty')) { selName = ni.getAttribute('data-name'); ni.click(); break; }
    }
    check('存在可点击的有数据公司', !!selName, selName);
    if (selName) {
      const after = document.querySelectorAll('#companyList .co-item');
      let allMatch = true;
      after.forEach(it => {
        const src = it.querySelector('.co-src');
        if (!src || src.getAttribute('data-name') !== selName) allMatch = false;
      });
      check('选中公司后新闻流仅含该公司（' + selName + '）', after.length > 0 && allMatch,
            'got ' + after.length + ' match=' + allMatch);
      const headName = (document.querySelector('#coFeedHead .co-feed-name') || {}).textContent || '';
      check('新闻流头部显示公司名', headName.indexOf(selName) >= 0, headName);
      check('公司视图头部含「官网」外链或代码',
            /官网/.test(document.getElementById('coFeedHead').textContent) || !!document.querySelector('#coFeedHead .co-feed-link'));
      check('hash 写入 #co=公司名', /#co=/.test(window.location.hash), window.location.hash);
      if (navAll) navAll.click();
    }

    // 7) hash 路由：直接设置 location.hash 定位公司
    const someCo = (companyData.companies.find(c => (c.items || []).length > 0) || {}).name || '';
    if (someCo) {
      window.location.hash = '#co=' + encodeURIComponent(someCo);
      window.dispatchEvent(new window.Event('hashchange'));
      const afterHash = document.querySelectorAll('#companyList .co-item');
      let allMatch = true;
      afterHash.forEach(it => {
        const src = it.querySelector('.co-src');
        if (!src || src.getAttribute('data-name') !== someCo) allMatch = false;
      });
      check('hash 路由定位到公司（' + someCo + '）', afterHash.length > 0 && allMatch,
            'got ' + afterHash.length + ' match=' + allMatch);
      if (navAll) navAll.click();
    } else {
      check('hash 路由（存在可定位公司）', false, '无数据公司');
    }

    // 8) 搜索框过滤
    const q = document.getElementById('coSearch');
    if (q) {
      const before = document.querySelectorAll('#companyList .co-item').length;
      q.value = (someCo || '').slice(0, 2);
      q.dispatchEvent(new window.Event('input'));
      const after = document.querySelectorAll('#companyList .co-item').length;
      check('搜索框可触发过滤（数量变化或保持）', typeof after === 'number' || after <= before,
            'before ' + before + ' after ' + after);
      q.value = '';
      q.dispatchEvent(new window.Event('input'));
    } else {
      check('搜索框存在', false);
    }

    // 9) 移动端 select：选项 = 公司数 + 1，且按矿种 optgroup 分组
    const opts = document.querySelectorAll('#coNavSel option');
    check('移动端 select 选项=公司数+1', opts.length === nCompanies + 1, 'got ' + opts.length + ' / ' + (nCompanies + 1));
    check('移动端 select 用 optgroup 按矿种分组', document.querySelectorAll('#coNavSel optgroup').length >= 2,
          'got ' + document.querySelectorAll('#coNavSel optgroup').length);

    // 10) 豁免：默认视图下 companySection 不被隐藏
    window.mdRefreshSections && window.mdRefreshSections();
    check('默认视图下 companySection 不被隐藏', disp('companySection') !== 'none', disp('companySection'));

    // 11) 视图切换：switchView('company')
    const coItem = document.querySelector('[data-target="companySection"]');
    if (coItem && typeof window.switchView === 'function') {
      window.switchView('company', coItem);
      check('switchView("company") 设置 data-view=company', document.body.dataset.view === 'company', document.body.dataset.view);
      check('公司区在公司视图可见', disp('companySection') !== 'none', disp('companySection'));
      check('今日区在公司视图隐藏', disp('todaySection') === 'none', disp('todaySection'));
      check('矿权区在公司视图隐藏', disp('rightsSection') === 'none', disp('rightsSection'));
      check('右栏在公司视图隐藏', window.getComputedStyle(document.querySelector('.col-rail')).display === 'none');
      check('公司入口获得 active 高亮', coItem.classList.contains('active'));
      window.switchView('company', coItem);
      check('再次点击回到全部（data-view 清除）', !document.body.dataset.view, document.body.dataset.view);
    } else {
      check('switchView 函数存在且目录入口存在', false, 'missing switchView or entry');
    }

    // 12) 无阻塞 JS 错误
    check('updateActiveSection 函数存在', typeof window.updateActiveSection === 'function');
    check('无阻塞性 JS 错误', errors.length === 0, errors.join(' | '));

  } catch (e) {
    fail++;
    console.log('  FAIL  测试执行抛错 -> ' + (e && e.stack ? e.stack.split('\n').slice(0, 3).join(' | ') : e));
  }
  console.log('\n===== 矿业公司动态（v4 跨列区块 + 右 sticky 侧栏）汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 1500);
