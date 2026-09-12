// 简报五节结构化渲染回归测试（2026-09-12，二次修订）
//
// 演进（三次修订，勿混淆）：
//   ① 首版「要点层 highlights + 完整层 brief_sections」两层；用户指出要点层与下方
//      「今日要闻」内容重复 → 移除要点层，改为单一形态：五节结构化 + 默认收起。
//      该轮**没动内容长度**，展开后仍是 18 条 / 4184 字、平均每条 232 字（= 把新闻列表抄一遍）。
//   ② 2026-09-12 三次修订：用户反馈「3500 多字实在太多，只要关键信息」→
//      简报条目改为**逐条精炼句**（每条 ≤ 80 字）+ 剔除低信息量例行条目（发运/工商变更…），
//      实测 16 条 / 1057 字。§9.2.5「单条不截断」与 §10.1「每节全量」由此被 §16 取代：
//      精炼句由生成端 BRIEF_DIGEST 逐条撰写，不再是 news.summary 的原样搬运。
//   ③ 本测试对②加硬约束：单条 ≤80 字、总量 ≤1200 字、无例行条目、条数少于当日新增。
//
// 本测试覆盖三块：
//   ① 数据契约（直接读 morning_report.json，不需要浏览器）
//   ② 渲染行为（jsdom + 本地 http + fetch 桥接，因为 jsdom 不实现 fetch）
//   ③ 回退路径（把 brief_sections 剥掉后必须退回旧的 report markdown 渲染）
//
// ⚠️ jsdom 不做布局，scrollHeight 恒为 0，折叠判定会静默失效；故在 beforeParse 里把
//    HTMLElement.prototype.scrollHeight 覆盖为定值，让折叠分支真实走一遍。
const fs = require('fs');
const path = require('path');
const http = require('http');
const { JSDOM } = require('jsdom');

const ROOT = __dirname;
const PORT = 8822;
const REPORT = JSON.parse(fs.readFileSync(path.join(ROOT, 'morning_report.json'), 'utf8'));

let pass = 0, fail = 0;
function check(name, cond, why) {
  if (cond) { pass++; console.log('  PASS  ' + name + (why ? '  → ' + why : '')); }
  else { fail++; console.log('  FAIL  ' + name + (why ? '  → ' + why : '')); }
}
function skip(name, why) { console.log('  SKIP  ' + name + (why ? '  → ' + why : '')); }
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ==================== ① 数据契约 ====================
console.log('===== ① 数据契约：brief_sections / report =====');

const bsec = REPORT.brief_sections;
check('brief_sections 存在且为数组', Array.isArray(bsec));
check('brief_sections 至少 1 节', Array.isArray(bsec) && bsec.length > 0,
  '实际 ' + (Array.isArray(bsec) ? bsec.length : 'N/A') + ' 节');
if (Array.isArray(bsec)) {
  const emptyItems = bsec.filter(s => !s || !Array.isArray(s.items) || s.items.length === 0);
  check('无空节（空节不收录）', emptyItems.length === 0, emptyItems.length ? '空节 ' + emptyItems.length + ' 个' : '共 ' + bsec.length + ' 节');
  const badCount = bsec.filter(s => s.count !== s.items.length);
  check('每节 count == items.length', badCount.length === 0,
    badCount.length ? badCount.map(s => s.name + ':' + s.count + '/' + s.items.length).join(',') : '');
  check('每节 name 非空', bsec.every(s => s && typeof s.name === 'string' && s.name.trim()));
  check('每条 item 的 t 非空', bsec.every(s => s.items.every(it => it && typeof it.t === 'string' && it.t.trim())));
  const total = bsec.reduce((n, s) => n + s.items.length, 0);
  const repBullets = String(REPORT.report || '').split('\n').filter(l => l.trim().startsWith('- ')).length;
  check('分节总条数 == report 的条目数', total === repBullets, total + ' vs ' + repBullets);
  const noName = bsec.filter(s => !['行情', '政策与产业', '勘查与技术', '并购与投资', '矿权市场'].includes(s.name));
  check('节名都在五节白名单内', noName.length === 0, noName.map(s => s.name).join(','));
  const badU = bsec.filter(s => s.items.some(it => it.u && !/^https?:\/\//.test(it.u)));
  check('item 的 u（若有）均为 http(s) 链接', badU.length === 0,
    badU.length ? '异常 ' + badU.length + ' 节' : '带链接 ' + bsec.reduce((n, s) => n + s.items.filter(i => i.u).length, 0) + ' 条');
}

// —— 2026-09-12 三次修订：内容本身精炼（用户要求「把关键信息总结一下就行」）——
const BRIEF_MAX = 80, BRIEF_TOTAL_MAX = 1200;
const ROUTINE_WORDS = ['装车发运', '出厂检验', '启运', '工商登记变更', '工商变更', '完成工商',
  '业绩说明会', '投资者关系', '机构调研', '持续督导', '核查意见', '法律意见书',
  '股东大会', '董事会决议', '监事会', '异常波动', '问询函', '关注函',
  '更正公告', '补充公告', '权益变动', '减持', '增持'];
if (Array.isArray(bsec)) {
  const allT = bsec.reduce((a, s) => a.concat(s.items.map(i => i.t)), []);
  const over = allT.filter(t => t.length > BRIEF_MAX);
  const lens = allT.map(t => t.length);
  check('每条精炼句 ≤ ' + BRIEF_MAX + ' 字', over.length === 0,
    over.length ? over.length + ' 条超长：' + over.map(t => t.length + '字').join(',')
                : '最长 ' + Math.max.apply(null, lens) + ' 字');
  const totalChars = lens.reduce((n, v) => n + v, 0);
  check('简报总字数 ≤ ' + BRIEF_TOTAL_MAX + '（原 4184 字）', totalChars <= BRIEF_TOTAL_MAX,
    totalChars + ' 字 / ' + allT.length + ' 条，平均 ' + Math.round(totalChars / allT.length) + ' 字');
  const hit = allT.filter(t => ROUTINE_WORDS.some(w => t.indexOf(w) >= 0));
  check('无低信息量例行条目混入简报', hit.length === 0,
    hit.length ? hit.map(t => t.slice(0, 22)).join(' | ') : '0 条（例行条目仅在下方新闻列表）');
  const newCount = (REPORT.stats && REPORT.stats.new_count) || 0;
  check('简报条数少于当日新增条数（体现精选）', allT.length < newCount,
    allT.length + ' 条简报 vs ' + newCount + ' 条新增');
  check('精炼句非空且不含「（原题：」噪声',
    allT.every(t => t.trim() && t.indexOf('（原题：') < 0));
  check('每条精炼句以句末标点收尾', allT.every(t => /[。！？）]$/.test(t.trim())),
    allT.filter(t => !/[。！？）]$/.test(t.trim())).map(t => t.slice(-12)).join(' | ') || '全部合规');
}

check('report 仍保留（兜底文本）', typeof REPORT.report === 'string' && REPORT.report.trim().length > 0,
  (REPORT.report || '').length + ' 字');
check('stats/sections/top_news 未被破坏',
  !!REPORT.stats && !!REPORT.sections && Array.isArray(REPORT.top_news));

// highlights：2026-09-12 二次修订后前端不再渲染。生成端可继续产出，但若产出则结构须合法。
const hls = REPORT.highlights;
if (Array.isArray(hls) && hls.length) {
  check('highlights 仍产出且结构合法（前端当前不渲染，留待复用）',
    hls.every(h => h && typeof h.t === 'string' && h.t.trim()) && hls.length <= 8,
    hls.length + ' 条');
} else {
  skip('highlights 结构校验', '生成端已不产出该字段（前端本就不渲染，无影响）');
}

// ==================== ② / ③ 渲染 ====================
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.png': 'image/png', '.css': 'text/css; charset=utf-8' };

function makeServer(stripSections) {
  return http.createServer((req, res) => {
    const u = new URL(req.url, 'http://127.0.0.1:' + PORT);
    const name = decodeURIComponent(u.pathname).replace(/^\/+/, '') || 'index.html';
    if (name === 'morning_report.json' && stripSections) {
      const body = JSON.stringify(Object.assign({}, REPORT, { highlights: undefined, brief_sections: undefined }));
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(body);
      return;
    }
    const p = path.join(ROOT, name);
    if (!fs.existsSync(p) || !fs.statSync(p).isFile()) {
      res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end('404');
      return;
    }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(name)] || 'application/octet-stream' });
    fs.createReadStream(p).pipe(res);
  });
}

function installFetch(win) {
  win.fetch = (u, o) => globalThis.fetch(new URL(String(u), win.location.href).toString(), o || {});
  if (typeof win.matchMedia !== 'function') {
    win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
  }
  win.HTMLElement.prototype.scrollTo = function () {};
  win.scrollTo = function () {};
  win.HTMLElement.prototype.scrollIntoView = function () {};
  // jsdom 不做布局：scrollHeight 恒为 0，会让「内容超高→默认收起」的分支静默不执行。
  // 这里固定返回 900（> 420 阈值），保证折叠逻辑被真实覆盖。
  Object.defineProperty(win.HTMLElement.prototype, 'scrollHeight', { configurable: true, get() { return 900; } });
}

async function loadPage(stripSections) {
  const server = makeServer(stripSections);
  await new Promise(r => server.listen(PORT, '127.0.0.1', r));
  const dom = await JSDOM.fromURL('http://127.0.0.1:' + PORT + '/index.html', {
    runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true, beforeParse: installFetch
  });
  const win = dom.window, doc = win.document;
  const deadline = Date.now() + 12000;
  while (Date.now() < deadline) {
    const m = doc.getElementById('briefMain');
    if (m && m.querySelectorAll('li').length > 0 && !doc.querySelector('#briefMain .skeleton')) break;
    await sleep(150);
  }
  await sleep(400); // 等 setupBriefClamp 里的 setTimeout(apply,300) 走完
  return { dom, win, doc, server };
}

(async () => {
  let s1 = null, s2 = null;
  try {
    // ---------- ② 渲染（正常数据）----------
    console.log('\n===== ② 渲染：五节结构化摘要 + 默认收起 =====');
    const p1 = await loadPage(false); s1 = p1.server;
    const doc = p1.doc, win = p1.win;

    const main = doc.getElementById('briefMain');
    check('#briefMain 已渲染内容', !!main && main.textContent.trim().length > 0);

    // —— 要点层与高异动行必须消失（本轮改动的核心）——
    check('不再渲染要点层（.brief-hl）', doc.querySelectorAll('#briefMain .brief-hl').length === 0);
    check('不再渲染要点层容器（.brief-hl-wrap）', doc.querySelectorAll('#briefMain .brief-hl-wrap').length === 0);
    check('不再渲染类别小标（.hl-cat）', doc.querySelectorAll('#briefMain .hl-cat').length === 0);
    check('不再渲染高异动行（.brief-alert）', doc.querySelectorAll('#briefMain .brief-alert').length === 0);
    const wantAlert = !!(REPORT.sections && REPORT.sections.anomalies && REPORT.sections.anomalies.max_severity === 'high');
    check('数据即使有 high 级异动也不出现异动行', wantAlert ? doc.querySelectorAll('#briefMain .brief-alert').length === 0 : true,
      'max_severity=' + (REPORT.sections && REPORT.sections.anomalies ? REPORT.sections.anomalies.max_severity : '?') + '（异动行已于 2026-09-12 二次修订移除）');

    const sub = doc.getElementById('briefSub');
    check('副标题固定为「按分类摘要」', !!sub && sub.textContent.trim() === '按分类摘要',
      sub ? sub.textContent.trim() : '(无)');

    // —— 结构化分节层 ——
    const full = doc.querySelector('#briefMain .brief-full');
    check('结构化分节层存在', !!full);
    check('分节层不带 hidden（默认在 DOM 内，靠高度裁剪收起）',
      !!full && !full.hasAttribute('hidden') && full.hidden === false);

    if (full) {
      const fullLis = full.querySelectorAll('li');
      const total = (bsec || []).reduce((n, s) => n + s.items.length, 0);
      check('分节层 li 数 == brief_sections 总条数', fullLis.length === total, fullLis.length + ' vs ' + total);

      const secs = full.querySelectorAll('.brief-sec');
      check('节标题数 == brief_sections 节数', secs.length === (bsec || []).length,
        secs.length + ' vs ' + (bsec || []).length);

      const badges = [...full.querySelectorAll('.brief-sec .sec-n')];
      check('每个节标题都带条数徽标', badges.length === secs.length, badges.length + '/' + secs.length);
      const badgeOk = badges.every((b, i) => parseInt(b.textContent, 10) === (bsec[i] ? bsec[i].items.length : -1));
      check('条数徽标数值与该节实际条数一致', badgeOk, badges.map(b => b.textContent).join(','));

      check('分节层不出现「今日暂无…」占位句', !/今日暂无/.test(full.textContent));
    }

    // —— 默认收起（420px 折叠）——
    const more = doc.getElementById('briefMore');
    check('默认收起：内容超高时 #briefMain 带 brief-clamp（折叠后 380px）', main.classList.contains('brief-clamp'));
    check('展开按钮可见', !!more && more.hidden === false);
    check('按钮文案为「展开全部（N 条）」', !!more && /^展开全部（\d+ 条）$/.test(more.textContent.trim()),
      more ? more.textContent.trim() : '(无)');

    if (more) {
      more.dispatchEvent(new win.MouseEvent('click', { bubbles: true }));
      check('点击后解除折叠', !main.classList.contains('brief-clamp'));
      check('点击后按钮变「收起」', more.textContent.trim() === '收起', more.textContent.trim());
      more.dispatchEvent(new win.MouseEvent('click', { bubbles: true }));
      check('再点击恢复折叠', main.classList.contains('brief-clamp'));
      check('再点击按钮恢复展开文案', /^展开全部/.test(more.textContent.trim()), more.textContent.trim());
    }

    // —— 条目点击定位下方新闻卡片 ——
    const jumps = [...doc.querySelectorAll('#briefMain a[data-jump]')];
    check('分节条目带 data-jump 链接', jumps.length > 0, jumps.length + ' 条');
    if (jumps.length) {
      const a = jumps[0];
      const url = a.getAttribute('data-jump');
      const target = [...doc.querySelectorAll('.news-item')].find(e => e.getAttribute('data-url') === url);
      if (target) {
        a.dispatchEvent(new win.MouseEvent('click', { bubbles: true, cancelable: true }));
        check('点击简报条目 → 对应新闻卡片高亮', target.classList.contains('brief-flash'));
      } else {
        skip('点击跳转高亮', '该条不在当前页 DOM（' + String(url).slice(0, 56) + '）');
      }
    }
  } catch (e) {
    fail++;
    console.log('  FAIL  ② 渲染阶段异常 → ' + (e && e.message));
  } finally {
    if (s1) s1.close();
  }

  try {
    // ---------- ③ 回退路径（剥掉两个字段）----------
    console.log('\n===== ③ 回退：无 brief_sections 时走 markdown =====');
    const p2 = await loadPage(true); s2 = p2.server;
    const doc2 = p2.doc;
    const main2 = doc2.getElementById('briefMain');
    check('#briefMain 仍有内容（回退渲染成功）', !!main2 && main2.textContent.trim().length > 0);
    check('回退时不渲染结构化分节层', !doc2.querySelector('#briefMain .brief-full'));
    check('回退时渲染 report 的 markdown 列表', doc2.querySelectorAll('#briefMain > ul > li').length > 0,
      doc2.querySelectorAll('#briefMain > ul > li').length + ' 条');
    check('回退时也不渲染要点层/异动行',
      doc2.querySelectorAll('#briefMain .brief-hl, #briefMain .brief-alert').length === 0);
    const sub2 = doc2.getElementById('briefSub');
    check('回退时副标题同为「按分类摘要」', !!sub2 && sub2.textContent.trim() === '按分类摘要',
      sub2 ? sub2.textContent.trim() : '(无)');
    check('回退时同样走高度折叠（内容超高）', !!main2 && main2.classList.contains('brief-clamp'));
  } catch (e) {
    fail++;
    console.log('  FAIL  ③ 回退阶段异常 → ' + (e && e.message));
  } finally {
    if (s2) s2.close();
  }

  // ---------- ④ 折叠按钮（#briefToggle）选择器守卫 ----------
  // 2026-09-12：用户反馈「今日简报右上角那个小圆按钮点不动」。
  //   根因：CSS 写成 `.briefStrip.brief-collapsed` —— 元素的 class 是 `brief-strip`，
  //   而 `briefStrip` 是它的 **id**。选择器匹配不到任何元素，JS 确实 toggle 了 class，
  //   但没有任何样式响应，观感就是「点了没反应」。
  console.log('\n===== ④ 折叠按钮选择器守卫 =====');
  {
    const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
    const appjs = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
    // 只取真正的 <style> 块：先剔掉 <script>，否则 JS 字符串里的内容会被当 CSS 解析
    const noScript = html.replace(/<script[\s\S]*?<\/script>/gi, '');
    const css = (noScript.match(/<style[^>]*>[\s\S]*?<\/style>/gi) || []).join('\n');
    check('取到 index.html 的 CSS 块', css.length > 1000, css.length + ' 字符');

    check('折叠规则挂在真实类名 .brief-strip 上',
      /\.brief-strip\.brief-collapsed\s+\.brief-card\s*\{[^}]*display\s*:\s*none/.test(css));
    check('不再出现 .briefStrip 这类「把 id 当 class」的选择器', !/\.briefStrip[\s.{:,#]/.test(css));
    check('折叠时按钮旋转同样用 .brief-strip',
      /\.brief-strip\.brief-collapsed\s+#briefToggle\s*\{[^}]*rotate\(-90deg\)/.test(css));
    check('#briefToggle 是 button 且初始 aria-expanded=true',
      /<button id="briefToggle"[^>]*aria-expanded="true"/.test(html));
    check('JS 折叠时同步 aria-expanded',
      /classList\.toggle\('brief-collapsed'\)[\s\S]{0,140}aria-expanded/.test(appjs));
    // 2026-09-12：折叠状态持久化（永久记住 + 首帧前恢复）。两处 key 必须一致，故加漂移守卫。
    const BKEY = 'mdBriefCollapsed';
    check('app.js 用常量保存折叠 key',
      appjs.includes("var BRIEF_COLLAPSE_KEY='" + BKEY + "'"));
    check('app.js 读折叠状态（getItem）', /getItem\(BRIEF_COLLAPSE_KEY\)/.test(appjs));
    check('app.js 写折叠状态（setItem）', /setItem\(BRIEF_COLLAPSE_KEY\b/.test(appjs));
    check('index.html 有绘制前恢复折叠态的内联脚本',
      new RegExp("<script>try\\{if\\(localStorage\\.getItem\\('" + BKEY + "'\\)==='1'\\)").test(html));
    check('内联脚本恢复时同步 aria-expanded',
      /classList\.add\('brief-collapsed'\)[\s\S]{0,120}aria-expanded/.test(html));
    check('key 无硬编码漂移（app.js 定义 1 次 / html 字面量 1 次）',
      (appjs.match(/BRIEF_COLLAPSE_KEY\s*=/g) || []).length === 1 &&
      (html.match(new RegExp(BKEY, 'g')) || []).length === 1,
      'app.js x' + (appjs.match(/BRIEF_COLLAPSE_KEY\s*=/g) || []).length +
      ' / html x' + (html.match(new RegExp(BKEY, 'g')) || []).length);

    // 通用守卫：CSS 里不得出现「与页面某个 id 同名」的 camelCase 类选择器
    //   （本工程约定：class 用 kebab-case、id 用 camelCase；撞名基本就是写错了）
    const ids = new Set((html.match(/\bid="[^"]+"/g) || []).map(s => s.slice(4, -1)));
    const cls = new Set((css.match(/\.[A-Za-z_][A-Za-z0-9_-]*/g) || []).map(s => s.slice(1)));
    const collide = [...cls].filter(c => ids.has(c) && /[a-z][A-Z]/.test(c));
    check('CSS 无「id 名当类名」的死选择器', collide.length === 0, collide.join(', ') || '无');
  }

  // ---------- ⑤ 折叠态持久化行为验证 ----------
  // 2026-09-12：④ 那 6 条是静态断言（只证明「代码在」）。这里真解析一遍 DOM，证明「代码在用」。
  //   关键：只开 runScripts、不开 resources ⇒ 外链 app.js 不会被加载，
  //   于是这里看到的 DOM 状态只可能来自 index.html 里那段 pre-paint 内联脚本 ——
  //   正是「首帧就是收起的，不依赖 app.js」这一主张的直接证据。
  console.log('\n===== ⑤ 折叠态持久化行为（预置存储 → 解析后立即生效） =====');
  {
    const rawHtml = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
    const mkDom = (val) => new JSDOM(rawHtml, {
      runScripts: 'dangerously',
      url: 'https://example.org/',
      beforeParse(window) {
        if (val !== null) window.localStorage.setItem('mdBriefCollapsed', val);
      }
    });

    const d1 = mkDom('1');
    const s1 = d1.window.document.getElementById('briefStrip');
    const t1 = d1.window.document.getElementById('briefToggle');
    check('存储=1 → 解析后 #briefStrip 已带 brief-collapsed（app.js 未加载）',
      !!s1 && s1.classList.contains('brief-collapsed'));
    check('存储=1 → 按钮 aria-expanded 同步为 false',
      !!t1 && t1.getAttribute('aria-expanded') === 'false');
    d1.window.close();

    const d2 = mkDom('0');
    const s2b = d2.window.document.getElementById('briefStrip');
    const t2b = d2.window.document.getElementById('briefToggle');
    check('存储=0 → 解析后不带 brief-collapsed', !!s2b && !s2b.classList.contains('brief-collapsed'));
    check('存储=0 → 按钮 aria-expanded=true',
      !!t2b && t2b.getAttribute('aria-expanded') === 'true');
    d2.window.close();

    const d3 = mkDom(null);
    const s3 = d3.window.document.getElementById('briefStrip');
    check('从未折叠过（无存储）→ 默认展开', !!s3 && !s3.classList.contains('brief-collapsed'));
    d3.window.close();
  }

  console.log('\n==== 简报渲染回归：' + pass + ' PASS / ' + fail + ' FAIL ====');
  process.exit(fail ? 1 : 0);
})();
