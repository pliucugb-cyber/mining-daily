/**
 * 2026-09-13 价格区单位去重测试（jsdom + 静态契约）
 * 背景：用户反馈「分组标题已写 国内盘·人民币/吨、LME 外盘·美元/吨，每行价格后面
 *       再写一遍 元/吨 / 美元/吨 是重复」。
 * 契约（REFERENCE.md §42.11）：
 *   ① 与分组同单位的卡片，.pc-unit 加 .pc-unit-same（CSS display:none 隐藏重复单位）
 *   ② 与分组不同的单位（上海金 元/克、白银 元/千克）必须保持可见 —— 否则被误读成 /吨
 *   ③ 只隐藏、不删 DOM 文本 —— 价格 CSV 导出与预警解析仍读 .pc-unit
 *   ④ 分组标题声明单位：国内盘 · 人民币/吨
 * 运行：node test_price_unit_dedup.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const raw = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log('  PASS  ' + name); }
  else { fail++; console.log('  FAIL  ' + name + (extra ? '  -> ' + extra : '')); }
}

console.log('\n===== ① 静态契约（正则，不依赖渲染）=====');

// 同单位隐藏数量
const nShfe = (raw.match(/<div class="pc-unit pc-unit-same">元\/吨<\/div>/g) || []).length;
const nLme = (raw.match(/<div class="pc-unit pc-unit-same">美元\/吨<\/div>/g) || []).length;
check('① 国内盘 8 张卡的「元/吨」已标记隐藏', nShfe === 8, 'n=' + nShfe);
check('① LME 6 张卡的「美元/吨」已标记隐藏', nLme === 6, 'n=' + nLme);

// 异单位保留
check('② 上海金「元/克」单位可见（未加 same 类）',
  raw.includes('<div class="pc-unit">元/克</div>') &&
  !raw.includes('<div class="pc-unit pc-unit-same">元/克</div>'));
check('② 白银「元/千克」单位可见（未加 same 类）',
  raw.includes('<div class="pc-unit">元/千克</div>') &&
  !raw.includes('<div class="pc-unit pc-unit-same">元/千克</div>'));

// CSS 规则
check('① CSS 定义 .pc-unit-same{display:none}',
  /\.pc-unit-same\s*\{\s*display\s*:\s*none\s*\}/.test(raw));
check('① CSS 有 :has(.pc-unit-same) 列收窄规则',
  /\.price-card:has\(\.pc-unit-same\)\s*\{[^}]*grid-template-columns/.test(raw));
check('① 移动端断点也收窄（≤768px）',
  /@media\(max-width:768px\)\{\.price-card:has\(\.pc-unit-same\)/.test(raw));

// 分组标题
check('④ 国内盘标题声明单位「人民币/吨」',
  raw.includes("content:'国内盘 · 人民币/吨'"));
check('④ LME 标题声明单位「美元/吨」',
  raw.includes("content:'LME 外盘 · 美元/吨'"));

// ③ 文本保留（CSV 依赖）
const htmlOnly = raw;
const shfeSeg = htmlOnly.slice(htmlOnly.indexOf('id="priceCardsShfe"'), htmlOnly.indexOf('id="priceCardsLme"'));
check('③ 隐藏单位仍保留 DOM 文本（元/吨 出现 8 次）',
  (shfeSeg.match(/元\/吨/g) || []).length === 8,
  'n=' + (shfeSeg.match(/元\/吨/g) || []).length);

console.log('\n===== ② 运行时（jsdom：CSV 导出仍能读到单位）=====');

let html = raw;
['app.js', 'news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  html = html.replace(new RegExp('<script src="' + f + '[^>]*></script>'),
    () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
});

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true,
  url: 'https://pliucugb-cyber.github.io/mining-daily/',
  beforeParse(win) {
    if (typeof win.matchMedia !== 'function') {
      win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    }
    if (typeof win.fetch !== 'function') win.fetch = () => Promise.reject(new Error('stub'));
  }
});
const { window } = dom;
const doc = window.document;

setTimeout(() => {
  const shfe = doc.getElementById('priceCardsShfe');
  const lme = doc.getElementById('priceCardsLme');
  check('② 价格区两行容器存在', !!shfe && !!lme);

  // 每张卡仍有 .pc-unit 节点且 textContent 正确（CSS 只隐藏、不改文本）
  if (shfe) {
    const cards = shfe.querySelectorAll('.price-card');
    let unitOk = 0, sameOk = 0, keepUnit = 0;
    cards.forEach(c => {
      const u = c.querySelector('.pc-unit');
      if (!u) return;
      const txt = (u.textContent || '').trim();
      const isSame = u.classList.contains('pc-unit-same');
      if (txt === '元/吨' && isSame) sameOk++;
      if (txt === '元/克' || txt === '元/千克') { keepUnit++; if (isSame) unitOk = -999; }
    });
    check('③ 国内盘同单位卡（元/吨）都有 same 类', sameOk === 8, 'n=' + sameOk);
    check('② 国内盘异单位卡（元/克、元/千克）未加 same 类', keepUnit === 2 && unitOk !== -999, 'keepUnit=' + keepUnit);
  }
  if (lme) {
    const cards = lme.querySelectorAll('.price-card');
    let sameOk = 0;
    cards.forEach(c => {
      const u = c.querySelector('.pc-unit');
      if (u && (u.textContent || '').trim() === '美元/吨' && u.classList.contains('pc-unit-same')) sameOk++;
    });
    check('③ LME 全部 6 张卡都有 same 类', sameOk === 6, 'n=' + sameOk);
  }

  // 计算样式：same 元素应 display:none（jsdom 支持类选择器 + CSS 解析，@media 不评估，
  // 但 .pc-unit-same{display:none} 在顶层，jsdom 能给出计算值）
  const oneSame = doc.querySelector('.pc-unit-same');
  if (oneSame) {
    const d = window.getComputedStyle(oneSame).display;
    check('① 同单位元素计算样式 display:none', d === 'none', 'display=' + d);
  } else {
    check('① 能找到 .pc-unit-same 元素', false, '未找到');
  }
  const oneKeep = doc.querySelector('#priceCardsShfe .pc-unit:not(.pc-unit-same)');
  if (oneKeep) {
    const d = window.getComputedStyle(oneKeep).display;
    check('② 异单位元素未被隐藏（display 非 none）', d !== 'none', 'display=' + d);
  }

  // CSV 导出仍能读单位
  if (typeof window.exportPriceCsv === 'function') {
    let captured = '';
    const origCreate = window.document.createElement.bind(window.document);
    window.URL.createObjectURL = () => { return 'blob:stub'; };
    window.Blob = function (parts) {
      captured = (parts && parts[0]) ? String(parts[0]) : '';
      return { size: captured.length, type: 'text/csv' };
    };
    try { window.exportPriceCsv(); } catch (e) { /* DOM click 可能受限 */ }
    check('③ CSV 导出仍含单位列（元/吨 / 美元/吨）',
      captured.includes('元/吨') && captured.includes('美元/吨'),
      'captured len=' + captured.length);
  } else {
    check('③ exportPriceCsv 可调用', false, '函数不存在');
  }

  console.log('\n===== 汇总 =====');
  console.log('  ' + pass + ' PASS / ' + fail + ' FAIL');
  process.exit(fail ? 1 : 0);
}, 900);
