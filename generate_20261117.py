# -*- coding: utf-8 -*-
"""
生成 2026-11-17 矿业资讯速览 index.html（周二）
- 11-16 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-10-16）回补历史条目
- 换入 11-17 采集的 11-15 至 11-17 条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 与 LME 均为 11-16 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；
  电解钴保留上日 SMM 值并标注
- 矿权条目：今日新增公告走 #rightsCards 既有窗口，不进主列表
- 保留：会展 IIFE / 搜索 / CSV / PDF / 防横跳 / 内联自愈引信 / 价格三视图
- 境外条目保留英文原题（data-orig-title + 摘要末尾「原题：…」）
"""

import re, datetime, json, glob, os
import sys
from source_whitelist import is_allowed
from generate_common import (
    ni, card, _replace_block, split_items, item_url, strip_new, _esc, render_cat_groups,
    UP, DOWN, FLAT, TAG_TODAY, TAG_ARCH, TAG_RIGHTS,
    CAT_KQ, CAT_ZK, CAT_HY, CAT_GJ, CAT_MA, CAT_ZC, CAT_SC, MA_REQUIRE, window,
    THEME_BUCKET, LEGACY_BUCKET, bucket,
    item_after_cutoff as _item_after_cutoff,
    _lib_item as _lib_item_raw,
    _reclassify_ma as _reclassify_ma_raw,
    dedup_same_event, item_title, same_event,
    unit_class, UNIT_SHFE_GROUP, UNIT_LME_GROUP,
)
from functools import partial


SITE_NAME = '矿业资讯速览'   # 站点名（浏览器标签页标题）——约定见 REFERENCE.md §39
SRC = 'index.html'
with open(SRC, encoding='utf-8') as f:
    html = f.read()
_ORIG_SIZE = len(html)

REPORT = '2026-11-17'
GRAB = '2026-11-17'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年11月\d{2}日 星期.',
                         r'\g<1>2026年11月17日 星期二', html)
assert _n_badge == 1, 'date-badge 替换次数异常: %d' % _n_badge
now = datetime.datetime.now().strftime('%H:%M')
html = re.sub(r'今日新增（2026-\d{2}-\d{2} 抓取）', '今日新增（%s 抓取）' % GRAB, html)
html = re.sub(r'id="priceStripNote"[^>]*>2026-\d{2}-\d{2} 更新',
              'id="priceStripNote">%s 更新' % REPORT, html)
html = re.sub(r'name="build-version" content="\d{8}-\d{4}"',
              'name="build-version" content="%s-%s"' % (REPORT.replace('-', ''), now.replace(':', '')), html)

# ============ 2. 价格卡刷新（全部现算，禁止手抄） ============
_ph = json.load(open('price_history_detail.json', encoding='utf-8'))['series']

SHFE_DEFS = [
    ('cum', '沪铜', 'SHFE', '元/吨', 0),
    ('alm', '沪铝', 'SHFE', '元/吨', 0),
    ('pbm', '沪铅', 'SHFE', '元/吨', 0),
    ('znm', '沪锌', 'SHFE', '元/吨', 0),
    ('snm', '沪锡', 'SHFE', '元/吨', 0),
    ('nim', '沪镍', 'SHFE', '元/吨', 0),
    ('au9999', '上海金', 'Au99.99', '元/克', 2),
    ('agtd', '白银', 'Ag(T+D)', '元/千克', 0),
    ('lcm', '碳酸锂', '主力连续', '元/吨', 0),
]
shfe_cards = []
for slug, name, tag, unit, nd in SHFE_DEFS:
    pts = _ph[slug]['points']
    prev, cur = pts[-2][1], pts[-1][1]
    chg = cur - prev
    pct = chg / prev * 100.0 if prev else 0.0
    val = format(cur, ',.%df' % nd)
    arrow = UP if chg >= 0 else DOWN
    sign = '+' if chg >= 0 else ''
    chgtxt = '%s %s%s (%s%.2f%%)' % (arrow, sign, format(chg, ',.%df' % nd), sign, pct)
    shfe_cards.append(card(slug, name, tag, val, unit, chgtxt, 'up' if chg >= 0 else 'down',
                           group_unit=UNIT_SHFE_GROUP))
shfe_html = ''.join(shfe_cards)
# 电解钴：无当日源，保留上日 SMM 值并标注
shfe_html += ('<div class="price-card "><div class="pc-name">电解钴 <span class="pc-tag">SMM %s</span></div>'
              '<div class="pc-value">304,940</div><div class="%s">元/吨</div>'
              '<div class="pc-chg">上日 304,940（SMM 未更新）</div></div>'
              % (DATA_ASOF, unit_class('元/吨', UNIT_SHFE_GROUP)))

_lme = json.load(open('lme_data.json', encoding='utf-8'))['metals']
_lme_map = {m['slug']: m for m in _lme}
LME_DEFS = [
    ('lcpt', 'LME 铜'), ('lalt', 'LME 铝'), ('lznt', 'LME 锌'),
    ('lldt', 'LME 铅'), ('lnkt', 'LME 镍'), ('ltnt', 'LME 锡'),
]
lme_list = []
for slug, name in LME_DEFS:
    m = _lme_map[slug]
    if m['price'] is None:
        lme_list.append((slug, name, 'LME', '--', '美元/吨', '暂无数据', 'flat'))
        continue
    arrow = UP if m['chg'] >= 0 else DOWN
    val = format(m['price'], ',.2f')
    sign = '+' if m['chg'] >= 0 else ''
    chg = '%s %s (%s%.2f%%)' % (arrow, sign + format(m['chg'], ',.2f'), sign, m['chg_pct'])
    lme_list.append((slug, name, 'LME', val, '美元/吨', chg, 'up' if m['chg'] >= 0 else 'down'))
lme_html = ''.join(card(*c, group_unit=UNIT_LME_GROUP) for c in lme_list)

html = _replace_block(html, '<div class="price-cards" id="priceCardsShfe">', shfe_html)
html = _replace_block(html, '<div class="price-cards price-cards-lme" id="priceCardsLme">', lme_html)

# ============ 3. 解析今日/往期两个区 ============
i_t = html.find(TAG_TODAY)
i_a = html.find(TAG_ARCH)
i_r = html.find(TAG_RIGHTS)
assert 0 <= i_t < i_a < i_r, 'markers not found'

m_today = html.find('<!-- ==================== 今日新增')
assert m_today != -1, '今日新增 marker missing'

today_raw = html[i_t:i_a]
arch_raw = html[i_a:i_r]

today_items = split_items(today_raw)
arch_items = split_items(arch_raw)

prev_today = [(cat, strip_new(it)) for cat, it in today_items if '<div class="news-item' in it and cat != CAT_KQ]
arch_keep = [(cat, strip_new(it)) for cat, it in arch_items
             if '<div class="news-item' in it and cat != CAT_KQ and item_after_cutoff(it)]

# ── URL → (内容类, 地域) 索引：让存量条目也能按新分类体系重新分桶 ──
_url_theme = {}
for _fn in sorted(glob.glob('data/news_????-??.json')):
    try:
        _lib = json.load(open(_fn, encoding='utf-8'))['news']
    except Exception:
        continue
    for _e in _lib:
        _u = _e.get('url', '')
        if _u and _e.get('region'):
            _url_theme[_u] = (_e.get('category', ''), _e.get('region', ''))


def _reclassify_by_url(cat, it):
    """用月库里的 LLM 分类结果覆盖旧桶名。查不到则原样返回。"""
    th_rg = _url_theme.get(item_url(it))
    return bucket(th_rg[0], th_rg[1]) if th_rg else cat


merge_seq = []
seen_url = set()
for cat, it in prev_today + arch_keep:
    url = item_url(it)
    if url in seen_url:
        continue
    seen_url.add(url)
    merge_seq.append((_reclassify_by_url(cat, it), it))

# 2026-10-29 一次性清理：chinania.org.cn 源已禁用且死链已从月库/前端库清除，
# 但现有 index.html 往期区仍残留其卡片（arch_keep 继承自旧 html），
# 此处统一剔除，确保重生成的 index.html 不再渲染该死链。
merge_seq = [(c, it) for c, it in merge_seq if 'chinania.org.cn' not in it]

merge_seq = dedup_same_event(merge_seq)

# ============ 3.5 从累计库回补 30 天窗口 ============
CAT_MAP = dict(LEGACY_BUCKET)
CAT_MAP.update(THEME_BUCKET)
LIB_SKIP = {'矿权交易', '并购与投资'}
_lib_item = partial(_lib_item_raw, cat_map=CAT_MAP)

_lib_pool = []
for _fn in sorted(glob.glob('data/news_????-??.json')):
    try:
        _lib = json.load(open(_fn, encoding='utf-8'))['news']
    except Exception:
        continue
    for _e in _lib:
        if _e.get('category') in LIB_SKIP:
            continue
        _odf = _e.get('orig_date_full', '') or ''
        if _odf < CUTOFF_DT.isoformat():
            continue
        _url = _e.get('url', '')
        if not _url or _url in seen_url:
            continue
        _it = _lib_item(_e)
        if not _it:
            continue
        _lib_pool.append((_odf, _url, _it))
_lib_pool.sort(key=lambda t: t[0], reverse=True)
for _odf, _url, _it in _lib_pool:
    seen_url.add(_url)
    merge_seq.append(_it)
print('library backfill added:', len(_lib_pool))

new_items = [
    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202611/7ff88cd147dc43dba58687ff7c70bcdd.html',
                '长江有色网', '11-17',
                'LME 金属期货全线下跌，伦铜领跌收于近五个月低位',
                '周一晚间 LME 金属期货全线下跌，伦铜领跌并收于近五个月低位。市场将本轮下跌归因于美联储加息预期升温与人工智能投资热潮降温，基本金属整体承压、库存与需求预期同步转弱。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202611/9c86e7f3e26a4b499f8e84f7b9a76342.html',
                '长江有色网', '11-16',
                '沪银大跌 6.42%，金银价格双双创年内低点',
                '11 月 16 日国内贵金属板块全线下行：沪金跌 1.18% 报 828.28 元/克，沪银跌 6.42%，广期所铂、钯分别收跌 3.1% 和 1.78%。通胀粘性叠加美联储鹰派表态压制降息预期，金银双双创出年内新低，避险买盘持续退场，贵金属整体承压。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202611/76ecad4784e943809a6fc407ab0c462a.html',
                '长江有色网', '11-16',
                '碳酸锂主力收跌 3.65%，电池级现货均价降至 9 万元/吨',
                '11 月 16 日长江综合电池级碳酸锂（99.5%）均价 90,000 元/吨、工业级（99.2%）均价 87,000 元/吨，均较上一交易日下跌 2,500 元/吨；碳酸锂主力合约收跌 3.65% 报 88,240 元/吨，期现联动走弱。供给结构分化、去库承接力度持续衰减，市场观望情绪升温。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202611/5a33df391a09466db454fb56a1814cc3.html',
                '长江有色网', '11-16',
                '工业硅开工持续回落，西南枯水期减产逐步落地',
                '11 月 16 日长江现货 441# 硅均价 9,900 元/吨、553# 硅均价 9,600 元/吨，两个主流牌号均与上一交易日持平；工业硅主力 2612 合约收涨 0.29%，期现走势分化。西南地区进入枯水期，硅厂减产落地、开工率持续回落，供需博弈加剧。')),

    (CAT_SC, ni('https://www.mining.com/web/goldman-forecasts-gold-price-to-take-two-years-to-recapture-all-time-highs/',
                'MINING.COM', '11-16',
                '高盛：金价收复历史高点或需两年，2028 年底看 5,600 美元/盎司',
                '高盛策略师在 11 月 16 日报告中称，美联储持续收紧将使金价短期继续承压、波动加大；一旦转向降息、西方 ETF 需求恢复，预计到 2028 年底金价升至每盎司 5,600 美元，2027 年底看 4,650 美元。金价 1 月末曾创近 5,600 美元历史高点，今年以来累计下跌近 11%，11 月 16 日交投于约 3,860 美元。',
                orig_title='Goldman forecasts gold price to take two years to recapture all-time highs')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202611/t20261113_2942463.html',
                '自然资源部', '11-13',
                '王登红：锂成矿多时代多旋回，找矿视野不应被旧框架束缚',
                '中国地质科学院矿产资源研究所研究员王登红在自然资源部访谈中表示，锂矿分卤水型与伟晶岩硬岩型两大类，我国卤水型资源体量最大；西昆仑—松潘—甘孜「亚洲锂腰带」长 2,800 余千米，集中了一批超大型伟晶岩锂矿床。他指出锂成矿多时代、多旋回，云英岩型、花岗岩型、沉积黏土型等非常规资源正进入视野；当前优先开发高品位盐湖卤水与优质锂辉石矿床，低品位花岗岩型、黏土型及深部隐伏矿体宜作战略储备。')),

    (CAT_ZC, ni('http://gi.mnr.gov.cn/202611/t20261113_2942491.html',
                '自然资源部', '11-13',
                '四部门公布新一批国家级绿色矿山名单，296 家矿山入选',
                '自然资源部、生态环境部、国家金融监督管理总局、国家林业和草原局联合发布 2026 年第 31 号公告，公布新一批国家级绿色矿山名单。按照自然资办发〔2025〕8 号文要求，经省级推荐、审核论证、抽查核实、社会公示等程序，共 296 家矿山通过遴选并纳入国家级绿色矿山名录，接受社会监督。公告成文日期为 2026 年 11 月 10 日。')),

    # ── 🔍 找矿成果与勘查技术 ───────────────────────────────────
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202611/t20261116_10364773.htm',
                '全球矿产资源信息系统', '11-16',
                '南澳霍普斯山金矿深部见矿 34.9 米、金品位 2.3 克/吨',
                '金马金属（Golden Horse Metals）宣布，南澳州南克鲁斯地区霍普斯山项目钻孔在 398.7 米深处见矿 34.9 米、金品位 2.3 克/吨，见矿垂直深度 300 米，为该矿迄今最深见矿，矿体真厚度估计为见矿厚度的 40% 至 80%。项目勘探目标 200 万盎司，预计明年首次估算资源量；加通贝祥估计首个资源量可达 100 万盎司、时间或在 2027 年初。')),

    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsyj/202611/t20261116_10364774.htm',
                '全球矿产资源信息系统', '11-16',
                '澳洲矿业公司更名第一钪业，重启昆士兰斯科尼镍钴项目',
                '正在更名为第一钪业（First Scandium）的澳洲矿业公司（Australian Mines）宣布聚焦关键金属，已重启停滞近 10 年的昆士兰州斯科尼镍钴项目。其新南威尔士州弗莱明顿项目有望成为该州第二个钪矿，公司同时在重新评估此前搁置的昆士兰州钪矿；斯科尼项目拉克诺探区从地表见矿 27 米、钪品位 0.0883%。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.smm.cn/news/XNPWAJDU4ADYTIUW7FFX25YD23VHRNG7MKKP4JA',
                '上海有色网', '11-16',
                '天齐锂业年产 1,000 吨电池级金属锂工厂在重庆竣工',
                '11 月 12 日，天齐锂业年产 1,000 吨高能锂电材料电池级金属锂项目竣工仪式在重庆铜梁举行，为全国首个全自动电池级金属锂工厂。项目投产后，天齐锂业重庆金属锂总产能将提升至 1,600 吨/年。项目研发出行业首台首套单槽产能最大的高效节能锂金属电解设备，在蒸馏、铸锭、整形包装等后段处理环节均有创新。')),

    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-11-16/1225673315.PDF',
                '巨潮资讯网', '11-16',
                '康普化学铜萃取剂产线控产结束，合成环节产量恢复至控产前水平',
                '重庆康普化学（920033）公告，公司铜萃取剂产线合成环节产量已逐步恢复至控产前水平，本次控产计划实施完毕。公司 2025 年 6 月因存货库存趋于饱和，对铜萃取剂产线实施阶段性控产，合成环节月均产量控制在原月均产量的 20% 以内；2026 年 3 月恢复至 50% 左右。公司称前期控产有效降低了半成品库存水平，后续将跟踪市场变化灵活调控产能。',
                embed='pdf')),

    (CAT_HY, ni('https://geoglobal.mnr.gov.cn/zx/kydt/hyyxdt/202611/t20261116_10364771.htm',
                '全球矿产资源信息系统', '11-16',
                '第三季度南非采矿业环比下降 6%，铂族金属拖累最大',
                '南非国家统计局数据显示，9 月该国采矿业同比下降 10.7%、矿产品销售同比下降 4.1%；铁矿石下降 23.7%、煤下降 13.4%、铂族金属下降 9.9%、金刚石下降 63.1%。经季节调整后 9 月采矿业生产环比增长 2.8%，但第三季度整体较第二季度下降 6%，其中铂族金属下降 12.5%、拖累 3.5 个百分点。')),

    (CAT_HY, ni('https://www.mining.com/chinas-rare-earth-giants-double-profits-as-prices-soar/',
                'MINING.COM', '11-16',
                '中国两大稀土企业前三季净利翻倍，氧化镨钕价格涨 62%',
                '北方稀土前三季度净利润 36.5 亿元（约 5.472 亿美元），专注重稀土的中国稀土资源与技术公司净利润 4.08 亿元（约 6,110 万美元）、同比增逾一倍。供给管控收紧推动价格上行，氧化镨钕价格较管控措施推出时上涨 62% 至 71.9 万元/吨；两家公司是 2024 年中国仅有的配额持有者，全年业绩预计将超出分析师预期。',
                orig_title="China's rare earth giants double profits as prices soar")),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475357',
                '中国有色金属报', '11-15',
                '敖宏会见智利铜与矿业研究中心和自由港相关负责人',
                '11 月 12 日至 13 日，中国有色金属工业协会党委书记敖宏在协会本部分别会见智利铜与矿业研究中心主席克里斯蒂安·昆齐奥和自由港-麦克默伦公司高级副总裁哈维尔·塔格。双方围绕全球铜市场供需形势、铜产业绿色低碳转型、国际矿业合作等议题交流，并就依托「亚洲铜业周」平台深化数据共享、联合研究和高层对话机制达成共识。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/rio-pledges-250m-to-address-panguna-damage/',
                'MINING.COM', '11-16',
                '力拓承诺 2.5 亿美元治理潘古纳铜金矿遗留问题',
                '力拓宣布出资 2.5 亿美元（3.56 亿加元），与布干维尔铜业、布干维尔自治区政府及社区领袖共同设立基金，用于应对已停产的潘古纳铜金矿造成的环境与人权影响，资金将在未来数年内分期支付。该矿 1972 年投产、1989 年因内战停产，力拓 2016 年将所持股份无偿转给布干维尔与巴新政府；2024 年独立调查提出 24 项建议。',
                orig_title='Rio pledges $250 million to address Panguna damage')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202611/t20261116_10364772.htm',
                '全球矿产资源信息系统', '11-16',
                '亚美尼亚加大吸引矿业外资力度，矿业论坛吸引近 400 名国际代表',
                '亚美尼亚在 2026 年 10 月 16 日至 17 日举办的第三届亚美尼亚矿业论坛上表示，将加大吸引国际矿业投资，以把握全球矿产需求增长机遇，同时解决监管、地质勘查与公众信任方面的长期问题。总理帕希尼扬、副总理格里戈良及国土部部长等出席，近 400 位国际矿企高管、投资者、专家与政府官员参会；副总理称目标不仅是提高产量，而是实现高质量发展。')),

    (CAT_GJ, ni('https://www.mining.com/web/korea-zinc-cuts-recycling-deal-to-feed-7-4-billion-us-smelter/',
                'MINING.COM', '11-16',
                '韩国锌业合并美国回收业务组建 Jupiter，为 74 亿美元田纳西冶炼厂供料',
                '韩国锌业将把美国回收子公司 PedalPoint Recycling 与 Solarcycle 合并组建 Jupiter，从退役信息技术与能源基础设施中回收金属，供其计划投资 74 亿美元的田纳西州克拉克斯维尔冶炼综合体使用。韩国锌业持股 70%、Solarcycle 持股 30%；Jupiter 初期在美国运营 8 座回收厂、约 250 名员工，冶炼厂获美国政府支持、计划 2029 年投产，可精炼锌、铜、金、银及锑、锗等金属。',
                orig_title='Korea Zinc cuts recycling deal to feed $7.4 billion US smelter')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://news.smm.cn/news/C2QFNXQVIU2CLJVQTYQAUQYWCQGRX76B6ZB7BDI',
                '上海有色网', '11-16',
                '新宙邦与亿纬锂能签 60 万吨电解液长单，期限 2026—2030 年',
                '新宙邦（300037）11 月 13 日晚公告，与亿纬锂能（300014）签订《长期供货协议》，2026 年至 2030 年预计供应电解液 60 万吨，实际订单规模可在预计需求量基础上上下浮动 10%；亿纬锂能将在协议生效后 30 个工作日内支付预付款，专项用于锁定上游核心原材料产能。此前 11 月 5 日，天赐材料子公司九江天赐亦与亿纬锂能签订 45 万吨电解液长单，期限 2027 年至 2029 年。')),

    # ── 💼 矿权交易（今日公告 9 宗）─────────────────────────────
    (CAT_KQ, ni('https://ky.mnr.gov.cn/kyqcrgg/tkq/202611/t20261117_10364804.htm',
                '矿业权市场', '11-16',
                '新疆和静哈尔干金多金属矿探矿权挂牌，面积 26.9464 平方千米',
                '新疆维吾尔自治区自然资源厅委托自治区公共资源交易中心，以挂牌方式出让和静县哈尔干金多金属矿勘查等 5 个探矿权。其中哈尔干宗勘查矿种为金矿，面积 26.9464 平方千米，起始价 403.5 万元、出让收益率 2.3%，挂牌时间为 2026 年 12 月 28 日至 2027 年 1 月 12 日，按价高者得原则确定竞得人。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/kyqcrgg/tkq/202611/t20261117_10364809.htm',
                '矿业权市场', '11-16',
                '新疆伽师肖尔库勒东铜多金属矿探矿权挂牌，起始价 185.28 万元',
                '新疆伽师县肖尔库勒东铜多金属矿勘查探矿权挂牌出让，勘查矿种为铜矿，面积 30.8952 平方千米，起始价 185.28 万元、出让收益率 1.2%，挂牌时间为 2026 年 12 月 28 日至 2027 年 1 月 12 日。该宗为自治区自然资源厅本批 5 个探矿权之一。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/kyqcrgg/tkq/202611/t20261117_10364807.htm',
                '矿业权市场', '11-16',
                '新疆乌恰阿克然铜矿探矿权挂牌，面积 60.8731 平方千米',
                '新疆乌恰县阿克然铜矿勘查探矿权挂牌出让，勘查矿种为铜矿，面积 60.8731 平方千米，起始价 304.05 万元、出让收益率 1.2%，挂牌时间为 2026 年 12 月 28 日至 2027 年 1 月 12 日。该宗为自治区自然资源厅本批 5 个探矿权之一。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/jggs/jjgs/202611/t20261117_10364793.htm',
                '矿业权市场', '11-16',
                '湖南株洲长垅矿区金矿普查探矿权 4,050 万元成交',
                '湖南省公共资源交易中心公示，株洲市芦淞区长垅矿区金矿普查探矿权于 2026 年 11 月 4 日网上挂牌成交，竞得人为湖南禹晶固体矿产地质勘查有限公司。该探矿权勘查矿种为金矿，面积 8.0607 平方千米，起始价 50 万元、出让收益率 2.3%，成交价 4,050 万元，公示文号湘资矿公示〔2026〕14 号。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/jggs/jjgs/202611/t20261117_10364795.htm',
                '矿业权市场', '11-16',
                '湖南平江八里铅锌铌钽矿普查探矿权 2,320 万元成交',
                '湖南省平江县八里矿区铅锌铌钽矿普查探矿权于 2026 年 11 月 4 日挂牌成交，竞得人为湖南宸鑫矿业有限公司。该探矿权勘查矿种为铅、锌、铌、钽，面积 15.3333 平方千米，起始价 100 万元、出让收益率 2.3%，成交价 2,320 万元，公示文号湘资矿公示〔2026〕17 号。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/jggs/jjgs/202611/t20261117_10364791.htm',
                '矿业权市场', '11-16',
                '湖南炎陵荣塘脉石英矿普查探矿权 110 万元成交',
                '湖南省炎陵县荣塘矿区脉石英矿普查探矿权于 2026 年 11 月 4 日挂牌成交，竞得人为炎陵县瀚铄矿业有限公司。该探矿权勘查矿种为脉石英，面积 0.6011 平方千米，起始价 10 万元、出让收益率 3.1%，成交价 110 万元，公示文号湘资矿公示〔2026〕15 号。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/zrgs/tkzrgs/202611/t20261117_10364789.htm',
                '矿业权市场', '11-16',
                '云南巍山西窑—大字山铜多金属矿探矿权 20 万元转让',
                '大理白族自治州自然资源和规划局公示，云南省巍山县西窑—大字山铜多金属矿详查探矿权以出售方式转让，转让价格 20 万元。转让人为云南雄洲恒房地产开发有限公司，受让人为大理恒合矿业有限责任公司，探矿权面积 18.7467 平方千米，公示文号大探转公示〔2026〕11 号。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/zrgs/tkzrgs/202611/t20261117_10364790.htm',
                '矿业权市场', '11-16',
                '辽宁岫岩石庙沟金矿普查探矿权以作价出资方式转让',
                '辽宁省自然资源厅公示，岫岩县石庙沟金矿普查探矿权以作价出资方式转让，转让价格为 0 万元。转让人为凤城市青城子熔鑫镁制品有限公司，受让人为凤城市鑫汇矿业有限公司，探矿权勘查矿种为金矿、面积 5.2945 平方千米，公示文号辽自然资探转公字〔2026〕32 号。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/zrgs/ckzrgs/202611/t20261117_10364786.htm',
                '矿业权市场', '11-16',
                '广西梧州水胜口—牛栏冲银矿采矿权 500 万元转让',
                '广西壮族自治区自然资源厅公示，梧州市福联矿业有限公司龙圩区水胜口—牛栏冲银矿采矿权以出售方式转让，转让价格 500 万元，受让人为梧州瑞达矿业有限公司，矿区面积 0.8773 平方千米、开采矿种为银矿。据 2016 年评审备案的详查报告，截至 2015 年 10 月 31 日矿区保有银矿石量 23.51 万吨、银金属量 44.45 吨，伴生金金属量 40.27 千克。')),

]

# ============ 并购关键词重归类 ============

CAT_MA2 = CAT_MA
_reclassify_ma = partial(_reclassify_ma_raw, cat_ma=CAT_MA2, ma_require=MA_REQUIRE)

unique_new = []
new_seen_url = set()
for cat, it in new_items:
    url = item_url(it)
    if url in new_seen_url:
        continue
    new_seen_url.add(url)
    unique_new.append((_reclassify_ma(_reclassify_by_url(cat, it), it), it))
new_items = unique_new

# —— 分桶 PIN（按内容口径：勘查成果属 🔍、政策属 📜、企业事故/产能属 🏭，勿被 _reclassify_ma 依「投资」二字拉到 💰）——
_PIN_CAT = [
    ('LME 金属期货全线下跌', CAT_SC),
    ('沪银大跌', CAT_SC),
    ('碳酸锂主力', CAT_SC),
    ('工业硅开工', CAT_SC),
    ('高盛', CAT_SC),
    ('王登红', CAT_ZC),
    ('绿色矿山', CAT_ZC),
    ('霍普斯山', CAT_ZK),
    ('第一钪业', CAT_ZK),
    ('天齐锂业', CAT_HY),
    ('康普化学', CAT_HY),
    ('南非采矿业', CAT_HY),
    ('稀土企业前三季', CAT_HY),
    ('敖宏会见', CAT_HY),
    ('潘古纳', CAT_GJ),
    ('亚美尼亚', CAT_GJ),
    ('韩国锌业', CAT_GJ),
    ('新宙邦', CAT_MA),
    ('哈尔干', CAT_KQ),
    ('肖尔库勒东', CAT_KQ),
    ('阿克然', CAT_KQ),
    ('长垅', CAT_KQ),
    ('八里矿区', CAT_KQ),
    ('荣塘', CAT_KQ),
    ('西窑', CAT_KQ),
    ('石庙沟', CAT_KQ),
    ('水胜口', CAT_KQ),
]


def _pin_cat(title, cat):
    for _kw, _c in _PIN_CAT:
        if _kw in (title or ''):
            return _c
    return cat


new_items = [(_pin_cat(item_title(_it), _c), _it) for _c, _it in new_items]

merge_seq = [x for x in merge_seq if item_url(x[1]) not in new_seen_url]
merge_seq = dedup_same_event(merge_seq)

# ============ 3.6 数字落地校验（复用 verify_numbers） ============
# 2026-10-25 A03：严格模式下校验失败/校验器故障必须非零退出、不写正式产物
# （旧实现吞异常后继续 → strict 守门形同虚设）。分类见 generate_site.py 同段注释。
_STRICT_NUM = os.environ.get('VERIFY_NUMBERS_STRICT') == '1'
try:
    from verify_numbers import verify_new_items
    _num_issues = verify_new_items(new_items, REPORT, strict=_STRICT_NUM)
    if _num_issues:
        print('[num-warn] 共 %d 条摘要存在数字未在源文找到，请人工核对' % len(_num_issues))
except AssertionError as _e:
    if _STRICT_NUM:
        print('[verify_numbers] 严格模式：数字落地校验未通过，终止生成（不写 index.html）：%s' % _e)
        sys.exit(1)
    print('[num-warn] %s' % _e)
except Exception as _e:
    if _STRICT_NUM:
        print('[verify_numbers] 严格模式：数字校验器故障，终止生成（不写 index.html）：%s' % _e)
        sys.exit(1)
    print('[verify_numbers] 警告：数字校验未执行（工具故障）：%s' % _e)
_new_titles = [item_title(it) for _c, it in new_items]
if _new_titles:
    merge_seq = [x for x in merge_seq
                 if not any(same_event(item_title(x[1]), _t) for _t in _new_titles)]
for _i in range(len(new_items)):
    for _j in range(_i + 1, len(new_items)):
        if same_event(item_title(new_items[_i][1]), item_title(new_items[_j][1])):
            print('[warn] 今日新增内部疑似同事件重复: %s <-> %s'
                  % (item_title(new_items[_i][1])[:40], item_title(new_items[_j][1])[:40]))

arch_groups = render_cat_groups(merge_seq, mark_new=False)
today_groups = render_cat_groups(new_items, mark_new=True)

# ============ 5. 拼装新区 ============
n_today = len(new_items)
arch_n = len(merge_seq)
all_n = n_today + arch_n

new_today_block = ('<!-- ==================== 今日新增（%s 抓取） ==================== -->\n' % GRAB +
                   '<div class="section" id="todaySection">\n'
                   '<div class="section-title today"><span class="icon">🔥</span> 今日新增（%s 抓取）<span class="news-count" id="todayCount">%d条</span></div>\n'
                   % (GRAB, n_today) + ''.join(today_groups) + '</div>\n')

new_arch_block = ('<!-- ==================== 往期内容 ==================== -->\n'
                  '<div class="section" id="archiveSection">\n'
                  '<div class="section-title"><span class="icon">📰</span> 往期内容（滚动保留最近30天）'
                  '<span class="news-count" id="archiveCount">%d条</span></div>\n'
                  '<div class="fold-toggle" id="foldToggle" style="display:none" onclick="toggleOldFold()">▸ 展开更早内容</div>\n'
                  % arch_n + ''.join(arch_groups) + '</div>\n')

html = html[:m_today] + new_today_block + new_arch_block + html[i_r:]
html = html.replace('<!-- ==================== 今日新增 ==================== -->', '', 1)

# ============ 6. 更新计数与 AI 提示 ============
html = re.sub(r'id="tocAllCount"[^>]*>\d+<', 'id="tocAllCount">%d<' % all_n, html)
html = re.sub(r'id="tocTodayCount"[^>]*>\d+<', 'id="tocTodayCount">%d<' % n_today, html)
html = re.sub(r'id="tocArchiveCount"[^>]*>\d+<', 'id="tocArchiveCount">%d<' % arch_n, html)
html = re.sub(r'今日 \d+ 条新闻的智能解读', '今日 %d 条新闻的智能解读' % n_today, html)

# ============ 7. div 收支自检 ============
_body = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', '', html)
_open = len(re.findall(r'<div\b', _body))
_close = len(re.findall(r'</div>', _body))
assert _open == _close, 'div 收支不平衡: open=%d close=%d' % (_open, _close)

_buf = html.encode('utf-8')
assert len(_buf) > _ORIG_SIZE * 0.9, 'refuse to write suspiciously small index.html: %d bytes (orig %d)' % (len(_buf), _ORIG_SIZE)
with open(SRC + '.tmp', 'w', encoding='utf-8') as f:
    f.write(html)
os.replace(SRC + '.tmp', SRC)

print('OK index.html -> today=%d archive=%d all=%d size=%d div=%d/%d'
      % (n_today, arch_n, all_n, len(html), _open, _close))
