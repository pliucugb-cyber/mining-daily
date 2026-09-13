/**
 * 2026-09-13 事件·数据日历（轻量版）前端渲染契约测试（jsdom）。
 *
 * 验证：
 *  - #eventCalendar 为 index.html 静态容器（重建边界：兄弟节点，不被生成脚本抹掉）；
 *  - 从新闻标题派生事件（事件词 + 可解析日期），无日期的标题不进日历；
 *  - 未来项 .ec-upcoming（≤90 天带「即将」）、过去项 .ec-past 淡化；
 *  - 按日期组织：未来升序在前、过去降序在后；
 *  - 类型标签（会议/政策/数据/截止）、外链、来源渲染正确；
 *  - 空数据 → 占位「暂无已收录的近期事件」（不用「今日暂无」，避免与简报口径打架）。
 * 不依赖网络：自定义 NEWS_DATA 注入。
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const HERE = __dirname;

const MY_DATA = {
  updated: '2026-09-13 08:00:00',
  meta: { report_date: '2026-09-13' },
  schema: '1.2-slim',
  total: 5,
  news: [
    { t: '2项镁行业新标准获批 2027年3月1日起实施', u: 'https://x/y1', s: '政策与监管' },
    { t: '2026中国国际矿业大会将于9月10日开幕', u: 'https://x/y2', s: '行业动态' },
    { t: '2026年9月20日 中国有色金属论坛将在北京召开', u: 'https://x/y3', s: '行业动态' },
    { t: '云铝股份召开深化一本部多基地改革推进会', u: 'https://x/y4', s: '行业动态' }, // 有事件词但无日期 → 排除
    { t: '7月份美国铜进口量创历史新高', u: 'https://x/y5', s: '市场与价格' }            // 无事件词无日期 → 排除
  ]
};

function buildHtml() {
  let html = fs.readFileSync(path.join(HERE, 'index.html'), 'utf-8');
  const reg = new RegExp('<script src="news-data.js"[^>]*></script>');
  html = html.replace(reg, '<script>window.NEWS_DATA=' + JSON.stringify(MY_DATA) + ';</script>');
  ['lme-data.js', 'price-history.js'].forEach(f => {
    const tag = new RegExp('<script src="' + f + '"[^>]*></script>');
    const p = path.join(HERE, f);
    if (fs.existsSync(p)) html = html.replace(tag, () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
    else html = html.replace(tag, '');
  });
  const ap = path.join(HERE, 'app.js');
  html = html.replace(new RegExp('<script src="app.js"[^>]*></script>'), '');
  html = html.replace('</body>', '<script>' + fs.readFileSync(ap, 'utf-8') + '</script>\n</body>');
  return html;
}

const html = buildHtml();
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
    win.addEventListener('error', e => errors.push('window.error: ' + (e.message || e.error)));
    const oe = win.console.error;
    win.console.error = (...a) => { errors.push('console.error: ' + a.join(' ')); oe.apply(win.console, a); };
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
  console.log('===== 事件·数据日历（轻量版）渲染 =====');

  // 1. 静态容器存在（重建边界）
  check('index.html 含静态容器 #eventCalendar', !!doc.getElementById('eventCalendar'));
  check('含 .ec-body 填充槽', !!doc.getElementById('ecBody'));

  const rows = doc.querySelectorAll('#ecBody .ec-row');
  check('渲染行数 == 3（无日期项已排除）', rows.length === 3, 'rows=' + rows.length);

  // 2. 顺序：未来升序在前（09-20 → 2027-03-01），后接过去（09-10）
  const titles = Array.from(rows).map(r => r.querySelector('.ec-title').textContent);
  check('首行=9月20日有色金属论坛（未来·最近）', /9月20日/.test(titles[0]), titles[0]);
  check('次行=2027年3月1日镁标准（未来·远）', /2027年3月1日/.test(titles[1]), titles[1]);
  check('末行=9月10日矿业大会（过去）', /9月10日/.test(titles[2]), titles[2]);

  // 3. 未来/过去 分类
  check('前两行为 .ec-upcoming', rows[0].classList.contains('ec-upcoming') && rows[1].classList.contains('ec-upcoming'));
  check('末行为 .ec-past（淡化）', rows[2].classList.contains('ec-past'));

  // 4. 「即将」仅 ≤90 天（09-20 差 7 天；2027-03-01 差 ~169 天不标）
  check('09-20 行带「即将」徽标', !!rows[0].querySelector('.ec-soon') && /即将/.test(rows[0].textContent));
  check('2027-03-01 行不带「即将」（>90天）', !rows[1].querySelector('.ec-soon'));

  // 5. 类型标签
  check('09-20 行类型=会议（t-meeting）', rows[0].querySelector('.ec-tag.t-meeting') && /会议/.test(rows[0].querySelector('.ec-tag').textContent));
  check('2027-03-01 行类型=政策（t-policy）', rows[1].querySelector('.ec-tag.t-policy') && /政策/.test(rows[1].querySelector('.ec-tag').textContent));

  // 6. 外链正确（target=_blank、href 命中）
  const a0 = rows[0].querySelector('.ec-title a');
  check('事件标题为外链且 target=_blank', a0 && a0.getAttribute('target') === '_blank' && /y3/.test(a0.getAttribute('href')), a0 && a0.getAttribute('href'));
  const a1 = rows[1].querySelector('.ec-title a');
  check('政策事件外链命中 y1', a1 && /y1/.test(a1.getAttribute('href')));

  // 7. 排除项不出现
  check('无日期的「云铝股份召开」未进日历', doc.getElementById('ecBody').textContent.indexOf('云铝股份召开') < 0);
  check('无事件词的「美国铜进口」未进日历', doc.getElementById('ecBody').textContent.indexOf('美国铜进口') < 0);

  // 8. 计数
  const cnt = doc.getElementById('ecCount');
  check('news-count 显示「3条」', cnt && cnt.textContent === '3条', cnt && cnt.textContent);

  // 9. 空数据占位（不用「今日暂无」）
  try {
    window.NEWS_DATA.news = [];
    window.__mdEventCalendar.render();
    const empty = doc.getElementById('ecBody').querySelector('.ec-empty');
    check('空数据 → 占位「暂无已收录的近期事件」', empty && /暂无已收录的近期事件/.test(empty.textContent), empty && empty.textContent);
    check('空数据占位不含「今日暂无」（避免与简报口径打架）', empty && empty.textContent.indexOf('今日暂无') < 0);
  } catch (e) { check('空数据占位渲染', false, e.message); }

  if (errors.length) console.log('  [info] 非日历相关 console 错误 ' + errors.length + ' 条：' + errors.slice(0, 3).join(' | '));

  console.log('-'.repeat(40));
  console.log('PASS=' + pass + '  FAIL=' + fail);
  process.exit(fail ? 1 : 0);
}, 500);
