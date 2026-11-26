// test_sw_cache_mismatch.js
// 2026-11-26 事故回归 —— 「HTML 新 / SW 旧」死局根治守护
//
// 用户诊断：build=20261126-0100（HTML 新），caches=mining-daily-20261125-1939（SW 旧），
//   sw=受控，app.js=未执行，news=缺失。根因是弱网导致 sw.js 更新检查失败，
//   旧 SW 继续控制页面、用坏缓存喂残缺 app.js；v1(换 query)/v2(fetch 内联) 的请求
//   同样被旧 SW 的 fetch handler 拦截，绕不过 SW ⇒ 永久红条。
//
// v3 修复：内联脚本读 caches.keys()，发现 ≠ 当前 build 的 mining-daily- 旧缓存
//   且 app.js 未启动时 → 注销 SW + 清 CacheStorage + cache-bust reload。
//   三道闸：app.js 正常不动作 / 无旧缓存不动作 / sessionStorage 按 build 只重置一次。
//
// 本测试抽取 index.html 的 v3 IIFE 到 jsdom 沙箱，mock caches / serviceWorker / location。
//
// 运行：node test_sw_cache_mismatch.js
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
function flush() { return new Promise(r => setImmediate(r)); }

// ── 抽取 v3 守卫 IIFE ─────────────────────────────────────────────────────
const START = '  // ===== SW 缓存版本错配守卫 v3';
const END = '  })();';
const s = HTML.indexOf(START);
const e = s < 0 ? -1 : HTML.indexOf(END, s);
const block = (s >= 0 && e >= 0) ? HTML.slice(s, e + END.length) : '';

console.log('\n=== A. 静态结构守护 ===');
check('A1 含 v3 缓存错配守卫 IIFE', block.indexOf('缓存版本错配守卫 v3') >= 0, 'block=' + block.length);
check('A2 通过 caches.keys() 检查本机缓存', block.indexOf('caches.keys()') >= 0);
check('A3 只认 mining-daily-<build> 命名空间', /mining-daily-\\d\{8\}-\\d\{4\}/.test(block));
check('A4 与当前 build 不同的才视为旧缓存', block.indexOf("n!==want") >= 0);
check('A5 app.js 正常启动则跳过（防误伤闸1）',
  block.indexOf('if(window.__mdBooted&&window.__mdAppEvaluated)return') >= 0);
check('A6 离线时跳过（防误伤闸2）', block.indexOf('navigator.onLine===false') >= 0);
check('A7 sessionStorage 按 build 只重置一次（防误伤闸3）', /GFLAG\+'_'\+b/.test(block));
check('A8 注销全部 SW 注册', /getRegistrations[\s\S]*unregister\(\)/.test(block));
check('A9 清空 CacheStorage', /caches\.delete\(n\)/.test(block));
check('A10 带 _mdsw cache-bust 重载', block.indexOf("set('_mdsw'") >= 0);
check('A11 多级定时器错开 v2 看门狗', block.indexOf('[6000,16000,32000,60000]') >= 0);
check('A12 监听 controllerchange 复查（拼接写法避免与旧守卫切段冲突）',
  block.indexOf("addEventListener(_cc") >= 0 && block.indexOf("'controller'+'change'") >= 0);
check('A13 v2 三次失败后兜底调用守卫', HTML.indexOf('if(window.mdSwCacheGuard)window.mdSwCacheGuard()') >= 0);
check('A14 build 已 bump 到 20261126-0300', /name="build-version" content="20261126-0300"/.test(HTML));
check('A15 v1 的 __mdretry 方案无残留', HTML.indexOf('__mdretry') < 0);
// 2026-11-26 二次事故：同 build「只清一次」在旧 SW 复活时把后续全挡死。
check('A16 守卫支持 force 参数（v2 终极兜底跳过冷却）', block.indexOf('function guard(force)') >= 0);
check('A17 同 build 最多清 3 次（防旧 SW 复活后无第二次机会）', block.indexOf('st.n>=3') >= 0);
check('A18 20 秒冷却期（防 reload 死循环）', block.indexOf('(Date.now()-st.t)<20000') >= 0);
check('A19 对外暴露 force 变体', HTML.indexOf('window.mdSwCacheGuardForce=function(){ guard(true); }') >= 0);
check('A20 诊断含自愈状态字段 appRetry/guard',
  HTML.indexOf('appRetry:') >= 0 && HTML.indexOf('guard:(window.__mdGuardState') >= 0);

// ── 沙箱：把 location 换导航换成可观测桩，避免 jsdom 真导航 ────────────────
function makeSandbox(opts) {
  opts = opts || {};
  const dom = new JSDOM('<!doctype html><html><head><meta name="build-version" content="20261126-0200"></head><body></body></html>',
    { runScripts: 'outside-only', url: 'https://pliucugb-cyber.github.io/mining-daily/' });
  const w = dom.window;
  const timers = [], listeners = [], log = [], nav = [], store = {};
  w.setTimeout = function (fn, ms) { timers.push({ fn: fn, ms: ms || 0 }); return timers.length; };
  w.clearTimeout = function () {};
  w.console = { info: function () {}, warn: function (m) { log.push(String(m)); }, error: function () {} };

  w.__mdBooted = opts.booted === true;
  w.__mdAppEvaluated = opts.evaluated === true;
  Object.defineProperty(w.navigator, 'onLine', { configurable: true, get: function () { return opts.online !== false; } });

  w.caches = {
    keys: function () { return Promise.resolve(opts.caches || []); },
    delete: function (n) { log.push('delete:' + n); return Promise.resolve(true); }
  };
  const regs = opts.regs === undefined
    ? [{ unregister: function () { log.push('unregister'); return Promise.resolve(true); } }]
    : opts.regs;
  w.navigator.serviceWorker = {
    getRegistrations: function () { return Promise.resolve(regs); },
    addEventListener: function (t) { listeners.push(t); }
  };
  Object.defineProperty(w, 'sessionStorage', { configurable: true, value: {
    getItem: function (k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
    setItem: function (k, v) { store[k] = String(v); }
  } });
  w.__mdNav = function (u) { nav.push(String(u)); };
  w.__mdReload = function () { nav.push('reload'); };

  let code = block.replace(/location\.replace\(/g, 'window.__mdNav(')
                  .replace(/location\.reload\(\)/g, 'window.__mdReload()');
  w.eval(code);
  return { w: w, timers: timers, listeners: listeners, log: log, nav: nav, store: store, guard: w.mdSwCacheGuard };
}

console.log('\n=== B. 错配场景：应触发彻底重置 ===');
(async function () {
  {
    const sb = makeSandbox({ caches: ['mining-daily-20261125-1939'] });
    sb.guard(); await flush(); await flush();
    check('B1 旧缓存 + app.js 未启动 → 触发重载', sb.nav.length === 1, 'nav=' + JSON.stringify(sb.nav));
    check('B2 重载 URL 带 _mdsw cache-bust', /_mdsw=\d+/.test(sb.nav[0] || ''));
    check('B3 注销 SW 注册', sb.log.indexOf('unregister') >= 0, JSON.stringify(sb.log));
    check('B4 删除旧缓存', sb.log.some(function (l) { return l.indexOf('delete:mining-daily-20261125-1939') === 0; }));
    check('B5 写入本 build 的防循环 flag', sb.store['md_sw_cache_guard_20261126-0200'] === '1');
  }

  console.log('\n=== C. 防误伤：不该触发的场景 ===');
  {
    const sb = makeSandbox({ booted: true, evaluated: true, caches: ['mining-daily-20261125-1939'] });
    sb.guard(); await flush(); await flush();
    check('C1 app.js 已正常执行 → 不重置', sb.nav.length === 0);
    check('C2 也不写防循环 flag', !sb.store['md_sw_cache_guard_20261126-0200']);
  }
  {
    const sb = makeSandbox({ caches: ['mining-daily-20261126-0200'] });
    sb.guard(); await flush(); await flush();
    check('C3 缓存与 build 一致（无旧缓存）→ 不重置', sb.nav.length === 0);
  }
  {
    const sb = makeSandbox({ online: false, caches: ['mining-daily-20261125-1939'] });
    sb.guard(); await flush(); await flush();
    check('C4 离线 → 不重置（等联网）', sb.nav.length === 0);
  }
  {
    const sb = makeSandbox({ caches: [] });
    sb.guard(); await flush(); await flush();
    check('C5 无缓存（首次访问）→ 不重置', sb.nav.length === 0);
  }

  console.log('\n=== D. 防循环与定时器 ===');
  {
    const sb = makeSandbox({ caches: ['mining-daily-20261125-1939'] });
    sb.guard(); await flush(); await flush();
    const after1 = sb.nav.length;
    sb.guard(); await flush(); await flush();
    check('D1 同一 build 冷却期内不重复重置', sb.nav.length === after1 && after1 === 1, 'nav=' + sb.nav.length);
    // 2026-11-26 二次事故核心：冷却期内 force 必须能突破（旧 SW 复活时 v2 终极兜底靠它）
    sb.w.mdSwCacheGuardForce(); await flush(); await flush();
    check('D1b force 在冷却期内仍强制重置（救旧 SW 复活）', sb.nav.length === 2, 'nav=' + sb.nav.length);
    check('D2 注册 4 级错开定时器', sb.timers.length === 4, 'timers=' + sb.timers.length);
    check('D3 定时器延迟与 v2 错开（6/16/32/60s）',
      sb.timers.map(function (t) { return t.ms; }).join(',') === '6000,16000,32000,60000');
    check('D4 监听 controllerchange', sb.listeners.indexOf('controllerchange') >= 0);
  }
  {
    // build 变化时 flag 应失效 → 新 build 可再重置一次
    const dom = new JSDOM('<!doctype html><html><head><meta name="build-version" content="20261126-0300"></head><body></body></html>',
      { runScripts: 'outside-only', url: 'https://pliucugb-cyber.github.io/mining-daily/' });
    const w = dom.window;
    w.setTimeout = function () { return 1; };
    const nav = [], store = { 'md_sw_cache_guard_20261126-0200': '1' };
    w.console = { warn: function () {}, info: function () {} };
    w.__mdBooted = false; w.__mdAppEvaluated = false;
    Object.defineProperty(w.navigator, 'onLine', { configurable: true, get: function () { return true; } });
    w.caches = { keys: function () { return Promise.resolve(['mining-daily-20261126-0200']); }, delete: function () { return Promise.resolve(true); } };
    w.navigator.serviceWorker = { getRegistrations: function () { return Promise.resolve([]); }, addEventListener: function () {} };
    Object.defineProperty(w, 'sessionStorage', { configurable: true, value: {
      getItem: function (k) { return store[k] || null; }, setItem: function (k, v) { store[k] = v; }
    } });
    w.__mdNav = function (u) { nav.push(u); };
    w.__mdReload = function () { nav.push('reload'); };
    let code = block.replace(/location\.replace\(/g, 'window.__mdNav(').replace(/location\.reload\(\)/g, 'window.__mdReload()');
    w.eval(code);
    w.mdSwCacheGuard(); await flush(); await flush();
    check('D5 新 build 时旧 flag 不阻挡（可再重置）', nav.length === 1, 'nav=' + nav.length);
  }

  console.log('\n=== 结果 ===');
  console.log('PASS=' + pass + '  FAIL=' + fail);
  process.exit(fail ? 1 : 0);
})();
