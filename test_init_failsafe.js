// test_init_failsafe.js
// 2026-09-11 事故回归测试：初始化单点故障隔离 + 页面侧「按实际状态」自愈
//
// 事故现象：静态内容（含价格卡）正常，但热榜/简报/要闻永久停在「加载中…」，页面无任何报错。
// 根因链：
//   ① app.js 顶层是一条平铺调用链（initSpecial → fetchHotNews → … → refresh，末尾 IIFE 里 renderDigest）；
//   ② 链上任何一步抛异常，都会中断整个顶层流程，后面的渲染调用全部不执行；
//   ③ 而这些「自愈/看门狗」逻辑本身也写在 app.js 里 —— app.js 挂了就等于没有自愈；
//   ④ 于是页面静默卡死，用户只能看到永久「加载中…」。
// 三轮加固后本测试锁住三层防线：
//   防线一（app.js）：平铺链逐步 try/catch 隔离（mdSafeStep），单步失败不再拖垮后续。
//   防线二（app.js）：不再把「初始化顺序」伪装成「功能坏了」——QA_ROWS 占位 + 热榜数据源退化。
//   防线三（index.html）：内联自愈——**按页面实际状态**判断（区块是否仍停在占位），
//                        数据缺失就带 cache:reload 重取并内联注入，再补跑对应渲染。
//                        判据刻意不用标志位：新 HTML + 旧 app.js 混装时标志位会说谎。
// 另附行为验证：见 test_data_selfheal.js（故意让 news-data.js 首次 404，验证页面真能自愈）。
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
// 2026-09-11 第三轮加固：不再让「初始化顺序问题」伪装成「某个功能坏了」
check('热榜本地计算不再硬依赖 QA_ROWS',
  /var rows=\(window\.QA_ROWS&&window\.QA_ROWS\.length\)\?window\.QA_ROWS:\(\(window\.NEWS_DATA&&window\.NEWS_DATA\.news\)\|\|\[\]\)/.test(appSrc),
  'QA_ROWS 由中段 qaInitData() 填充；顶层中途抛错时它会停留在 undefined，'
  + '旧写法 QA_ROWS.length 直接 TypeError → 热榜显示「加载失败」，把根因伪造成「热榜坏了」');
check('QA_ROWS 在最顶部先占位成数组',
  /window\.QA_ROWS\s*=\s*window\.QA_ROWS\s*\|\|\s*\[\]/.test(appSrc),
  '避免中途中断时 QA_ROWS 为 undefined');
check('提供幂等的 qaReinit（自愈重跑不会让下拉选项翻倍）',
  /function qaReinit\s*\(/.test(appSrc) && /__mdQaSelSnap/.test(appSrc)
  && /window\.qaReinit\s*=\s*qaReinit/.test(appSrc),
  'qaInitData 会往 select 里 append 选项，重复调用会出现「铜 (12)」成倍重复');

console.log('\n===== ② index.html：按「页面实际状态」自愈（不依赖 app.js 是否跑完）=====');
check('内联脚本里存在自愈调度（mdPass）',
  /function mdPass\s*\(/.test(html) && html.indexOf('[1200,3000,7000,14000]') >= 0,
  '这是 app.js 挂掉/跑一半/是旧版时唯一的救援路径');
check('兜底渲染清单覆盖关键区块',
  ['qaInitData', 'fetchHotNews', 'loadBrief', 'renderDigest'].every(fn => html.indexOf("'" + fn + "'") >= 0),
  '热榜 / 简报 / 要闻 / 问答数据四类动态内容');
check('数据自愈清单覆盖三个数据脚本',
  ['news-data.js', 'lme-data.js', 'price-history.js'].every(f => html.indexOf("'" + f + "'") >= 0),
  '三者分别提供 NEWS_DATA / LME_DATA / PRICE_HISTORY，缺任一都会让动态区块整片空白');
check('数据自愈用 fetch(cache:reload) 取文本后内联注入',
  /fetch\(a\.f\+'\?_r='/.test(html) && /s\.textContent=js/.test(html),
  '绕开脚本加载与 SW 缓存路径：即便 SW 回的是坏副本也能救回来');
check('判定依据是「区块是否仍停在占位」而非标志位',
  /加载中\|提取中\|获取中/.test(html) && /function mdPending\s*\(/.test(html) && /function mdOk\s*\(/.test(html),
  '信任标志位会漏掉「脚本跑了一半就中断」「HTML 新但 app.js 是旧版」等情形');
check('看门狗判据用 mdPending()（按实际渲染结果）',
  /if\(!pend\.length&&!\(window\.__mdErrors\|\|\[\]\)\.length\)return/.test(html),
  '只看 __mdBooted 会漏掉「脚本跑了一半就中断」——正是本次事故');
check('资源加载失败时记录确切 URL',
  /t\.src\|\|t\.href/.test(html) && /mdIgnoreUrl/.test(html),
  '此前只记到一个没有 message 的 Event（显示为 [object Event]），等于没有线索');
check('忽略第三方统计脚本的加载失败',
  /goatcounter\|gc\\\.zgo\\\.at/.test(html),
  '统计脚本取不到属正常，不能拿它报警，否则横幅天天误报');
check('捕获运行时错误并写入 __mdErrors',
  /addEventListener\('error'/.test(html) && /unhandledrejection/.test(html),
  '故障必须可见，不能静默');
check('横幅含错误详情占位 .md-boot-detail',
  html.indexOf('md-boot-detail') >= 0,
  '把真实错误显示出来，便于远程定位');
check('横幅含诊断状态行与复制入口',
  html.indexOf('md-boot-diag') >= 0 && /window\.mdCopyDiag/.test(html) && /function mdDiagLine/.test(html),
  '一次截图/粘贴即可定位，不用再靠猜');

console.log('\n===== ③ 语法层面：注入中断后 app.js 仍可解析 =====');
try {
  new vm.Script(appSrc);
  check('app.js 可被真正解析', true);
} catch (e) {
  check('app.js 可被真正解析', false, String(e && e.message).slice(0, 120));
}

console.log('\n===== 结果：' + pass + ' PASS / ' + fail + ' FAIL =====');
process.exit(fail ? 1 : 0);
