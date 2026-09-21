/**
 * 2026-09-14 矿业公司动态（官网新闻流）运行时渲染回归（jsdom，v2）
 * 覆盖：① fetch 根目录 company_news.json 并渲染扁平 .co-item 新闻流 + 概要 chips + 矿种过滤 chips
 *       ② #companySection 在 refreshSectionVisibility 下不被隐藏（豁免）
 *       ③ switchView('company') 设置 data-view=company 且隐藏其它主区块、显示公司区
 *       ④ 左侧目录存在 🏢 矿业公司 入口（data-target=companySection）
 *       ⑤ 矿种过滤 chip 点击后新闻流按矿种收敛
 *       ⑥ 无阻塞 JS 错误
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
    // 0) 入口与容器存在
    check('目录含 🏢 矿业公司 入口', !!document.querySelector('[data-target="companySection"]'));
    check('companySection 容器存在', !!document.getElementById('companySection'));
    check('companyList 容器存在', !!document.getElementById('companyList'));

    // 1) 运行时渲染：扁平新闻流 .co-item + 概要 chips + 矿种过滤 chips
    const items = document.querySelectorAll('#companyList .co-item');
    check('渲染出扁平新闻条目（数量=counts.items）', items.length === totalItems && totalItems > 0,
          'got ' + items.length + ' / expect ' + totalItems);
    const chips = document.querySelectorAll('#coSummary .co-chip');
    check('概要 chips >= 4', chips.length >= 4, 'got ' + chips.length);
    const fchips = document.querySelectorAll('#coFilters .co-fchip');
    check('矿种过滤 chips >= 2（含「全部」）', fchips.length >= 2, 'got ' + fchips.length);
    const coCount = (document.getElementById('coCount') || {}).textContent || '';
    check('coCount 显示公司家数', /家/.test(coCount), coCount);
    // 抽查：首条含公司名 + 标题 + http(s) 外链
    const first = items[0];
    const titleOk = first && first.querySelector('.co-title') && first.querySelector('.co-title').textContent.trim().length > 0;
    check('首条含新闻标题', !!titleOk);
    const srcOk = first && first.querySelector('.co-src') && first.querySelector('.co-src').textContent.trim().length > 0;
    check('首条含公司来源名', !!srcOk);
    const linkOk = first && first.querySelector('.co-title') &&
                   /^https?:\/\//.test(first.querySelector('.co-title').getAttribute('href') || '');
    check('首条标题为 http(s) 外链', !!linkOk);

    // 2) 矿种过滤：点第一个非「全部」chip，新闻流应只剩该矿种
    let filteredOk = true, filName = '';
    for (const fc of fchips) {
      if (fc.getAttribute('data-sec') !== '__all__') { filName = fc.getAttribute('data-sec'); fc.click(); break; }
    }
    if (filName) {
      const after = document.querySelectorAll('#companyList .co-item');
      // 每条 .co-cat 都应为该矿种
      let allMatch = true;
      after.forEach(it => { if ((it.querySelector('.co-cat') || {}).textContent !== filName) allMatch = false; });
      check('矿种过滤后新闻流收敛到「' + filName + '」', after.length > 0 && allMatch,
            'got ' + after.length + ' match=' + allMatch);
      // 还原
      const allChip = document.querySelector('#coFilters .co-fchip[data-sec="__all__"]');
      if (allChip) allChip.click();
    } else {
      check('矿种过滤可用（存在非全部 chip）', false, '无');
    }

    // 3) 豁免：refreshSectionVisibility 不隐藏 companySection（默认视图）
    window.mdRefreshSections && window.mdRefreshSections();
    check('默认视图下 companySection 不被隐藏', disp('companySection') !== 'none', disp('companySection'));

    // 4) 视图切换：switchView('company')
    const coItem = document.querySelector('[data-target="companySection"]');
    window.switchView('company', coItem);
    check('switchView("company") 设置 data-view=company', document.body.dataset.view === 'company', document.body.dataset.view);
    check('公司区在公司视图可见', disp('companySection') !== 'none', disp('companySection'));
    check('今日区在公司视图隐藏', disp('todaySection') === 'none', disp('todaySection'));
    check('矿权区在公司视图隐藏', disp('rightsSection') === 'none', disp('rightsSection'));
    check('右栏在公司视图隐藏', window.getComputedStyle(document.querySelector('.col-rail')).display === 'none');
    check('公司入口获得 active 高亮', coItem.classList.contains('active'));

    // 5) 再次点击同一项 -> 回到全部
    window.switchView('company', coItem);
    check('再次点击回到全部（data-view 清除）', !document.body.dataset.view, document.body.dataset.view);
    check('companySection 回到全部后可见', disp('companySection') !== 'none', disp('companySection'));

    // 6) 无阻塞 JS 错误
    check('updateActiveSection 函数存在', typeof window.updateActiveSection === 'function');
    check('无阻塞性 JS 错误', errors.length === 0, errors.join(' | '));

  } catch (e) {
    fail++;
    console.log('  FAIL  测试执行抛错 -> ' + e.message);
  }
  console.log('\n===== 矿业公司动态（官网新闻流）汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 1200);
