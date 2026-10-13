/**
 * 2026-10-13 矿业热榜打分重做（时效主导）回归测试（jsdom）
 *
 * 背景：旧公式 score = 来源权重×10 + max(0,30-天数×4) + 热词20/普通词5
 *   权重项最高 120 分、时效项最高 30 分且 8 天以上归零 ⇒ 自然资源部（权重 12）
 *   任何一条旧稿保底 120 分，把当日新稿（最多 60 分）永远挤出前 5，
 *   热榜长期停在 9 月的稿子上 —— 即用户报的「矿业热榜好久没更新」。
 *
 * 覆盖：① 参数与函数就位 ② 程序性公告降噪（不误伤官方新闻）
 *       ③ 时效闸门 ④ 来源多样性 ⑤ 时效主导（旧算法必然失败的硬断言）
 *       ⑥ 换一换仍可用
 * 运行：node test_hotrank_20261013.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
['news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  const tag = new RegExp('<script src="' + f + '[^>]*></script>');
  html = html.replace(tag, () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
});
{
  const p = path.join(__dirname, 'app.js');
  if (fs.existsSync(p)) {
    html = html.replace(new RegExp('<script src="app.js"[^>]*></script>'), '');
    html = html.replace('</body>', '<script>' + fs.readFileSync(p, 'utf-8') + '</script>\n</body>');
  }
}

const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'https://pliucugb-cyber.github.io/mining-daily/',
  beforeParse(win) {
    if (typeof win.matchMedia !== 'function') {
      win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    }
    if (typeof win.fetch !== 'function') {
      win.fetch = () => Promise.reject(new Error('jsdom: fetch stub'));
    }
  }
});
const { window } = dom;
const doc = window.document;

let pass = 0, fail = 0;
// 编号跑进方括号：run_tests_all.py 的「PASS + 数字」计数正则会把 "PASS 1a" 里的 1 当成通过数
function check(name, cond, detail) {
  const label = String(name).replace(/^(\S+)\s/, '[$1] ');
  if (cond) { pass++; console.log('  PASS  ' + label + (detail ? '  → ' + detail : '')); }
  else { fail++; console.log('  FAIL  ' + label + (detail ? '  → ' + detail : '')); }
}
function todayStr() {
  const n = new Date();
  return n.getFullYear() + '-' + String(n.getMonth() + 1).padStart(2, '0') + '-' + String(n.getDate()).padStart(2, '0');
}

setTimeout(() => {
  const REPORT = (typeof window.qaReportDate === 'function' && window.qaReportDate()) || todayStr();
  const anchor = new Date(REPORT + 'T00:00:00');
  function dayDiff(d) {
    const x = new Date(String(d) + 'T00:00:00');
    if (isNaN(x.getTime())) return 9999;
    return Math.round((anchor - x) / 86400000);
  }

  const MAX_AGE = window.HOT_MAX_AGE, FALLBACK = window.HOT_FALLBACK_AGE, CAP = window.HOT_SRC_CAP;
  const pool = window.__hotPool || [];

  console.log('\n[1] 参数与函数就位   报告日=' + REPORT);
  check('1a 闸门/多样性常量已定义', MAX_AGE === 14 && FALLBACK === 30 && CAP === 2,
        'MAX_AGE=' + MAX_AGE + ' FALLBACK=' + FALLBACK + ' CAP=' + CAP);
  check('1b mdHotIsNoise / computeHotNewsLocal 已就位',
        typeof window.mdHotIsNoise === 'function' && typeof window.computeHotNewsLocal === 'function');
  check('1c 候选池非空', pool.length > 0, 'pool=' + pool.length);

  console.log('\n[2] 程序性公告降噪');
  check('2a 矿权挂牌出让成交结果公示 → 过滤',
        window.mdHotIsNoise({ s: '矿业权市场', t: '辽宁省北票市长皋沟金矿普查探矿权网上挂牌出让成交结果公示' }) === true);
  check('2b 采矿权转让公示 → 过滤',
        window.mdHotIsNoise({ s: '矿业权市场', t: '北票市富贵鸟矿业有限公司采矿权转让公示' }) === true);
  check('2c 【探矿权·变更登记】→ 过滤',
        window.mdHotIsNoise({ s: '矿业权市场·登记结果', t: '【探矿权·变更登记】内蒙古呼伦贝尔市扎兰屯市庙尔山锌多金属矿勘探（锌矿）' }) === true);
  check('2d 官方重大成果（含「突破/战略」）→ 放行',
        window.mdHotIsNoise({ s: '自然资源部', t: '新一轮找矿突破战略行动再获标志性成果' }) === false);
  check('2e 自然资源部专家库名单公示 → 放行（不误伤官方）',
        window.mdHotIsNoise({ s: '自然资源部', t: '自然资源部公示矿业权出让权限非油气矿产勘查方案评审专家库名单' }) === false);
  check('2f 行业媒体新闻 → 放行',
        window.mdHotIsNoise({ s: 'SMM 国际站', t: '津巴布韦前三季度锂产品出口额突破 21.59 亿美元' }) === false);
  const noiseInPool = pool.filter(x => /^矿业权市场/.test(x.s) && /公示\s*$|公告\s*$|变更登记|登记结果/.test(x.t));
  check('2g 候选池内无矿权程序性公告', noiseInPool.length === 0, '命中=' + noiseInPool.length);

  console.log('\n[3] 时效闸门');
  const over = pool.filter(x => dayDiff(x.d) > FALLBACK);
  check('3a 池内无超过兜底闸门(' + FALLBACK + '天)的条目', over.length === 0,
        over.length ? '越界示例: ' + over.slice(0, 2).map(x => x.d + ' ' + x.t.slice(0, 16)).join(' | ') : '0 条越界');

  console.log('\n[4] 来源多样性');
  const per = {};
  pool.forEach(x => { per[x.s] = (per[x.s] || 0) + 1; });
  const maxPer = Math.max.apply(null, Object.keys(per).map(k => per[k]));
  check('4a 同一来源在候选池中不超过 ' + CAP + ' 条', maxPer <= CAP, '最大来源=' + maxPer + ' 条');
  const topSrc = Object.keys(per).sort((a, b) => per[b] - per[a]).slice(0, 3).map(k => k + '×' + per[k]);
  console.log('       池内主要来源: ' + topSrc.join(', '));

  console.log('\n[5] 时效主导（旧算法必然失败的硬断言）');
  const within7 = pool.filter(x => dayDiff(x.d) <= 7).length;
  const within14 = pool.filter(x => dayDiff(x.d) <= 14).length;
  const freshRatio = pool.length ? within7 / pool.length : 0;
  check('5a 池内「≤7天」条目占比 ≥ 50%', freshRatio >= 0.5,
        within7 + '/' + pool.length + ' = ' + (freshRatio * 100).toFixed(0) + '%');
  check('5b 池内「>14天」条目数为 0（闸门严格生效）', within14 === pool.length,
        '>14天=' + (pool.length - within14) + ' 条');
  const shown = [...doc.querySelectorAll('#hotListBody li.hot-item')];
  check('5c 榜单已渲染条目', shown.length > 0, '显示=' + shown.length + ' 条');
  if (shown.length) {
    const first = shown[0];
    const firstDate = ((first.querySelector('.hot-meta span:nth-child(2)') || {}).textContent || '').replace(/^[\s·]+/, '');
    const fy = REPORT.slice(0, 4) + '-' + firstDate.slice(0, 5);
    check('5d 榜首条目距今 ≤ 14 天', dayDiff(fy) <= 14, '榜首日期=' + fy + '（距今 ' + dayDiff(fy) + ' 天）');
  }

  console.log('\n[6] 换一换仍可用');
  const btn = doc.getElementById('hotRefreshBtn');
  const pages = Math.ceil(pool.length / window.mdHotCount()) || 1;
  check('6a 候选池可支撑多页轮换', pool.length > window.mdHotCount(), 'pool=' + pool.length + ' pages=' + pages);
  check('6b 换一换按钮可见', !!btn && btn.style.display !== 'none');
  const before = [...doc.querySelectorAll('#hotListBody .hot-title')].map(a => a.textContent).join('|');
  try { window.hotShuffle(); } catch (e) { check('6c hotShuffle 可调用', false, String(e)); }
  const after = [...doc.querySelectorAll('#hotListBody .hot-title')].map(a => a.textContent).join('|');
  check('6c 换一换后内容发生变化', pages > 1 ? before !== after : true, 'pages=' + pages);

  console.log('\n===== 热榜回归测试：' + pass + ' 通过 / ' + fail + ' 失败 =====');
  process.exit(fail ? 1 : 0);
}, 900);
