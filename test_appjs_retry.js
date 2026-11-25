// test_appjs_retry.js
// 2026-11-25 事故回归 —— app.js 加载失败后「永久红条」的根治守护
//
// 用户现象：手机打开日报持续显示「页面脚本出错（app.js 未执行）」，
//   点「立即重试加载」「强制重新加载（清缓存）」、关标签页重开三种方法都无效。
// 根因链：
//   ① github.io 国内访问极不稳（实测单请求卡满 25s、传输被截断）；
//   ② app.js 约 320KB 单文件，某次请求失败/HTTP 缓存残留残缺响应 → __mdBooted 永远 false；
//   ③ 用户三个手动方法请求的仍是同一个 app.js?v=<固定指纹> → 缓存里残缺文件被反复读取；
//   ④ 自动自愈又被 sessionStorage 的 RESET_FLAG 会话级锁死，试一次就放弃。
// 修复：index.html 内联重试器包装 mdScriptFail，app.js 加载失败时用
//   全新 ?__mdretry=<时间戳> URL 动态注入绕过 HTTP 缓存；退避重试 3 次，
//   成功自动同步横幅清红条。用户全程无感。
//
// 本测试抽取 index.html 里的重试器 IIFE 到 jsdom 沙箱独立跑，不依赖整页加载，
// 也不受其它内联脚本干扰。
//
// 运行：node test_appjs_retry.js
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = __dirname;
const HTML = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');

let pass = 0, fail = 0;
function check(name, cond, why) {
  if (cond) { pass++; console.log('  PASS  ' + name + (why ? '  → ' + why : '')); }
  else { fail++; console.log('  FAIL  ' + name + (why ? '  → ' + why : '')); }
}

// ── 从 index.html 抽取重试器 IIFE ──────────────────────────────────────────
const START = '  // ===== app.js 加载失败自动重试';
const END = '  })();';
const s = HTML.indexOf(START);
const e = s < 0 ? -1 : HTML.indexOf(END, s);
const block = (s >= 0 && e >= 0) ? HTML.slice(s, e + END.length) : '';

console.log('\n=== A. 静态结构守护 ===');
check('A1 index.html 含 app.js 重试器 IIFE', block.length > 200, 'block=' + block.length + ' chars');
check('A2 重试器使用唯一 query 绕缓存', block.indexOf('__mdretry') >= 0);
check('A3 有重试次数上限（防无限循环）', /S\.tries>=S\.max/.test(block));
check('A4 成功后主动同步横幅清红条', /window\.mdSyncBanner\(\)/.test(block));
check('A5 保留原 app.js script 标签（测试隔离依赖）',
  /<script src="app\.js"[^>]*><\/script>/.test(HTML));
check('A6 onerror 仍走 mdScriptFail 钩子', /mdScriptFail&&window\.mdScriptFail\('app\.js'\)/.test(HTML));
check('A7 8 秒看门狗覆盖「请求挂起无回调」', /\},8000\)/.test(block) && /script\[src\*="app\.js"\]/.test(block));

// ── jsdom 沙箱实测重试链 ───────────────────────────────────────────────────
function makeSandbox() {
  const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>',
    { runScripts: 'outside-only' });
  const w = dom.window;
  // 假定时器：退避立即执行，看门狗(>=8000ms)不自动触发；setInterval 只跑一次
  w.setTimeout = function (fn, ms) { if (ms >= 8000) return 0; fn(); return 0; };
  w.setInterval = function (fn) { fn(); return 1; };
  w.clearInterval = function () {};
  // 捕获动态注入的 script，但不真的发起网络
  const injected = [];
  const origCreate = w.document.createElement.bind(w.document);
  w.document.createElement = function (tag) {
    const el = origCreate(tag);
    if (String(tag).toLowerCase() === 'script') injected.push(el);
    return el;
  };
  // 原钩子与横幅打点
  const calls = { origFail: [], banner: 0 };
  w.mdScriptFail = function (name) { calls.origFail.push(name); };
  w.mdSyncBanner = function () { calls.banner++; };
  w.eval(block);
  return { w, injected, calls };
}

console.log('\n=== B. 重试链行为实测 ===');
{
  const { w, injected, calls } = makeSandbox();
  check('B1 重试器已注册', typeof w.mdAppRetry === 'function');
  check('B2 原 mdScriptFail 钩子被保留', typeof w.mdScriptFailOrig === 'function');

  // 非 app.js 的失败仍走原钩子（不误伤其它资源）
  w.mdScriptFail('sw.js');
  check('B3 其它脚本名仍走原提示钩子',
    calls.origFail.join(',') === 'sw.js', 'origFail=' + calls.origFail.join(','));
  check('B4 其它脚本名不触发 app.js 重试', injected.length === 0);

  // app.js 失败 → 第一次重试，URL 带唯一 query
  w.mdScriptFail('app.js');
  check('B5 app.js 失败触发动态重试', injected.length === 1, 'injected=' + injected.length);
  const u1 = injected[0] && injected[0].src || '';
  check('B6 重试 URL 带 __mdretry 时间戳', /app\.js\?__mdretry=\d+-\d+/.test(u1), u1);

  // 第一次 onerror → 退避后立即注入第二次，URL 必须不同（绕缓存关键）
  injected[0].onerror();
  check('B7 失败后自动重试第二次', injected.length === 2);
  const u2 = injected[1] && injected[1].src || '';
  check('B8 每次重试 URL 都不同（绕开损坏缓存）', u1 !== u2, u1 + ' vs ' + u2);

  // 第二次 onerror → 第三次
  injected[1].onerror();
  check('B9 失败后自动重试第三次', injected.length === 3);

  // 第三次 onerror → 达上限，不再注入，回落原提示
  injected[2].onerror();
  check('B10 达到上限后停止重试（防无限循环）', injected.length === 3);
  check('B11 三次全失败后回落原红条提示',
    calls.origFail.indexOf('app.js') >= 0, 'origFail=' + calls.origFail.join(','));
}

console.log('\n=== C. 成功恢复 / 防重入 ===');
{
  const { w, injected, calls } = makeSandbox();
  w.mdScriptFail('app.js');
  check('C1 重试进行中拒绝重复触发', (function () {
    w.mdAppRetry();
    return injected.length === 1;
  })(), 'injected=' + injected.length);

  // 模拟 app.js 这次加载成功并执行
  w.__mdBooted = true;
  injected[0].onload();
  check('C2 加载成功后主动同步横幅（清红条）', calls.banner >= 1, 'banner=' + calls.banner);
  check('C3 成功后 busy 标志复位', w.__mdAppRetryState.busy === false);

  // 已 booted 后不再重试
  w.mdAppRetry();
  check('C4 已执行后不再注入脚本', injected.length === 1);
}

console.log('\n=== D. 看门狗不误伤测试环境 ===');
{
  // 页面里没有 app.js 标签时（多数测试会 replace 掉），8s 看门狗不得注入
  const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>',
    { runScripts: 'outside-only' });
  const w = dom.window;
  const fired = [];
  w.setTimeout = function (fn, ms) { if (ms >= 8000) { fired.push(fn); return 1; } fn(); return 0; };
  w.setInterval = function () { return 1; };
  w.clearInterval = function () {};
  const injected = [];
  const origCreate = w.document.createElement.bind(w.document);
  w.document.createElement = function (tag) {
    const el = origCreate(tag);
    if (String(tag).toLowerCase() === 'script') injected.push(el);
    return el;
  };
  w.eval(block);
  check('D1 看门狗已注册', fired.length === 1);
  fired[0]();  // 模拟 8s 到点
  check('D2 无 app.js 标签时不误触发重试', injected.length === 0, 'injected=' + injected.length);
}

console.log('\n────────────────────────────────');
console.log('PASS=' + pass + '  FAIL=' + fail);
process.exit(fail ? 1 : 0);
