// test_appjs_retry.js
// 2026-11-25/26 事故回归 —— app.js 加载失败后「永久红条」的根治守护
//
// 用户现象：手机与电脑都显示「页面脚本出错（app.js 未执行）」，
//   点「立即重试加载」「强制重新加载（清缓存）」、关标签页重开都无效，
//   今日简报 / 要闻 / 热榜永久停在「加载中…」。
// v1 教训（2026-11-25）：用新查询串重载 <script src> 无效——
//   SW 的 matchFlexible() 忽略查询串，命中同一个被污染的缓存条目；
//   且 onload 只代表响应到达，不代表脚本真的求值成功。
// v2 修复（2026-11-26）：复用页面已验证的 mdRepairData 机制——
//   fetch(cache:'reload') 拿源码 → 校验启动信标 → 内联 script 执行（不再发资源请求，
//   连 SW 缓存一起绕开）→ 校验双信标 → 成功同步横幅清红条。
//
// 本测试抽取 index.html 里的重试器 IIFE 到 jsdom 沙箱独立跑，mock fetch 精确控制每条链。
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
function flush() { return new Promise(r => setImmediate(r)); }

// ── 抽取重试器 IIFE ───────────────────────────────────────────────────────
const START = '  // ===== app.js 加载失败自动重试';
const END = '  })();';
const s = HTML.indexOf(START);
const e = s < 0 ? -1 : HTML.indexOf(END, s);
const block = (s >= 0 && e >= 0) ? HTML.slice(s, e + END.length) : '';

const APP_SRC = 'window.__mdBooted=true; window.__mdAppEvaluated=true;';

console.log('\n=== A. 静态结构守护 ===');
check('A1 index.html 含 v2 重试器 IIFE', block.indexOf('重试 v2') >= 0, 'block=' + block.length);
check('A2 用 fetch(cache:reload) 绕 HTTP 缓存', block.indexOf("{cache:'reload'}") >= 0);
check('A3 用唯一 query 标记（日志/穿透）', block.indexOf('__mdrepair') >= 0);
check('A4 校验源码含启动信标（拒绝残缺响应）', block.indexOf("t.indexOf('__mdBooted=true')<0") >= 0);
check('A5 内联 script 执行（不产生资源请求，绕开 SW）', block.indexOf('s.textContent=code') >= 0);
check('A6 校验双信标 __mdBooted + __mdAppEvaluated',
  block.indexOf('if(!window.__mdBooted)throw') >= 0 && block.indexOf('if(!window.__mdAppEvaluated)throw') >= 0);
check('A7 有重试次数上限（防无限循环）', /S\.tries>=S\.max/.test(block));
check('A8 多级看门狗覆盖挂起/假 onload', block.indexOf('[8000,20000,45000]') >= 0);
check('A9 成功后主动同步横幅清红条', /window\.mdSyncBanner\(\)/.test(block));
check('A10 保留原 app.js script 标签（测试隔离依赖）',
  /<script src="app\.js"[^>]*><\/script>/.test(HTML));
check('A11 onerror 仍走 mdScriptFail 钩子', /mdScriptFail&&window\.mdScriptFail\('app\.js'\)/.test(HTML));
check('A12 v1 的 __mdretry 方案已彻底移除', block.indexOf('__mdretry') < 0);

// ── jsdom 沙箱 ────────────────────────────────────────────────────────────
function makeSandbox(fetchImpl, recorder) {
  const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>',
    { runScripts: 'outside-only' });
  const w = dom.window;
  const timers = [];
  w.setTimeout = function (fn, ms) { timers.push({ fn: fn, ms: ms || 0 }); return timers.length; };
  w.clearTimeout = function () {};
  w.setInterval = function () { return 1; };
  w.clearInterval = function () {};
  const injected = [];
  const origCreate = w.document.createElement.bind(w.document);
  w.document.createElement = function (tag) {
    const el = origCreate(tag);
    if (String(tag).toLowerCase() === 'script') {
      injected.push(el);
      // jsdom outside-only 不执行内联脚本：拦截 textContent 赋值时手动 eval
      let code = '';
      Object.defineProperty(el, 'textContent', {
        get: function () { return code; },
        set: function (v) { code = String(v); try { w.eval(code); } catch (err) { w.__inlineErr = String(err); } },
        configurable: true
      });
    }
    return el;
  };
  const calls = recorder || { origFail: [], banner: 0, fetch: [] };
  w.mdScriptFail = function (name) { calls.origFail.push(name); };
  w.mdSyncBanner = function () { calls.banner++; };
  w.fetch = fetchImpl || function (url, opts) {
    calls.fetch.push({ url: url, opts: opts });
    return Promise.resolve({ ok: true, text: function () { return Promise.resolve(APP_SRC); } });
  };
  w.eval(block);
  return { w, injected, calls, timers };
}

(async function () {
  console.log('\n=== B. 重试链行为实测 ===');
  {
    const c = { origFail: [], banner: 0, fetch: [] };
    const sb = makeSandbox(null, c);
    const { w, injected } = sb;
    check('B1 重试器已注册', typeof w.mdAppRetry === 'function');
    check('B2 原 mdScriptFail 钩子被保留', typeof w.mdScriptFailOrig === 'function');

    w.mdScriptFail('sw.js');
    check('B3 其它脚本名仍走原提示钩子', c.origFail.join(',') === 'sw.js', 'origFail=' + c.origFail.join(','));
    check('B4 其它脚本名不触发 app.js 自愈', c.fetch.length === 0);

    w.mdScriptFail('app.js');
    await flush(); await flush();
    check('B5 app.js 失败触发 fetch 自愈', c.fetch.length === 1, 'fetch=' + c.fetch.length);
    check('B6 fetch URL 带 __mdrepair 标记', /app\.js\?__mdrepair=/.test(c.fetch[0].url), c.fetch[0].url);
    check('B7 fetch 使用 cache:reload', c.fetch[0].opts && c.fetch[0].opts.cache === 'reload');
    check('B8 源码内联执行（无 src 资源请求）', injected.length === 1 && !injected[0].src);
    check('B9 双信标置位后判定恢复成功', w.__mdBooted === true && w.__mdAppEvaluated === true);
    check('B10 成功后同步横幅清红条', c.banner >= 1, 'banner=' + c.banner);
    check('B11 成功后 busy 复位', w.__mdAppRetryState.busy === false);
    check('B12 已恢复后不再重复 fetch', (w.mdAppRetry(), c.fetch.length === 1));
  }

  console.log('\n=== C. 残缺响应 / 失败重试 / 上限 ===');
  {
    let n = 0;
    const c = { origFail: [], banner: 0, fetch: [] };
    const sb = makeSandbox(function (url, opts) {
      c.fetch.push({ url: url, opts: opts });
      n++;
      return Promise.resolve({ ok: true, text: function () {
        // 前两次返回残缺源码（无启动信标），第三次给完整源码
        return Promise.resolve(n < 3 ? 'var broken=1;' : APP_SRC);
      } });
    }, c);
    const { w, injected, timers } = sb;
    w.mdScriptFail('app.js');
    await flush(); await flush();
    check('C1 残缺源码不注入执行', injected.length === 0, 'injected=' + injected.length);
    check('C2 残缺源码不算恢复，横幅未被清', c.banner === 0);
    // 手动触发退避定时器
    const backoff = timers.filter(t => t.ms > 0 && t.ms < 8000);
    check('C3 失败后排了退避重试定时器', backoff.length === 1, 'timers=' + backoff.length);
    backoff[0].fn();
    await flush(); await flush();
    check('C4 第二次残缺仍未注入', injected.length === 0);
    const backoff2 = timers.filter(t => t.ms > 0 && t.ms < 8000 && !t.done);
    backoff2[0].fn();
    await flush(); await flush();
    check('C5 第三次完整源码成功内联执行', injected.length === 1 && w.__mdBooted === true);
    check('C6 恢复后清红条', c.banner >= 1);
  }
  {
    const c = { origFail: [], banner: 0, fetch: [] };
    const sb = makeSandbox(function (url, opts) {
      c.fetch.push({ url: url, opts: opts });
      return Promise.resolve({ ok: false, status: 503 });
    }, c);
    const { w } = sb;
    w.mdScriptFail('app.js');
    await flush(); await flush();
    const t1 = sb.timers.filter(t => t.ms > 0 && t.ms < 8000);
    check('C7 HTTP 失败后排退避', t1.length === 1);
    t1[0].fn(); await flush(); await flush();
    const t2 = sb.timers.filter(t => t.ms > 0 && t.ms < 8000).slice(1);
    t2[0].fn(); await flush(); await flush();
    check('C8 三次失败后达到上限', w.__mdAppRetryState.tries === 3, 'tries=' + w.__mdAppRetryState.tries);
    const before = c.fetch.length;
    w.mdAppRetry(); await flush();
    check('C9 达上限后不再发起新 fetch（防死循环）', c.fetch.length === before);
  }

  console.log('\n=== D. 看门狗不误伤 ===');
  {
    const sb = makeSandbox();
    const { w, timers } = sb;
    const wd = timers.filter(t => t.ms >= 8000);
    check('D1 注册了三级看门狗', wd.length === 3, 'count=' + wd.length);
    check('D2 看门狗延迟为 8s/20s/45s',
      wd[0].ms === 8000 && wd[1].ms === 20000 && wd[2].ms === 45000);
    wd[0].fn(); await flush(); await flush();
    check('D3 首级看门狗完成一次自愈', sb.calls.fetch.length === 1, 'fetch=' + sb.calls.fetch.length);
    wd[1].fn(); wd[2].fn(); await flush(); await flush();
    check('D4 双信标已置位，后两级看门狗跳过（不重复执行）', sb.calls.fetch.length === 1);
  }

  console.log('\n────────────────────────────────');
  console.log('PASS=' + pass + '  FAIL=' + fail);
  process.exit(fail ? 1 : 0);
})();
