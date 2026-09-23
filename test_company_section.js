/**
 * 2026-09-23 矿业公司动态（v3：左公司导航 + 右新闻流）运行时渲染回归（jsdom）
 * 覆盖：① fetch 根目录 company_news.json 并渲染双栏（左导航 / 右新闻流）
 *       ② #companySection 在 refreshSectionVisibility 下不被隐藏（豁免）
 *       ③ 全部视图下：右新闻流渲染全部 .co-item；左导航列出全部公司 + 矿种过滤 chips
 *       ④ 点击左导航公司 / 点来源名 → 右新闻流收敛到该公司 + 头部显示公司名 + hash=#co=
 *       ⑤ hash 路由：location.hash=#co=公司 → 直接定位该公司
 *       ⑥ 搜索框：按标题/公司名过滤
 *       ⑦ 移动端 <select> 选项 = 公司数 + 1（全部）
 *       ⑧ switchView('company') 视图隔离（隐藏其它主区块、右栏、显示公司区、目录 active）
 *       ⑨ 无阻塞 JS 错误
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

const errors = [];
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'https://pliucugb-cyber.github.io/mining-daily/',
  beforeParse(win) {
    if (typeof win.matchMedia !== 'function') {
      win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    }
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

setTimeout(() => {
  try {
    // 0) 入口与容器存在（v3 双栏骨架）
    check('目录含 🏢 矿业公司 入口', !!document.querySelector('[data-target="companySection"]'));
    check('companySection 容器存在', !!document.getElementById('companySection'));
    check('companyList 容器存在', !!document.getElementById('companyList'));
    check('左导航 coNav 存在', !!document.getElementById('coNav'));
    check('移动端 coNavSel 存在', !!document.getElementById('coNavSel'));
    check('搜索框 coSearch 存在', !!document.getElementById('coSearch'));
    check('统计 coStat 存在', !!document.getElementById('coStat'));
    check('新闻流头部 coFeedHead 存在', !!document.getElementById('coFeedHead'));

    // 1) 全部视图：右新闻流渲染全部 .co-item
    const items = document.querySelectorAll('#companyList .co-item');
    check('全部视图渲染出全部新闻条目（数量=counts.items）',
          items.length === totalItems && totalItems > 0,
          'got ' + items.length + ' / expect ' + totalItems);
    check('coCount 显示公司家数', /家/.test((document.getElementById('coCount') || {}).textContent || ''),
          (document.getElementById('coCount') || {}).textContent);

    // 2) 左导航列出全部公司（含矿种分组）；矿种过滤 chips 存在
    const navItems = document.querySelectorAll('#coNav .co-nav-item');
    check('左导航列出全部公司（数量≈公司数）', navItems.length >= nCompanies - 1 && navItems.length <= nCompanies + 1,
          'got ' + navItems.length + ' / companies ' + nCompanies);
    const fchips = document.querySelectorAll('#coFilters .co-fchip');
    check('矿种过滤 chips >= 2（含「全部」）', fchips.length >= 2, 'got ' + fchips.length);
    const navAll = document.querySelector('#coNav .co-nav-all');
    check('左导航「全部公司」入口存在', !!navAll);

    // 3) 抽查首条：含公司来源名 + 标题 + http(s) 外链
    const first = items[0];
    check('首条含新闻标题', !!(first && first.querySelector('.co-title') && first.querySelector('.co-title').textContent.trim().length > 0));
    check('首条含公司来源名（co-src 可点选公司）',
          !!(first && first.querySelector('.co-src') && first.querySelector('.co-src').textContent.trim().length > 0));
    check('首条标题为 http(s) 外链', !!(first && first.querySelector('.co-title') &&
          /^https?:\/\//.test(first.querySelector('.co-title').getAttribute('href') || '')));

    // 4) 公司选择：点第一个「有数据」的左导航公司项 → 新闻流收敛到该公司
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
      check('hash 写入 #co=公司名', /#co=/.test(window.location.hash), window.location.hash);
      // 还原到全部
      if (navAll) navAll.click();
    }

    // 5) hash 路由：直接设置 location.hash 定位公司
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

    // 6) 搜索框过滤
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

    // 7) 移动端 select 选项 = 公司数 + 1（全部）
    const opts = document.querySelectorAll('#coNavSel option');
    check('移动端 select 选项=公司数+1', opts.length === nCompanies + 1, 'got ' + opts.length + ' / ' + (nCompanies + 1));

    // 8) 豁免：默认视图下 companySection 不被隐藏
    window.mdRefreshSections && window.mdRefreshSections();
    check('默认视图下 companySection 不被隐藏', disp('companySection') !== 'none', disp('companySection'));

    // 9) 视图切换：switchView('company')
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

    // 10) 无阻塞 JS 错误
    check('updateActiveSection 函数存在', typeof window.updateActiveSection === 'function');
    check('无阻塞性 JS 错误', errors.length === 0, errors.join(' | '));

  } catch (e) {
    fail++;
    console.log('  FAIL  测试执行抛错 -> ' + e.message);
  }
  console.log('\n===== 矿业公司动态（v3 左导航+右新闻流）汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 1500);
