/**
 * 2026-09-13 矿权登记结果（kyreg_tk / kyreg_ck）前端渲染契约测试（jsdom）。
 *
 * 验证：登记数据进入矿权专区后，走独立的 register 分支渲染，
 *   - 不再以 other 混入交易卡片、不再满屏「—」；
 *   - 卡片展示 矿种 / 面积 / 有效期 / 权利人，底部显示 发证机关；
 *   - 仍与既有 出让/转让/结果 卡片共存，且 .rr-amount 条数 == 行数（§42.3 契约）；
 *   - 用 method="登记" 可单独筛出登记条目。
 * 不依赖网络：自定义 NEWS_DATA 注入。
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const HERE = __dirname;

function buildHtml() {
  let html = fs.readFileSync(path.join(HERE, 'index.html'), 'utf-8');
  // 注入自定义矿权数据，替换 news-data.js（不读真实大文件）
  const reg = new RegExp('<script src="news-data.js"[^>]*></script>');
  html = html.replace(reg, '<script>window.NEWS_DATA=' + JSON.stringify(MY_DATA) + ';</script>');
  // lme-data / price-history 若存在则内联，否则删标签（避免 404 噪声）
  ['lme-data.js', 'price-history.js'].forEach(f => {
    const tag = new RegExp('<script src="' + f + '"[^>]*></script>');
    const p = path.join(HERE, f);
    if (fs.existsSync(p)) html = html.replace(tag, () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
    else html = html.replace(tag, '');
  });
  // app.js 移到 </body> 前（等价 defer 语义），删原带 onerror 的标签
  const ap = path.join(HERE, 'app.js');
  html = html.replace(new RegExp('<script src="app.js"[^>]*></script>'), '');
  html = html.replace('</body>', '<script>' + fs.readFileSync(ap, 'utf-8') + '</script>\n</body>');
  return html;
}

const MY_DATA = {
  updated: '2026-09-13 08:00:00',
  schema: '1.2-slim',
  total: 3,
  news: [
    {
      d: '2026-09-09', t: '【探矿权·变更登记】某某铅锌多金属矿勘探（铅矿）',
      s: '矿业权市场·登记结果', u: 'https://ky.mnr.gov.cn/dj/tk/?lic=T100000202509210001',
      g: ['铅', '锌'], c: '矿权市场',
      m: '许可证号 T100000202509210001｜探矿权人 新疆某某勘查开发有限公司｜面积 0.57530｜有效期 2026-09-08至2046-09-07｜发证机关 自然资源部｜地理位置 新疆阿勒泰地区富蕴县',
      n: '2026-09-09'
    },
    {
      d: '2026-09-10', t: '【采矿权·首次登记】某某铜矿（铜矿）',
      s: '矿业权市场·登记结果', u: 'https://ky.mnr.gov.cn/dj/ck/?lic=C100000202509210002',
      g: ['铜'], c: '矿权市场',
      m: '许可证号 C100000202509210002｜采矿权人 某某矿业开发有限责任公司｜面积 1.23456｜有效期 2026-09-10至2056-09-09｜发证机关 新疆维吾尔自治区自然资源厅',
      n: '2026-09-10'
    },
    {
      d: '2026-09-10', t: '某某铅锌矿采矿权挂牌出让公告',
      s: '矿业权市场', u: 'https://ky.mnr.gov.cn/kyqcrgg/ckq/202609/t20260910_10310000.htm',
      g: ['铅', '锌'], c: '矿权市场',
      m: '起始价1000.0万元，竞买保证金200.0万元，面积10.500000平方千米，挂牌期2026年09月10日 至 2026年09月30日。',
      n: '2026-09-10'
    }
  ]
};

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
  console.log('===== 矿权登记结果渲染（register 分支） =====');
  const all = doc.querySelectorAll('#rightsCards .rights-row');
  check('矿权卡片共渲染 3 行', all.length === 3, '行数=' + all.length);

  const regRows = doc.querySelectorAll('#rightsCards .rights-row[data-method="登记"]');
  check('登记条目 method=登记 共 2 行', regRows.length === 2, '登记行数=' + regRows.length);

  // 登记卡片不得满屏「—」：两张登记卡片各自的 有效期/权利人/矿种/发证机关 都应有真实值
  const validityRe = /\d{4}-\d{2}-\d{2}至\d{4}-\d{2}-\d{2}/;
  const holderRe = /权利人<\/span><b[^>]*>([^<]+)</;
  const mineralRe = /矿种<\/span><b[^>]*>([^<]+)</;
  const authRe = /发证机关：([^<]+)</;
  let regAllOk = true, regDetail = '';
  regRows.forEach(r => {
    const t = r.textContent;
    const hm = r.innerHTML.match(holderRe);
    const mm = r.innerHTML.match(mineralRe);
    const am = r.innerHTML.match(authRe);
    const ok = /有效期/.test(t) && validityRe.test(t) && /权利人/.test(t)
      && hm && hm[1] && hm[1] !== '—'
      && mm && mm[1] && mm[1] !== '—'
      && am && am[1] && am[1] !== '—';
    if (!ok) { regAllOk = false; regDetail = t.slice(0, 100); }
  });
  check('两张登记卡片：有效期/权利人/矿种/发证机关 均非空', regAllOk, regDetail);
  // 类型标签（取含探矿权许可证的那张）
  const tkRow = Array.from(regRows).find(r => /探矿权·/.test(r.textContent));
  check('登记卡片类型标签=登记结果', tkRow && tkRow.querySelector('.rr-type')
    && tkRow.querySelector('.rr-type').textContent === '登记结果', tkRow && tkRow.querySelector('.rr-type').textContent);
  check('探矿权登记卡片矿种=铅矿', tkRow && mineralRe.test(tkRow.innerHTML)
    && tkRow.innerHTML.match(mineralRe)[1] === '铅矿');
  // 底部发证机关（探矿权=自然资源部）
  check('探矿权登记卡片底部显示 发证机关：自然资源部', tkRow && authRe.test(tkRow.innerHTML)
    && tkRow.innerHTML.match(authRe)[1] === '自然资源部');

  // 交易卡片仍正常（非登记条目走 listing 分支）
  const listRow = doc.querySelector('#rightsCards .rights-row[data-method="挂牌"]');
  check('交易卡片（挂牌）仍渲染且含起始价', listRow && /1,000 万元/.test(listRow.textContent), listRow && listRow.textContent.slice(0, 60));

  // 金额 pill 条数 == 行数（§42.3 契约：每行一个 .rr-amount）
  const amtEls = doc.querySelectorAll('#rightsCards .rights-row .rr-amount');
  check('金额 pill 条数 == 卡片行数', amtEls.length === all.length, 'amt=' + amtEls.length + ' rows=' + all.length);
  // 登记卡片金额 pill 为「—」（无交易价，契约允许）
  const regAmt = tkRow ? tkRow.querySelector('.rr-amount') : null;
  check('登记卡片金额 pill 显示「—」', regAmt && /—/.test(regAmt.textContent), regAmt && regAmt.textContent);

  // 筛选 method=登记：只留登记条目
  const fm = doc.getElementById('rightsFilterMethod');
  if (fm) {
    fm.value = '登记';
    // 触发 change（app.js 已 bindRights 监听）
    fm.dispatchEvent(new window.Event('change', { bubbles: true }));
    const after = doc.querySelectorAll('#rightsCards .rights-row');
    check('筛选「登记结果」后仅剩 2 行', after.length === 2, '剩=' + after.length);
    fm.value = '';
    fm.dispatchEvent(new window.Event('change', { bubbles: true }));
  } else {
    check('rightsFilterMethod 存在', false);
  }

  // 矿种筛选（铜）应命中登记铜矿：先确认登记铜矿在全部数据里
  const fmin = doc.getElementById('rightsFilterMineral');
  if (fmin) {
    fmin.value = '铜';
    fmin.dispatchEvent(new window.Event('change', { bubbles: true }));
    const cu = doc.querySelectorAll('#rightsCards .rights-row');
    check('矿种筛选「铜」命中采矿权登记铜矿（1 行）', cu.length === 1, '命中=' + cu.length);
    fmin.value = '';
    fmin.dispatchEvent(new window.Event('change', { bubbles: true }));
  }

  // 数据层错误不应出现（仅记录，不计入失败）
  if (errors.length) console.log('  [info] 非矿权相关 console 错误 ' + errors.length + ' 条：' + errors.slice(0, 3).join(' | '));

  console.log('-'.repeat(40));
  console.log('PASS=' + pass + '  FAIL=' + fail);
  process.exit(fail ? 1 : 0);
}, 400);
