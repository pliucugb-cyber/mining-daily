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
    // 预设 localStorage 收藏
    const sampleFavs = [
      { url: 'https://example.com/fav1', title: '收藏测试1', src: '测试源', date: '09-09' },
      { url: 'https://example.com/fav2', title: '收藏测试2', src: '测试源', date: '09-08' }
    ];
    window.localStorage.setItem('mining_daily_favorites', JSON.stringify(sampleFavs));
    const sampleHistory = [
      { url: 'https://example.com/hist1', title: '历史测试1', src: '测试源', time: new Date('2026-09-09T10:00:00').toISOString() },
      { url: 'https://example.com/hist2', title: '历史测试2', src: '测试源', time: new Date('2026-09-08T10:00:00').toISOString() }
    ];
    window.localStorage.setItem('mining_daily_history', JSON.stringify(sampleHistory));

    check('renderFavHistoryAggregate 函数存在', typeof window.renderFavHistoryAggregate === 'function');

    // 1) fav 聚合视图
    window.setFilter('fav', true);
    check('fav 模式下 todaySection 隐藏', disp('todaySection') === 'none', disp('todaySection'));
    check('fav 模式下 archiveSection 隐藏', disp('archiveSection') === 'none', disp('archiveSection'));
    check('fav 模式下 archivedFavSection 显示', disp('archivedFavSection') !== 'none', disp('archivedFavSection'));
    const favListCount = document.getElementById('archFavList').querySelectorAll('.news-item').length;
    check('fav 聚合列表条目数 = fav 总数（含归档2条）', favListCount === 2, 'count=' + favListCount);
    const favTitle = document.querySelector('#archivedFavSection .section-title').childNodes[0].textContent;
    check('fav 聚合区标题为「我的收藏」', favTitle.indexOf('我的收藏') >= 0, favTitle);

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
    check('history 聚合列表条目数 = history 总数（含归档2条）', histListCount === 2, 'count=' + histListCount);
    const histTitle = document.querySelector('#archivedFavSection .section-title').childNodes[0].textContent;
    check('history 聚合区标题为「浏览记录」', histTitle.indexOf('浏览记录') >= 0, histTitle);

    check('无阻塞性 JS 错误', errors.length === 0, errors.join(' | '));
  } catch (e) {
    fail++;
    console.log('  FAIL  测试执行抛错 → ' + e.message);
  }
  console.log('\n===== 收藏/历史聚合视图汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 600);
