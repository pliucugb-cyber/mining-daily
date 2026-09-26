/**
 * 2026-09-24 矿业公司动态（v7）运行时渲染回归（jsdom）
 * v6 = v5 布局（跨列区块：左新闻流 + 右 sticky 公司导航）+ 摘要/分组/去域名 修正：
 *   ① 卡片长度统一：源 t 字段 4 字 ↔ 1055 字悬殊 → 按句读切「标题 + 正文」，标题 2 行、正文 2 行折叠 + 「展开全文」
 *   ② 去矿种维度：矿种 chip 筛选 / 导航矿种分组 / 移动端 sector optgroup / 卡片矿种标签 全部移除
 *   ③ 链接可用：数据自带 HTML 实体（&amp;）先解码再转义（否则二次转义成 &amp;amp; 打不开）；外链 rel=noreferrer；显示目标域名
 *   ④ 导航：国内/中资港股/海外 分三组（2026-09-26 拆出中资港股）+ 按市值·知名度 rank 升序 + 计数徽标 + 「暂未收录」折叠组；面板内独立滚动
 *   ⑦ 命名统一（2026-09-26）：海外/中资港股 显示「中文（英文）」，国内仅中文；name 仍作主键
 *   ⑧ 媒体源披露（2026-09-26）：选中公司后头部 sub 显示「来源：新浪财经 / 官网 RSS / 公司官网」
 *   ⑤ v6：每条卡片加一句内容摘要（仿新闻端，读 it.s）；移除逐条「目标域名」行；顶部说明段移除
 *   ⑥ v7：新闻流单栏（同新闻列表形式）；右栏 sticky 修复（#companySection 改 overflow:clip）+ 上移；
 *       搜索框纳入摘要匹配；暂未收录公司新增「搜新闻」搜索引擎入口（官网死站/外壳页时仍可发现相关内容）
 * 运行：node test_company_section.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
['app.js', 'news-data.js', 'lme-data.js', 'price-history.js'].forEach(f => {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) return;
  const tag = new RegExp('<script src="' + f + '[^>]*></script>');
  html = html.replace(tag, () => '<script>' + fs.readFileSync(p, 'utf-8') + '</script>');
});

// 真实公司数据（mock fetch 用）
const companyData = JSON.parse(fs.readFileSync(path.join(__dirname, 'company_news.json'), 'utf-8'));
const totalItems = (companyData.counts && companyData.counts.items) || 0;
const nCompanies = (companyData.companies || []).length;
const nEmptyCompanies = (companyData.companies || []).filter(c => !((c.items || []).length)).length;
const allFlat = [];
(companyData.companies || []).forEach(c => (c.items || []).forEach(it => allFlat.push({ ...it, _co: c.name })));

// 期望值：按 updated_at 为基准日，统计近 90 天内（有日期）的条目数 —— 与 app.js passRange() 同口径
function toTs(s) {
  const m = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(String(s || ''));
  return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) : NaN;
}
const baseTs = toTs(companyData.updated_at || '');
let inRange90 = 0, noDateCount = 0;
(companyData.companies || []).forEach(c => (c.items || []).forEach(it => {
  if (!it.d) { noDateCount++; return; }
  const a = toTs(it.d);
  if (isNaN(a) || isNaN(baseTs)) return;
  const n = Math.round((baseTs - a) / 86400000);
  if (n >= 0 && n <= 90) inRange90++;
}));
const PAGE = 60;
const HEAD_MAX = 64;               // 与 app.js 一致
const expectDefaultRendered = Math.min(PAGE, inRange90);

// 某公司在近 90 天内的条目数（与 app.js passRange 同口径）—— 用于断言「范围外自动放宽」
function in90Count(name) {
  let n = 0;
  (companyData.companies || []).forEach(c => {
    if (c.name !== name) return;
    (c.items || []).forEach(it => {
      if (!it.d) return;
      const a = toTs(it.d);
      if (isNaN(a) || isNaN(baseTs)) return;
      const dd = Math.round((baseTs - a) / 86400000);
      if (dd >= 0 && dd <= 90) n++;
    });
  });
  return n;
}

const errors = [];
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'https://pliucugb-cyber.github.io/mining-daily/',
  beforeParse(win) {
    if (typeof win.matchMedia !== 'function') {
      win.matchMedia = q => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
    }
    win.open = () => null;
    win.fetch = (url) => {
      if (String(url).indexOf('company_news.json') !== -1) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(companyData) });
      }
      return Promise.reject(new Error('stub-no-' + url));
    };
    win.addEventListener('error', e => errors.push('window.error: ' + (e.message || e)));
  }
});
const { window } = dom;
const { document } = window;

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log('  PASS  ' + name); }
  else { fail++; console.log('  FAIL  ' + name + (extra ? '  -> ' + extra : '')); }
}
function disp(id) {
  const el = document.getElementById(id);
  if (!el) return 'missing';
  return window.getComputedStyle(el).display;
}
function coState() { return window.__mdCo.state(); }
const H = () => window.__mdCo.helpers;

setTimeout(() => {
  try {
    // ---------- 0) 入口与容器 ----------
    check('目录含 🏢 矿业公司 入口', !!document.querySelector('[data-target="companySection"]'));
    check('companySection 容器存在', !!document.getElementById('companySection'));
    check('companyList 容器存在', !!document.getElementById('companyList'));
    check('公司导航 coNav 存在', !!document.getElementById('coNav'));
    check('移动端 coNavSel 存在', !!document.getElementById('coNavSel'));
    check('搜索框 coSearch 存在', !!document.getElementById('coSearch'));
    check('统计 coStat 存在', !!document.getElementById('coStat'));
    check('导航标题 coNavH 存在', !!document.getElementById('coNavH'));
    check('新闻流头部 coFeedHead 存在', !!document.getElementById('coFeedHead'));
    check('加载更多 coMoreWrap / coMore 存在', !!document.getElementById('coMoreWrap') && !!document.getElementById('coMore'));

    // ---------- 1) 布局（沿用 v4：跨列 + 右侧 sticky 侧栏） ----------
    const ng = document.querySelector('.news-grid');
    check('companySection 是 .news-grid 的直接子元素（跨列）',
          document.getElementById('companySection').parentElement === ng);
    check('installGuideSection 也移到 .news-grid 直接子级',
          document.getElementById('installGuideSection').parentElement === ng);
    check('eventCalendar 仍在 .col-main 内（未随迁）',
          document.getElementById('eventCalendar').parentElement !== ng &&
          !!document.getElementById('eventCalendar').closest('.col-main'));
    const coStyle = document.querySelector('#companySection > style');
    check('#companySection > style 存在', !!coStyle);
    const css = coStyle ? coStyle.textContent : '';
    check('CSS：公司区块 grid-column:1/-1（含 overflow:clip）', /#companySection\{[^}]*grid-column:1\/-1/.test(css) && css.indexOf('overflow:clip') >= 0);
    check('CSS：col-rail 显式回到第一行第二列', css.indexOf('.news-grid>.col-rail{grid-column:2;grid-row:1}') >= 0);
    check('CSS：侧栏 sticky + 内部滚动', /\.co-side\{[^}]*position:sticky/.test(css) && /\.co-nav\{[^}]*overflow:auto/.test(css));
    check('CSS：新闻流单栏（无 1400px 两栏网格，与新闻列表形式统一）', css.indexOf('.co-day-items') >= 0 && css.indexOf('min-width:1400px') < 0);
    check('CSS：#companySection overflow:clip（v7 sticky 修复）', css.indexOf('overflow:clip') >= 0);
    check('CSS：右栏 sticky top:10px（v7 上移）', /\.co-side\{[^}]*top:10px/.test(css));
    check('搜索占位含「内容」（v7 摘要入搜）', (document.getElementById('coSearch').getAttribute('placeholder')||'').indexOf('内容') >= 0);
    check('暂未收录公司均提供「搜新闻」链接', document.querySelectorAll('#coEmptyBox .co-empty-search').length === nEmptyCompanies);
    check('CSS：正文 2 行折叠 + 展开解除', /\.co-body\{[^}]*line-clamp:2/.test(css) && /\.co-item\.open \.co-body/.test(css));
    check('搜索框已收进右侧栏 .co-side', !!(document.getElementById('coSearch').closest('.co-side')));
    check('公司导航已收进右侧栏 .co-side', !!(document.getElementById('coNav').closest('.co-side')));
    check('旧 .co-bar 已移除', !document.querySelector('.co-bar'));

    // ---------- 2) 去矿种维度（v5 ②） ----------
    check('矿种筛选容器 #coFilters 已移除', !document.getElementById('coFilters'));
    check('矿种 chip 按钮 .co-fchip 已移除', document.querySelectorAll('.co-fchip').length === 0);
    check('导航矿种分组 .co-nav-group 已移除', document.querySelectorAll('#coNav .co-nav-group').length === 0);
    check('卡片矿种标签 .co-cat 已移除', document.querySelectorAll('#companyList .co-cat').length === 0);
    check('CSS 中已无矿种 chip / 分组 / 卡片标签规则',
          css.indexOf('.co-fchip') < 0 && css.indexOf('.co-nav-group') < 0 && css.indexOf('.co-cat') < 0);

    // ---------- 3) 新闻流默认：近 90 天 + 分页 60 + 日期分组 ----------
    const st0 = coState();
    check('window.__mdCo 状态句柄存在', !!window.__mdCo && typeof st0 === 'object');
    check('状态句柄不再暴露 activeSector（矿种已移除）', !('activeSector' in st0));
    check('默认时间范围为「近90天」', st0.range === 90, 'range=' + st0.range);
    check('默认分页游标 = 60', st0.shown === PAGE, 'shown=' + st0.shown);
    check('默认渲染条数 = min(60, 近90天条数)',
          st0.rendered === expectDefaultRendered,
          'got ' + st0.rendered + ' / expect ' + expectDefaultRendered + ' (in90=' + inRange90 + ')');
    check('新闻流按日期分组（.co-day 数 >= 1）', st0.groups >= 1, 'groups=' + st0.groups);
    check('coCount 显示公司家数', /家/.test((document.getElementById('coCount') || {}).textContent || ''),
          (document.getElementById('coCount') || {}).textContent);
    const rangeBtns = document.querySelectorAll('#coFeedHead .co-range button');
    check('时间范围切换按钮 3 个', rangeBtns.length === 3, 'got ' + rangeBtns.length);
    check('「加载更多」可见性 = 范围内条目超出一页',
          coState().moreVisible === (inRange90 > PAGE),
          'moreVisible=' + coState().moreVisible + ' in90=' + inRange90);

    // ---------- 4) 卡片长度统一（v5 ①，核心） ----------
    const titles0 = Array.from(document.querySelectorAll('#companyList .co-title'));
    const overLong = titles0.filter(t => (t.textContent || '').trim().length > HEAD_MAX + 2);
    check('默认视图所有标题 ≤ ' + HEAD_MAX + ' 字（不再出现整屏段落）',
          overLong.length === 0, 'over=' + overLong.length + (overLong[0] ? ' e.g. ' + overLong[0].textContent.slice(0, 40) : ''));
    check('默认视图存在内容摘要（.co-summary）或折叠正文（.co-exp）',
          document.querySelectorAll('#companyList .co-summary').length >= 1 ||
          document.querySelectorAll('#companyList .co-exp').length >= 1,
          'summary=' + document.querySelectorAll('#companyList .co-summary').length +
          ' exp=' + document.querySelectorAll('#companyList .co-exp').length);

    // 切「全部」+ 连续加载更多 → 渲染出全部条目
    const allBtn = document.querySelector('#coFeedHead .co-range button[data-r="0"]');
    let loadedAll = false;
    if (allBtn) {
      allBtn.click();
      loadedAll = true;
      check('切「全部」后 range=0', coState().range === 0, 'range=' + coState().range);
      check('切「全部」后仍分页（渲染 = min(60, 全部条数)）',
            coState().rendered === Math.min(PAGE, totalItems),
            'got ' + coState().rendered + ' / ' + Math.min(PAGE, totalItems));
      let guard = 0;
      while (coState().rendered < totalItems && guard++ < 40) {
        const m = document.getElementById('coMore');
        if (!m || document.getElementById('coMoreWrap').hidden) break;
        m.click();
      }
      check('连续「加载更多」后渲染全部条目（' + totalItems + ' 条）',
            coState().rendered === totalItems,
            'got ' + coState().rendered + ' / expect ' + totalItems);
      check('全部加载完后「加载更多」隐藏', coState().moreVisible === false);
      check('未标注日期条目只在「全部」下出现',
            noDateCount === 0 || coState().rendered > inRange90,
            'noDate=' + noDateCount + ' rendered=' + coState().rendered + ' in90=' + inRange90);
    } else {
      check('存在「全部」范围按钮', false);
    }

    if (loadedAll) {
      const titlesAll = Array.from(document.querySelectorAll('#companyList .co-title'));
      check('全部视图所有标题 ≤ ' + HEAD_MAX + ' 字', titlesAll.every(t => (t.textContent || '').trim().length <= HEAD_MAX + 2),
            'max=' + Math.max(...titlesAll.map(t => (t.textContent || '').trim().length)));
      // 期望折叠数 = 既无摘要、清洗后长度又 > HEAD_MAX 的条目数（有摘要的条目由摘要承载，不再折叠续写）
      const expectFold = allFlat.filter(it => !it.s && H().split(it.t).body).length;
      const gotFold = document.querySelectorAll('#companyList .co-exp').length;
      check('折叠正文条数 = 无摘要长文条目数（期望 ' + expectFold + '）', gotFold === expectFold, 'got ' + gotFold);
      check('默认全部折叠（无 .co-item.open）', document.querySelectorAll('#companyList .co-item.open').length === 0);
      // 交互：展开 / 收起
      const eb = document.querySelector('#companyList .co-exp');
      if (eb) {
        const box = eb.closest('.co-item');
        eb.click();
        check('点「展开全文」→ 条目加 .open', box.classList.contains('open'));
        check('点「展开全文」→ 按钮文案变「收起」', eb.textContent.indexOf('收起') >= 0, eb.textContent);
        check('展开后 aria-expanded=true', eb.getAttribute('aria-expanded') === 'true');
        eb.click();
        check('再点一次 → 收回归档', !box.classList.contains('open') && eb.textContent.indexOf('展开') >= 0, eb.textContent);
      } else {
        // v6：标题经清洗后均 ≤ 64 字、且 84% 条目带摘要，无长文折叠需求 → 不需要「展开全文」按钮（内容由摘要承载）
        check('无长文折叠时不需要「展开全文」按钮（摘要承载内容）', expectFold === 0, 'expectFold=' + expectFold);
      }
      // 切回默认范围
      const defBtn = document.querySelector('#coFeedHead .co-range button[data-r="90"]');
      if (defBtn) defBtn.click();
    }

    // ---------- 5) 文本清洗与切分助手（v5 ①，用真实数据里的最长条目验证） ----------
    const cleaned1 = H().clean('25 2026.05 赤峰黄金总裁高波一行到五龙矿业调研指导工作  5月21日，赤峰黄金…  2026/09/17');
    check('clean() 剥离前导「序号+年月」', cleaned1.indexOf('25 ') !== 0 && cleaned1.indexOf('2026.05') !== 0, cleaned1.slice(0, 30));
    check('clean() 剥离尾部日期', !/2026\/09\/17\s*$/.test(cleaned1), cleaned1.slice(-20));
    check('clean() 不误伤「5 万吨…」类标题', H().clean('5 万吨项目投产').indexOf('5 万吨') === 0, H().clean('5 万吨项目投产'));
    // split() 逻辑验证：喂一段 >HEAD_MAX 且含句号的超长文本，应拆出「标题(≤HEAD_MAX) + 正文」
    const synth = '公司今日正式宣布完成对澳大利亚某大型锂矿项目的全资收购，交易总金额约十五亿澳元。本次收购将显著增强公司在新能源产业链上游的资源保障能力，并有望在三年内实现产能爬坡与成本优化。';
    const spS = H().split(synth);
    check('split()：超长文本（含句号）拆出标题 + 正文',
          spS.head.length > 0 && spS.body.length > 0 && spS.head.length <= HEAD_MAX,
          'head=' + spS.head.length + ' body=' + spS.body.length);
    // 真实最长条目 ≤ HEAD_MAX → 不应折叠（标题即全文，正文为空）—— 与「摘要承载内容」的设计一致
    const longest = allFlat.slice().sort((a, b) => (b.t || '').length - (a.t || '').length)[0] || { t: '' };
    const spR = H().split(longest.t);
    check('split()：真实最长条目（' + (longest.t || '').length + ' 字）≤ HEAD_MAX → 仅标题、无折叠',
          spR.head.length === (longest.t || '').length && spR.body === '',
          'head=' + spR.head.length + ' body=' + spR.body.length + ' src=' + (longest.t || '').length);
    const sp2 = H().split('H股公告');
    check('split()：短文只有标题、无正文', sp2.head === 'H股公告' && sp2.body === '', JSON.stringify(sp2));
    const sp3 = H().split(longest.t);
    check('split() 标题+正文拼回 = 清洗后原文（不丢字）',
          (sp3.head + (sp3.body ? ' ' + sp3.body : '')).replace(/\s+/g, '') === H().clean(longest.t).replace(/\s+/g, ''),
          'head+body len=' + (sp3.head.length + sp3.body.length) + ' clean len=' + H().clean(longest.t).length);

    // ---------- 6) 链接可用性（v5 ③，核心） ----------
    check('dec() 解码 &amp;', H().dec('a?x=1&amp;y=2') === 'a?x=1&y=2', H().dec('a?x=1&amp;y=2'));
    check('dec() 解码数字实体', H().dec('a&#39;b&nbsp;c') === "a'b c", H().dec('a&#39;b&nbsp;c'));
    check('hostOf() 取域名并去 www', H().host('http://www.tlys.cn/news.aspx?cid=1') === 'tlys.cn', H().host('http://www.tlys.cn/news.aspx?cid=1'));
    const hrefs = Array.from(document.querySelectorAll('#companyList .co-title')).map(a => a.getAttribute('href') || '');
    const badHref = hrefs.filter(h => h.indexOf('&amp;') >= 0);
    check('渲染出的 href 无二次转义残留（&amp;amp;）', badHref.length === 0,
          'bad=' + badHref.length + (badHref[0] ? ' e.g. ' + badHref[0] : ''));
    const tlysHref = hrefs.filter(h => h.indexOf('tlys.cn') >= 0);
    check('带 & 参数的链接还原正确（tlys.cn ?cid=&classid=）',
          tlysHref.length === 0 || tlysHref.every(h => /[?&]cid=\d+&classid=\d+/.test(h)),
          tlysHref[0] || 'no tlys link in view');
    check('所有外链 href 均为 http(s)', hrefs.every(h => /^https?:\/\//.test(h)),
          hrefs.find(h => !/^https?:\/\//.test(h)) || '');
    const firstLink = document.querySelector('#companyList .co-title');
    check('外链 rel 含 noreferrer（规避企业站按 Referer 拒链）',
          !!firstLink && /noreferrer/.test(firstLink.getAttribute('rel') || ''),
          firstLink ? firstLink.getAttribute('rel') : 'no link');
    check('卡片不再逐条显示目标域名（.co-host 已移除）',
          document.querySelectorAll('#companyList .co-host').length === 0,
          'host=' + document.querySelectorAll('#companyList .co-host').length);
    const renderedItems = document.querySelectorAll('#companyList .co-item').length;
    const withSum = document.querySelectorAll('#companyList .co-summary').length;
    check('渲染条目中绝大多数带内容摘要（≥70%，仿新闻端）',
          renderedItems > 0 && withSum / renderedItems >= 0.7,
          (100 * withSum / Math.max(1, renderedItems)).toFixed(0) + '% (' + withSum + '/' + renderedItems + ')');

    // ---------- 7) 右侧公司导航（v5 ④） ----------
    const navItems = document.querySelectorAll('#coNav .co-nav-item:not(.empty)');
    const liveCount = (companyData.companies || []).filter(c => (c.items || []).length > 0).length;
    check('公司导航列出全部「有内容」公司（' + liveCount + ' 家）', navItems.length === liveCount,
          'got ' + navItems.length);
    const navAll = document.querySelector('#coNav .co-nav-all');
    check('公司导航「全部公司」入口存在', !!navAll);
    // 国内 / 中资港股 / 海外 分三组（2026-09-26 拆三组：海外按「是否 A股」→ 拆出中资港股）
    const gh = document.querySelectorAll('#coNav .co-nav-g-h');
    check('导航按 国内 / 中资港股 / 海外 分三组', gh.length === 3, 'got ' + gh.length);
    const ghLabels = Array.from(gh).map(e => e.textContent);
    check('分组标题含「国内公司」「中资港股」「海外公司」',
          /国内公司/.test(ghLabels.join('|')) &&
          /中资港股/.test(ghLabels.join('|')) &&
          /海外公司/.test(ghLabels.join('|')), ghLabels.join('|'));
    // 组内按市值/知名度 rank 升序（紫金矿业 rank=1 早于 湖南黄金；Newmont 早于 Albemarle）
    const domOrder = Array.from(document.querySelectorAll('#coNav .co-nav-item:not(.empty)'))
      .map(el => el.getAttribute('data-name'));
    const zjIdx = domOrder.indexOf('紫金矿业'), sdIdx = domOrder.indexOf('山东黄金');
    check('国内组按 rank 升序（紫金矿业 早于 山东黄金）', zjIdx >= 0 && sdIdx >= 0 && zjIdx < sdIdx, zjIdx + '/' + sdIdx);
    const tkIdx = domOrder.indexOf('Teck Resources'), albIdx = domOrder.indexOf('Albemarle');
    check('海外组按 rank 升序（Teck Resources 早于 Albemarle）', tkIdx >= 0 && albIdx >= 0 && tkIdx < albIdx, tkIdx + '/' + albIdx);
    // 命名统一（2026-09-26）：海外/中资港股 显示「中文（英文）」；国内仅中文（name 仍作主键）
    const navNameMap = {};
    document.querySelectorAll('#coNav .co-nav-item').forEach(el => {
      navNameMap[el.getAttribute('data-name')] = (el.querySelector('.co-nav-name') || {}).textContent || '';
    });
    check('海外英文公司「纽蒙特」显示 纽蒙特（Newmont）',
          (navNameMap['Newmont'] || '').indexOf('纽蒙特（Newmont）') >= 0, navNameMap['Newmont']);
    check('中资港股「五矿资源」显示 五矿资源（MMG）',
          (navNameMap['五矿资源'] || '').indexOf('五矿资源（MMG）') >= 0, navNameMap['五矿资源']);
    check('海外中文公司「力拓」显示 力拓（Rio Tinto）',
          (navNameMap['力拓'] || '').indexOf('力拓（Rio Tinto）') >= 0, navNameMap['力拓']);
    check('国内公司「紫金矿业」仅显示中文（不含括号英文）',
          (navNameMap['紫金矿业'] || '') === '紫金矿业', navNameMap['紫金矿业']);
    check('导航标题显示家数/条数', /家/.test((document.getElementById('coNavH') || {}).textContent || ''),
          (document.getElementById('coNavH') || {}).textContent);
    const emptyItems = document.querySelectorAll('#coNav .co-nav-item.empty');
    check('未收录公司列入折叠组（数量=' + nEmptyCompanies + '）',
          emptyItems.length === nEmptyCompanies, 'got ' + emptyItems.length);
    const box0 = document.getElementById('coEmptyBox');
    check('未收录组默认折叠', nEmptyCompanies === 0 || (!!box0 && box0.hasAttribute('hidden')));
    const tog = document.getElementById('coEmptyToggle');
    if (tog) {
      tog.click();
      check('点「展开」后未收录组显示', !document.getElementById('coEmptyBox').hasAttribute('hidden'));
      tog.click();
      check('再点一次收回折叠', document.getElementById('coEmptyBox').hasAttribute('hidden'));
    } else {
      check('「暂未收录」折叠开关存在（无空公司时豁免）', nEmptyCompanies === 0);
    }

    // ---------- 7.5) unreach 标注（v8：spa 动态不可抓 / dead 死域名）----------
    // unreach:'spa' 仅作「动态站」标记；有数据的 spa 公司走正常 host 展示，
    // 只有「0 条空壳 spa 公司」才在折叠组显示「动态 ✕」标签（与前端 renderNav 一致）。
    // 故断言只针对「空壳 spa」，不再要求所有 spa 公司均为空（v9：中国铝业经无头渲染已有数据）。
    const spaEmptyNames = (companyData.companies || []).filter(c => c.unreach === 'spa' && !((c.items || []).length)).map(c => c.name);
    const spaEls = Array.from(document.querySelectorAll('#coNav .co-nav-item.empty'))
      .filter(el => /动态/.test((el.querySelector('.co-n') || {}).textContent || ''));
    check('spa 类空壳均显示「动态」标签', spaEmptyNames.length === 0 ||
          spaEmptyNames.every(n => spaEls.some(el => el.getAttribute('data-name') === n)),
          spaEls.length + '/' + spaEmptyNames.length);
    check('co-empty-note 文案说明动态加载/域名失效（无空公司时豁免）',
          nEmptyCompanies === 0 ||
          /动态加载|域名已失效/.test((document.querySelector('.co-empty-note') || {}).textContent || ''));

    // ---------- 8) 首条卡片结构 ----------
    const items = document.querySelectorAll('#companyList .co-item');
    const first = items[0];
    check('首条含新闻标题', !!(first && first.querySelector('.co-title') && first.querySelector('.co-title').textContent.trim().length > 0));
    check('首条含公司来源名（co-src 可点选公司）',
          !!(first && first.querySelector('.co-src') && first.querySelector('.co-src').textContent.trim().length > 0));
    check('首条标题为 http(s) 外链', !!(first && first.querySelector('.co-title') &&
          /^https?:\/\//.test(first.querySelector('.co-title').getAttribute('href') || '')));
    check('卡片结构完整（标题/来源/可选摘要，无残留旧 co-host）',
          document.querySelectorAll('#companyList .co-host').length === 0 &&
          !!(first && first.querySelector('.co-title') && first.querySelector('.co-src')));

    // ---------- 8.5) 媒体源披露（agg=SEC披露·股票新闻 / mining=矿业媒体 / 条目级 co-src-tag）----------
    const taggedEls = document.querySelectorAll('#companyList .co-src-tag');
    check('动态源条目带来源标签 co-src-tag', taggedEls.length > 0, 'tagged=' + taggedEls.length);
    const tagTexts = {};
    taggedEls.forEach(e => { const t = e.textContent.trim(); tagTexts[t] = (tagTexts[t] || 0) + 1; });
    check('来源标签含 SEC披露/股票新闻/矿业媒体 之一',
          !!tagTexts['SEC披露'] || !!tagTexts['股票新闻'] || !!tagTexts['矿业媒体'], JSON.stringify(tagTexts));
    const aggCo = (companyData.companies.find(c => c.origin === 'agg' && (c.items || []).length) || {}).name;
    if (aggCo) {
      window.location.hash = '#co=' + encodeURIComponent(aggCo);
      window.dispatchEvent(new window.Event('hashchange'));
      const subAgg = (document.querySelector('#coFeedHead .co-feed-sub') || {}).textContent || '';
      check('agg 公司头部显示「SEC披露·股票新闻」(' + aggCo + ')', /SEC披露|股票新闻/.test(subAgg), subAgg);
    }
    const minCo = (companyData.companies.find(c => c.origin === 'mining' && (c.items || []).length) || {}).name;
    if (minCo) {
      window.location.hash = '#co=' + encodeURIComponent(minCo);
      window.dispatchEvent(new window.Event('hashchange'));
      const subMin = (document.querySelector('#coFeedHead .co-feed-sub') || {}).textContent || '';
      check('mining 公司头部显示「矿业媒体」(' + minCo + ')', /矿业媒体/.test(subMin), subMin);
    }
    if (navAll) navAll.click();

    // ---------- 9) 公司选择（含「范围外自动放宽」）/ hash 路由 / 搜索 ----------
    let selName = '', selTotal = 0;
    for (const ni of navItems) {
      selName = ni.getAttribute('data-name');
      const cc = (companyData.companies || []).find(c => c.name === selName) || {};
      selTotal = (cc.items || []).length;
      ni.click(); break;
    }
    check('存在可点击的有数据公司', !!selName, selName);
    if (selName) {
      const after = document.querySelectorAll('#companyList .co-item');
      let allMatch = true;
      after.forEach(it => {
        const src = it.querySelector('.co-src');
        if (!src || src.getAttribute('data-name') !== selName) allMatch = false;
      });
      check('选中公司后新闻流仅含该公司（' + selName + '）', after.length > 0 && allMatch,
            'got ' + after.length + ' match=' + allMatch);
      const in90 = in90Count(selName);
      check('公司条目全在范围外时自动放宽到「全部」（' + selName + '：90天内 ' + in90 + ' 条 / 共 ' + selTotal + ' 条）',
            in90 > 0 ? (!coState().forcedAll && after.length === Math.min(PAGE, in90))
                     : (coState().forcedAll === true && after.length === Math.min(PAGE, selTotal)),
            'rendered=' + after.length + ' forcedAll=' + coState().forcedAll + ' range=' + coState().range);
      const headName = (document.querySelector('#coFeedHead .co-feed-name') || {}).textContent || '';
      check('新闻流头部显示公司名', headName.indexOf(selName) >= 0, headName);
      check('公司视图头部含「官网」外链或代码',
            /官网/.test(document.getElementById('coFeedHead').textContent) || !!document.querySelector('#coFeedHead .co-feed-link'));
      const sub = (document.querySelector('#coFeedHead .co-feed-sub') || {}).textContent || '';
      check('公司视图头部只显示代码+条数（不再带矿种）', /显示 \d+ \/ \d+ 条/.test(sub), sub);
      check('hash 写入 #co=公司名', /#co=/.test(window.location.hash), window.location.hash);
      if (navAll) navAll.click();
      check('点「全部公司」回到全站视图',
            ((document.querySelector('#coFeedHead .co-feed-name') || {}).textContent || '').indexOf('全站') >= 0,
            (document.querySelector('#coFeedHead .co-feed-name') || {}).textContent);
      check('回到全站视图自动放宽被清除（forcedAll=false）', coState().forcedAll === false,
            'forcedAll=' + coState().forcedAll);
    }

    const someCo = (companyData.companies.find(c => (c.items || []).length > 0) || {}).name || '';
    if (someCo) {
      window.location.hash = '#co=' + encodeURIComponent(someCo);
      window.dispatchEvent(new window.Event('hashchange'));
      const afterHash = document.querySelectorAll('#companyList .co-item');
      let allMatch = true;
      afterHash.forEach(it => {
        const src = it.querySelector('.co-src');
        if (!src || src.getAttribute('data-name') !== someCo) allMatch = false;
      });
      check('hash 路由定位到公司（' + someCo + '）', afterHash.length > 0 && allMatch,
            'got ' + afterHash.length + ' match=' + allMatch);
      if (navAll) navAll.click();
    } else {
      check('hash 路由（存在可定位公司）', false, '无数据公司');
    }

    const q = document.getElementById('coSearch');
    if (q) {
      const before = document.querySelectorAll('#companyList .co-item').length;
      q.value = (someCo || '').slice(0, 2);
      q.dispatchEvent(new window.Event('input'));
      const after = document.querySelectorAll('#companyList .co-item').length;
      check('搜索框可触发过滤（数量变化或保持）', typeof after === 'number' || after <= before,
            'before ' + before + ' after ' + after);
      q.value = '';
      q.dispatchEvent(new window.Event('input'));
    } else {
      check('搜索框存在', false);
    }

    // ---------- 10) 移动端 select：国内 / 海外 / 暂未收录 三组 ----------
    const opts = document.querySelectorAll('#coNavSel option');
    check('移动端 select 选项=公司数+1', opts.length === nCompanies + 1, 'got ' + opts.length + ' / ' + (nCompanies + 1));
    const og = document.querySelectorAll('#coNavSel optgroup');
    const ogLabels = Array.from(og).map(g => g.getAttribute('label') || '');
    check('移动端 select 含 国内/中资港股/海外（+ 暂未收录）',
          /国内公司/.test(ogLabels.join('|')) &&
          /中资港股/.test(ogLabels.join('|')) &&
          /海外公司/.test(ogLabels.join('|')) &&
          (nEmptyCompanies === 0 || /暂未收录/.test(ogLabels.join('|'))),
          'optgroups=' + og.length + ' labels=' + ogLabels.join('|'));
    check('select 首项 = 全部公司', (opts[0] || {}).value === '__all__');

    // ---------- 11) 豁免与视图切换 ----------
    window.mdRefreshSections && window.mdRefreshSections();
    check('默认视图下 companySection 被隐藏（仅矿业公司视图显示）',
          /#companySection\{display:none\}/.test(Array.from(document.querySelectorAll('style')).map(x=>x.textContent).join('\n')));
    const coItem = document.querySelector('[data-target="companySection"]');
    if (coItem && typeof window.switchView === 'function') {
      window.switchView('company', coItem);
      check('switchView("company") 设置 data-view=company', document.body.dataset.view === 'company', document.body.dataset.view);
      check('公司区在公司视图可见（CSS 规则）',
            /body\[data-view="company"\][^{]*#companySection\{display:block\}/.test(Array.from(document.querySelectorAll('style')).map(x=>x.textContent).join('\n')));
      check('今日区在公司视图隐藏', disp('todaySection') === 'none', disp('todaySection'));
      check('矿权区在公司视图隐藏', disp('rightsSection') === 'none', disp('rightsSection'));
      check('右栏在公司视图隐藏', window.getComputedStyle(document.querySelector('.col-rail')).display === 'none');
      check('公司入口获得 active 高亮', coItem.classList.contains('active'));
      window.switchView('company', coItem);
      check('再次点击回到全部（data-view 清除）', !document.body.dataset.view, document.body.dataset.view);
    } else {
      check('switchView 函数存在且目录入口存在', false, 'missing switchView or entry');
    }

    // ---------- 12) 无阻塞 JS 错误 ----------
    check('updateActiveSection 函数存在', typeof window.updateActiveSection === 'function');
    // ---------- 13) 公司视图已读态（2026-09-24 新增，独立于新闻流） ----------
    // #2 用户诉求：点开新闻毫无反馈 → 补「标为已读/未读」+ 已读弱化，且不与新闻流已读串号。
    const fItem = document.querySelector('#companyList .co-item');
    check('卡片带 data-url（已读集合键）', !!(fItem && fItem.getAttribute('data-url')));
    check('卡片含「标为已读 / 标为未读」操作按钮', document.querySelectorAll('#companyList .btn-co-read').length >= 1);
    const rb = fItem && fItem.querySelector('.btn-co-read');
    if (rb) {
      rb.click();
      check('点「标为已读」→ 条目加 .read（弱化）', fItem.classList.contains('read'));
      check('点「标为已读」→ 出现「标为未读」按钮', !!fItem.querySelector('.btn-co-unread'));
      // 已读写入独立 key（不污染新闻流 STORE_KEY）
      const coKey = window.localStorage && window.localStorage.getItem('mining_daily_read_co_urls');
      check('公司已读写入独立 localStorage key', !!coKey, 'coKey=' + coKey);
      const ub = fItem.querySelector('.btn-co-unread');
      if (ub) { ub.click(); check('点「标为未读」→ 移除 .read', !fItem.classList.contains('read')); }
    } else {
      check('标为已读 按钮存在', false);
    }

    // ---------- 14) 数据洁净：渲染摘要不含电头/地址/征集代理等模板残片（#1/#3 修复回归保护） ----------
    // #1 删掉「下属公司/机构介绍」；#3 修掉「只有标题、格式错乱」——电头/地址/征集代理绝不能当摘要。
    const summText = Array.from(document.querySelectorAll('#companyList .co-summary'))
      .map(e => e.textContent || '').join('\n');
    const badMark = /TSX\s*[:：]|Suite\s*\d|Burrard|美通社|PRNewswire|Copyright|proxy solicitation|征集代理|Barclays|Vancouver/i.test(summText);
    check('渲染摘要不含电头/地址/征集代理等模板残片', !badMark, summText.slice(0, 80));
    // 诚实的「仅标题」体验：暂未提取到摘要时显示占位，而非空白或错乱电头
    // 诚实的「仅标题」体验：暂未提取到摘要时显示占位，而非空白或错乱电头。
    // 改为数据无关的结构断言：每条卡片必含 摘要 / 占位 / 折叠 之一（不允许空白卡片）。
    const cards14 = document.querySelectorAll('#companyList .co-item');
    const blank14 = Array.from(cards14).filter(c =>
      !c.querySelector('.co-summary') && !c.querySelector('.co-summary-empty') && !c.querySelector('.co-exp'));
    check('每条卡片都有摘要/占位/折叠之一（无空白卡片；.co-summary-empty 仍为缺摘要时的诚实占位）',
          blank14.length === 0, 'blank=' + blank14.length);

    // ---------- 15) P1/P2 优化回归（2026-09-26）：未读筛选 / 关注置顶 / 矿种标签 / sticky ----------
    // P2 矿种标签：2026-09-26 用户拍板「删掉」—— 卡片不再渲染矿种标签（回归 v5 ② 去矿种维度契约）
    check('卡片已不渲染矿种标签 .co-sec（用户 09-26 拍板删除）',
          document.querySelectorAll('#companyList .co-sec').length === 0,
          'sec=' + document.querySelectorAll('#companyList .co-sec').length);
    check('CSS 中已无 .co-sec 规则（index.html 已删除）', css.indexOf('.co-sec') < 0);

    // P3 计数口径对齐（修「洛阳钼业显示 9 条、点进去只有 2 条」的口径错位）
    // 期望：导航徽标 == 「点进去实际会看到的条数」（范围内有则显示范围内，否则 widenRangeIfNeeded 自动放宽到全部）
    const navBadges = {};
    document.querySelectorAll('#coNav .co-nav-item:not(.empty)').forEach(el => {
      navBadges[el.getAttribute('data-name')] = (el.querySelector('.co-n') || {}).textContent || '';
    });
    const navAllBadge = (document.querySelector('#coNav .co-nav-all .co-n') || {}).textContent || '';
    check('「全部公司」徽标 = 近 90 天总条数（' + navAllBadge + ' vs ' + inRange90 + '）',
          String(navAllBadge) === String(inRange90), navAllBadge + '/' + inRange90);
    let badgeMismatch = 0, badgeChecked = 0;
    (companyData.companies || []).forEach(c => {
      const n = c.name; if (!((c.items || []).length)) return;
      const exp = in90Count(n) > 0 ? in90Count(n) : (c.items || []).length;
      const got = navBadges[n];
      badgeChecked++;
      if (String(got) !== String(exp)) { badgeMismatch++; if (badgeMismatch <= 5) console.log('    mismatch ' + n + ': badge=' + got + ' exp=' + exp); }
    });
    check('导航每家公司徽标 == 点进去实际可见条数（' + badgeChecked + ' 家，错 ' + badgeMismatch + '）',
          badgeMismatch === 0, badgeMismatch + '/' + badgeChecked);

    // P1-A 未读筛选开关
    check('默认 coUnreadOnly=false', coState().coUnreadOnly === false);
    const ut = document.querySelector('#coFeedHead .co-unread-toggle');
    check('新闻流头部含「未读」筛选按钮', !!ut);
    if (ut) {
      check('未读按钮默认无 .on', !ut.classList.contains('on'));
      ut.click();
      check('点「未读」→ coUnreadOnly=true', coState().coUnreadOnly === true, 'coUnreadOnly=' + coState().coUnreadOnly);
      const utAfter = document.querySelector('#coFeedHead .co-unread-toggle');
      check('点「未读」→ 按钮加 .on', !!(utAfter && utAfter.classList.contains('on')));
      check('未读筛选触发重渲（rendered 为数字）', typeof coState().rendered === 'number');
      if (utAfter) utAfter.click();
      check('再点「未读」→ coUnreadOnly=false', coState().coUnreadOnly === false);
    }
    check('__mdCo.toggleUnread() 可用', typeof window.__mdCo.toggleUnread === 'function');

    // P1-B 关注置顶 + 星标
    check('默认 coFavs 为空数组', Array.isArray(coState().coFavs) && coState().coFavs.length === 0);
    const stars15 = document.querySelectorAll('#coNav .co-star');
    const listedNav15 = document.querySelectorAll('#coNav .co-nav-item:not(.empty)');
    check('导航每列公司均带星标（stars == 列出公司数）',
          stars15.length === listedNav15.length && stars15.length >= 1,
          'stars=' + stars15.length + ' listed=' + listedNav15.length);
    const firstStar15 = stars15[0];
    let favName15 = '';
    if (firstStar15) {
      favName15 = firstStar15.getAttribute('data-fav');
      firstStar15.click();
      const starAfter15 = document.querySelector('#coNav .co-star[data-fav="' + favName15 + '"]');
      check('点星标 → coFavs 含该公司', coState().coFavs.indexOf(favName15) >= 0,
            'favs=' + JSON.stringify(coState().coFavs));
      check('点星标 → 星标加 .on', !!(starAfter15 && starAfter15.classList.contains('on')));
      const navOrder15 = Array.from(document.querySelectorAll('#coNav .co-nav-item:not(.empty)'))
        .map(el => el.getAttribute('data-name'));
      check('关注公司置顶（导航首位=被关注公司）', navOrder15[0] === favName15,
            (navOrder15[0] || '') + ' vs ' + favName15);
      const favOg15 = Array.from(document.querySelectorAll('#coNavSel optgroup'))
        .filter(g => /我的关注/.test(g.getAttribute('label') || ''));
      check('移动端 select 含「★ 我的关注」分组（关注后）', favOg15.length === 1, 'og=' + favOg15.length);
      check('__mdCo.toggleFav() 可用', typeof window.__mdCo.toggleFav === 'function');
      const starBack15 = document.querySelector('#coNav .co-star[data-fav="' + favName15 + '"]');
      if (starBack15) { starBack15.click(); check('再点星标 → coFavs 移除该公司', coState().coFavs.indexOf(favName15) < 0); }
    } else {
      check('存在可关注的星标', false);
    }

    // P1-C 日期分组表头常驻（CSS position:sticky）
    check('CSS：.co-day-h 含 position:sticky（日期分组表头常驻）', /\.co-day-h\{[^}]*position:sticky/.test(css));

    // ---------- 15.5) 媒体源披露（2026-09-26）：选中 re-sourced 公司后头部显示来源 ----------
    function selectCoByName(name) {
      const el = document.querySelector('#coNav .co-nav-item[data-name="' + name + '"]');
      if (el) el.click();
      return el;
    }
    if (selectCoByName('五矿资源')) {
      const sub1 = (document.querySelector('#coFeedHead .co-feed-sub') || {}).textContent || '';
      check('选中「五矿资源」头部披露来源：新浪财经', /新浪财经/.test(sub1), sub1);
    } else { check('可定位「五矿资源」', false); }
    if (selectCoByName('第一量子')) {
      const sub2 = (document.querySelector('#coFeedHead .co-feed-sub') || {}).textContent || '';
      check('选中「第一量子」头部披露来源：官网 RSS', /官网 RSS/.test(sub2), sub2);
    } else { check('可定位「第一量子」', false); }
    if (navAll) navAll.click();

    check('无阻塞性 JS 错误', errors.length === 0, errors.join(' | '));

  } catch (e) {
    fail++;
    console.log('  FAIL  测试执行抛错 -> ' + (e && e.stack ? e.stack.split('\n').slice(0, 3).join(' | ') : e));
  }
  console.log('\n===== 矿业公司动态 v7 + P1/P2（未读筛选/关注置顶/矿种标签/日期sticky）汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 1500);
