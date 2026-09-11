/**
 * 2026-09-11 A4 回归：移动端会展条目去重（vault 迁移必须在移动端执行）
 *
 * 根因（修复前）：expo/vault IIFE 的 init() 开头 `if(!isDesktop()) return;` 把
 *   整段（含 vault 迁移）都挡在移动端之外 → 会展条目既留在主信息流、又出现在
 *   「会议」tab，移动端双份（A4 重复）。
 * 修复：vault 迁移在**所有视口**执行；只有桌面侧栏迷你卡（#expoMini/#expoMiniList）
 *   注入才由 isDesktop() 把关。
 *
 * 验证：用最小 DOM（含 todaySection + 一个会展条目 + 一个普通条目 + expoMini/expoMiniList）
 *   直接驱动 expo IIFE，断言：
 *   ① 移动端：会展条目被移入 #expoVault（主信息流不再重复）→ 消除重复源；
 *   ② 移动端：#expoMiniList 保持空（迷你卡仅在桌面注入）；
 *   ③ 桌面端：#expoMiniList 被注入、且 #expoVault 同样收到条目。
 *
 * 关键：app.js 在 DOMContentLoaded 后才跑初始化（且 expo IIFE 自己也在 DOMContentLoaded
 *   后 setTimeout(init,0)）。JSDOM 对「构造后再注入的 <script>」不会补发
 *   DOMContentLoaded，因此必须把 app.js 作为页面原始 <script> 随 HTML 一起交给 JSDOM
 *   （runScripts:'dangerously'），由 JSDOM 驱动完整生命周期。
 *
 * 运行：node test_a4_expo_mobile.js   （需仓库 node_modules/jsdom）
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const APPJS = fs.readFileSync(path.join(__dirname, 'app.js'), 'utf-8');

function buildDom(isDesktop) {
  const html = `<!DOCTYPE html><html><head></head><body>
    <div id="todaySection">
      <div class="news-item" data-expo="1">
        <a class="news-title" href="https://example.com/m1">2026 国际矿业大会将于北京召开</a>
        <span class="news-meta">09-11</span>
      </div>
      <div class="news-item" data-plain="1">
        <a class="news-title" href="https://example.com/p1">某矿企第三季度利润预增</a>
        <span class="news-meta">09-11</span>
      </div>
    </div>
    <div id="archiveSection"></div>
    <div id="expoMini" style="display:none"><ul id="expoMiniList"></ul></div>
    <script>${APPJS}</script>
  </body></html>`;
  const errors = [];
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    url: 'https://pliucugb-cyber.github.io/mining-daily/',
    beforeParse(win) {
      // 视口模拟：桌面 max-width 不匹配；移动 max-width 匹配
      win.matchMedia = q => ({
        matches: /max-width/.test(q) ? !isDesktop : false,
        media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}
      });
      win.fetch = () => Promise.reject(new Error('jsdom: fetch stub'));
      try { Object.defineProperty(win, 'innerWidth', { value: isDesktop ? 1280 : 375, configurable: true, writable: true }); } catch (e) {}
      win.addEventListener('error', e => errors.push('window.error: ' + (e && e.message)));
      win.console.error = (...a) => { errors.push('console.error: ' + a.join(' ')); };
    }
  });
  return { dom, window: dom.window, errors };
}

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name + (detail ? '  → ' + detail : '')); }
  else { fail++; console.log('  FAIL  ' + name + (detail ? '  → ' + detail : '')); }
}

function run(isDesktop, label, done) {
  const { window, errors } = buildDom(isDesktop);
  const doc = window.document;
  setTimeout(() => {
    const vault = doc.getElementById('expoVault');
    const mini = doc.getElementById('expoMiniList');
    const today = doc.getElementById('todaySection');
    const expoInFeed = today.querySelector('.news-item[data-expo="1"]');
    const expoInVault = vault && vault.querySelector('.news-item[data-expo="1"]');
    const plainStillInFeed = today.querySelector('.news-item[data-plain="1"]');

    console.log('===== ' + label + ' =====');
    check(label + '：#expoVault 已创建（迁移跑过）', !!vault);
    check(label + '：会展条目已移出主信息流（消除重复源）', !expoInFeed);
    check(label + '：会展条目进入 #expoVault', !!expoInVault);
    check(label + '：非会展条目仍留在主信息流（未被误迁）', !!plainStillInFeed);
    if (isDesktop) {
      check(label + '：桌面迷你卡 #expoMiniList 已注入会展条目', !!mini && mini.children.length > 0,
        'miniList=' + (mini ? mini.children.length : 'n/a'));
    } else {
      check(label + '：移动端不注入迷你卡（#expoMiniList 为空）', !!mini && mini.children.length === 0,
        'miniList=' + (mini ? mini.children.length : 'n/a'));
    }
    // 仅报告 expo 路径外的异常，不阻断断言
    const noise = errors.filter(e => !/fetch|Failed to fetch|NetworkError|GoatCounter|zcounter/i.test(e));
    if (noise.length) console.log('  (info) 非阻断 JS 噪声 ' + noise.length + ' 条：' + noise.slice(0, 2).join(' | '));
    done();
  }, 800);
}

run(false, '① 移动端（A4 重复根因修复点）', () => {
  run(true, '② 桌面端（迷你卡仍须正常）', () => {
    console.log('\n===== 汇总 =====');
    console.log('  通过 ' + pass + ' / 失败 ' + fail);
    process.exit(fail ? 1 : 0);
  });
});
