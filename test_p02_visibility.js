// P0-2 回归测试：热榜 / AI 深度解析区块的可见性
// 验证修复后：有内容→显示；纯占位（加载中/空）→隐藏；「未配置 Key」→显示（那是填 Key 入口）
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://example.com/' });
const w = dom.window;
const d = w.document;

function st(id) {
  const el = d.getElementById(id);
  if (!el) return 'MISSING';
  return el.style.display === 'none' ? 'HIDDEN' : 'VISIBLE';
}

setTimeout(() => {
  console.log('=== 函数是否挂到 window ===');
  console.log('  mdRefreshSections:', typeof w.mdRefreshSections);
  console.log('  mdSetDsKey       :', typeof w.mdSetDsKey);
  console.log('  getDsKey         :', typeof w.getDsKey);

  console.log('\n=== 场景1：AI 区块为「未配置 Key」占位（应有填写入口 → 必须 VISIBLE）===');
  const aiBody = d.getElementById('aiBody');
  aiBody.innerHTML = '<div class="ai-disabled">🤖 AI 解析未配置</div>';
  w.mdRefreshSections();
  console.log('  aiSection:', st('aiSection'), '(期望 VISIBLE)');

  console.log('\n=== 场景2：AI 区块为「加载中」占位（应 HIDDEN）===');
  aiBody.innerHTML = '<div class="ai-loading">加载中…</div>';
  w.mdRefreshSections();
  console.log('  aiSection:', st('aiSection'), '(期望 HIDDEN)');

  console.log('\n=== 场景3：AI 区块有真实内容（应 VISIBLE）===');
  aiBody.innerHTML = '<div class="ai-card">要点：xxxx</div>';
  w.mdRefreshSections();
  console.log('  aiSection:', st('aiSection'), '(期望 VISIBLE)');

  console.log('\n=== 场景4：热榜无条目（应 HIDDEN）/ 有条目（应 VISIBLE）===');
  const hot = d.getElementById('hotListSection');
  const hl = hot.querySelector('.hotlist-list') || hot;
  hl.innerHTML = '';
  w.mdRefreshSections();
  console.log('  无 hot-item :', st('hotListSection'), '(期望 HIDDEN)');
  hl.innerHTML = '<li class="hot-item top1"><span class="hot-rank">1</span>测试</li>';
  w.mdRefreshSections();
  console.log('  有 hot-item :', st('hotListSection'), '(期望 VISIBLE)');

  console.log('\n=== 场景5：普通新闻区回归（不应被误伤）===');
  const today = d.getElementById('todaySection');
  console.log('  todaySection:', st('todaySection'), '(有今日新闻→期望 VISIBLE)');

  console.log('\n=== 场景6：Key 存取（填错格式应拒绝）===');
  console.log('  填 "abc"   ->', w.mdSetDsKey('abc'), '(期望 false)');
  console.log('  填 sk- 合法 ->', w.mdSetDsKey('sk-testkey1234567890abcd'), '(期望 true)');
  console.log('  getDsKey() ->', (w.getDsKey() || '').slice(0, 10) + '...', '(期望 sk-testkey...)');
  w.mdClearDsKey();
  console.log('  清除后     ->', JSON.stringify(w.getDsKey()), '(期望 "")');

  console.log('\n=== 场景7：源码中不得残留内嵌 Key ===');
  console.log('  QA_DS_KEY_B64 出现次数:', (html.match(/QA_DS_KEY_B64/g) || []).length, '(期望 0)');
  console.log('  QA_DS_SALT    出现次数:', (html.match(/QA_DS_SALT/g) || []).length, '(期望 0)');
  console.log('  源码含 sk- 明文:', /['"]sk-[A-Za-z0-9]{16,}/.test(html), '(期望 false)');

  process.exit(0);
}, 1500);
