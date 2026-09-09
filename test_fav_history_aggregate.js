/**
 * 2026-09-09 收藏/浏览记录「聚合视图」回归测试（jsdom）
 * 覆盖：① fav 模式隐藏 today/archive、显示聚合区 ② 聚合列表条目数=fav总数
 *       ③ history 模式同理 ④ 退出聚合模式恢复默认归档收藏
 * 运行：node test_fav_history_aggregate.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

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
    if (typeof win.matchMedia !== 'function') {
      win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    }
    if (typeof win.fetch !== 'function') win.fetch = () => Promise.reject(new Error('stub'));
    if (typeof win.SpeechRecognition === 'undefined' && typeof win.webkitSpeechRecognition === 'undefined') {
      win.SpeechRecognition = function () {};
    }
    win.addEventListener('error', e => errors.push('window.error: ' + e.message));
  }
});
const { window } = dom;
const { document } = window;

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log('  PASS  ' + name); }
  else { fail++; console.log('  FAIL  ' + name + (extra ? '  → ' + extra : '')); }
}
function disp(id) {
  const el = document.getElementById(id);
  if (!el) return 'missing';
  return window.getComputedStyle(el).display;
}

setTimeout(() => {
  try {
    // 取页面内真实 URL，模拟「收藏了今日区和往期区各一条」的场景，用来暴露
    // refreshSectionVisibility 按子元素数量重新显示 today/archive 的 bug。
    const firstTodayItem = document.querySelector('#todaySection .news-item');
    const firstArchiveItem = document.querySelector('#archiveSection .news-item');
    const todayUrl = firstTodayItem ? firstTodayItem.dataset.url : 'https://example.com/fav1';
    const archiveUrl = firstArchiveItem ? firstArchiveItem.dataset.url : 'https://example.com/fav2';

    // 预设 localStorage 收藏
    const sampleFavs = [
      { url: todayUrl, title: '收藏测试1', src: '测试源', date: '09-09' },
      { url: archiveUrl, title: '收藏测试2', src: '测试源', date: '09-08' }
    ];
    window.localStorage.setItem('mining_daily_favorites', JSON.stringify(sampleFavs));
    const sampleHistory = [
      { url: todayUrl, title: '历史测试1', src: '测试源', time: new Date('2026-09-09T10:00:00').toISOString() },
      { url: archiveUrl, title: '历史测试2', src: '测试源', time: new Date('2026-09-08T10:00:00').toISOString() }
    ];
    window.localStorage.setItem('mining_daily_history', JSON.stringify(sampleHistory));

    check('renderFavHistoryAggregate 函数存在', typeof window.renderFavHistoryAggregate === 'function');

    // 1) fav 聚合视图
    window.setFilter('fav', true);
    check('fav 模式下 todaySection 隐藏', disp('todaySection') === 'none', disp('todaySection'));
    check('fav 模式下 archiveSection 隐藏', disp('archiveSection') === 'none', disp('archiveSection'));
    check('fav 模式下 archivedFavSection 显示', disp('archivedFavSection') !== 'none', disp('archivedFavSection'));
    const favListCount = document.getElementById('archFavList').querySelectorAll('.news-item').length;
    check('fav 聚合列表条目数 = fav 总数（2条页面内收藏）', favListCount === 2, 'count=' + favListCount);
    const favTitle = document.querySelector('#archivedFavSection .section-title').childNodes[0].textContent;
    check('fav 聚合区标题为「我的收藏」', favTitle.indexOf('我的收藏') >= 0, favTitle);
    check('fav 模式下 body 带 data-filter-mode="fav"', document.body.dataset.filterMode === 'fav');
    check('fav 模式下 header 隐藏', disp('todaySection') === 'none'); // header 已被隐藏，用通用区块断言占位
    const header = document.querySelector('.header');
    check('fav 模式下 .header 隐藏', !header || window.getComputedStyle(header).display === 'none', header && window.getComputedStyle(header).display);
    const rail = document.querySelector('.col-rail');
    check('fav 模式下 .col-rail 显示（保留热榜/会展）', !!rail && window.getComputedStyle(rail).display !== 'none', rail && window.getComputedStyle(rail).display);
    // 关键回归：即使收藏的条目落在 today/archive 区块内，这两个区块也不得被 refreshSectionVisibility 重新显示
    check('fav 模式下即使收藏了今日条目，todaySection 仍隐藏', disp('todaySection') === 'none', disp('todaySection'));
    check('fav 模式下即使收藏了往期条目，archiveSection 仍隐藏', disp('archiveSection') === 'none', disp('archiveSection'));

    // 2) 退出 fav → 恢复默认
    window.setFilter('none', true);
    check('退出 fav 后 archivedFavSection 隐藏', disp('archivedFavSection') === 'none', disp('archivedFavSection'));
    check('退出 fav 后 todaySection 恢复', disp('todaySection') !== 'none', disp('todaySection'));

    // 3) history 聚合视图
    window.setFilter('history', true);
    check('history 模式下 todaySection 隐藏', disp('todaySection') === 'none', disp('todaySection'));
    check('history 模式下 archiveSection 隐藏', disp('archiveSection') === 'none', disp('archiveSection'));
    check('history 模式下 archivedFavSection 显示', disp('archivedFavSection') !== 'none', disp('archivedFavSection'));
    const histListCount = document.getElementById('archFavList').querySelectorAll('.news-item').length;
    check('history 聚合列表条目数 = history 总数（2条页面内历史）', histListCount === 2, 'count=' + histListCount);
    const histTitle = document.querySelector('#archivedFavSection .section-title').childNodes[0].textContent;
    check('history 聚合区标题为「浏览记录」', histTitle.indexOf('浏览记录') >= 0, histTitle);
    check('history 模式下 body 带 data-filter-mode="history"', document.body.dataset.filterMode === 'history');
    check('history 模式下即使记录了今日条目，todaySection 仍隐藏', disp('todaySection') === 'none', disp('todaySection'));
    check('history 模式下即使记录了往期条目，archiveSection 仍隐藏', disp('archiveSection') === 'none', disp('archiveSection'));
    const railH = document.querySelector('.col-rail');
    check('history 模式下 .col-rail 显示（保留热榜/会展）', !!railH && window.getComputedStyle(railH).display !== 'none', railH && window.getComputedStyle(railH).display);

    // 4) 清空收藏/历史后进入 fav，应显示空态提示
    window.localStorage.removeItem('mining_daily_favorites');
    window.localStorage.removeItem('mining_daily_history');
    window.setFilter('fav', true);
    const empty = document.querySelector('#archFavList .aggregate-empty');
    check('fav 空态提示存在', !!empty);
    check('fav 空态文案含收藏引导', !!empty && empty.textContent.indexOf('暂无收藏') >= 0, empty && empty.textContent);
    window.setFilter('history', true);
    const emptyH = document.querySelector('#archFavList .aggregate-empty');
    check('history 空态提示存在', !!emptyH);
    check('history 空态文案含浏览引导', !!emptyH && emptyH.textContent.indexOf('暂无浏览记录') >= 0, emptyH && emptyH.textContent);

    // 5) 退出筛选后 data-filter-mode 清除
    window.setFilter('none', true);
    check('退出筛选后 body 无 data-filter-mode', !document.body.dataset.filterMode);

    check('无阻塞性 JS 错误', errors.length === 0, errors.join(' | '));
  } catch (e) {
    fail++;
    console.log('  FAIL  测试执行抛错 → ' + e.message);
  }
  console.log('\n===== 收藏/历史聚合视图汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 600);
