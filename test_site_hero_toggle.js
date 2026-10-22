/**
 * 2026-10-23 站点 hero「关于本站」开关回归测试
 *
 * 背景：该 toggle 自 2026-10-08（fb05b94）上线起就是**空操作**——内联脚本逻辑写反：
 *   var o = !d.hasAttribute('hidden');        // o = 当前是否展开
 *   if(o){ 保持展开 } else { 保持收起 }        // 点击只是重新确认当前状态
 * 线上实测确认（hidden 恒 true，点了不展开）。2026-10-23 借 UI 调整（按钮并入定位句做文字链）
 * 之际修为真正 toggle，并加本测试守住，防回归。
 *
 * 断言：
 *   A 静态结构：按钮在 .site-hero-tag 段落内（inline 文字链，不再独占一行）、aria-expanded 初始 false；
 *   B 交互：点击 → 详情展开 + 文案 ▴ + aria-expanded=true；再点 → 收起 + ▾ + false（真 toggle）；
 *   C 样式契约：.site-hero-toggle 为无边框文字链（border:none + 虚线 underline），不再是有描边 pill。
 *
 * 运行：node test_site_hero_toggle.js   （需仓库 node_modules/jsdom）
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = __dirname;
const HTML = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf-8');

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name + (detail ? '  → ' + detail : '')); }
  else { fail++; console.log('  FAIL  ' + name + (detail ? '  → ' + detail : '')); }
}

const dom = new JSDOM(HTML, {
  runScripts: 'dangerously',
  url: 'https://pliucugb-cyber.github.io/mining-daily/',
  beforeParse(win) {
    win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    win.fetch = () => Promise.reject(new Error('jsdom: fetch stub'));
    try { Object.defineProperty(win, 'innerWidth', { value: 1280, configurable: true, writable: true }); } catch (e) {}
  },
});
const doc = dom.window.document;

setTimeout(() => {
  console.log('===== A 静态结构 =====');
  const tag = doc.querySelector('#siteHero .site-hero-tag');
  const btn = doc.getElementById('siteHeroToggle');
  const detail = doc.getElementById('siteHeroDetail');
  check('[A1] hero 定位句与按钮均存在', !!tag && !!btn && !!detail);
  check('[A2] 按钮并入定位句段落内（inline 文字链，2026-10-23）', !!tag && !!btn && tag.contains(btn),
    btn ? 'parent=' + btn.parentElement.className : 'n/a');
  check('[A3] aria-expanded 初始为 false', btn && btn.getAttribute('aria-expanded') === 'false',
    btn ? btn.getAttribute('aria-expanded') : 'n/a');
  check('[A4] 详情默认收起', detail && detail.hasAttribute('hidden'));

  console.log('===== B 交互（真 toggle，防 10-08 空操作回归）=====');
  if (btn && detail) {
    btn.click();
    check('[B1] 点击后详情展开', !detail.hasAttribute('hidden'));
    check('[B2] 展开后文案为 ▴', btn.textContent.indexOf('▴') >= 0, btn.textContent);
    check('[B3] 展开后 aria-expanded=true', btn.getAttribute('aria-expanded') === 'true');
    btn.click();
    check('[B4] 再点后详情收起', detail.hasAttribute('hidden'));
    check('[B5] 收起后文案回 ▾', btn.textContent.indexOf('▾') >= 0, btn.textContent);
    check('[B6] 收起后 aria-expanded=false', btn.getAttribute('aria-expanded') === 'false');
  } else {
    check('[B1-B6] 交互', false, '元素缺失，跳过');
  }

  console.log('===== C 样式契约 =====');
  // 注意：jsdom 的 cssstyle 会把 border:none 归一化成 border:medium（style=none、width=medium），
  //      真实浏览器无此怪癖 → 断言以 borderStyle==='none' 为准，别匹配 cssText 文本。
  let borderNone = false, dotted = false, oldPill = false;
  for (const sh of doc.styleSheets) {
    let rules; try { rules = sh.cssRules; } catch (e) { continue; }
    for (const r of rules) {
      if (!r.selectorText) continue;
      if (r.selectorText.indexOf('.site-hero-toggle') >= 0 && r.selectorText.indexOf(':hover') < 0) {
        if (r.style.borderStyle === 'none') borderNone = true;
        if (r.style.textDecorationStyle === 'dotted') dotted = true;
        if (r.style.borderStyle === 'solid') oldPill = true;
      }
    }
  }
  check('[C1] .site-hero-toggle 无边框（文字链，非 pill）', borderNone && !oldPill,
    'borderStyle=none:' + borderNone + ' solid:' + oldPill);
  check('[C2] .site-hero-toggle 虚线下划线', dotted);

  console.log('\n===== 汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 800);
