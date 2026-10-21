/**
 * 2026-10-21 「会议日程」模块回归测试（含自动抓取与移动端会议 tab）
 *
 * 背景：右栏原「近期会展」靠 isExpo 关键词从新闻标题里"捡"会议条目，实测 10 月库 407 条仅命中
 *   3 条（其中 2 条是同一场会的不同源），过 14 天闸门只剩 1 条 → 卡片常年空、内容几乎不变动。
 *   根因是方向错了：装的是"已召开会议的事后报道"。现改为：
 *     上半区「会议日程」＝独立数据源 conference-data.js 驱动（未来/进行中会议 + 倒计时）；
 *     下半区「会议资讯」＝仍是新闻派生（2026-10-13 既定契约：仍进 #expoMiniList、仍受 14 天闸门）。
 *
 * 断言：
 *   A 桌面卡片：有日期会议默认 5 条可见、其余折叠；「日期待定」独立成区并限量；
 *     倒计时文案正确；按开始日期升序；展开按钮只展开自己那组；页脚与官方链接。
 *   B 无会议数据 → 卡片整块隐藏。
 *   C 有会议数据 + 有新闻会展 → expoMiniList 仍装新闻条目（不破 10-13 契约）、「会议资讯」子标题可见。
 *   D 移动端「会议」tab：#meetingSection 内含会议日程块（与右栏同源）。
 *   E 静态契约：conferences.json manual/auto 分区、源注册表多源、fetch_conferences.py 关键机制、
 *     deploy_pages.py 登记 conference-data.js。
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
    `<script>window.CONFERENCE_DATA = ${JSON.stringify({ updated: BASE, source: 'test', items: conf })};</script>`;
  const html = `<!DOCTYPE html><html><head></head><body>
    <div id="todaySection">${todayItems || ''}</div>
    <div id="archiveSection"></div>
    <div class="section" id="rightsSection"></div>
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
      win.console.error = (...a) => { errors.push('console.error: ' + a.join(' ')); }
    }
  });
  return { dom, window: dom.window, doc: dom.window.document, errors };
}

const whenOf = (doc) => Array.prototype.map.call(
  doc.querySelectorAll('#expoConfList li.expo-conf-item .expo-conf-when b'), e => e.textContent.trim());

// ===== A 桌面卡片 =====
function runA(done) {
  const { doc, errors } = buildDom('', ITEMS);
  setTimeout(() => {
    console.log('===== A 桌面卡片（有日期 + 日期待定）=====');
    const box = doc.getElementById('expoMini');
    const cl = doc.getElementById('expoConfList');
    const text = cl ? cl.textContent : '';
    check('[A1] 卡片可见', box && box.style.display !== 'none', 'display=' + (box ? box.style.display : 'n/a'));
    check('[A2] 已结束会议被剔除', text.indexOf('已结束的会议') < 0);
    check('[A3] 进行中标注「进行中」', text.indexOf('进行中') >= 0);
    check('[A4] 今天/明天倒计时', text.indexOf('今天开始') >= 0 && text.indexOf('明天开始') >= 0);
    check('[A5] N 天倒计时', text.indexOf('还有 4 天') >= 0);
    check('[A6] 远期按月倒计时', /还有 \d+ 个月/.test(text), (text.match(/还有 \d+ 个月/) || [''])[0]);
    const wh = whenOf(doc);
    check('[A7] 按开始日期升序', wh[0] === '10.20-23' && wh[1] === '10.21-22' && wh[2] === '10.22' && wh[3] === '10.25-27' && wh[4] === '11.5-6', wh.join(' | '));
    const datedVis = cl ? cl.querySelectorAll('li.expo-conf-item:not(.expo-conf-tbd):not([hidden])').length : 0;
    check('[A8] 有日期会议默认 5 条可见', datedVis === 5, 'visible=' + datedVis);
    const datedExtra = cl ? cl.querySelectorAll('li.expo-g-dated') : [];
    check('[A9] 有日期折叠项默认 hidden', datedExtra.length === 2 && cl.querySelectorAll('li.expo-g-dated[hidden]').length === 2,
      'extra=' + datedExtra.length);
    const div = cl ? cl.querySelector('.expo-sub-head-in') : null;
    check('[A10] 「日期待定」分区标题存在', !!div && div.textContent.indexOf('日期待定') >= 0, div ? div.textContent.trim() : 'n/a');
    check('[A11] 日期待定条目已渲染', text.indexOf('日期待定的会议') >= 0);
    const bD = cl ? cl.querySelector('.expo-btn-dated') : null;
    check('[A12] 有「展开全部」按钮(有日期组)', !!bD, bD ? bD.textContent.trim() : 'n/a');
    if (bD) bD.onclick();
    check('[A13] 展开后有日期折叠项全显示', cl.querySelectorAll('li.expo-g-dated[hidden]').length === 0);
    check('[A14] 按钮文案变「收起」', bD && bD.textContent.indexOf('收起') >= 0, bD ? bD.textContent.trim() : 'n/a');
    const foot = doc.getElementById('expoConfFoot');
    check('[A15] 页脚显示数据截至日与总数', foot && foot.textContent.indexOf(BASE) >= 0 && /\d+ 场/.test(foot.textContent),
      foot ? foot.textContent.trim() : 'n/a');
    const firstA = cl ? cl.querySelector('li.expo-conf-item a') : null;
    check('[A16] 条目带官方链接', !!firstA && firstA.getAttribute('href') === 'https://example.com/now',
      firstA ? firstA.getAttribute('href') : 'n/a');
    check('[A17] 地点显示在日期位旁', text.indexOf('山东日照') >= 0);
    check('[A18] 备注(报名截止)已展示', text.indexOf('报名优惠截止') >= 0);
    const noise = errors.filter(e => !/fetch|Failed to fetch|NetworkError|GoatCounter|zcounter|refresh/i.test(e));
    if (noise.length) console.log('  (info) 非阻断噪声 ' + noise.length + ' 条: ' + noise[0].slice(0, 80));
    done();
  }, 1000);
}

// ===== B 无会议数据 =====
function runB(done) {
  const { doc } = buildDom('', null);
  setTimeout(() => {
    console.log('===== B 无会议数据、无新闻会展 =====');
    const box = doc.getElementById('expoMini');
    const cl = doc.getElementById('expoConfList');
    check('[B1] 卡片整块隐藏', box && box.style.display === 'none', 'display=' + (box ? box.style.display : 'n/a'));
    check('[B2] 日程列表为空', cl && cl.children.length === 0, 'li=' + (cl ? cl.children.length : 'n/a'));
    done();
  }, 1000);
}

// ===== C 有会议数据 + 有新闻会展 =====
function runC(done) {
  const news = item('2026 智能矿山论坛举行', '10-20', 'data-c="1"');
  const { doc } = buildDom(news, ITEMS);
  setTimeout(() => {
    console.log('===== C 有会议数据 + 有新闻会展 =====');
    const box = doc.getElementById('expoMini');
    const cl = doc.getElementById('expoConfList');
    const ul = doc.getElementById('expoMiniList');
    const nh = doc.getElementById('expoNewsHead');
    check('[C1] 卡片可见', box && box.style.display !== 'none');
    check('[C2] 日程列表有内容', cl && cl.querySelectorAll('li.expo-conf-item').length === 8,
      'li=' + (cl ? cl.querySelectorAll('li.expo-conf-item').length : 'n/a'));
    check('[C3] 新闻会展仍在 #expoMiniList（10-13 契约不破）', ul && ul.querySelectorAll('li').length >= 1,
      'li=' + (ul ? ul.querySelectorAll('li').length : 'n/a'));
    check('[C4] 「会议资讯」子标题可见', nh && !nh.hidden && nh.style.display !== 'none');
    done();
  }, 1000);
}

// ===== D 移动端「会议」tab =====
function runD(done) {
  const { doc } = buildDom('', ITEMS);
  setTimeout(() => {
    console.log('===== D 移动端「会议」tab =====');
    const ms = doc.getElementById('meetingSection');
    check('[D1] 会议区块已注入', !!ms);
    const mc = ms ? ms.querySelector('.meeting-conf') : null;
    check('[D2] 会议日程块存在', !!mc);
    const rows = mc ? mc.querySelectorAll('.meeting-conf-list li') : [];
    check('[D3] 日程条目已渲染', rows.length > 0, 'li=' + rows.length);
    const t = mc ? mc.textContent : '';
    check('[D4] 含会议名与倒计时', t.indexOf('正在进行的会议') >= 0 && t.indexOf('进行中') >= 0);
    check('[D5] 含地点', t.indexOf('山东日照') >= 0);
    const a = mc ? mc.querySelector('.mc-main a') : null;
    check('[D6] 条目带链接', !!a && a.getAttribute('href') === 'https://example.com/now',
      a ? a.getAttribute('href') : 'n/a');
    done();
  }, 1000);
}

// ===== E 静态契约 =====
function runE(done) {
  console.log('===== E 静态契约 =====');
  const rd = p => fs.readFileSync(path.join(ROOT, p), 'utf-8');
  let conf = null;
  try { conf = JSON.parse(rd('data/conferences.json')); } catch (e) { }
  check('[E1] data/conferences.json 可解析', !!conf);
  if (conf) {
    check('[E2] 有人工区且非空', Array.isArray(conf.manual) && conf.manual.length > 0, 'manual=' + (conf.manual || []).length);
    check('[E3] 有自动区（可为 0 条）', Array.isArray(conf.auto), 'auto=' + (conf.auto || []).length);
  }
  let srcs = null;
  try { srcs = JSON.parse(rd('data/conference_sources.json')); } catch (e) { }
  check('[E4] 源注册表可解析', !!srcs && Array.isArray(srcs.sources));
  if (srcs) {
    check('[E5] 注册了多个数据源（≥3）', srcs.sources.length >= 3, 'sources=' + srcs.sources.length);
    const ids = srcs.sources.map(s => s.id);
    check('[E6] 源覆盖国内+国际', ids.some(i => /geosociety|cnmn/.test(i)) && ids.some(i => /gmr|miningjournal|pdac/.test(i)),
      ids.join(','));
    check('[E7] 每个源都有 url 与 parser', srcs.sources.every(s => s.url && s.parser));
  }
  const fc = rd('fetch_conferences.py');
  check('[E8] fetch_conferences.py 存在且有源注册表机制', fc.length > 3000 && fc.indexOf('conference_sources.json') >= 0);
  check('[E9] 人工区与自动区分离存放', fc.indexOf("'manual'") >= 0 && fc.indexOf("'auto'") >= 0);
  check('[E10] 全源失败时保留原数据不落盘', fc.indexOf('所有源都失败') >= 0);
  check('[E11] 锚定式日期抽取（不取正文首个日期）', fc.indexOf('parse_anchored_cn_date') >= 0);
  check('[E12] 过期会议不进日程', fc.indexOf('filter_items') >= 0);
  const dp = rd('deploy_pages.py');
  check('[E13] deploy_pages.py REQUIRED 已登记', /'conference-data\.js'/.test(dp.split('BUST_FILES')[0]));
  check('[E14] deploy_pages.py BUST_FILES 已登记', /BUST_FILES = \[[^\]]*'conference-data\.js'/.test(dp));
  const ih = rd('index.html');
  check('[E15] index.html 引用 conference-data.js', ih.indexOf('src="conference-data.js"') >= 0);
  check('[E16] index.html 有 #expoConfList 容器', ih.indexOf('id="expoConfList"') >= 0);
  check('[E17] index.html 有移动端 .meeting-conf 样式', ih.indexOf('.meeting-conf{') >= 0);
  const aj = rd('app.js');
  check('[E18] app.js 暴露 mdConf 供移动端复用', aj.indexOf('window.__mdConf') >= 0);
  check('[E19] app.js 移动端会议 tab 注入日程', aj.indexOf('mdMeetingConfHtml') >= 0);
  // E20 致命回归防线：2026-10-21 实际踩过 —— render_js 用 "\n".join 拼数组漏了逗号，
  //     生成的 conference-data.js 语法非法 → 线上 <script> 解析失败 → window.CONFERENCE_DATA
  //     未定义 → 会议日程卡整块空白（页面不报错，最难发现）。故此处必须断言生成物可解析。
  let cdsrc = '';
  try { cdsrc = rd('conference-data.js'); } catch (e) { }
  let parseOk = false;
  try { new Function('window', cdsrc)({ }); parseOk = true; } catch (e) { }
  check('[E20] conference-data.js 可被解析（漏逗号会语法错）', parseOk);
  check('[E21] 生成器条目间带逗号（",\\n".join）', fc.indexOf('",\\n".join(lines)') >= 0 || fc.indexOf("',\\n'.join(lines)") >= 0);
  done();
}

runA(() => {
  runB(() => {
    runC(() => {
      runD(() => {
        runE(() => {
          console.log('\n===== 汇总 =====');
          console.log('  通过 ' + pass + ' / 失败 ' + fail);
          process.exit(fail ? 1 : 0);
        });
      });
    });
  });
});
