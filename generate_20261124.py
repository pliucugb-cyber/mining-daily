# -*- coding: utf-8 -*-
"""
生成 2026-11-24 矿业资讯速览 index.html（周二）
- 11-23 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30）回补历史条目
- 换入 11-24 采集的条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 与 LME 均为 11-23 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）
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

REPORT = '2026-11-24'
GRAB = '2026-11-24'
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
                         r'\g<1>2026年11月24日 星期二', html)
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
    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202611/t20261124_10372855.htm',
                '全球矿产资源信息系统', '11-24',
                '印尼拟将矿业权许可收益的70%归政府，仅适用未来交易',
                '据矿业周刊援引路透社报道，印尼能源部长周一表示，政府正制定一项计划，将通过股权或收入分成方式，把矿业权许可收益的 70% 归交政府。总统普拉博沃称国家应确保获得「所有矿业许可至少 70% 的收益」，矿业部长巴利尔·拉哈达利亚称将尊重现有许可，所有权变化只适用于未来交易。惠誉旗下 CreditSights 指出，上述表态再次引发政策不确定性担忧；印尼是全球最大动力煤、镍和锡出口国，也是重要的铜出口国。')),

    (CAT_ZC, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/kysf/202611/t20261124_10372856.htm',
                '全球矿产资源信息系统', '11-24',
                '科特迪瓦拟将矿企权利金由6%提至9.5%',
                '据矿业周刊援引彭博通讯社报道，科特迪瓦计划上调矿企权利金以增加政府收入，为与国际货币基金组织就新一轮资金援助谈判作准备。方案将把权利金从矿产收入的 6% 提高到 9.5%，用于资助矿区基础设施和社会经济计划的社区发展税率从 0.5% 提高到 3%。调整方案已获内阁批准并提交国会，矿业部长称希望 2026 年底前通过新矿法。在该国经营金矿的企业包括因代沃矿业、蒙太奇黄金和联盟黄金，去年黄金产量约 60 吨。')),

    (CAT_ZC, ni('https://news.smm.cn/news/X7T4O7KOFWSJCQPJK5VROVAYP5IVKZZYCZOTKXQ',
                '上海有色网', '11-24',
                '刚果（金）11月30日起再度暂停钴出口，期限未定',
                '全球最大钴生产国刚果（金）的监管机构 ARECOMS 11 月 23 日声明，自 11 月 30 日起暂停所有钴出口，暂停期限暂未确定，理由是解决国际市场供应过剩、推动市场可持续再平衡。这是该国自 2025 年 2 月首次实施全面出口禁令以来第二次采取类似措施，此前的八个月配额制未能阻止钴价回落。刚果钴氢氧化物价格自今年 4 月触及峰值后几近腰斩；目前持有最大出口配额的企业包括洛阳钼业、嘉能可及欧亚资源集团。')),

    # ── 🔍 找矿成果与勘查技术 ───────────────────────────────────
    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475524',
                '中国有色金属报', '11-24',
                '西北有色七一七总队连中两标，达茂旗铜镍矿详查设计进尺1500米',
                '西北有色地矿集团七一七总队公司地质勘查院近日先后中标「内蒙古自治区达茂旗某铜镍矿详查钻探技术服务」和「陕西省某耕地提质增效」两个项目。达茂旗铜镍矿详查项目是该院近年来在内蒙古承接的首个钻探施工项目，设计钻探总进尺 1500 米、单孔孔深 500 米，10 月 30 日已举行开钻仪式。陕西项目属渭河中上游山水林田湖草沙一体化保护和修复工程子项目，统筹生态修复与耕地保护。')),

    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475496',
                '中国有色金属报', '11-23',
                '丰山铜矿深部找矿增储与伴生元素回收两项成果获一等奖',
                '中色大冶丰山铜矿报送的「丰山铜矿北缘深部资源找矿增储」和「硫、钼、金、银等有价元素强化回收关键技术研究及应用」两个项目成果，在中色大冶科技与人才大会上同获科学技术成果一等奖。前者指向矿山北缘深部接续资源的找矿增储，后者聚焦硫、钼、金、银等伴生有价元素回收率提升，两项成果均由矿山一线技术团队完成。')),

    (CAT_ZK, ni('https://news.metal.com/newscontent/UT5GUR3EJ2IWTTQ7B77G2OZ5PIZ5DUXMCTAADXA-western-australias-goongarrie-nickel-cobalt-project-secures-a588-million-for-pre-feed-work',
                'SMM 国际站', '11-23',
                '住友等日企全额出资5880万澳元，推进西澳Goongarrie镍钴项目pre-FEED',
                'Ardea Resources 11 月 23 日公告，已与日本住友金属矿山、三菱商事及其合资公司 GH Nickel 签署修订协议，日方将承担西澳 Kalgoorlie 镍钴项目 Goongarrie Hub 在可研之前阶段（pre-FEED）的全部 5880 万澳元预算。加上此前已投入的 9850 万澳元可研资金，日方研究出资承诺累计约 1.573 亿澳元；签约同时其持股由 35% 升至 45% 并接管指导委员会，若作出最终投资决定将进一步升至 60%、Ardea 保留 40%。该 hub 此前公布资源量 5.84 亿吨、含钴约 25 万吨。',
                orig_title='Western Australia\u2019s Goongarrie Nickel-Cobalt Project Secures A$58.8 Million for Pre-FEED Work')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/6F2ONDMHUOM224PPK3PYJ5JLEKIXLPGMJL6NRBY',
                '上海有色网', '11-23',
                'LME铜库存升至近五个月新高，超七成堆在美国仓库',
                '上期所数据显示，11 月 20 日当周沪铜库存减少 11.59% 至 30846 吨，处近三年相对低位；国际铜库存减少 200 吨至 9551 吨。LME 铜库存上周先降后增，最新为 332025 吨，升至近五个月新高，其中超七成位于美国仓库，区域集中度较高；纽铜库存回落至 805219 短吨，仍处历史高位附近。此前市场提前布局 2027 年起对精炼铜进口征 15% 关税的可能，COMEX 铜较 LME 维持溢价，形成海外累库、国内缺库的割裂格局。')),

    (CAT_SC, ni('https://news.smm.cn/news/ZHVRKUTSQJWUMZQSTDA4NUIWAY3EV6I76RYBD7A',
                '上海有色网', '11-23',
                '交易商开始把美国积压的铜运往中国，两年贸易流向逆转',
                '关税预期降温叠加中国市场供应紧缺，正驱动全球铜贸易流向发生根本转变：交易商已开始将积压在美国港口的铜运往中国，终结过去两年铜持续单向涌入美国的格局。据英国《金融时报》报道，约六艘运铜船已离开长滩和洛杉矶港驶向中国，彭博此前援引知情人士称部分原定运往美国的铜被改道、涉及规模约数万吨。伦铜本周自 10 月底逾 14670 美元/吨的高位跌至不足 12600 美元/吨，Marex 数据显示约 94% 的 LME 与 COMEX 铜库存仍积压在美国。')),

    # ── 💼 矿权交易 ─────────────────────────────────────────────
    (CAT_KQ, ni('https://ky.mnr.gov.cn/xycrgs/ckq/202611/t20261124_10371467.htm',
                '矿业权市场', '11-24',
                '陕西榆林三台界煤矿深部资源采矿权拟协议出让，面积6.2159平方公里',
                '陕西省自然资源厅公示，拟以协议方式向陕西榆林榆阳区三台界煤矿出让其深部资源采矿权，开采矿种为煤，开采规模 90 万吨/年，矿区面积 6.2159 平方千米，地理位置为榆林市榆阳区。出让依据为矿业权出让交易规则和深化矿产资源管理改革相关意见，公示文号为陕自然资矿出公示〔2026〕9 号，公示期 11 月 24 日至 12 月 7 日。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/zrgs/tkzrgs/202611/t20261124_10371440.htm',
                '矿业权市场', '11-24',
                '赤峰东上毛卜罗铅锌矿勘探探矿权拟转让，面积3.1686平方公里',
                '赤峰市自然资源局公示，翁牛特旗达立安矿产品贸易有限公司拟将「赤峰市翁牛特旗东上毛卜罗铅锌矿勘探」探矿权转让给赤峰银仑矿业有限公司，转让方式为出售、转让价格 0 万元。该探矿权勘查矿种为铅矿，勘查面积 3.1686 平方千米，勘查许可证有效期 2025 年 8 月 6 日至 2030 年 8 月 5 日，公示文号赤探转示〔2026〕007 号，公示期 11 月 24 日至 12 月 7 日。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475485',
                '中国有色金属报', '11-23',
                '中金岭南前三季度营收607.5亿元、利润总额18.27亿元',
                '中金岭南 2026 年前三季度实现营业收入 607.5 亿元、同比增长 25.36%，其中实体营收占比 93.36%、同比增长 38.38%；实现利润总额 18.27 亿元、同比增长 65.5%。公司在 2026 年《财富》中国 500 强位列第 282 位，比上年上升 5 位。面对多重外部不利因素，公司统筹推进生产经营、深化改革与项目攻坚，稳住了发展基本盘。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475488',
                '中国有色金属报', '11-23',
                '新疆有色火烧云公司余热发电、五效蒸发两套装置投运',
                '新疆有色集团火烧云公司 11 月 9 日完成余热发电、五效蒸发两套关键装置调试投运，破解了余热利用率偏低、生产废水处置受限的问题。此前受系统联调复杂、多专业协同难度大等因素影响，余热发电系统未实现稳定并网发电，五效蒸发装置也未能连续稳定运行。该公司组织公辅分厂工艺、检修、电气、仪表等多专业技术力量攻关，11 月 7 日实现机组一次冲转。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://news.smm.cn/news/7GNS62HPHTK6PX5YVCNM7AH6ODFVNNPZYJNUKEA',
                '上海有色网', '11-24',
                '第一量子接受重启巴拿马Cobre Panama铜矿的五项谈判条件',
                '巴拿马政府 11 月 23 日表示，第一量子矿业旗下 Minera Panama 已接受该国政府就重启 Cobre Panama 铜矿谈判提出的五项条件，包括承认巴拿马拥有矿产资源、矿山须为巴拿马人提供更多就业、遵守最高环境标准、尊重国家主权宪法和法律。该矿自 2023 年起关闭，原因是公众环保抗议及巴拿马最高法院裁定其合同违宪，关闭前约占全球铜产量的 1%。政府称在作出最终重启决定前将权衡公众意见。')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202611/t20261124_10372857.htm',
                '全球矿产资源信息系统', '11-24',
                '必和必拓推南澳铜金铀扩产计划，总投资136亿至174亿美元',
                '据 Miningnews.net 报道，必和必拓已推出分阶段扩产计划，拟投资 136 亿至 174 亿美元，将南澳州矿山产量提高到 100 万吨铜当量，其中铜 65 万吨。第一阶段到 2035 年铜产量扩至 50 万吨、铜当量 80 万吨，内部收益率 14%—17%，年均资本约 13 亿美元并于 2030 年达峰。扩产同步使铀产量从 4000 吨增至 6000 吨、金增长 45% 至 57 万盎司/年，公司称现有铜资源量足以生产约 80 年。')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/NVVKGE6M46KUQRFFINBM3S3OMCEUJMHM37I5UZQ-anglogold-ashanti-plans-25bn-quebradona-copper-mine-in-colombia-targeting-80000-tyr',
                'SMM 国际站', '11-24',
                'AngloGold拟投25亿美元开发哥伦比亚Quebradona铜矿，年产铜8万吨',
                'AngloGold Ashanti 计划投资约 25 亿美元开发哥伦比亚安蒂奥基亚省的 Quebradona 地下铜矿，目标年产铜 8 万吨、年出口额约 15 亿美元，前提是取得环境许可。项目资源量 1.2 亿吨、铜品位 1.23%，含铜 147 万吨，计划 2028 年开工建设。项目首个环评 2021 年被搁置，2025 年的保护区命令正受司法挑战，勘探权已延长至 2027 年 12 月。',
                orig_title='AngloGold Ashanti plans $2.5bn Quebradona copper mine in Colombia, targeting 80,000 t/yr')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-24/1225683916.PDF',
                '巨潮资讯网', '11-24',
                '上海誉升完成对艾艾精工要约收购，持股升至40%',
                '艾艾精工要约收购期限于 11 月 20 日届满，预受要约股东账户 5 户、预受股份 4827.67 万股，占公司总股本的 36.94461%；收购人上海誉升同风金属材料科技有限公司按预定 1308.04 万股（占总股本 10.01%）等比例收购，要约价格 27.54 元/股、现金支付。收购完成后上海誉升持有 5226.93 万股、占总股本 40.00%，公司股权分布仍符合上市条件，股票于 11 月 24 日开市起复牌。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-24/1225684915.PDF',
                '巨潮资讯网', '11-24',
                '天齐锂业董事长提议回购4亿至8亿元，用于注销或股权激励',
                '天齐锂业 11 月 23 日收到董事长蒋安琪出具的提议回购函，提议以自有资金或自筹资金通过深交所交易系统集中竞价回购公司 A 股。回购资金总额不低于 4 亿元、不超过 8 亿元，回购价格不高于董事会审议回购方案决议前 30 个交易日交易均价的 150%，期限为董事会审议通过后 12 个月内，股份用于注销、维护公司价值及股东权益或股权激励、员工持股计划。',
                embed='pdf')),
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
    ('矿业权管理', CAT_ZC),
    ('再生铅', CAT_ZC),
    ('梦想', CAT_ZK),
    ('佩莱南', CAT_ZK),
    ('Lexington', CAT_ZK),
    ('伦铜周线', CAT_SC),
    ('高盛', CAT_SC),
    ('邬二湾', CAT_KQ),
    ('郝泉沟', CAT_KQ),
    ('亚洲铜业周', CAT_HY),
    ('原镁', CAT_HY),
    ('Kalayi', CAT_GJ),
    ('Bahodopi', CAT_GJ),
    ('Merdeka', CAT_GJ),
    ('KFM', CAT_MA)
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
