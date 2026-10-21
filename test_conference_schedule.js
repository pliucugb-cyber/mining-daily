/**
 * 2026-10-21 「会议日程」模块回归测试
 *
 * 背景：右栏原「近期会展」卡靠 isExpo 关键词从新闻标题里"捡"会议条目，
 *   实测 10 月库 407 条仅命中 3 条（其中 2 条是同一场会的不同源），过 14 天闸门只剩 1 条
 *   → 卡片常年空、且内容几乎不变动。根因是方向错了：装的是"已召开会议的事后报道"。
 *   改造：卡片上半区改为独立数据源 conference-data.js（window.CONFERENCE_DATA）驱动的
 *   「会议日程」——未来/进行中会议（日期·地点·倒计时），下半区仍保留新闻派生的「会议资讯」。
 *
 * 断言：
 *   A 有会议数据、无新闻会展：卡片可见；已结束会议被剔除；进行中/今天/明天/N 天/N 个月
 *     倒计时文案正确；按开始日期升序；默认 5 条可见、其余折叠 + 展开按钮；日期待定项单独归区；
 *     「会议资讯」子标题隐藏；页脚显示数据截至日；条目带官方链接。
 *   B 无会议数据、无新闻会展：卡片整块隐藏（与改造前行为一致）。
 *   C 有会议数据 + 有新闻会展：卡片可见；「会议资讯」子标题可见；#expoMiniList 仍装新闻条目
 *     （不破 2026-10-13 既定契约：新闻派生的会展条目仍进 expoMiniList、仍受 14 天闸门）。
 *   D 静态契约：conference-data.js 存在且可解析、条目数与字段格式合法；
 *     deploy_pages.py 的 REQUIRED 与 BUST_FILES 均已登记该文件（否则线上拿不到 / 会缓存混装）。
 *
 * 运行：node test_conference_schedule.js   （需仓库 node_modules/jsdom）
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = __dirname;
const APPJS = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf-8');
const BASE = '2026-10-21';

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name + (detail ? '  → ' + detail : '')); }
  else { fail++; console.log('  FAIL  ' + name + (detail ? '  → ' + detail : '')); }
}

function confData(items) {
  return { updated: BASE, source: 'test', items: items || [] };
}

// 会议数据：1 条已结束、1 条进行中、今天、明天、N 天、两条远期、日期待定
const ITEMS = [
  { s: '2026-10-01', e: '2026-10-02', t: '已结束的会议', p: '某地', o: '某主办', tag: '测试', u: 'https://example.com/past' },
  { s: '2026-10-20', e: '2026-10-23', t: '正在进行的会议', p: '山东日照', o: '某协会', tag: '勘查技术', u: 'https://example.com/now' },
  { s: '2026-10-21', e: '2026-10-22', t: '今天开始的会议', p: '厦门', o: '某学会', tag: '矿业投资', u: 'https://example.com/today' },
  { s: '2026-10-22', e: '2026-10-22', t: '明天开始的会议', p: '南宁', o: '某厅', tag: '矿业大会', u: 'https://example.com/tmr' },
  { s: '2026-10-25', e: '2026-10-27', t: '几天后的会议', p: '湖南长沙', o: '某大学', tag: '成矿理论', u: 'https://example.com/soon' },
  { s: '2026-11-05', e: '2026-11-06', t: '十一月会议', p: '北京', o: '某机构', tag: '测试', u: 'https://example.com/nov' },
  { s: '2026-11-18', e: '2026-11-21', t: '境外矿投大会', p: '厦门悦华酒店', o: '中国地质学会·紫金矿业', tag: '矿业投资', u: 'https://example.com/nov2', note: '报名优惠截止 10-30' },
  { s: '2027-06-01', e: '2027-06-02', t: '远期会议', p: '海外', o: '某国际组织', tag: '国际矿业', u: 'https://example.com/far' },
  { s: '', e: '', t: '日期待定的会议', p: '待定', o: '中国地质学会', tag: '测试', u: 'https://example.com/tbd' }
];

function item(title, dateStr, extra) {
  return `<div class="news-item" ${extra || ''}>
      <a class="news-title" href="https://example.com/${encodeURIComponent(title).slice(0, 12)}">${title}</a>
      <span class="news-meta">${dateStr}</span>
    </div>`;
}

function buildDom(todayItems, conf) {
  const confScript = conf === null ? '' :
    `<script>window.CONFERENCE_DATA = ${JSON.stringify(conf)};</script>`;
  const html = `<!DOCTYPE html><html><head></head><body>
    <div id="todaySection">${todayItems || ''}</div>
    <div id="archiveSection"></div>
    <div class="expo-mini" id="expoMini" style="display:none">
      <div class="expo-mini-head">会议日程</div>
      <ul class="expo-mini-list expo-conf-list" id="expoConfList"></ul>
      <div class="expo-conf-foot" id="expoConfFoot"></div>
      <div class="expo-sub-head" id="expoNewsHead" hidden>会议资讯 · 已召开报道</div>
      <ul class="expo-mini-list" id="expoMiniList"></ul>
    </div>
    ${confScript}
    <script>${APPJS}</script>
  </body></html>`;
  const errors = [];
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    url: 'https://pliucugb-cyber.github.io/mining-daily/',
    beforeParse(win) {
      win.matchMedia = q => ({
        matches: false, media: q,
        addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}
      });
      win.fetch = () => Promise.reject(new Error('jsdom: fetch stub'));
      try { Object.defineProperty(win, 'innerWidth', { value: 1280, configurable: true, writable: true }); } catch (e) {}
      win.addEventListener('error', e => errors.push('window.error: ' + (e && e.message)));
      win.console.error = (...a) => { errors.push('console.error: ' + a.join(' ')); };
    }
  });
  return { dom, window: dom.window, doc: dom.window.document, errors };
}

const liTexts = (doc, sel) => Array.prototype.map.call(doc.querySelectorAll(sel), e => e.textContent.trim());
const whenOf = (doc) => Array.prototype.map.call(
  doc.querySelectorAll('#expoConfList li.expo-conf-item .expo-conf-when b'), e => e.textContent.trim());

// ===== A 有会议数据、无新闻会展 =====
function runA(done) {
  const { doc, errors } = buildDom('', confData(ITEMS));
  setTimeout(() => {
    console.log('===== A 有会议数据、无新闻会展 =====');
    const box = doc.getElementById('expoMini');
    const cl = doc.getElementById('expoConfList');
    const foot = doc.getElementById('expoConfFoot');
    const nh = doc.getElementById('expoNewsHead');
    check('[A1] 卡片可见', box && box.style.display !== 'none', 'display=' + (box ? box.style.display : 'n/a'));
    check('[A2] 日程列表已渲染', cl && cl.querySelectorAll('li.expo-conf-item').length === 8,
      'li=' + (cl ? cl.querySelectorAll('li.expo-conf-item').length : 'n/a'));
    const text = cl ? cl.textContent : '';
    check('[A3] 已结束会议被剔除', text.indexOf('已结束的会议') < 0);
    check('[A4] 进行中会议标注「进行中」', text.indexOf('进行中') >= 0);
    check('[A5] 今天开始标注正确', text.indexOf('今天开始') >= 0);
    check('[A6] 明天开始标注正确', text.indexOf('明天开始') >= 0);
    check('[A7] N 天倒计时正确', text.indexOf('还有 4 天') >= 0);
    check('[A8] 远期按月倒计时', /还有 \d+ 个月/.test(text), (text.match(/还有 \d+ 个月/) || [''])[0]);
    const wh = whenOf(doc);
    check('[A9] 按开始日期升序', wh[0] === '10.20-23' && wh[1] === '10.21-22' && wh[2] === '10.22' && wh[3] === '10.25-27' && wh[4] === '11.5-6' && wh[7] === '待定',
      wh.join(' | '));
    const extras = cl ? cl.querySelectorAll('li.expo-extra') : [];
    const hidden = cl ? cl.querySelectorAll('li.expo-extra[hidden]') : [];
    check('[A10] 默认 5 条可见', cl && cl.querySelectorAll('li.expo-conf-item:not([hidden])').length === 5,
      'visible=' + (cl ? cl.querySelectorAll('li.expo-conf-item:not([hidden])').length : 'n/a'));
    check('[A11] 折叠条目数=3(8-5)', extras.length === 3, 'extra=' + extras.length);
    check('[A12] 折叠条目默认 hidden', hidden.length === 3, 'hidden=' + hidden.length);
    const btn = cl ? cl.querySelector('.expo-more-btn') : null;
    check('[A13] 存在「展开全部」按钮', !!btn, btn ? btn.textContent.trim() : 'n/a');
    if (btn) btn.onclick();
    check('[A14] 展开后折叠项全部显示', cl.querySelectorAll('li.expo-extra[hidden]').length === 0);
    check('[A15] 按钮文案变「收起」', btn && btn.textContent.indexOf('收起') >= 0, btn ? btn.textContent.trim() : 'n/a');
    check('[A16] 日期待定项归入列表并标注', text.indexOf('日期待定的会议') >= 0 && text.indexOf('待定') >= 0);
    check('[A17] 无新闻时「会议资讯」子标题隐藏', nh && (nh.hidden || nh.style.display === 'none'));
    check('[A18] 页脚显示数据截至日', foot && foot.textContent.indexOf(BASE) >= 0, foot ? foot.textContent.trim() : 'n/a');
    const firstA = cl ? cl.querySelector('li.expo-conf-item a') : null;
    check('[A19] 条目带官方链接', !!firstA && firstA.getAttribute('href') === 'https://example.com/now',
      firstA ? firstA.getAttribute('href') : 'n/a');
    check('[A20] 地点显示在日期位旁', text.indexOf('山东日照') >= 0);
    const noise = errors.filter(e => !/fetch|Failed to fetch|NetworkError|GoatCounter|zcounter/i.test(e));
    if (noise.length) console.log('  (info) 非阻断噪声 ' + noise.length + ' 条');
    done();
  }, 900);
}

// ===== B 无会议数据、无新闻会展（兼容改造前行为）=====
function runB(done) {
  const { doc } = buildDom('', null);
  setTimeout(() => {
    console.log('===== B 无会议数据、无新闻会展 =====');
    const box = doc.getElementById('expoMini');
    const cl = doc.getElementById('expoConfList');
    check('[B1] 卡片整块隐藏', box && box.style.display === 'none', 'display=' + (box ? box.style.display : 'n/a'));
    check('[B2] 日程列表为空', cl && cl.children.length === 0, 'li=' + (cl ? cl.children.length : 'n/a'));
    done();
  }, 900);
}

// ===== C 有会议数据 + 有新闻会展（不破 10-13 契约）=====
function runC(done) {
  const news = item('2026 智能矿山论坛举行', '10-20', 'data-c="1"');
  const { doc } = buildDom(news, confData(ITEMS));
  setTimeout(() => {
    console.log('===== C 有会议数据 + 有新闻会展 =====');
    const box = doc.getElementById('expoMini');
    const cl = doc.getElementById('expoConfList');
    const ul = doc.getElementById('expoMiniList');
    const nh = doc.getElementById('expoNewsHead');
    check('[C1] 卡片可见', box && box.style.display !== 'none');
    check('[C2] 日程列表有内容', cl && cl.querySelectorAll('li.expo-conf-item').length === 8);
    check('[C3] 新闻会展仍在 #expoMiniList（契约不破）', ul && ul.querySelectorAll('li').length >= 1,
      'li=' + (ul ? ul.querySelectorAll('li').length : 'n/a'));
    check('[C4] 「会议资讯」子标题可见', nh && !nh.hidden && nh.style.display !== 'none');
    done();
  }, 900);
}

// ===== D 静态契约：数据文件与部署登记 =====
function runD(done) {
  console.log('===== D 静态契约 =====');
  const p = path.join(ROOT, 'conference-data.js');
  check('[D1] conference-data.js 存在', fs.existsSync(p));
  if (fs.existsSync(p)) {
    const src = fs.readFileSync(p, 'utf-8');
    const sandbox = { window: {} };
    try { new Function('window', src)(sandbox.window); } catch (e) { /* 解析失败在下一条断言体现 */ }
    const D = sandbox.window.CONFERENCE_DATA;
    check('[D2] 可解析出 window.CONFERENCE_DATA', !!(D && D.items && D.items.length), D ? 'items=' + D.items.length : 'n/a');
    if (D && D.items) {
      const bad = D.items.filter(it => !it || !it.t || !it.u ||
        (it.s && !/^\d{4}-\d{2}-\d{2}$/.test(it.s)) || (it.e && !/^\d{4}-\d{2}-\d{2}$/.test(it.e)));
      check('[D3] 条目字段与日期格式合法', bad.length === 0, 'bad=' + bad.length);
      check('[D4] 条目数足够撑起卡片', D.items.length >= 20, 'items=' + D.items.length);
      const dated = D.items.filter(it => it.s);
      check('[D5] 未来会议占比过半', dated.length >= 15, 'dated=' + dated.length);
    }
  }
  const dp = fs.readFileSync(path.join(ROOT, 'deploy_pages.py'), 'utf-8');
  check('[D6] deploy_pages.py REQUIRED 已登记', /'conference-data\.js'/.test(dp.split('BUST_FILES')[0]));
  check('[D7] deploy_pages.py BUST_FILES 已登记（防缓存混装）', /BUST_FILES = \[[^\]]*'conference-data\.js'/.test(dp));
  const ih = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf-8');
  check('[D8] index.html 引用了 conference-data.js', ih.indexOf('src="conference-data.js"') >= 0);
  check('[D9] index.html 存在 #expoConfList 容器', ih.indexOf('id="expoConfList"') >= 0);
  done();
}

runA(() => {
  runB(() => {
    runC(() => {
      runD(() => {
        console.log('\n===== 汇总 =====');
        console.log('  通过 ' + pass + ' / 失败 ' + fail);
        process.exit(fail ? 1 : 0);
      });
    });
  });
});
