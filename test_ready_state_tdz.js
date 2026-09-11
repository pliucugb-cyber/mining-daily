// test_ready_state_tdz.js
// 2026-09-11 事故（第三轮，真正根因）回归测试 —— **defer 脚本的 readyState 语义**
//
// 用户现象：今日要闻 / 热榜 / AI 检索全空（简报正常），强制清缓存无效。
// 用户给出的诊断：
//   [脚本错误] Uncaught ReferenceError: Cannot access 'newsSearchText' before initialization
//   [补渲染失败] qaReinit → Cannot read properties of undefined (reading 'forEach')
//   [补渲染失败] renderDigest → Cannot read properties of undefined (reading 'forEach')
//
// 机制（已用本测试的对照实验证实）：
//   ① index.html 里 4 个脚本都是 defer。**真实浏览器执行 defer 脚本时
//      document.readyState 已经是 'interactive'**，不是 'loading'。
//   ② app.js 里的矿权 IIFE 写成
//        if(readyState==='loading') addEventListener(DOMContentLoaded, ...);
//        else { renderRightsSection(); injectRightsResultSummary(); bindRights(); }
//      于是走 else 分支，**在 app.js 求值期间当场执行业务初始化**。
//   ③ 而它读到的模块状态（newsSearchText）声明在文件第 ~695 行 —— 还没执行到 →
//      TDZ ReferenceError。
//   ④ 后果不是「少个筛选」，而是 **app.js 在此处整体中断**：其后所有顶层语句都不执行，
//      包括 2319 行的初始化链和 2139/2793 行的 var 赋值。
//      于是热榜/要闻/AI 检索全空、下拉框无选项；而静态内容（生成器写死）照常显示。
//
// 为什么以前所有测试都漏掉：jsdom 执行 defer 脚本时 readyState 仍是 'loading'，
// 走的是安全的 DOMContentLoaded 分支 —— 本地怎么跑都是好的。
//
// 对照实验（修复前 app.js = git HEAD）：
//   tookElse=true  → 走了求值期立即初始化分支
//   hasTDZ=true    → 复现 "Cannot access 'newsSearchText' before initialization"
//   appEvaluated=false / QA_MINERALS_len=0 → app.js 求值中断、后续 var 未赋值
//   修复后：tookElse=false、reachedRights318=true、appEvaluated=true、
//           QA_MINERALS_len=33、DIGEST_SRC_len=14、hasTDZ=false、errors=[]
//
// 运行：node test_ready_state_tdz.js
const fs = require('fs');
const path = require('path');
const http = require('http');
const { JSDOM, VirtualConsole } = require('jsdom');

const ROOT = __dirname;
const PORT = 8817;

let pass = 0, fail = 0;
function check(name, cond, why) {
  if (cond) { pass++; console.log('  PASS  ' + name + (why ? '  → ' + why : '')); }
  else { fail++; console.log('  FAIL  ' + name + (why ? '  → ' + why : '')); }
}

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.png': 'image/png', '.css': 'text/css; charset=utf-8'
};

function loadPage() {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const u = new URL(req.url, 'http://127.0.0.1:' + PORT);
      const name = decodeURIComponent(u.pathname).replace(/^\/+/, '') || 'index.html';
      const p = path.join(ROOT, name);
      if (!fs.existsSync(p) || !fs.statSync(p).isFile()) {
        res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' }); res.end('404'); return;
      }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(name)] || 'application/octet-stream' });
      fs.createReadStream(p).pipe(res);
    });
    const jsdomErrors = [];
    const vc = new VirtualConsole();
    vc.on('jsdomError', e => jsdomErrors.push(String(
      (e && (e.detail && (e.detail.message || e.detail.stack) || e.message)) || e).split('\n')[0]));
    server.listen(PORT, '127.0.0.1', () => {
      JSDOM.fromURL('http://127.0.0.1:' + PORT + '/index.html', {
        runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true, virtualConsole: vc,
        beforeParse(win) {
          // ★ 本测试的核心：模拟真实浏览器 —— defer 脚本执行期间 readyState 已是 'interactive'。
          //   jsdom 默认会保持 'loading'，那正是这个 bug 长期隐身的原因。
          Object.defineProperty(win.document, 'readyState', { configurable: true, get() { return 'interactive'; } });
          win.fetch = (u, o) => globalThis.fetch(new URL(String(u), win.location.href).toString(), o || {});
          win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
          win.HTMLElement.prototype.scrollTo = function () {};
          win.scrollTo = function () {};
        }
      }).then(dom => resolve({ dom, server, jsdomErrors })).catch(err => { server.close(); reject(err); });
    });
  });
}

(async function main() {
  const appSrc = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
  const htmlSrc = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
  const appLines = appSrc.split(/\r?\n/);

  console.log('===== ① 结构断言：不得在求值期执行业务初始化 =====');
  // 注意：app.js 的说明注释里**引用了**旧写法（便于后人理解根因），
  // 因此这里要忽略注释行，只检查真正的代码行。
  const codeLines = appLines.filter(l => !l.trim().startsWith('//') && !l.trim().startsWith('*'));
  const badLine = codeLines.findIndex(l => l.indexOf('else { renderRightsSection();') >= 0);
  check('app.js 不再有「求值期立即调用」形态',
    badLine < 0,
    'git HEAD 版正是这一行 → 实测复现 TDZ 并让整个脚本中断');
  check('IIFE 的即时分支改为延迟初始化（setTimeout 0）',
    codeLines.some(l => /else setTimeout\(mdInitRights, 0\);/.test(l)),
    '放到本轮求值结束之后，所有顶层声明都已就绪');
  const declLine = appLines.findIndex(l => l.indexOf("let newsSearchText=''") >= 0) + 1;
  check('newsSearchText 声明已提到文件最前端（前 60 行内）',
    declLine > 0 && declLine <= 60,
    '实际在第 ' + declLine + ' 行；原在第 ~695 行 → 早于它的调用必然 TDZ');
  ['filterMode', 'tagFilter', 'newsSearchText', 'oldExpanded'].forEach(v => {
    const n = appLines.slice(0, 60).filter(l => new RegExp('^let ' + v + '=').test(l)).length;
    check('模块状态 ' + v + ' 在前 60 行声明且只声明一次', n === 1, '出现次数=' + n);
  });
  check('app.js 末行是「求值完成」信标',
    appLines.filter(l => l.trim()).slice(-1)[0].trim() === 'window.__mdAppEvaluated=true;',
    '任何中断都会让这个信标缺失 → 线上可一眼判定「脚本跑了一半」');
  check('index.html 诊断信息暴露 evaluated 字段',
    htmlSrc.indexOf('evaluated:!!window.__mdAppEvaluated') >= 0,
    '复制诊断信息即可看出是「执行中断」而不是「未执行」');

  console.log('\n===== ② 行为断言：强制 readyState=interactive 加载页面 =====');
  {
    const { dom, server, jsdomErrors } = await loadPage();
    const w = dom.window;
    await new Promise(r => setTimeout(r, 5000));
    const doc = w.document;
    const errs = [].concat(w.__mdErrors || [], jsdomErrors).map(String)
      .filter(x => !/goatcounter/.test(x));

    check('app.js 求值到底（__mdAppEvaluated === true）',
      w.__mdAppEvaluated === true,
      'false/undefined 即「脚本中断在半路」，后续所有顶层语句都没执行');
    check('没有 TDZ / 未捕获脚本错误',
      !errs.some(x => /before initialization/.test(x)) && !errs.some(x => /Uncaught/.test(x)),
      errs.length ? '错误：' + errs.slice(0, 3).join(' | ') : '无错误');
    check('列表型全局已真实赋值（QA_MINERALS / DIGEST_SRC）',
      (w.QA_MINERALS || []).length > 10 && (w.DIGEST_SRC || []).length > 0,
      'QA_MINERALS=' + (w.QA_MINERALS || []).length + ' DIGEST_SRC=' + (w.DIGEST_SRC || []).length
      + '（中断时这两处会停在占位空数组）');

    const digest = (doc.getElementById('digestStrip') || {}).textContent || '';
    check('今日要闻已渲染（不再是「要闻提取中…」）',
      digest.trim().length > 0 && digest.indexOf('提取中') < 0,
      '要闻文本=' + digest.replace(/\s+/g, ' ').trim().slice(0, 50));
    const hot = (doc.getElementById('hotListBody') || {}).textContent || '';
    check('热榜已渲染（不再是「加载中…」）',
      hot.trim().length > 0 && hot.indexOf('加载中') < 0 && hot.indexOf('加载失败') < 0,
      '热榜文本=' + hot.replace(/\s+/g, ' ').trim().slice(0, 50));

    dom.window.close();
    server.close();
  }

  console.log('\n===== 结果：' + pass + ' PASS / ' + fail + ' FAIL =====');
  process.exit(fail ? 1 : 0);
})().catch(e => {
  console.error('测试异常：', e && (e.stack || e.message || e));
  process.exit(1);
});
