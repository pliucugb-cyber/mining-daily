/**
 * 2026-10-13 会展卡「时效闸门＋瘦身」回归
 *
 * 背景：右栏 #expoMini「近期会展」的内容=会展类新闻，且会把 archive 里的旧会展一直挂着
 *   （实测全库 16 条会展，9 条 >30 天）→ 卡片显旧又占位。本次改造：
 *     ① 时效闸门：只展示近 14 天（+无日期条目保守保留）；
 *     ② 瘦身：默认只显示 3 条，其余折叠，按钮「展开全部 N 条」；
 *     ③ 无近期会展 → 整块隐藏（display:none）。
 *   注意：条目仍一律移入 #expoVault（维持 2026-09-11 A4 去重语义不变）。
 *
 * 断言：
 *   A 混合场景：旧会展(40天前)不进卡；近期 5 条 → 3 条可见 + 2 条折叠 + 展开按钮；
 *     展开后 2 条显示、按钮变「收起」；旧会展仍在 vault；非会展仍留主信息流。
 *   B 全旧场景：只有旧会展 → 卡片隐藏（display:none）、列表清空；旧条目仍在 vault。
 *
 * 运行：node test_expo_recency_20261013.js   （需仓库 node_modules/jsdom）
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const APPJS = fs.readFileSync(path.join(__dirname, 'app.js'), 'utf-8');

function mmddAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function item(title, dateStr, extra) {
  return `<div class="news-item" ${extra || ''}>
      <a class="news-title" href="https://example.com/${encodeURIComponent(title).slice(0, 12)}">${title}</a>
      <span class="news-meta">${dateStr}</span>
    </div>`;
}

function buildDom(todayItems) {
  const html = `<!DOCTYPE html><html><head></head><body>
    <div id="todaySection">${todayItems}</div>
    <div id="archiveSection"></div>
    <div id="expoMini" style="display:none"><ul id="expoMiniList"></ul></div>
    <script>${APPJS}</script>
  </body></html>`;
  const errors = [];
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    url: 'https://pliucugb-cyber.github.io/mining-daily/',
    beforeParse(win) {
      win.matchMedia = q => ({
        matches: /max-width/.test(q) ? false : false,
        media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}
      });
      win.fetch = () => Promise.reject(new Error('jsdom: fetch stub'));
      try { Object.defineProperty(win, 'innerWidth', { value: 1280, configurable: true, writable: true }); } catch (e) {}
      win.addEventListener('error', e => errors.push('window.error: ' + (e && e.message)));
      win.console.error = (...a) => { errors.push('console.error: ' + a.join(' ')); };
    }
  });
  return { dom, window: dom.window, doc: dom.window.document, errors };
}

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name + (detail ? '  → ' + detail : '')); }
  else { fail++; console.log('  FAIL  ' + name + (detail ? '  → ' + detail : '')); }
}

// ===== A 混合场景 =====
function runA(done) {
  const recent = [
    item('2026 国际矿业大会将于北京召开', mmddAgo(1), 'data-a="1"'),
    item('2026 有色金属年会召开', mmddAgo(5), 'data-b="1"'),
    item('2026 智能矿山论坛举行', mmddAgo(10), 'data-c="1"'),
    item('2026 铜业峰会举办', mmddAgo(13), 'data-d="1"'),
    item('2026 铝业大会召开', mmddAgo(3), 'data-e="1"'),
  ].join('');
  const oldExpo = item('2026 稀土年会召开', mmddAgo(40), 'data-old="1"');
  const plain = item('某矿企第三季度利润预增', mmddAgo(1), 'data-plain="1"');
  const { doc, errors } = buildDom(recent + oldExpo + plain);
  setTimeout(() => {
    const ul = doc.getElementById('expoMiniList');
    const box = doc.getElementById('expoMini');
    const vault = doc.getElementById('expoVault');
    console.log('===== A 混合场景（近期5 + 旧1 + 普通1）=====');
    check('[A1] 卡片可见', box && box.style.display !== 'none', 'display=' + (box ? box.style.display : 'n/a'));
    const text = ul ? ul.textContent : '';
    check('[A2] 旧会展(40天前)不进卡片', text.indexOf('稀土年会') < 0);
    check('[A3] 近期会展已渲染(>=3条)', ul && ul.querySelectorAll('li').length >= 3, 'li=' + (ul ? ul.querySelectorAll('li').length : 'n/a'));
    const extra = ul ? ul.querySelectorAll('.expo-extra') : [];
    const extraHidden = ul ? ul.querySelectorAll('.expo-extra[hidden]') : [];
    check('[A4] 折叠条目=2(5条-3条可见)', extra.length === 2, 'extra=' + extra.length);
    check('[A5] 折叠条目默认 hidden', extraHidden.length === 2, 'hidden=' + extraHidden.length);
    const btn = ul ? ul.querySelector('.expo-more-btn') : null;
    check('[A6] 存在「展开全部」按钮', !!btn, btn ? btn.textContent.trim() : 'n/a');
    check('[A7] 旧会展已移入 vault', !!(vault && vault.querySelector('.news-item[data-old="1"]')));
    check('[A8] 非会展条目仍留主信息流', !!doc.querySelector('#todaySection .news-item[data-plain="1"]'));
    // 展开
    if (btn) btn.onclick();
    const hiddenAfter = ul.querySelectorAll('.expo-extra[hidden]').length;
    check('[A9] 点击展开后 2 条折叠条目显示', hiddenAfter === 0, 'hidden=' + hiddenAfter);
    check('[A10] 按钮文案变为「收起」', btn && btn.textContent.indexOf('收起') >= 0, btn ? btn.textContent.trim() : 'n/a');
    if (btn) btn.onclick();
    check('[A11] 再次点击收起', ul.querySelectorAll('.expo-extra[hidden]').length === 2);
    const noise = errors.filter(e => !/fetch|Failed to fetch|NetworkError|GoatCounter|zcounter/i.test(e));
    if (noise.length) console.log('  (info) 非阻断噪声 ' + noise.length + ' 条');
    done();
  }, 900);
}

// ===== B 全旧场景 =====
function runB(done) {
  const oldOnly = item('2026 稀土年会召开', mmddAgo(40), 'data-old="1"');
  const plain = item('某矿企第三季度利润预增', mmddAgo(1), 'data-plain="1"');
  const { doc } = buildDom(oldOnly + plain);
  setTimeout(() => {
    const ul = doc.getElementById('expoMiniList');
    const box = doc.getElementById('expoMini');
    const vault = doc.getElementById('expoVault');
    console.log('===== B 全旧场景（仅旧会展1条）=====');
    check('[B1] 卡片整块隐藏', box && box.style.display === 'none', 'display=' + (box ? box.style.display : 'n/a'));
    check('[B2] 列表清空', ul && ul.children.length === 0, 'li=' + (ul ? ul.children.length : 'n/a'));
    check('[B3] 旧会展仍移入 vault(保留可搜)', !!(vault && vault.querySelector('.news-item[data-old="1"]')));
    done();
  }, 900);
}

runA(() => {
  runB(() => {
    console.log('\n===== 汇总 =====');
    console.log('  通过 ' + pass + ' / 失败 ' + fail);
    process.exit(fail ? 1 : 0);
  });
});
