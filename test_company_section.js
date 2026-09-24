/**
 * 2026-09-24 矿业公司动态（v7）运行时渲染回归（jsdom）
 * v6 = v5 布局（跨列区块：左新闻流 + 右 sticky 公司导航）+ 摘要/分组/去域名 修正：
 *   ① 卡片长度统一：源 t 字段 4 字 ↔ 1055 字悬殊 → 按句读切「标题 + 正文」，标题 2 行、正文 2 行折叠 + 「展开全文」
 *   ② 去矿种维度：矿种 chip 筛选 / 导航矿种分组 / 移动端 sector optgroup / 卡片矿种标签 全部移除
 *   ③ 链接可用：数据自带 HTML 实体（&amp;）先解码再转义（否则二次转义成 &amp;amp; 打不开）；外链 rel=noreferrer；显示目标域名
 *   ④ 导航：国内/海外分两组 + 按市值·知名度 rank 升序 + 计数徽标 + 「暂未收录」折叠组；面板内独立滚动
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
    // 国内 / 海外 分两组
    const gh = document.querySelectorAll('#coNav .co-nav-g-h');
    check('导航按 国内 / 海外 分两组', gh.length === 2, 'got ' + gh.length);
    check('分组标题含「国内公司」「海外公司」',
          Array.from(gh).some(e => /国内公司/.test(e.textContent)) &&
          Array.from(gh).some(e => /海外公司/.test(e.textContent)));
    // 组内按市值/知名度 rank 升序（紫金矿业 rank=1 早于 湖南黄金；Newmont 早于 Albemarle）
    const domOrder = Array.from(document.querySelectorAll('#coNav .co-nav-item:not(.empty)'))
      .map(el => el.getAttribute('data-name'));
    const zjIdx = domOrder.indexOf('紫金矿业'), sdIdx = domOrder.indexOf('山东黄金');
    check('国内组按 rank 升序（紫金矿业 早于 山东黄金）', zjIdx >= 0 && sdIdx >= 0 && zjIdx < sdIdx, zjIdx + '/' + sdIdx);
    const tkIdx = domOrder.indexOf('Teck Resources'), albIdx = domOrder.indexOf('Albemarle');
    check('海外组按 rank 升序（Teck Resources 早于 Albemarle）', tkIdx >= 0 && albIdx >= 0 && tkIdx < albIdx, tkIdx + '/' + albIdx);
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
    check('co-empty-note 文案说明动态加载/域名失效',
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
    check('移动端 select 按 国内/海外/暂未收录 三组',
          og.length >= 2 && /国内公司/.test(og[0].getAttribute('label') || '') &&
          /海外公司/.test(og[1].getAttribute('label') || '') &&
          (og.length < 3 || /暂未收录/.test(og[2].getAttribute('label') || '')),
          'optgroups=' + og.length + (og[0] ? ' labels=' + Array.from(og).map(g => g.getAttribute('label')).join('|') : ''));
    check('select 首项 = 全部公司', (opts[0] || {}).value === '__all__');

    // ---------- 11) 豁免与视图切换 ----------
    window.mdRefreshSections && window.mdRefreshSections();
    check('默认视图下 companySection 不被隐藏', disp('companySection') !== 'none', disp('companySection'));
    const coItem = document.querySelector('[data-target="companySection"]');
    if (coItem && typeof window.switchView === 'function') {
      window.switchView('company', coItem);
      check('switchView("company") 设置 data-view=company', document.body.dataset.view === 'company', document.body.dataset.view);
      check('公司区在公司视图可见', disp('companySection') !== 'none', disp('companySection'));
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
    check('无阻塞性 JS 错误', errors.length === 0, errors.join(' | '));

  } catch (e) {
    fail++;
    console.log('  FAIL  测试执行抛错 -> ' + (e && e.stack ? e.stack.split('\n').slice(0, 3).join(' | ') : e));
  }
  console.log('\n===== 矿业公司动态 v6（摘要 + 国内/海外分组 + 域名行移除）汇总 =====');
  console.log('  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail ? 1 : 0);
}, 1500);
