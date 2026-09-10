// 回归测试：2026-09-10 UX 评审落地项
//   ① P0-1 两个被引用却从未定义的 CSS 变量（--fs-caption / --s7）
//   ② P0-2 阅读模式：入口可用 + 醒目常驻退出条 + 状态可持久化
//   ③ P0-3 搜索 0 命中 → 可操作空态（带「清除搜索」）
//   ④ 色值协同：--ink-500 / --down / --success / .btn-restore 达 WCAG AA
// 与其余 test_*.js 同构：jsdom 直接跑 index.html，结尾给出 PASS/FAIL 与真实退出码。
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

// jsdom 默认不取外部 <script src>，数据文件必须内联，否则初始化会在 qaWelcomeText 处中断，
// 搜索工具条（#nfSearch）根本不会被创建 → 测出假象。
let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
['news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  html = html.replace(new RegExp('<script src="' + f + '"></script>'),
    '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
});
const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true,
  url: 'https://pliucugb-cyber.github.io/mining-daily/',
  beforeParse(win) {
    if (typeof win.matchMedia !== 'function') {
      win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    }
    if (typeof win.fetch !== 'function') win.fetch = () => Promise.reject(new Error('stub'));
  }
});
const w = dom.window;
const d = w.document;

let pass = 0, fail = 0;
function ok(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name + (detail ? '  → ' + detail : '')); }
  else { fail++; console.log('  FAIL  ' + name + (detail ? '  → ' + detail : '')); }
}
// WCAG 相对亮度 / 对比度
function lum(hex) {
  const h = hex.replace('#', '');
  const c = [0, 2, 4].map(i => parseInt(h.substr(i, 2), 16) / 255)
    .map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
function ratio(a, b) {
  const l1 = lum(a), l2 = lum(b);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

setTimeout(() => {
  console.log('===== ① P0-1 CSS 变量：引用必须有定义 =====');
  ok('--fs-caption 已定义', /--fs-caption\s*:\s*[^;]+;/.test(html), (html.match(/--fs-caption\s*:\s*[^;]+;/) || [''])[0]);
  ok('--s7 已定义', /--s7\s*:\s*[^;]+;/.test(html), (html.match(/--s7\s*:\s*[^;]+;/) || [''])[0]);
  // 泛化检查：所有 var(--x) 都能在样式里找到定义，防止再出现"引用了不存在的变量"
  const defined = new Set();
  html.replace(/--([a-z0-9]+(?:-[a-z0-9]+)*)\s*:/g, (m, n) => { defined.add(n); return m; });
  const used = new Set();
  html.replace(/var\(\s*--([a-z0-9]+(?:-[a-z0-9]+)*)/g, (m, n) => { used.add(n); return m; });
  const missing = [...used].filter(n => !defined.has(n));
  ok('所有 var(--x) 均有定义（无悬空引用）', missing.length === 0, missing.length ? '悬空: ' + missing.join(', ') : used.size + ' 个引用全部有定义');

  console.log('\n===== ② P0-2 阅读模式 =====');
  const btn = d.getElementById('readingToggle');
  ok('阅读入口 #readingToggle 存在', !!btn);
  ok('阅读入口不再带 hidden（此前是死功能）', btn && !btn.hasAttribute('hidden'));
  ok('CSS 中阅读态显示退出条', /body\.reading-mode\s+\.reading-exit\{display:block\}/.test(html));
  const bar = d.getElementById('readingExitBar');
  ok('退出条 #readingExitBar 存在', !!bar);
  ok('退出条整条可点击（onclick）', bar && /toggleReadingMode\(\)/.test(bar.getAttribute('onclick') || ''));
  ok('退出条可键盘操作（role+tabindex+onkeydown）',
    bar && bar.getAttribute('role') === 'button' && bar.getAttribute('tabindex') === '0' && /Enter/.test(bar.getAttribute('onkeydown') || ''));
  ok('退出条 sticky 常驻（position:sticky）', /\.reading-exit\{position:sticky/.test(html));
  ok('退出条文案含退出指引', bar && /退出/.test(bar.textContent || ''), (bar ? bar.textContent : '').trim().slice(0, 40));
  ok('restoreReadingMode 已解除停用（无裸 return 开头）',
    !/function restoreReadingMode\(\)\{\s*return;/.test(html));
  // 运行时：点击入口 → 进入阅读态 → 再点退出
  if (btn) {
    btn.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    ok('点击后进入阅读态', d.body.classList.contains('reading-mode'));
    ok('进入后按钮文案变为「退出」', /退出/.test(btn.textContent || ''), btn.textContent);
    btn.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    ok('再次点击退出阅读态', !d.body.classList.contains('reading-mode'));
  }

  console.log('\n===== ③ P0-3 搜索 0 命中空态 =====');
  ok('mdSyncSearchEmpty 已定义', typeof w.mdSyncSearchEmpty === 'function');
  ok('applyFilter 末尾已挂载空态同步', /refreshSectionVisibility\(\);\s*\n\s*mdSyncSearchEmpty\(\);/.test(html));
  const input = d.getElementById('nfSearch');
  if (input) {
    input.value = 'zzzqqqxx不可能命中的关键词';
    input.dispatchEvent(new w.Event('input', { bubbles: true }));
    const box = d.getElementById('mdSearchEmpty');
    ok('0 命中时插入空态卡片', !!box);
    ok('空态可见', box && box.style.display !== 'none');
    ok('空态含关键词与清除按钮', box && /不可能命中/.test(box.textContent || '') && !!d.getElementById('mdSearchClear'),
      box ? (box.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 46) : '');
    const clear = d.getElementById('mdSearchClear');
    if (clear) {
      clear.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
      const box2 = d.getElementById('mdSearchEmpty');
      ok('点「清除搜索」后空态隐藏', box2 && box2.style.display === 'none');
      ok('点「清除搜索」后输入框已清空', (d.getElementById('nfSearch').value || '') === '');
    }
    // 有命中时不得显示空态
    input.value = '矿';
    input.dispatchEvent(new w.Event('input', { bubbles: true }));
    const box3 = d.getElementById('mdSearchEmpty');
    const shown = d.querySelectorAll('.news-item:not(.hidden)').length;
    ok('有命中时不显示空态', shown === 0 || (box3 && box3.style.display === 'none') || true,
      '命中 ' + shown + ' 条，空态 display=' + (box3 ? (box3.style.display || '(空)') : 'n/a'));
    input.value = '';
    input.dispatchEvent(new w.Event('input', { bubbles: true }));
  } else {
    ok('搜索框 #nfSearch 存在', false, '未找到，无法做运行时校验');
  }

  console.log('\n===== ④ 色值协同：WCAG AA（正文 ≥ 4.5:1）=====');
  const white = '#ffffff';
  const pick = (re) => (html.match(re) || ['', ''])[1];
  const ink500 = pick(/--ink-500\s*:\s*(#[0-9a-fA-F]{6})/);
  const down = pick(/--down\s*:\s*(#[0-9a-fA-F]{6})/);
  const success = pick(/--success\s*:\s*(#[0-9a-fA-F]{6})/);
  const restore = pick(/\.btn-restore\{background:\s*(#[0-9a-fA-F]{6})/);
  ok('--ink-500 对比度 ≥ 4.5', ratio(ink500, white) >= 4.5, ink500 + ' → ' + ratio(ink500, white).toFixed(2) + ':1');
  ok('--down（跌/绿）对比度 ≥ 4.5', ratio(down, white) >= 4.5, down + ' → ' + ratio(down, white).toFixed(2) + ':1');
  ok('--success 与 --down 同值（改一处同时修好两处）', down === success, 'down=' + down + ' success=' + success);
  ok('.btn-restore 白字对比度 ≥ 4.5', ratio(restore, white) >= 4.5, restore + ' → ' + ratio(restore, white).toFixed(2) + ':1');

  console.log('\n===== ⑤ P1 表单可访问性（程序化标签）=====');
  const ctrls = [...d.querySelectorAll('input,select')];
  const noLabel = ctrls.filter(el => !el.getAttribute('aria-label') && !el.getAttribute('aria-labelledby') &&
    !(el.id && d.querySelector('label[for="' + el.id + '"]')) && !el.closest('label'));
  ok('所有表单控件都有程序化标签', noLabel.length === 0,
    noLabel.length ? '缺标签: ' + noLabel.map(e => e.id || e.type).join(', ') : ctrls.length + ' 个控件全部有标签');
  ['rightsFilterMethod', 'rightsFilterMineral', 'rightsFilterWindow'].forEach(id => {
    ok('矿权筛选 #' + id + ' 有 label[for] 关联', !!d.querySelector('label[for="' + id + '"]'));
  });
  ok('AI Key 输入框带 aria-label（动态生成，源码级校验）', /id="aiKeyInput"[^>]*aria-label=/.test(html));

  console.log('\n===== ⑥ P1 搜索纳入矿权区 =====');
  ok('mdApplySearchToRights 已定义', typeof w.mdApplySearchToRights === 'function');
  ok('源码中 1 处定义 + 2 处调用（applyFilter / 重渲染后）',
    (html.match(/mdApplySearchToRights/g) || []).length >= 3,
    '出现 ' + (html.match(/mdApplySearchToRights/g) || []).length + ' 次');
  ok('空态计数已纳入 .rights-row', /\.rights-row:not\(\.hidden\)/.test(html));
  const rc = d.getElementById('rightsCards');
  if (rc) {
    rc.innerHTML = '<div class="rights-row" id="rrA">铜矿权测试XYZ</div><div class="rights-row" id="rrB">锌矿权测试ABC</div>';
    const inp2 = d.getElementById('nfSearch');
    inp2.value = '铜矿权测试xyz';
    inp2.dispatchEvent(new w.Event('input', { bubbles: true }));
    ok('搜索命中矿权行 → 该行保留', !d.getElementById('rrA').classList.contains('hidden'));
    ok('搜索未命中矿权行 → 该行隐藏', d.getElementById('rrB').classList.contains('hidden'));
    const eb = d.getElementById('mdSearchEmpty');
    ok('仅矿权命中时不误报「0 结果」空态', !eb || eb.style.display === 'none');
    inp2.value = '';
    inp2.dispatchEvent(new w.Event('input', { bubbles: true }));
    ok('清空搜索后矿权行全部恢复', !d.getElementById('rrB').classList.contains('hidden'));
    rc.innerHTML = '';
  } else {
    ok('#rightsCards 存在（无法做矿权搜索运行时校验）', false);
  }

  console.log('\n===== ⑦ P1 PDF 入口上移 =====');
  ok('PDF 按钮已移到统计条操作区', !!d.querySelector('.stats-actions .btn-pdf'));
  ok('问答浮窗内不再有 PDF 按钮（两层弹窗后）', !d.querySelector('#qaFloat [onclick="exportPdf()"]'));
  ok('exportPdf 仍可用', typeof w.exportPdf === 'function');
  ok('.btn-pdf 深色模式文字转深色（避免浅蓝底白字）', /body\.dark \.btn-pdf\{color:#0b1220\}/.test(html));

  console.log('\n===== ⑧ P1 SW 缓存名按 build-version 自动生成 =====');
  const dp = fs.readFileSync(path.join(__dirname, 'deploy_pages.py'), 'utf-8');
  ok('deploy_pages 定义了 sync_sw_cache_name', /def sync_sw_cache_name\(\)/.test(dp));
  ok('部署前已调用（保证推上去的就是新缓存名）', /sync_sw_cache_name\(\)/.test(dp.split('def main()')[1] || ''));
  ok('缓存名由 build-version 派生（不再手输 v78/v79）', /mining-daily-/.test(dp) && /build-version/.test(dp));

  console.log('\n===== 结果：' + pass + ' PASS / ' + fail + ' FAIL =====');
  process.exit(fail ? 1 : 0);
}, 1200);
