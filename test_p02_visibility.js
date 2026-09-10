// 回归测试：热榜可见性 / AI 入口（悬浮球）/ Key 存取 / 源码无内嵌 Key
// 2026-09-09 修订：原「AI 深度解析」区块已从页面移除（AI 入口只剩左下角 #qaFab 悬浮球），
// 旧的 aiBody/aiSection 场景已失效，改为校验「悬浮球入口存在」+「旧区块不得复活」。
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
// 2026-09-10 性能优化：应用逻辑已外置为 app.js(defer)，jsdom 不会自动拉取外部脚本，
// 故在此内联 app.js + 数据脚本（顺序 news->lme->price->app），等价于 defer 执行后状态。
['app.js', 'news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  html = html.replace(new RegExp('<script src="' + f + '"[^>]*></script>'),
    () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
});
const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://example.com/' });
const w = dom.window;
const d = w.document;

let pass = 0, fail = 0;
function ok(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name + (detail ? '  → ' + detail : '')); }
  else { fail++; console.log('  FAIL  ' + name + (detail ? '  → ' + detail : '')); }
}
function st(id) {
  const el = d.getElementById(id);
  if (!el) return 'MISSING';
  return el.style.display === 'none' ? 'HIDDEN' : 'VISIBLE';
}

setTimeout(() => {
  console.log('===== ① 函数挂载 =====');
  ok('mdRefreshSections 已定义', typeof w.mdRefreshSections === 'function');
  ok('mdSetDsKey 已定义', typeof w.mdSetDsKey === 'function');
  ok('getDsKey 已定义', typeof w.getDsKey === 'function');

  console.log('\n===== ② AI 入口 = 左下角悬浮球（原 AI 深度解析区块已移除）=====');
  const fab = d.getElementById('qaFab');
  ok('悬浮球 #qaFab 存在', !!fab);
  ok('悬浮球可见', fab && fab.style.display !== 'none', fab ? 'display=' + (fab.style.display || '(空)') : '');
  ok('悬浮球带「搜新闻 / 问 AI」文案', fab && /问\s*AI/.test(fab.textContent || ''), fab ? (fab.textContent || '').trim() : '');
  ok('已移除的 aiBody 不在静态 DOM（防死代码复活）', !d.getElementById('aiBody'));
  ok('已移除的 aiSection 不在静态 DOM', !d.getElementById('aiSection'));
  ok('页面 JS 对 aiBody 缺失有守卫（if(!body)return）', /getElementById\('aiBody'\)[\s\S]{0,200}?if\(!body\)return/.test(html));

  console.log('\n===== ③ 热榜：空→隐藏 / 有内容→显示 =====');
  const hot = d.getElementById('hotListSection');
  const hl = hot && (hot.querySelector('.hotlist-list') || hot);
  if (hl) {
    hl.innerHTML = '';
    w.mdRefreshSections();
    ok('无 hot-item 时热榜隐藏', st('hotListSection') === 'HIDDEN', st('hotListSection'));
    hl.innerHTML = '<li class="hot-item top1"><span class="hot-rank">1</span>测试</li>';
    w.mdRefreshSections();
    ok('有 hot-item 时热榜显示', st('hotListSection') === 'VISIBLE', st('hotListSection'));
  } else {
    ok('热榜容器存在', false, 'hotListSection 未找到');
  }

  console.log('\n===== ④ 今日区回归（不应被误伤）=====');
  ok('todaySection 可见', st('todaySection') === 'VISIBLE', st('todaySection'));

  console.log('\n===== ⑤ Key 存取（非法格式应拒绝）=====');
  ok('填 "abc" 被拒绝', w.mdSetDsKey('abc') === false, 'got=' + w.mdSetDsKey('abc'));
  ok('填合法 sk- 被接受', w.mdSetDsKey('sk-testkey1234567890abcd') === true);
  ok('getDsKey 能取回', (w.getDsKey() || '').slice(0, 3) === 'sk-', (w.getDsKey() || '').slice(0, 10) + '...');
  w.mdClearDsKey();
  ok('清除后为空', w.getDsKey() === '' || w.getDsKey() == null, JSON.stringify(w.getDsKey()));

  console.log('\n===== ⑥ 源码中不得残留内嵌 Key =====');
  ok('无 QA_DS_KEY_B64 硬编码', (html.match(/QA_DS_KEY_B64/g) || []).length === 0, 'count=' + (html.match(/QA_DS_KEY_B64/g) || []).length);
  ok('无 QA_DS_SALT 硬编码', (html.match(/QA_DS_SALT/g) || []).length === 0, 'count=' + (html.match(/QA_DS_SALT/g) || []).length);
  ok('无 sk- 明文密钥', !/['"]sk-[A-Za-z0-9]{16,}/.test(html));

  console.log('\n===== 汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 1500);
