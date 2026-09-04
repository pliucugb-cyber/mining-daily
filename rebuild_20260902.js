/* 矿业新闻日报 index.html 重建脚本（2026-09-02 补跑）
 * 用法：node rebuild_20260902.js
 * 逻辑：保留全部 <style>/<script>，只重建 今日新增/往期内容 两块 + 价格栏数字
 */
const fs = require('fs');

const FILE = 'index.html';
const REPORT_DATE = '2026-09-02';
const KEEP_FROM = '08-26';   // 7天滚动：保留 >= 08-26

/* ---------- 今日新增条目 ---------- */
const NEW_ITEMS = [
  // 🔍 找矿成果与勘查技术
  { cat: '🔍 找矿成果与勘查技术', src: '自然资源部', date: '09-02',
    title: '新一轮找矿突破战略行动再获标志性成果 安徽茶亭铜金矿勘查取得重大突破',
    url: 'https://www.mnr.gov.cn/dt/ywbb/202609/t20260902_2937434.html',
    summary: '自然资源部发布新一轮找矿突破战略行动最新标志性成果，安徽茶亭铜金矿勘查取得重大突破，为长江中下游成矿带找矿提供新的资源接续。' },
  { cat: '🔍 找矿成果与勘查技术', src: '中国地质调查局', date: '09-02',
    title: '绿色矿业｜六大场景解锁我国绿色勘查新路径',
    url: 'https://www.cgs.gov.cn/ywdt/ddyw/202609/t20260902_867767.html',
    summary: '系统梳理我国绿色勘查在六大典型场景下的技术路径与装备应用，推动勘查全过程减扰动、低排放、可恢复。' },
  { cat: '🔍 找矿成果与勘查技术', src: '中国地质调查局', date: '09-01',
    title: '星-空-地-井协同勘查技术助力冈底斯找矿取得新突破',
    url: 'https://www.cgs.gov.cn/ywdt/dwdt/202609/t20260901_867682.html',
    summary: '通过卫星遥感、航空物探、地面调查与钻探验证四位一体协同，冈底斯成矿带深部找矿取得新进展，验证星-空-地-井一体化勘查技术体系的有效性。' },
  { cat: '🔍 找矿成果与勘查技术', src: '中国地质学会', date: '09-02',
    title: '《中国矿产地质志研编与重大创新》成果通过权威评审',
    url: 'https://www.geosociety.org.cn/?v1=v14&v4=v16&v2=6a967e1769a02&v3=v41',
    summary: '中国矿产地质志研编成果通过权威评审，系统总结全国成矿规律与找矿方向，为新一轮找矿突破战略行动提供基础支撑。' },
  { cat: '🔍 找矿成果与勘查技术', src: '中国地质学会', date: '09-02',
    title: '四川省地质学会战略性矿产资源勘查领域产业科技专家服务团组建',
    url: 'https://www.geosociety.org.cn/?v1=v14&v4=v17&v2=6a866ecaf3741&v3=v41',
    summary: '四川省地质学会组建战略性矿产资源勘查领域产业科技专家服务团，推动产学研协同与找矿技术成果转化。' },
  { cat: '🔍 找矿成果与勘查技术', src: '中国地质学会', date: '09-02',
    title: '专家下沉一线 技术赋能找矿——四川省地质学会产业科技专家服务团在行动',
    url: 'https://www.geosociety.org.cn/?v1=v14&v4=v17&v2=6a9720dc7a7e7&v3=v41',
    summary: '组织专家深入勘查一线开展技术指导，把成矿理论与勘查方法直接应用到找矿生产实践。' },

  // 💼 矿权交易
  { cat: '💼 矿权交易', src: '矿业权市场', date: '08-31',
    title: '湖北省大冶市铜山口外围铜多金属矿勘查网上挂牌出让公告',
    url: 'https://ky.mnr.gov.cn/kyqcrgg/tkq/202609/t20260901_10302816.htm',
    summary: '湖北大冶铜山口外围铜多金属矿勘查探矿权网上挂牌出让，属长江中下游铜铁金成矿带重点接续区。' },
  { cat: '💼 矿权交易', src: '矿业权市场', date: '08-31',
    title: '内蒙古翁牛特旗红石砬子铜多金属勘探探矿权转让公示',
    url: 'https://ky.mnr.gov.cn/zrgs/tkzrgs/202609/t20260901_10302808.htm',
    summary: '内蒙古翁牛特旗红石砬子铜多金属矿勘探探矿权转让公示，涉及大兴安岭中南段有色金属成矿带。' },

  // 🌐 国际矿业动态
  { cat: '🌐 国际矿业动态', src: '全球矿产资源', date: '09-02',
    title: '西澳穆尔金山钨矿成为世界级矿床',
    url: 'https://geoglobal.mnr.gov.cn/zx/kcykf/resources_update/202609/t20260902_10305001.htm',
    summary: '西澳穆尔金山钨矿资源量更新后跻身世界级矿床行列，全球钨资源供应格局或将生变。' },
  { cat: '🌐 国际矿业动态', src: '全球矿产资源', date: '09-01',
    title: '德国有意开发巴西关键矿产',
    url: 'https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202609/t20260901_10303965.htm',
    summary: '德国寻求与巴西在关键矿产领域开展合作开发，以分散供应链集中度、保障工业原料安全。' },
  { cat: '🌐 国际矿业动态', src: '全球矿产资源', date: '09-02',
    title: '印度同赞比亚恢复矿产投资谈判',
    url: 'https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202609/t20260902_10304999.htm',
    summary: '印度与赞比亚重启矿产投资谈判，聚焦铜及关键矿产的联合勘查开发与供应链合作。' },

  // 🏭 行业动态
  { cat: '🏭 行业动态', src: '中国有色金属工业协会', date: '09-01',
    title: '中国恩菲实施的非洲首例井下无人驾驶电机车项目通过验收并进入常态化运行',
    url: 'https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0901/61887.html',
    summary: '非洲首例井下无人驾驶电机车项目通过验收，标志我国智能矿山装备与技术在海外矿山实现常态化应用。' },
  { cat: '🏭 行业动态', src: '中国有色金属工业协会', date: '09-01',
    title: '上半年铜陵有色净利润同比翻倍',
    url: 'https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0901/61881.html',
    summary: '铜陵有色上半年经营业绩大幅增长，净利润同比翻倍，反映铜冶炼与加工环节盈利显著修复。' },
  { cat: '🏭 行业动态', src: '中国有色金属工业协会', date: '09-01',
    title: '陕西黄金集团西安秦金项目获陕西省科技厅立项',
    url: 'https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0901/61891.html',
    summary: '陕西黄金集团西安秦金项目获省级科技立项，聚焦黄金资源综合利用与绿色冶炼技术攻关。' },
  { cat: '🏭 行业动态', src: '中国有色网', date: '09-02',
    title: '一座钼矿何以在林海深处绘就“共生图景”',
    url: 'https://www.cnmn.com.cn/ShowNews1.aspx?id=473665',
    summary: '报道一座位于林区的钼矿如何在开发过程中统筹生态保护与资源利用，探索绿色矿山与生态修复协同路径。' },
  { cat: '🏭 行业动态', src: '中国有色网', date: '09-02',
    title: '英国加码投资关键矿产本土供应链建设',
    url: 'https://www.cnmn.com.cn/ShowNews1.aspx?id=473653',
    summary: '英国加大对关键矿产本土供应链的投资力度，旨在降低对外依赖、提升战略性矿产保障能力。' },
  { cat: '🏭 行业动态', src: '中国有色网', date: '09-02',
    title: '7月份锂行业运行情况',
    url: 'https://www.cnmn.com.cn/ShowNews1.aspx?id=473599',
    summary: '发布7月份锂行业运行数据，涉及碳酸锂产量、库存与消费情况，反映锂产业链供需边际变化。' },
  { cat: '🏭 行业动态', src: '中国黄金协会', date: '09-02',
    title: '2026年上半年我国黄金产量152.908吨，同比下降14.62%，黄金消费量511.412吨，同比增长1.23%',
    url: 'https://www.cngold.org.cn/news/show-9500.html',
    summary: '上半年国内黄金产量同比下降14.62%至152.908吨，黄金消费量511.412吨、同比增长1.23%，产消缺口进一步扩大。' },
  { cat: '🏭 行业动态', src: '中国黄金协会', date: '09-02',
    title: '中国黄金集团与中国地质大学（武汉）举行工作会商',
    url: 'https://www.cngold.org.cn/news/show-9503.html',
    summary: '校企双方围绕科技创新、人才培养与地质勘查成果转化开展会商，推动产学研深度融合。' },
  { cat: '🏭 行业动态', src: '中国黄金协会', date: '09-02',
    title: '持续增厚股东回报 紫金矿业公布111亿元中期分红方案',
    url: 'https://www.cngold.org.cn/news/show-9505.html',
    summary: '紫金矿业公布111亿元中期分红方案，在铜金价格高位背景下持续提升股东回报。' }
];

/* ---------- 价格数据（2026-09-02 抓取） ---------- */
const RATE = 6.7371;                       // USD/CNY
const liUsd = 23229.58, liChg = -523.04;   // 电池级碳酸锂 USD/吨
const coUsd = 45271.70, coChg = -6.72;     // 电解钴 USD/吨
const liCny = Math.round(liUsd * RATE);
const coCny = Math.round(coUsd * RATE);
const liPct = (liChg / (liUsd - liChg) * 100).toFixed(2);
const coPct = (coChg / (coUsd - coChg) * 100).toFixed(2);

// [名称, 标签, 值, 单位, 涨跌文本, 方向 up/down/'']
const PRICES = [
  ['沪铜',  'SHFE',     '108,050', '元/吨', '▼ -1,470 (-1.34%)', 'down'],
  ['沪铝',  'SHFE',     '24,075',  '元/吨', '▲ +5 (+0.02%)',     'up'],
  ['沪铅',  'SHFE',     '16,155',  '元/吨', '▲ +20 (+0.12%)',    'up'],
  ['沪锌',  'SHFE',     '26,580',  '元/吨', '▼ -400 (-1.48%)',   'down'],
  ['沪锡',  'SHFE',     '413,290', '元/吨', '▼ -10,110 (-2.39%)','down'],
  ['沪镍',  'SHFE',     '126,800', '元/吨', '▼ -960 (-0.75%)',   'down'],
  ['上海金','早盘价',   '931.36',  '元/克', '早盘 931.36',       ''],
  ['白银',  'Ag(T+D)',  '15,836',  '元/千克','今开 15,836',      ''],
  ['碳酸锂','电池级',   liCny.toLocaleString('en-US'), '元/吨（SMM折）',
                        '▼ ' + liChg.toFixed(0) + ' (' + liPct + '%)', 'down'],
  ['电解钴','SMM',      coCny.toLocaleString('en-US'), '元/吨（SMM折）',
                        (coChg < 0 ? '▼ ' : '▲ ') + Math.abs(coChg).toFixed(0) + ' (' + coPct + '%)',
                        Number(coPct) < 0 ? 'down' : (Number(coPct) > 0 ? 'up' : '')]
];

/* ---------- 工具：栈式提取 token ---------- */
function tokenize(seg) {
  const tokens = [];
  let i = 0;
  while (i < seg.length) {
    const a = seg.indexOf('<div class="news-item', i);
    const b = seg.indexOf('<div class="sub-cat"', i);
    if (a < 0 && b < 0) break;
    if (b >= 0 && (a < 0 || b < a)) {
      const e = seg.indexOf('</div>', b);
      tokens.push({ type: 'cat', text: seg.slice(b, e + 6) });
      i = e + 6; continue;
    }
    let depth = 0, j = a, re = /<div\b|<\/div>/g, m;
    re.lastIndex = a;
    while ((m = re.exec(seg))) {
      if (m[0] === '<div') depth++;
      else { depth--; if (depth === 0) { j = m.index + 6; break; } }
    }
    tokens.push({ type: 'item', text: seg.slice(a, j) });
    i = j;
  }
  return tokens;
}
const catLabel = t => t.replace(/<[^>]*>/g, '').replace(/\d+条(新增)?$/, '').trim();
const itemDate = t => (t.match(/ · ([0-9]{2}-[0-9]{2})/) || [])[1] || '';

/* ---------- 主流程 ---------- */
let h = fs.readFileSync(FILE, 'utf8');
const origLen = h.length;

// 1. 标题日期
h = h.replace(/<title>[^<]*<\/title>/, '<title>矿业新闻日报 ' + REPORT_DATE + '</title>');

// 2. priceStripNote
h = h.replace(/(<span class="price-strip-note" id="priceStripNote">)[^<]*(<\/span>)/,
  '$1' + REPORT_DATE + ' 更新 · 第一行 沪期主力/SMM·上金所（人民币） · 第二行 LME 美元/吨 · 涨红跌绿' + '$2');

// 3. SHFE 价格卡片整块重建
const shfeHtml = '<div class="price-cards" id="priceCardsShfe">' +
  PRICES.map(p => '<div class="price-card ' + p[5] + '"><div class="pc-name">' + p[0] +
    ' <span class="pc-tag">' + p[1] + '</span></div><div class="pc-value">' + p[2] +
    '</div><div class="pc-unit">' + p[3] + '</div><div class="pc-chg">' + p[4] + '</div></div>').join('') +
  '</div>';
const shfeStart = h.indexOf('<div class="price-cards" id="priceCardsShfe">');
const shfeEnd = h.indexOf('<div class="price-cards" id="priceCardsLme"');
if (shfeStart < 0 || shfeEnd < 0) throw new Error('未找到 priceCardsShfe / priceCardsLme');
h = h.slice(0, shfeStart) + shfeHtml + h.slice(shfeEnd);

// 4. 重建 今日新增 + 往期内容
const ti = h.indexOf('id="todaySection"');
const ai = h.indexOf('id="archiveSection"');
const fi = h.indexOf('id="archivedFavSection"');
if (ti < 0 || ai < 0 || fi < 0) throw new Error('未定位到 today/archive/archivedFav 区块');

// 4a. 旧往期条目（>= KEEP_FROM）按原分组保留
const archTokens = tokenize(h.slice(ai, fi));
const groups = [];
let cur = null;
archTokens.forEach(t => {
  if (t.type === 'cat') { cur = { label: catLabel(t.text), items: [] }; groups.push(cur); }
  else if (cur && itemDate(t.text) >= KEEP_FROM) { cur.items.push(t.text); }
});
const archGroups = groups.filter(g => g.items.length > 0);
const archTotal = archGroups.reduce((n, g) => n + g.items.length, 0);

// 4b. 今日新增分组
const todayCats = [];
NEW_ITEMS.forEach(it => {
  let g = todayCats.find(x => x.label === it.cat);
  if (!g) { g = { label: it.cat, items: [] }; todayCats.push(g); }
  g.items.push(it);
});
const itemHtml = it =>
  '<div class="news-item is-new" data-url="' + it.url + '" data-embed="ok"><div class="news-head"><span class="dot"></span><span class="badge-new">NEW</span><a class="news-title" href="' +
  it.url + '" target="_blank">' + it.title + '</a></div><div class="news-meta"><span class="src">' + it.src +
  '</span> · ' + it.date + '</div><div class="news-summary">' + it.summary +
  '</div><a class="btn-read" href="' + it.url + '" target="_blank">查看原文 →</a></div>';

const subCatHtml = (label, n, isNew) =>
  '<div class="sub-cat">' + label + '<span class="sub-count">' + n + '条' + (isNew ? '新增' : '') + '</span></div>\n';

let todayBlock = '<div class="section-title today"><span class="icon">🔥</span> 今日新增（' + REPORT_DATE +
  ' 抓取）<span class="news-count" id="todayCount">' + NEW_ITEMS.length + '条</span></div>\n';
todayCats.forEach(g => {
  todayBlock += subCatHtml(g.label, g.items.length, true);
  todayBlock += g.items.map(itemHtml).join('\n') + '\n';
});

let archBlock = '<div class="section-title"><span class="icon">📰</span> 往期内容（滚动保留最近7天）<span class="news-count" id="archiveCount">' +
  archTotal + '条</span></div>\n' +
  '<div class="fold-toggle" id="foldToggle" style="display:none" onclick="toggleOldFold()">▸ 展开更早内容</div>\n';
archGroups.forEach(g => {
  archBlock += subCatHtml(g.label, g.items.length, false);
  archBlock += g.items.join('\n') + '\n';
});

// 4c. 定位替换区间：todaySection 起始 → installGuideSection 之前的注释起始
//     【关键】终点必须是安装指引区，不能用 archivedFavSection，否则会把 installGuideSection 整段删掉
const segStart = h.lastIndexOf('<div class="section"', ti);
const segEnd = h.indexOf('<!-- ==================== 详细安装指引');
if (segStart < 0 || segEnd < 0 || segEnd <= segStart) throw new Error('替换区间定位失败');
const SEP = '\n<!-- ==================== 往期内容 ==================== -->\n';
// 整块重建：今日新增 + 分隔注释 + 往期内容
const finalSeg =
  '<div class="section" id="todaySection">\n' + todayBlock + '</div>\n' + SEP +
  '<div class="section" id="archiveSection">\n' + archBlock + '</div>\n';

h = h.slice(0, segStart) + finalSeg + h.slice(segEnd);

// 5. 结构完整性校验（防止整段误删）
//    含 v9 静态关键元素：若未来重建误吞 sticky-bar/设置面板/移动底栏/FAB/矿种云，立即报错而非静默损坏
//    注意：heroCard/src-avatar/rel-time/cat-* 由 JS 运行时注入，静态 HTML 无，不能列入（会误报）
const MUST = ['specialSection', 'qaAiBtn', 'priceCardsShfe', 'priceCardsLme', 'lme-data.js',
  'installGuideSection', 'archivedFavSection', 'guide-cols', '安卓 Chrome', 'Safari', 'guide-tip',
  'installTip', 'fold-toggle', '版权与免责声明', '1642988981@qq.com',
  'stickyBar', 'sbRefresh', 'sbDark', 'settingPop', 'mobBar', 'fabTop', 'mineralCloud', 'readProgress',
  'qaChatMsgs', 'qaChips',   // ① 多轮记忆 Chat UI 持久元素（位于 qaAiBox，在重建区间外）
  'alertMonitor', 'sbAlert',  // ③ 关键矿种异动监控面板（价格栏与问答条之间，重建区间外）
  'secSignal', 'secAdvisor',  // ② 三层级结构标签：信号中心 / AI 参谋
  'sentimentMonitor', 'signalsMonitor', 'knowledgeMonitor', 'morningReport',  // ④ AI 扩展四面板（信号中心 + AI参谋）
  'sentIdx', 'sentCommodities', 'sentThemes', 'sigList', 'knoList', 'morningBody',  // ④ 四面板内部渲染容器
  'morningRefresh', 'morningExport',  // ④ 晨报重生成/导出按钮
  // ⑥（2026-09-02）用户临时关闭情绪/知识后保留入口；价格研判信号点开 → /api/price-history 7 日 sparkline
  'sigSpark-', 'SIG_NAME_TO_SLUG', 'loadSigSpark', 'api/price-history'];
const lost = MUST.filter(k => h.indexOf(k) < 0);
if (lost.length) { console.error('❌ 结构校验失败，丢失：' + lost.join(', ')); process.exit(1); }
console.log('✅ 结构校验通过（' + MUST.length + ' 项关键元素齐全）');

// 5b. div 标签平衡校验（今日新增/往期两个 section 必须各自闭合）
const dOpen = (h.match(/<div\b/g) || []).length, dClose = (h.match(/<\/div>/g) || []).length;
if (dOpen !== dClose) {
  console.error('❌ div 不平衡：open ' + dOpen + ' / close ' + dClose); process.exit(1);
}
console.log('✅ div 平衡（' + dOpen + ' 对）');

fs.writeFileSync(FILE, h, 'utf8');

console.log('原始字节 ' + origLen + ' → ' + h.length);
console.log('今日新增 ' + NEW_ITEMS.length + ' 条（' + todayCats.map(g => g.label + ':' + g.items.length).join(' / ') + '）');
console.log('往期保留 ' + archTotal + ' 条（丢弃 ' + (archTokens.filter(t => t.type === 'item' && itemDate(t.text) && itemDate(t.text) < KEEP_FROM).length) + ' 条超期）');
console.log('往期分组：' + archGroups.map(g => g.label + ':' + g.items.length).join(' / '));
console.log('价格：碳酸锂 ' + liCny + ' 元/吨(' + liPct + '%) 电解钴 ' + coCny + ' 元/吨(' + coPct + '%)');
