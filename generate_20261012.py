# -*- coding: utf-8 -*-
"""
生成 2026-10-12 矿业资讯速览 index.html（周一）
- 10-11 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-13）回补历史条目
- 换入 10-12 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-09 收盘 + LME 10-09 收盘（10-12 05:30 国内未开盘），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易），不进主页列表
- 保留：会展 IIFE / 搜索 / CSV / PDF / 防横跳 / 内联自愈引信 / 价格三视图
- 境外条目保留英文原题（data-orig-title + 摘要末尾「原题：…」）
"""
import re, datetime, json, glob, os
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

REPORT = '2026-10-12'
GRAB = '2026-10-12'
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
                         r'\g<1>2026年10月12日 星期一', html)
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
for _fn in sorted(glob.glob('data/news_2026-*.json')):
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

merge_seq = dedup_same_event(merge_seq)

# ============ 3.5 从累计库回补 30 天窗口 ============
CAT_MAP = dict(LEGACY_BUCKET)
CAT_MAP.update(THEME_BUCKET)
LIB_SKIP = {'矿权交易', '并购与投资'}
_lib_item = partial(_lib_item_raw, cat_map=CAT_MAP)

_lib_pool = []
for _fn in sorted(glob.glob('data/news_2026-*.json')):
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
    (CAT_ZK, ni('https://www.cgs.gov.cn/ywdt/ddyw/202610/t20261011_870243.html',
                '中国地质调查局', '10-11',
                '第十八届全国矿床会议在长沙开幕，聚焦人工智能找矿与关键矿产勘查',
                '中国地质调查局报道，第十八届全国矿床会议在湖南长沙开幕，会议围绕成矿理论创新、关键矿产勘查、智能勘查技术、矿业绿色低碳转型、矿产资源全产业链建设等议题展开交流，并设置主题报告、专题研讨、合作签约等环节。会议要求大力发展人工智能找矿、高精度遥感、地球物理探测、地球化学勘查、绿色勘查等新技术新方法，推动传统勘查技术向智能化、精准化、绿色化转型升级，坚持产学研用协同创新，并积极推进国际合作与交流。')),

    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474447',
                '中国有色金属报', '10-09',
                '新书《地下金属矿山遗留矿开采环境探测及回采技术》系统梳理深部遗留矿安全回采技术',
                '中国有色金属报推介《地下金属矿山遗留矿开采环境探测及回采技术》一书。该书针对浅部资源枯竭、深部开采推进过程中遗留大量矿产资源的现状，提出金属矿山地下遗留矿安全回采的总体思路与技术路线，系统介绍遗留矿赋存环境探测技术、关键承载位置一般性原则、遗留矿可回采性评价方法，并以水平矿柱回采为例介绍回采技术方案与回采监测预测技术，最后给出遗留矿柱回采典型工程案例。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://www.mnr.gov.cn/gk/tzgg/202610/t20261008_2939647.html',
                '自然资源部', '10-08',
                '自然资源部就规范探矿权招标出让公开征求意见',
                '自然资源部公告，为贯彻落实《矿产资源法》《矿产资源法实施条例》，规范探矿权招标出让，助推新一轮找矿突破，支撑战略性矿产增储上产，该部研究起草了《自然资源部关于规范探矿权招标出让的通知（征求意见稿）》，现公开征求意见，意见建议请于 2026 年 10 月 23 日前通过电子邮件方式反馈。')),

    (CAT_ZC, ni('https://news.smm.cn/news/104149635',
                '上海有色网', '10-10',
                '商务部：反对以“产能过剩”为名行贸易保护主义之实',
                '上海有色网转载商务部消息，针对美东时间 10 月 7 日美贸易代表办公室称美国召集 14 个经济体高级官员签署应对所谓“结构性产能和生产过剩”问题的部长级联合声明，商务部新闻发言人表示，中方一贯认为看待产能问题要秉持全面、客观、公正态度，不能出于对自身产业竞争力和市场地位的担忧将经贸问题政治化；反对个别国家以所谓“产能过剩”为名行贸易保护主义之实，若有关经济体以此为借口采取损害中方利益的措施，中方将作出必要回应。')),

    (CAT_ZC, ni('https://news.smm.cn/news/104150502',
                '上海有色网', '10-10',
                '发改委主任郑栅洁主持民营企业座谈会，强调提高能源资源安全保障水平',
                '上海有色网转载国家发展改革委消息，10 月 10 日国家发展改革委主任郑栅洁主持召开民营企业座谈会，围绕准确把握三季度经济形势、积极应对国际供需情况变化，与石油化工、天然气供应、农业机械、人工智能应用等领域企业负责人深入交流。郑栅洁表示，将推动“十五五”规划、“六张网”建设实施方案等明确的重大工程项目尽早开工，推动科技创新与产业创新深度融合，进一步提升产业链供应链韧性、提高能源资源安全保障水平，并常态化向民间资本推介项目。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104149228',
                '上海有色网', '10-11',
                '隔夜金属普涨：伦锡领涨，伦铜、伦锌、伦铅及沪银走强',
                '上海有色网【隔夜行情】显示，隔夜金属普涨，伦锡领涨，伦铜、伦锌、伦铅及沪银走强，纽约金、纽约银周线收阳。')),

    (CAT_SC, ni('https://news.metal.com/en/newscontent/104150494-smm-expects-overall-copper-anode-operating-rate-to-pull-back-mom-in-october',
                'SMM 国际站', '10-11',
                'SMM：预计 10 月中国铜阳极板整体开工率环比回落',
                'SMM 国际站报道，SMM 预计 2026 年 10 月中国铜阳极板整体开工率将环比回落。',
                orig_title='SMM Expects Overall Copper Anode Operating Rate to Pull Back MoM in October')),

    (CAT_SC, ni('https://news.metal.com/en/newscontent/104150453-copper-platesheet-market-sees-strong-orders-post-holiday-smm-forecasts-high-operating-rates-in-october',
                'SMM 国际站', '10-11',
                'SMM：节后铜板带市场订单强劲，预计 10 月开工率维持高位',
                'SMM 国际站报道，国庆假期后铜板带市场订单表现强劲，SMM 预计 10 月行业开工率将维持高位。',
                orig_title='Copper Plate/Sheet Market Sees Strong Orders Post-Holiday, SMM Forecasts High Operating Rate in October')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474279',
                '中国有色金属报', '09-24',
                '沪铜现货升水突破千元大关，铜精矿现货加工费跌至历史低位',
                '中国有色金属报报道，铜现货升水突破 1000 元/吨，并一度升至 1100~1400 元/吨，长江现货铜升贴水均价达 1350 元/吨，期现结构呈现“现货强、期货弱”格局。低库存是直接推手——上海期货交易所铜仓单持续处于低位、可流通货源紧张，持货商挺价惜售；进口铜精矿现货加工费（TC）已跌至 -221.89 美元/干吨的历史低位，冶炼利润恶化，市场预计 10—11 月国内多家铜冶炼厂集中检修、部分企业已释放减产意愿。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-10-12/1225600444.PDF',
                '巨潮资讯网', '10-12',
                '江特电机：茜坑锂矿 300 万吨/年采矿工程安全设施设计通过审查',
                '巨潮资讯网披露，江西特种电机股份有限公司公告收到国家矿山安全监察局下发的《江西省宜丰县茜坑锂矿 300 万吨/年采矿工程安全设施设计审查意见书》（矿安非煤项目审字〔2026〕45 号），原则同意《安全设施设计》通过审查。茜坑锂矿采矿证证载面积 1.3826 平方公里，Li2O 平均品位按 0.44% 计算矿石资源储量 7293 万吨、按 0.39% 计算达 1.2667 亿吨，属大型锂矿，开采年限 30 年；安全设施设计通过审查是矿山由取得采矿权向依法开工建设推进的关键环节。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474352',
                '中国有色金属报', '09-29',
                '中铝贵州分公司 8021 电池铝箔用扁锭试制达标，具备市场化供货能力',
                '中国有色金属报报道，中铝贵州分公司合金事业部完成 8021 电池铝箔用扁锭试制开发，产品各项性能指标全部达标，正式具备市场化供货能力。8021 合金作为高端电池铝箔核心基材，凭借高韧性、高阻隔性、耐电解液腐蚀、低针孔率等优势适配软包锂电池与储能电池；此前国内高品质 8021 电池铝箔扁锭长期供不应求。该事业部针对熔体纯净度控制、氢含量管控、富铁相形态优化、组织均匀性等难题反复试验、迭代优化工艺参数，搭建起成熟标准化的制造工艺体系。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474193',
                '中国有色金属报', '09-22',
                '神火集团年产 5 万吨钠离子高性能电池铝箔项目开工',
                '中国有色金属报报道，神火集团年产 5 万吨钠离子高性能电池铝箔项目开工仪式在河南省商丘市示范区举行。项目规划建设约 4 万平方米现代化生产车间，配置 3 台 1850 毫米和 3 台 2150 毫米铝箔轧机，产品覆盖 1070、1100 等合金牌号、厚度 8~20 微米，面向钠离子电池正负极专用高性能铝箔；建设周期 24 个月，计划年内建成投产。项目建成后神火新材商丘基地铝箔加工能力整体跃升至 16.5 万吨，集团铝箔总产能将达 19 万吨。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474274',
                '中国有色金属报', '09-24',
                '中矿资源赞比亚卡通巴铜矿选矿厂建成投产',
                '中国有色金属报报道，中矿资源控股的赞比亚卡通巴矿业有限公司选矿厂完成建设期各项工作任务，正式进入生产运营阶段。卡通巴铜矿是中矿资源在赞比亚首个从零起步自主开发、自主运营的标志性项目，选矿厂建成投产标志项目由工程建设阶段迈入生产运营阶段，也标志公司在推进资源开发、延伸产业链条、提升资源价值转化能力方面迈出坚实一步。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474361',
                '中国有色金属报', '09-29',
                '株硬主导制定的硬质合金超声检测国际标准 ISO/TS 23867:2026 发布',
                '中国有色金属报报道，国际标准化组织正式发布由株洲硬质合金集团有限公司主导制定的国际标准 ISO/TS 23867:2026《硬质合金超声检测》。这是全球硬质合金行业首项超声检测国际标准，也是我国硬质合金行业自主主导制定的首项国际标准，由 ISO/TC 119/SC4 专业委员会归口管理。该标准自 2018 年 9 月提交提案、历经 8 年多轮国际评审与成员国投票后发布，界定了 A 型脉冲接触式纵波超声检测方法，并明确适用范围、标准试块制备、探头参数选型、缺陷判定依据等要求。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474434',
                '中国有色金属报', '10-12',
                '中国铜业呼伦贝尔驰宏锌基物料绿色冶炼技术通过评价，认定国际领先',
                '中国有色金属报报道，由中国铜业所属呼伦贝尔驰宏牵头完成的“多杂难处理锌基物料绿色冶炼与资源高效回收技术及应用”项目通过中国有色金属工业协会组织的科技成果评价，专家组认定整体技术达到国际领先水平。项目历时 6 年攻关，联合昆明理工大学、上海交通大学内蒙古研究院等单位，构建以氧压浸出—矿化沉铁为核心的短流程绿色冶炼新技术体系，建成国内规模最大的同类标杆工程，实现年产 14 万吨锌、6 万吨铅，并配套生产硫酸、白银、黄金、精铟及海绵镉、铜精矿、钴精矿等副产品。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsyj/202610/t20261010_10332110.htm',
                '全球矿产资源信息系统', '10-10',
                '艾芬豪三季度卡莫阿-卡库拉铜矿产量回升，基普希锌矿精矿增产',
                '全球矿产资源信息系统报道，艾芬豪矿业（Ivanhoe Mines）2026 年三季度卡莫阿-卡库拉（Kamoa-Kakula）铜矿产量回升，刚果（金）基普希（Kipushi）锌矿精矿锌产量实现增长。')),

    (CAT_GJ, ni('https://news.smm.cn/news/104149638',
                '上海有色网', '10-10',
                '铜价逼近历史高位，智利铜矿又爆罢工，摩根大通警告产量冲击或“相当显著”',
                '上海有色网报道，铜价逼近历史高位之际，智利铜矿再度爆发罢工。摩根大通警告，此轮罢工对铜产量的冲击可能“相当显著”。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://news.smm.cn/news/104150497',
                '上海有色网', '10-10',
                '兴业银锡要约收购威领股份 6.12% 股份完成过户，尚未取得控制权',
                '上海有色网报道，兴业银锡公告其全资子公司西藏山南锑金资源有限公司以 18.00 元/股向威领新能源股份有限公司全体股东发出部分要约，拟收购 78,177,450 股、占总股本 30.00%，要约期限为 2026 年 8 月 31 日至 9 月 29 日。截至 9 月 29 日预受要约股份 15,936,390 股、占总股本 6.12%，已超过占总股本 5.00% 的生效条件，本次要约收购生效，最终收购价款 286,855,020 元（不含税费）；截至目前公司尚未取得威领股份控制权。')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-10/1225599583.PDF',
                '巨潮资讯网', '10-10',
                '江钨装备向特定对象发行 A 股股票申请获上交所受理',
                '巨潮资讯网披露，江西江钨稀贵装备股份有限公司公告于 2026 年 10 月 9 日收到上海证券交易所《关于受理江西江钨稀贵装备股份有限公司沪市主板上市公司发行证券申请的通知》（上证上审（再融资）〔2026〕324 号），上交所依据相关规定对申请文件核对后认为文件齐备、符合法定形式，决定予以受理并依法进行审核。该事项尚需通过上交所审核并获得中国证监会同意注册的决定后方可实施。')),

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

merge_seq = [x for x in merge_seq if item_url(x[1]) not in new_seen_url]
merge_seq = dedup_same_event(merge_seq)

# ============ 3.6 数字落地校验（复用 verify_numbers） ============
try:
    from verify_numbers import verify_new_items
    _num_issues = verify_new_items(new_items, REPORT,
                                   strict=os.environ.get('VERIFY_NUMBERS_STRICT') == '1')
    if _num_issues:
        print('[num-warn] 共 %d 条摘要存在数字未在源文找到，请人工核对' % len(_num_issues))
except Exception as _e:
    print('[verify_numbers] 跳过: %s' % _e)
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
