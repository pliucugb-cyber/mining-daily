/**
 * PWA 安装卡片行为回归（jsdom，2026-09-12）
 *
 * 背景：用户反馈「手机端把日报装到桌面，Chrome 里两种方式都失败」。排查后确认网站侧合规
 * （真 Chrome 的 Page.getInstallabilityErrors 返回 0 条错误），但站内确有一个真 bug：
 *   安装卡片原先**只在页面初始化时渲染一次**，而 beforeinstallprompt 往往在此之后
 *   （且常在用户交互后）才触发 —— 事件到达时「立即安装」按钮该出现，卡片却早已画完，
 *   于是按钮永远不出现，用户只能照文字去翻浏览器菜单。
 *
 * 所以 ② 段这几条断言不是「代码在不在」，而是**行为真的发生了**：
 *   在旧实现上，② 段必然 FAIL（这正是它的价值）。
 *
 * 覆盖：
 *   ① 初始化后（未收到安装事件）→ 文字指引，无按钮
 *   ② 派发 beforeinstallprompt → 卡片自动出现「立即安装」按钮   ← 本轮修复的核心
 *   ③ 点「装不上？点这里」→ 展开排障正文 + 体检数据
 *   ④ 点「立即安装」→ 真的调用浏览器 prompt()，并记下「点过安装」
 *   ⑤ 预置失败记忆 → 卡片出现 ⚠️ 排障提示
 *   ⑥ 已安装（display-mode:standalone）→ 显示已安装、无安装入口
 *   ⑦ iOS → 显示 Safari 分享指引
 *   ⑧ 微信内置浏览器 → 提示「⋯ → 在浏览器打开」，且不给安装按钮（点了必然无效）
 *   ⑨ 面板内点「装不上？点这里」展开排障 → **不得把「我的」面板关掉弹回首页**
 *      （2026-09-12 用户实测 bug：卡片就地重渲染把 e.target 摘离 DOM，document 的
 *       「点面板外面就关闭」兜底把它误判成外部点击）
 *   ⑤ 内还断言：失败文案不再错误归因「安装未知应用」权限（2026-09-12 实测更正）
 *
 * 运行：node test_pwa_install_behavior.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const HTML_RAW = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
const APP_JS = fs.readFileSync(path.join(__dirname, 'app.js'), 'utf-8');

const IPHONE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 ' +
  '(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1';
const ANDROID_UA = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36';

let pass = 0, fail = 0;
function check(name, cond, why) {
  if (cond) { pass++; console.log('  PASS  ' + name + (why ? '  → ' + why : '')); }
  else { fail++; console.log('  FAIL  ' + name + (why ? '  → ' + why : '')); }
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

/** 造一个可注入状态的页面；prefs 直接写进 localStorage（解析前） */
function boot(opts) {
  opts = opts || {};
  let html = HTML_RAW;
  ['news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
    const p = path.join(__dirname, f);
    if (!fs.existsSync(p)) return;
    html = html.replace(new RegExp('<script src="' + f + '"[^>]*></script>'),
      () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
  });
  html = html.replace(new RegExp('<script src="app.js"[^>]*></script>'), '');
  html = html.replace('</body>', '<script>' + APP_JS + '</script>\n</body>');

  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    url: 'https://pliucugb-cyber.github.io/mining-daily/',
    beforeParse(win) {
      Object.defineProperty(win, 'innerWidth', { value: 375, configurable: true, writable: true });
      win.matchMedia = q => ({
        matches: !!(opts.standalone && /standalone/.test(String(q))),
        media: String(q), addEventListener() {}, removeEventListener() {},
        addListener() {}, removeListener() {}
      });
      try {
        Object.defineProperty(win.navigator, 'userAgent',
          { value: opts.ua || ANDROID_UA, configurable: true });
      } catch (e) {}
      if (opts.prefs) {
        for (const k of Object.keys(opts.prefs)) {
          try { win.localStorage.setItem(k, opts.prefs[k]); } catch (e) {}
        }
      }
      win.fetch = () => Promise.reject(new Error('jsdom: fetch stub'));
      if (typeof win.navigator.serviceWorker === 'undefined') { /* jsdom 无 SW，app.js 已 guard */ }
    }
  });
  return { dom, win: dom.window, doc: dom.window.document };
}

const cardEl = doc => doc.getElementById('mineInstallCard');
const cardText = doc => { const c = cardEl(doc); return c ? (c.textContent || '') : ''; };

(async () => {
  const doms = [];

  // ==================== ① 初始化态 ====================
  console.log('===== ① 初始化：未收到安装事件时 =====');
  const p1 = boot({}); doms.push(p1.dom);
  await sleep(300);
  check('#mineInstallCard 已注入', !!cardEl(p1.doc));
  check('卡片是文字指引（引导去浏览器菜单）', /浏览器菜单|主屏幕/.test(cardText(p1.doc)),
    '实际片段：' + cardText(p1.doc).slice(0, 26));
  check('此时没有「立即安装」按钮（浏览器尚未就绪）',
    !p1.doc.querySelector('#mineInstallCard [data-pwa="install"]'));

  // ==================== ② 事件到达 → 按钮出现（核心修复） ====================
  console.log('\n===== ② beforeinstallprompt 到达 → 卡片自动刷新出「立即安装」 =====');
  const ev = new p1.win.Event('beforeinstallprompt');
  ev.prompt = function () { ev.__prompted = true; };
  ev.userChoice = Promise.resolve({ outcome: 'accepted' });
  p1.win.dispatchEvent(ev);
  const btn = p1.doc.querySelector('#mineInstallCard [data-pwa="install"]');
  check('旧实现必失败的那条：卡片出现「立即安装」按钮', !!btn,
    btn ? '按钮文案=' + btn.textContent : '仍无按钮 → 说明事件到达后没有重渲染卡片');
  check('按钮文案为「安装为独立应用」', !!btn && btn.textContent === '安装为独立应用');
  check('卡片给出「添加到主屏幕」这条不依赖 Google 服务的通用路径',
    cardText(p1.doc).indexOf('添加到主屏幕') >= 0);

  // ==================== ③ 排障展开 ====================
  console.log('\n===== ③「装不上？点这里」展开排障 + 体检 =====');
  const help = p1.doc.querySelector('#mineInstallCard [data-pwa="help"]');
  check('有排障入口按钮', !!help, help ? '文案=' + help.textContent : '');
  if (help) help.click();
  const t3 = cardText(p1.doc);
  check('展开后点名「Google 服务」这一真实卡点', t3.indexOf('Google 服务') >= 0,
    '安卓 Chrome 装 PWA 需连 Google 服务生成应用包，国内手机够不到 —— 这是根因');
  check('展开后给出「添加到主屏幕」这条通用退路', t3.indexOf('添加到主屏幕') >= 0);
  // 2026-09-12 用户指示：这段文字**只讲手机**——电脑版在浏览器里点一下就能装，
  //   不该占用手机引导的篇幅（用户原话：「不要提电脑版如何安装」）。
  check('只讲手机安装、不提电脑端（用户明确要求）',
    t3.indexOf('电脑') < 0 && t3.indexOf('PC') < 0);
  check('给出 iPhone / Safari 这条手机端路径', t3.indexOf('Safari') >= 0);
  // 用户 2026-09-12：「并不是每个人手机上都会安装 Chrome 浏览器」→ 必须给全浏览器对照。
  const BROWSERS = ['Chrome', '小米浏览器', '华为浏览器', 'UC 浏览器', 'QQ 浏览器',
    '三星浏览器', 'Edge', 'Firefox'];
  const hitB = BROWSERS.filter(n => t3.indexOf(n) >= 0);
  check('按浏览器逐个给出入口（覆盖 >=6 种，不只讲 Chrome）', hitB.length >= 6,
    '命中 ' + hitB.length + '/' + BROWSERS.length + '：' + hitB.join('/'));
  check('标出「你现在用的浏览器」是哪一条', t3.indexOf('你现在用的浏览器') >= 0,
    '给出 8 条对照却不标当前那条，用户不知道该看哪条');
  check('给出微信里打开时的走法（⋯ → 在浏览器打开）', t3.indexOf('在浏览器打开') >= 0);
  check('手机引导按 ①②③④ 分步排版（不是一整段糊在一起）',
    ['①', '②', '③', '④'].every(m => t3.indexOf(m) >= 0));
  // 用户 2026-09-12 实测：MIUI/HyperOS 上 Chrome 的「添加到主屏幕」需要系统「桌面快捷方式」权限
  check('展开后给出小米「桌面快捷方式」权限这条实测可行路径',
    t3.indexOf('桌面快捷方式') >= 0 && t3.indexOf('权限管理') >= 0,
    '这条是用户实测走通的路，必须留在文案里');
  check('体检数据含当前运行模式', t3.indexOf('模式：') >= 0);
  check('体检数据反映「安装提示已就绪」', t3.indexOf('安装提示：已就绪') >= 0,
    '实际：' + (t3.match(/安装提示：[^ ]*/) || ['(无)'])[0]);
  check('体检数据含浏览器识别', /环境：.*Chrome/.test(t3));

  // ==================== ④ 点击安装 ====================
  console.log('\n===== ④ 点「立即安装」→ 调用浏览器 prompt() =====');
  const btn2 = p1.doc.querySelector('#mineInstallCard [data-pwa="install"]');
  if (btn2) btn2.click();
  await sleep(50);
  check('真的调用了浏览器安装提示（prompt）', ev.__prompted === true);
  check('记下「点过安装」（用于失败时给排障）',
    p1.win.localStorage.getItem('md_pwa_install_tried') === '1',
    '实际 %r'.replace('%r', String(p1.win.localStorage.getItem('md_pwa_install_tried'))));
  check('消费后清空 deferredPrompt（同一 prompt 不能重复用）', !p1.win.__deferredPrompt);

  // ==================== ⑤ 失败记忆 ====================
  console.log('\n===== ⑤ 上次点过但没装上 → 卡片给排障警示 =====');
  const p2 = boot({ prefs: { md_pwa_install_tried: '1', md_pwa_install_stalled: '1' } });
  doms.push(p2.dom);
  await sleep(300);
  const t5 = cardText(p2.doc);
  check('卡片出现 ⚠️ 失败排障提示', t5.indexOf('⚠️') >= 0 && t5.indexOf('没出现图标') >= 0,
    '实际片段：' + t5.slice(0, 40));
  // 断言盯的是**意图**（指向不依赖 Google 服务的通用退路），不是某一句具体措辞：
  //   各浏览器菜单里那项一会儿叫「添加到主屏幕」、一会儿叫「添加到桌面」，两种写法都算通过。
  check('提示里点名真实原因并指向通用退路',
    t5.indexOf('Google 服务') >= 0 &&
    (t5.indexOf('添加到主屏幕') >= 0 || t5.indexOf('添加到桌面') >= 0),
    '实际片段：' + t5.slice(0, 60));
  check('失败提示不再归因「安装未知应用」权限', t5.indexOf('安装未知应用') < 0);

  // ==================== ⑥ 已安装 ====================
  console.log('\n===== ⑥ 已在独立窗口运行（已安装）=====');
  const p3 = boot({ standalone: true }); doms.push(p3.dom);
  await sleep(300);
  const t6 = cardText(p3.doc);
  check('显示「已安装到主屏幕」', t6.indexOf('已安装到主屏幕') >= 0, '实际片段：' + t6.slice(0, 24));
  check('已安装时不再显示任何安装/排障入口（不打扰）',
    !p3.doc.querySelector('#mineInstallCard [data-pwa="install"]') &&
    !p3.doc.querySelector('#mineInstallCard [data-pwa="help"]'));

  // ==================== ⑦ iOS ====================
  console.log('\n===== ⑦ iOS（Safari）=====');
  const p4 = boot({ ua: IPHONE_UA }); doms.push(p4.dom);
  await sleep(300);
  const t7 = cardText(p4.doc);
  check('显示 Safari 分享添加指引', t7.indexOf('Safari') >= 0 && t7.indexOf('添加到主屏幕') >= 0,
    '实际片段：' + t7.slice(0, 40));
  check('iOS 不显示安卓式的「立即安装」按钮（beforeinstallprompt 在 iOS 不存在）',
    !p4.doc.querySelector('#mineInstallCard [data-pwa="install"]'));

  // ==================== ⑧ 微信内置浏览器 ====================
  console.log('\n===== ⑧ 微信内置浏览器（国内用户最常见的入口）=====');
  const WECHAT_UA = 'Mozilla/5.0 (Linux; Android 13; 2211133C Build/TKQ1.220829.002; wv) ' +
    'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/107.0.0.0 Mobile Safari/537.36 ' +
    'MicroMessenger/8.0.40.2420(0x28002837) WeChat/arm64 Weixin NetType/WIFI';
  const p5 = boot({ ua: WECHAT_UA }); doms.push(p5.dom);
  await sleep(300);
  // 即使浏览器就绪（事件到达），微信里也不该给「安装」按钮
  const ev5 = new p5.win.Event('beforeinstallprompt');
  ev5.prompt = function () { ev5.__prompted = true; };
  ev5.userChoice = Promise.resolve({ outcome: 'accepted' });
  p5.win.dispatchEvent(ev5);
  const t8 = cardText(p5.doc);
  check('识别为微信并提示「⋯ → 在浏览器打开」',
    t8.indexOf('微信') >= 0 && t8.indexOf('在浏览器打开') >= 0,
    '实际片段：' + t8.slice(0, 60));
  check('微信内不给「安装为独立应用」按钮（微信 WebView 点了必然无效）',
    !p5.doc.querySelector('#mineInstallCard [data-pwa="install"]'));

  // ==================== ⑨ 面板内展开排障不得关闭「我的」 ====================
  // 用户 2026-09-12 实测：在「我的」里点「装不上？点这里」，页面会弹回首页，
  //   要再进一次「我的」才能看到展开的内容 —— 明显不合理。
  // 根因：安装卡片展开/收起是**就地重渲染**（el.innerHTML 整体替换），
  //   把 e.target 从 DOM 里摘了下来；事件冒泡到 document 时 e.target.closest('#mineSheet')
  //   返回 null，被「点面板外面就关闭」的兜底逻辑误判成外部点击。
  //   → 所以这段断言盯的不是「代码在不在」，而是**面板到底还在不在**。
  console.log('\n===== ⑨ 面板内展开排障：不得把「我的」关掉弹回首页 =====');
  const p6 = boot({}); doms.push(p6.dom);
  await sleep(300);
  const mineTab = p6.doc.querySelector('#mobileTabBar .mtab[data-go="mine"]');
  check('底部导航里有「我的」tab', !!mineTab);
  if (mineTab) mineTab.click();
  const sheet6 = p6.doc.getElementById('mineSheet');
  check('点「我的」后面板打开',
    !!sheet6 && !sheet6.hidden && p6.doc.body.classList.contains('md-mine-open'));
  const help6 = p6.doc.querySelector('#mineInstallCard [data-pwa="help"]');
  if (help6) help6.click();
  check('一次点击就展开排障正文（不必退出再进一次）',
    cardText(p6.doc).indexOf('Google 服务') >= 0);
  check('展开排障后：面板仍然开着（旧实现必失败）',
    !!sheet6 && !sheet6.hidden && p6.doc.body.classList.contains('md-mine-open'),
    '旧实现：重渲染把 e.target 摘离 DOM → document 的「点外部关闭」误判 → 面板关闭并弹回首页');
  const help6b = p6.doc.querySelector('#mineInstallCard [data-pwa="help"]');
  check('展开按钮就地变成「收起」',
    !!help6b && help6b.textContent.indexOf('收起') >= 0,
    help6b ? '实际=' + help6b.textContent : '按钮丢失');
  if (help6b) help6b.click();
  check('再点一次收起后：面板依然开着',
    !!sheet6 && !sheet6.hidden && p6.doc.body.classList.contains('md-mine-open'));

  console.log('\n===== 结果：' + pass + ' PASS / ' + fail + ' FAIL =====');
  for (const d of doms) { try { d.window.close(); } catch (e) {} }
  process.exit(fail ? 1 : 0);
})();
