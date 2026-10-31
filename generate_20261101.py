# -*- coding: utf-8 -*-
"""
生成 2026-11-01 矿业资讯速览 index.html（周日）
- 10-31 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-10-03）回补历史条目
- 换入 11-01 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-30 收盘 + LME 10-30 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目：11-01 无新增出让公告（周日），14 日窗口由 news-data.js 直出 #rightsCards，不进主列表
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

REPORT = '2026-11-01'
GRAB = '2026-11-01'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年10月\d{2}日 星期.',
                         r'\g<1>2026年11月01日 星期日', html)
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
    # ── 🔍 找矿成果与勘查技术 ────────────────────────────────────
    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475038',
                '中国有色金属报', '10-29',
                '江西省地质局生态大队「十四五」新发现矿产地 27 处',
                '「十四五」期间累计实施各类地质勘查项目 129 项，完成钻探进尺约 30 万米、槽探工程近 8 万立方米，提交通过评审备案的地质成果报告 45 份，新发现矿产地 27 处，新提交大型矿床 19 处、中型矿床 19 处，其中锂、萤石等战略性矿产大中型矿床 7 处；同步拓展秘鲁、纳米比亚、津巴布韦等海外勘查市场。')),

    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475031',
                '中国有色金属报', '10-29',
                '江西省地质局第一大队落地多个千万元级找矿项目，市场首拓云南',
                '该大队 2026 年围绕锂、铁、铜钨、铅锌、萤石等优势与战略性矿种深耕赣西，先后落地安福罗家房铅锌多金属矿详查、赣县岭脑铜多金属矿普查、崇义松树排铜多金属矿地质勘查等一批千万元级项目；云南马关县冷水沟铜锌钨矿资源储量核实项目落地，找矿市场版图首次拓展到云南。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475090',
                '中国有色金属报', '10-30',
                '葛红林：全链协同加快建设镁业强国，前三季度原镁产量增 19.73%',
                '中国有色金属工业协会会长葛红林提出沿「资源—冶炼—合金加工—终端应用」价值链全链协同推进镁业强国建设。据镁业分会统计，2025 年国内原镁产量 109.35 万吨、同比增 6.6%，占全球 89.2%；2026 年 1—9 月累计约 87.02 万吨、同比增 19.73%。原生镁锭碳足迹核算团体标准 T/CNIA 0295—2025 已于 2025 年 9 月 1 日实施。')),

    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475032',
                '中国有色金属报', '10-29',
                '锌冶炼铁渣富氧熔炼团体标准发布，湘和有色参与起草',
                '由中国商品学会组织评审发布、青海湘和有色金属有限责任公司参与起草的团体标准《锌冶炼铁渣富氧熔炼—烟化还原技术》（T/CS 582—2026）获批并获颁起草证书，围绕场地条件、设备人员、原料储运、工艺管控、生态环保与安全生产作出规范，适用于以锌冶炼铁渣为原料开展固废减量与有价金属回收的生产企业和工程项目。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104189787',
                '上海有色网', '10-31',
                'Cochilco 下调智利铜产量预测至 494 万吨，上调今明两年铜价',
                '智利铜业委员会（Cochilco）10 月 30 日将 2026 年铜产量预测下调 8.4% 至 494 万吨（8 月预估为降 2.6% 至 527 万吨），主因矿石品位下降、检修与运营中断拖累加工回收率；预计 2027 年产量回升 3% 至 508 万吨。同期将 2026 年铜均价预测由 5.95 美元/磅上调至 6.18 美元/磅，2027 年由 5.10 上调至 5.95 美元/磅。')),

    (CAT_SC, ni('https://news.smm.cn/news/104189785',
                '上海有色网', '10-31',
                '智利 9 月铜产量同比降 15.1% 至 38.79 万吨',
                '智利统计局（INE）10 月 30 日公布，9 月铜产量同比下降 15.1% 至 387,870 吨；当月制造业产出同比增长 2.0%。该数据与 Cochilco 同日下调全年产量预测相互印证，运营中断与品位下滑是主因。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475040',
                '中国有色金属报', '10-29',
                '铜价高位震荡：美通胀反弹推升加息预期，矿端干扰仍在',
                '10 月铜价先扬后抑。美国 9 月非农就业仅增 2.9 万人、远低于 9 万预期，失业率升至 4.2%，曾支撑铜价走强；月中 9 月 CPI 同比涨 3.7%、核心 CPI 涨 2.6% 均超预期，市场对美联储年末加息概率升至 50%，美元指数最高上探 102.735，沪铜主力回吐上半月涨幅。海外矿山事故频发仍对铜精矿供应形成实质干扰。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475034',
                '中国有色金属报', '10-29',
                '中国铝型材产能分化：低端过剩与高端不足并存',
                '建筑门窗等中低端产能准入门槛低、以 6063 合金为主，产品同质化严重，竞争围绕加工费展开，受房地产周期影响开工率波动明显，是过剩压力主要来源；面向新能源汽车、航空航天、高端船舶的高端工业型材依赖大型挤压机与精密模具，国内稳定量产能力不足，部分高端牌号仍存进口依赖。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475033',
                '中国有色金属报', '10-29',
                '金川铜贵上线「红外成像+AI 算法」智能检测系统',
                '金川集团铜贵股份联动外部单位研发搭建「红外成像+AI 算法」智能检测系统，依托红外热像仪不间断采集电解槽槽面温度数据、由算法自动判别早期短路与烧板故障，实现全覆盖无盲区实时监测；投用后可减少反复揭布带来的热量流失与蒸汽能耗，提升阴极铜质量稳定性。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475026',
                '中国有色金属报', '10-29',
                '中铝集团携中国铜业向西藏巴青地震灾区捐赠 1500 万元',
                '10 月 22 日 22 时 33 分西藏那曲市巴青县发生 7.0 级地震。中铝集团携所属中国铜业紧急向灾区捐赠 1500 万元，用于支持现场救援、安置受灾群众与善后工作；集团表示将持续关注救援进展并与当地政府加强联系。')),

    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-10-31/1225647940.PDF',
                '巨潮资讯网', '10-31',
                '阿科力部分生产装置停产检修完成，复产时间延期',
                '无锡阿科力科技股份有限公司公告部分生产装置停产检修已完成，复产时间相应延期。涉及装置范围、延期原因与预计复产安排以公告正文披露为准。')),

    # ── 🌐 国际矿业动态 ────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/uranium-shares-slide-even-as-analysts-see-tighter-supply',
                'MINING.COM', '10-30',
                '铀矿股 9 月重挫，长期铀价仍处 18 年高位',
                '长期铀价处于 18 年多高位，铀矿股却大幅回调：VettaFi 全球铀矿指数 9 月跌 16%，Nasdaq Sprott 初级铀矿指数跌 22%，现货铀价几乎未动。BMI 预计现货铀价明年均价 95 美元/磅（今年 88 美元），今年全球矿山产量增 7.8%、含二次供应仍小幅过剩，明年转为短缺；TradeTech 长期铀价指标连续四个月维持 97 美元/磅，较一年前高 13 美元，处于 18 年多来最高位。',
                orig_title='Uranium shares slide even as analysts see tighter supply')),

    (CAT_GJ, ni('https://www.mining.com/perseus-mining-secures-backup-power-for-nyanzaga-gold-project',
                'MINING.COM', '10-30',
                'Perseus 为坦桑尼亚 Nyanzaga 金矿配置 28 台 1 兆瓦备用机组',
                'Perseus Mining 为坦桑尼亚西北部 Nyanzaga 金矿采购 28 台康明斯 KTA50G3 1 兆瓦集装箱式发电机组，并配套大容量燃油罐与泵橇，由南非 USP&E 提供应急电力系统，以弥补矿区远离可靠电网的短板。项目计划 2027 年 1 月首次浇金，投产后前 14 年年产金逾 20 万盎司，将占公司黄金产量的 28%。',
                orig_title='Perseus Mining secures backup power for Nyanzaga gold project')),

    (CAT_GJ, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475001',
                '中国有色金属报', '10-28',
                '敖宏赴英国访问，与托克、智利铜与矿业研究中心会谈',
                '中国有色金属工业协会党委书记敖宏 10 月 18—21 日在伦敦出席 2026 中国有色金属报告会期间，分别与中信期货伦敦办公室、托克集团、智利铜与矿业研究中心及国际铝业协会负责人会谈，围绕稳定矿产资源供应链、加快中国企业「走出去」、亚洲铜业周等议题交换意见。')),

    (CAT_GJ, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474973',
                '中国有色金属报', '10-27',
                '马拉维矿业部长率团访问中矿卡通巴矿业',
                '10 月 15 日，马拉维矿业部长托科扎尼·坦博率代表团访问中矿资源集团所属中矿卡通巴矿业，参观综合办公楼、选矿厂、光伏电站、采矿场与冶炼厂等核心区域，了解矿山建设进展、ESG 治理成效与未来规划，并对项目建设速度与绿色矿山理念给予肯定。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://news.smm.cn/news/104189801',
                '上海有色网', '10-31',
                '宝武镁业前三季度营收 70.63 亿元，子公司拟投建年产 1000 万吨白云岩项目',
                '宝武镁业三季报显示前三季度营业收入 70.63 亿元、同比增 1.34%，归母净利润 -8117.02 万元，主因镁价下行与联营企业投资损失增加；同期公告子公司拟投建年产 1000 万吨白云岩开采项目，以完善镁产业上游资源保障、夯实矿冶一体化产业链。')),

    (CAT_MA, ni('https://news.smm.cn/news/104186650',
                '上海有色网', '10-29',
                '马里马卡铜业为智利铜矿锁定至多 4 亿美元项目融资',
                '马里马卡铜业（Marimaca Copper）已选定一家专业矿业贷款机构，为智利北部安托法加斯塔地区露天铜矿寻求 3.75 亿至 4 亿美元项目融资，目标年底前完成。项目设计年产精炼铜约 5 万吨，总融资需求约 7.5 亿美元，已启动现场基础设施工程，计划明年下半年全面动工、2029 年首次产出。')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-31/1225649721.PDF',
                '巨潮资讯网', '10-31',
                '上海誉升同风金属材料拟对艾艾精工发起要约收购',
                '艾艾精工公告，上海誉升同风金属材料科技有限公司拟对公司股份发起要约收购，公司已披露要约收购报告书摘要及董事会致全体股东的报告书。要约价格、收购比例、期限与生效条件以公告正文披露为准。')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-31/1225648189.PDF',
                '巨潮资讯网', '10-31',
                '中铝国际披露境外项目合同签订进展',
                '中铝国际工程股份有限公司公告境外项目签订合同的进展情况。合同标的、金额、履行期限与生效条件以公告正文及后续披露为准。')),

    # ── 💼 矿权交易 ─────────────────────────────────────────────
    (CAT_KQ, ni('http://static.cninfo.com.cn/finalpage/2026-10-30/1225643974.PDF',
                '巨潮资讯网', '10-30',
                '红星发展拟转让万山鹏程矿业股权并处置相关债权',
                '贵州红星发展公告，大龙锰业及所属企业拟转让所持万山鹏程矿业有限责任公司部分债权资产，并同步披露该矿业公司股东全部权益价值评估报告。股权转让与债权转让的具体对价、受让方以公告及评估报告披露为准。')),


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

# —— 分桶 PIN（按内容口径：技改扩产属 🏭、勘查投入属 🔍，勿被 _reclassify_ma 依「投资」二字拉到 💰）——
_PIN_CAT = [
    ('生态大队', CAT_ZK),
    ('第一大队', CAT_ZK),
    ('葛红林', CAT_ZC),
    ('锌冶炼铁渣', CAT_ZC),
    ('Cochilco', CAT_SC),
    ('智利 9 月铜产量', CAT_SC),
    ('铜价高位震荡', CAT_SC),
    ('铝型材', CAT_HY),
    ('金川铜贵', CAT_HY),
    ('中铝集团携中国铜业', CAT_HY),
    ('阿科力', CAT_HY),
    ('铀矿股', CAT_GJ),
    ('Nyanzaga', CAT_GJ),
    ('敖宏', CAT_GJ),
    ('马拉维', CAT_GJ),
    ('宝武镁业', CAT_MA),
    ('马里马卡', CAT_MA),
    ('艾艾精工', CAT_MA),
    ('中铝国际披露', CAT_MA),
    ('红星发展', CAT_KQ),
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
