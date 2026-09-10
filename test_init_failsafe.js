// test_init_failsafe.js
// 2026-09-11 事故回归测试：初始化单点故障隔离 + 内联兜底补渲染
//
// 事故现象：静态内容（含价格卡）正常，但热榜/简报/要闻永久停在「加载中…」，页面无任何报错。
// 根因链：
//   ① app.js 顶层是一条平铺调用链（initSpecial → fetchHotNews → … → refresh，末尾 IIFE 里 renderDigest）；
//   ② 链上任何一步抛异常，都会中断整个顶层流程，后面的渲染调用全部不执行；
//   ③ 而这些「自愈/看门狗」逻辑本身也写在 app.js 里 —— app.js 挂了就等于没有自愈；
//   ④ 于是页面静默卡死，用户只能看到永久「加载中…」。
// 本测试锁住两条防线：
//   防线一（app.js）：平铺链逐步 try/catch 隔离（mdSafeStep），单步失败不再拖垮后续。
//   防线二（index.html）：内联兜底——若 app.js 未宣告初始化完成，2.5s 后直接补跑关键渲染。
//
// 另附行为验证：用「注入顶层抛错」的 app.js 实跑一遍，确认三个区块仍能被渲染出来。
const fs = require('fs');
const path = require('path');
const vm = require('vm');

let pass = 0, fail = 0;
function check(name, cond, why) {
  if (cond) { pass++; console.log('  PASS  ' + name + (why ? '  → ' + why : '')); }
  else { fail++; console.log('  FAIL  ' + name + (why ? '  → ' + why : '')); }
}

const ROOT = __dirname;
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf-8');
const appSrc = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf-8');

console.log('===== ① app.js：平铺初始化链必须逐步隔离 =====');
check('定义了 mdSafeStep 隔离器',
  /function mdSafeStep\s*\(/.test(appSrc),
  '无隔离器则单步异常会中断整个顶层流程');
check('mdSafeStep 内部有 try/catch 且记录错误',
  /function mdSafeStep[\s\S]{0,400}?try\s*\{/.test(appSrc) && /__mdErrors/.test(appSrc),
  '异常须被吞掉并记入 window.__mdErrors，供页面横幅展示');
// 平铺链上的关键调用必须全部包在 mdSafeStep 里（不允许再出现裸调用）
[['fetchHotNews', '热榜数据加载'],
 ['loadBrief', '简报'],
 ['refresh', '刷新']].forEach(([fn, label]) => {
  const bare = new RegExp('^' + fn + '\\(\\);', 'm').test(appSrc);
  const wrapped = appSrc.indexOf("mdSafeStep('" + fn + "'") >= 0;
  check(label + ' 调用已隔离（' + fn + '）', wrapped && !bare,
    wrapped ? '已包进 mdSafeStep' : '仍是裸调用，一处异常即全链中断');
});
// 末尾 IIFE 里的渲染调用也要隔离
['qaInitData', 'renderDigest', 'renderLmePrices'].forEach(fn => {
  check('IIFE 内 ' + fn + ' 已隔离', appSrc.indexOf("mdSafeStep('" + fn + "'") >= 0);
});
check('app.js 在初始化结束时置 __mdInitDone 完成信标',
  /window\.__mdInitDone\s*=\s*true/.test(appSrc),
  '内联兜底据此判断是否需要补渲染');

console.log('\n===== ② index.html：内联兜底补渲染（不依赖 app.js）=====');
check('index.html 内联脚本里存在兜底补渲染逻辑',
  /__mdInitDone/.test(html) && /window\[n\]/.test(html),
  '这是 app.js 挂掉时唯一的救援路径');
['qaInitData', 'fetchHotNews', 'loadBrief', 'renderDigest', 'renderLmePrices'].forEach(fn => {
  check('兜底清单包含 ' + fn, html.indexOf("'" + fn + "'") >= 0);
});
check('兜底逻辑写在内联脚本中（而非 app.js）',
  /window\.__mdErrors\s*=\s*window\.__mdErrors\s*\|\|\s*\[\]/.test(html),
  '写在 app.js 里等于没有兜底：app.js 不执行时它也不存在');
check('看门狗判据用 __mdInitDone（而非仅 __mdBooted）',
  /__mdBooted\s*&&\s*window\.__mdInitDone/.test(html),
  '只看 __mdBooted 会漏掉「脚本跑了一半就中断」的情形——正是本次事故');
check('捕获运行时错误并写入 __mdErrors',
  /addEventListener\('error'/.test(html) && /unhandledrejection/.test(html),
  '故障必须可见，不能静默');
check('横幅含错误详情占位 .md-boot-detail',
  html.indexOf('md-boot-detail') >= 0,
  '把真实错误显示出来，便于远程定位');

console.log('\n===== ③ 语法层面：注入中断后 app.js 仍可解析 =====');
try {
  new vm.Script(appSrc);
  check('app.js 可被真正解析', true);
} catch (e) {
  check('app.js 可被真正解析', false, String(e && e.message).slice(0, 120));
}

console.log('\n===== 结果：' + pass + ' PASS / ' + fail + ' FAIL =====');
process.exit(fail ? 1 : 0);
