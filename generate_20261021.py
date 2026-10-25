# -*- coding: utf-8 -*-
"""
生成 2026-10-21 矿业资讯速览 index.html（周三）
- 10-20 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-22）回补历史条目
- 换入 10-21 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-20 收盘 + LME 10-19 收盘（10-21 周三 05:30 未开盘），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易，本批新增 6 宗（大余高岭铜、磐石烟筒山金、桦甸朝阳山金钼、铜陵五马山金、商都大南房子铁、鞍山东广峪菱镁）），不进主页列表
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

REPORT = '2026-10-21'
GRAB = '2026-10-21'
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
                         r'\g<1>2026年10月21日 星期三', html)
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
    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474731',
                '中国有色金属报', '10-20',
                '紫金矿业保有铜资源约 1.1 亿吨、金 4610 吨，分列全球第三、第五',
                '紫金矿业第八次科技大会 10 月 17 日在福建上杭召开。公司目前保有金资源量 4610 吨、铜资源量约 1.1 亿吨，分列全球第五、第三；「十四五」期间自主勘查新增铜资源量 2346 万吨，吨铜勘查成本 71 元，仅为行业平均水平的三分之一。自研「震旦」三维激电系统探测深度超 1500 米，已在 40 余个勘查区应用，助塞尔维亚玛格铜金矿成为近 5 年全球绿地勘查发现的第二大铜矿。')),

    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474769',
                '中国有色金属报', '10-20',
                'Auro Metals Santa Barbara 一期钻探收官，加权金品位超资源模型 21.7%',
                'Auro Metals 披露 Santa Barbara 金铜矿一期钻探第六批、也是最终批化验结果：核心钻孔连续见矿 572 米，金品位 0.60 克/吨、铜 0.1%。一期 22 个钻孔、累计进尺 11047.35 米收官，完成率 110.5%；按孔长加权平均金品位 0.633 克/吨，较推断资源均值 0.52 克/吨高 21.7%，铜加权品位 0.102%。二期钻探已启动，规模为一期实际进尺的 181%。')),

    (CAT_ZK, ni('https://www.mining.com/study-nearly-doubles-value-lifts-resource-for-aclaras-penco-rare-earths-project',
                'MINING.COM', '10-19',
                'Aclara 智利 Penco 稀土项目税后净现值近翻倍至 3.44 亿加元',
                '阿克拉拉资源（Aclara Resources）更新智利 Penco 稀土项目初步经济评价：税后净现值 3.44 亿加元（约 2.43 亿美元），较 2021 年研究近乎翻倍，折现率由 5% 提高到 8%；矿山寿命延长 3 年至 17 年，内部收益率升至 26.1%，前期建设成本 2.44 亿加元。更新后探明加控制资源 3580 万吨、TREO 品位 2095ppm、含稀土氧化物 75025 吨，增 19%；计划 2027 年一季度完成可行性研究、2028 年建成。',
                orig_title='Study nearly doubles value, lifts resource for Aclara\u2019s Penco rare earths project')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.smm.cn/news/104169114',
                '上海有色网', '10-20',
                '工信部：严控氧化铝、铜冶炼新增产能，修订铜铝行业规范条件',
                '10 月 20 日国新办发布会上，工信部运行监测协调局局长陶青表示，下一步将落实原材料领域「十五五」规划和铝、铜等产业高质量发展实施方案，制定镁产业创新发展实施方案；深化产能治理，实施重点产品产能风险监测预警，严格执行电解铝产能置换政策，严控氧化铝、铜冶炼新增产能，修订铜、铝等行业规范条件，坚决遏制低水平重复建设。前三季度十种常用有色金属产量 6235 万吨、同比增 2.5%。')),

    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474563',
                '中国有色金属报', '10-20',
                '两项涉镁标准入选工信部 2026 年度工业节能降碳标准研究项目清单',
                '工信部节能与综合利用司 10 月 8 日公示《2026 年度工业节能降碳标准研究项目清单》，公示期 10 月 8 日至 14 日。《工业硅和镁单位产品能源消耗及碳排放限额》与《温室气体 产品碳足迹量化方法与要求 原生镁锭》两项涉镁标准入选：前者聚焦冶炼生产端能耗与碳排放限额，为能效对标、节能监察提供依据；后者统一原生镁锭碳足迹核算口径，支撑镁产品对接国际绿色贸易规则。')),

    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474750',
                '中国有色金属报', '10-20',
                '联合国启动关键矿产国家支持机制，印尼、赞比亚等 6 国首批入选',
                '9 月联合国在纽约气候峰会宣布启动关键能源转型矿产国家支持机制，印度尼西亚、赞比亚、几内亚、津巴布韦、马达加斯加和尼日利亚 6 国进入首批名单。机制不提供直接贷款，以政策设计、法律框架、环境与社会标准建设为抓手，推动 6 国从原矿出口转向本地加工与制造；刚果（金）等被列入后续 15 国扩展名单。')),

    (CAT_ZC, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202610/t20261020_10339988.htm',
                '全球矿产资源信息系统', '10-20',
                '美国「金库计划」拟向制造商发放最高 10 亿美元关键矿产贷款',
                '美国政府支持的金库计划（Project Vault）准备向寻求关键矿产的美国制造商发放最高 10 亿美元贷款，负责储备的 VaultCo 正与关键矿产供应链 70 多家企业洽谈，首批涉及 10 余家原始设备制造商。该计划今年 2 月启动，获美国进出口银行 100 亿美元贷款和近 20 亿美元私人投资，嘉能可与摩科瑞各出资 5 亿美元；摩科瑞已从刚果（金）运入 1.2 万吨铜。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104169115',
                '上海有色网', '10-20',
                'BNEF：铜矿需 3320 亿美元新投资，否则 2050 年累计缺口 2000 万吨',
                '彭博新能源财经（BNEF）10 月 20 日报告测算，铜矿行业需约 3320 亿美元新增投资才能避免供给冲击：若无大规模资本投入，全球铜市场到 2050 年将累计出现 2000 万吨缺口，并可能 2028 年率先供不应求。到 2050 年电气化相关铜需求将增 89% 至 2330 万吨，矿山总供给则从 2026 年 3000 万吨降至 2570 万吨；新铜矿从立项到投产平均 17 年，缺口最早 2043 年才有望收窄。')),

    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kydt/hyyxdt/202610/t20261020_10339987.htm',
                '全球矿产资源信息系统', '10-20',
                'ICSG：2027 年精炼铜过剩将扩大至 36.8 万吨',
                '国际铜研究小组（ICSG）10 月 14 日发布预测，全球精炼铜市场过剩将延续到 2027 年，过剩量由 2026 年的 10.4 万吨扩大到 2027 年的 36.8 万吨。2026、2027 年精炼铜产量分别增长 0.4% 和 3.4%，视消费量分别增长 1.5% 和 2.5%；矿山铜产量分别增长 1.3% 和 3.1%，印尼、印度和欧盟冶炼厂投产将推动明年精炼铜产量增长。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474762',
                '中国有色金属报', '10-20',
                '镁价逼近近 5 年低位，府谷 99.9% 镁锭成交 1.52 万元/吨',
                '国内镁市持续深度回调，截至 10 月 16 日陕西府谷 99.9% 镁锭主流出厂含税现金报价 1.52 万至 1.525 万元/吨，主流成交 1.52 万元/吨，较上上周六下调 200 元/吨，逼近近 5 年低位。本轮下调自 9 月 8 日开始、持续近 40 天；煤炭、硅铁价格上涨抬升成本，镁厂深度亏损，主产区部分企业已启动停产检修，市场进入震荡筑底阶段。')),

    (CAT_SC, ni('https://news.smm.cn/news/104168810',
                '上海有色网', '10-21',
                '章源钨业下调下半月长单报价，黑钨精矿降至 34.4 万元/标吨',
                '崇义章源钨业 10 月 20 日发布 10 月下半月长单采购报价：55% 黑钨精矿 34.4 万元/标吨、55% 白钨精矿 34.3 万元/标吨，均较上轮下调 2.1 万元/标吨；仲钨酸铵（国标零级）50 万元/吨，较上轮下调 5 万元/吨。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474758',
                '中国有色金属报', '10-20',
                '前三季度我国原镁产量 87.02 万吨，同比增 19.73%',
                '中国有色金属工业协会镁业分会统计，9 月国内原镁产量约 8.61 万吨，环比降 6.11%、同比降 3.8%；1—9 月累计产量 87.02 万吨，同比增 19.73%。分区域看，陕西累计产 60.46 万吨、同比增 32.65%，山西 12.08 万吨降 16.57%，内蒙古 2.45 万吨降 17.79%，新疆 4.32 万吨增 10.2%，产能持续向陕西集聚。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474746',
                '中国有色金属报', '10-20',
                '中矿资源楚梅布冶炼厂多金属回收一期试产，锗回收率取得阶段性成果',
                '中矿资源董事长王平卫一行 9 月 11 日至 15 日赴纳米比亚楚梅布冶炼厂调研，重点查看多金属回收项目一期回转窑试生产情况，该项目锗回收率取得阶段性成果，二期建设正推进。公司要求稳定当前生产指标、持续优化工艺、提升关键金属回收产量，推动技术优势转化为经济效益，争取今年第四季度产生效益。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474737',
                '中国有色金属报', '10-20',
                '西部矿业茶亭铜多金属矿采选工程可研通过评审',
                '西部矿业集团组织召开安徽省宣州区茶亭铜多金属矿（上长村矿段）采选工程可行性研究报告评审会，邀请中国恩菲、矿冶科技集团、长沙矿山研究院等单位专家评审。专家组认为报告章节齐全、内容与深度满足冶金矿山相关规范，同意修改完善后通过评审。该项目为集团「十五五」重点工程，评审通过为后续初步设计、环评报批和开工奠定基础。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474704',
                '中国有色金属报', '10-20',
                '国内首台 60 吨移动式铝棒均热炉通过验收',
                '苏州新长光热能科技有限公司自主研制的国内首台 60 吨移动式铝棒均热炉完成全部研发工作并通过验收，采用国内独有的移动式均热技术，获评 2026 年度中国有色金属建设协会工程设计成果奖。设备由均热炉和冷却炉组成、均采用轨道式「门」形结构，可在不同工作台之间移动，实现「一台炉体共用多个工作台」，研发历时两年。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474705',
                '中国有色金属报', '10-20',
                '招金矿业与金鹏机械签战略合作，锁定海外矿山项目与装备供应',
                '9 月 17 日，招金有色矿业有限公司与烟台金鹏矿业机械有限公司签署战略合作协议。按协议，金鹏机械向招金矿业推介符合投资标准的海外有色金属矿山项目并承担前期筛选与技术研判；同等商务条件下招金矿业优先选择金鹏机械作为项目设备供应商，金鹏提供装备供应、工程技术、安装运维等全周期服务。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-21/1225612740.PDF',
                '巨潮资讯网', '10-21',
                '天齐锂业前三季度预盈 51 亿至 60 亿元，同比增逾 27 倍',
                '天齐锂业 2026 年前三季度业绩预告：预计归属于上市公司股东的净利润 51 亿元至 60 亿元，上年同期 1.80 亿元，同比增长 2734.97% 至 3235.26%；扣非净利润 50.3 亿元至 59.3 亿元，同比增长 6957.09% 至 8219.79%；基本每股收益 3.00 元至 3.53 元。公司称主要锂产品销售均价同比明显增长，对联营公司 SQM 的投资收益亦大幅增长。',
                embed='pdf')),

    (CAT_MA, ni('https://www.mining.com/lithium-africa-weighs-60m-offer-for-springbok-lithium-project',
                'MINING.COM', '10-20',
                'Lithium Africa 收到含 6000 万美元的两份融资报价，Springbok 目标 2027 年投产',
                'Lithium Africa 就南非 Springbok 锂项目收到两份非约束性融资报价，其中一份为 6000 万美元投资：某财富全球 500 强旗下锂加工企业拟持新控股公司 55%，对应项目 100% 估值约 7000 万美元，资金中约 1000 万美元用于矿区钻探、5000 万美元建选厂。公司目标 2027 年上半年作出融资决定、2027 年下半年投产，另与 20 多家潜在对手方洽谈承购与预付款。',
                orig_title='Lithium Africa weighs $60M offer for Springbok lithium project')),

    (CAT_MA, ni('https://www.mining.com/phoenix-tailings-to-build-375m-rare-earth-plant-in-new-york',
                'MINING.COM', '10-20',
                'Phoenix Tailings 投 3.75 亿美元在纽约建稀土分离厂，2028 年满产',
                'Phoenix Tailings 宣布投资 3.75 亿美元在纽约州罗切斯特 Eastman 商业园建设商业规模稀土分离厂「Freedom Separation」，占地 50 万平方英尺，年处理稀土原料 1.8 万吨以上，满产后年产分离稀土氧化物超 4400 吨，2027 年爬产、2028 年满产。项目属其 12 亿美元 Freedom 计划，已获美国战争部战略资本办公室 5 亿美元有条件贷款承诺，纽约州另提供 300 万美元绩效税收抵免。',
                orig_title='Phoenix Tailings to build $375M rare earth plant in New York')),

    (CAT_MA, ni('https://news.metal.com/newscontent/104164719-vedanta-invests-600m-to-double-south-africa-zinc-capacity-to-500000-tons-amid-rising-prices',
                'SMM 国际站', '10-20',
                'Vedanta 投 6 亿美元将南非 Gamsberg 锌产能翻倍至 50 万吨',
                '韦丹塔（Vedanta）宣布投资近 6 亿美元，将其南非 Gamsberg 锌矿年产能翻倍至 50 万吨，南非总统拉马福萨出席扩产仪式。Gamsberg 两个矿体估算资源量 1.86 亿吨矿石；公司目标在印度与南非合计年产锌 300 万吨，其中 Vedanta Zinc International 承担 100 万吨。受矿山供应受限与冶炼扰动推动，LME 三个月期锌较一年前月均价上涨约 23%。',
                orig_title='Vedanta Invests $600M to Double South Africa Zinc Capacity to 500,000 Tons Amid Rising Prices')),

    # ── 🌐 国际矿业动态 ────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/glencore-clears-key-hurdle-for-peru-copper-expansion',
                'MINING.COM', '10-20',
                '嘉能可秘鲁 Coroccohuayco 铜扩建获土地准入，2029 年下半年投产',
                '嘉能可已取得秘鲁南部 Coroccohuayco 铜扩建项目所需的全部土地准入协议，正推进最终许可，目标 2029 年下半年首次产出。该项目将把 Antapaccay 矿区寿命延长至 40 年以上，该矿 2012 年投产、去年产铜约 14.6 万吨；公司今年早些时候已获 MEIA 环境批准，并收购邻近的 Quechua 铜项目。',
                orig_title='Glencore clears key hurdle for Peru copper expansion')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/104169063-rio-tinto-q3-copper-production-204500-mt-basically-flat-yoy-kennecott-flash-converting-furnace-rebuild-completed',
                'SMM 国际站', '10-20',
                '力拓三季度铜产量 20.45 万吨，维持全年 80 万~87 万吨指引',
                '力拓披露 2026 年三季度铜产量 20.45 万吨，同比基本持平、环比降 4%：蒙古奥尤陶勒盖地下矿持续爬产，铜精矿含铜 11.35 万吨、同比增 27%，抵消埃斯康迪达与科尼科特减产。美国科尼科特闪速吹炼炉 6 月底泄漏后约 70 天完成重建、8 月底恢复满负荷，当季阴极铜 1.17 万吨、同比降 10%、环比降 43%。公司维持全年铜产量指引 80 万至 87 万吨。',
                orig_title='Rio Tinto Q3 copper production 204,500 mt, basically flat YoY; Kennecott flash converting furnace rebuild completed')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/104168284-smm-analysis-bhps-copper-output-falls-19-in-q1-fy2027-why-is-full-year-guidance-unchanged',
                'SMM 国际站', '10-20',
                '必和必拓一季度铜产量降 18.8% 至 40.07 万吨，全年指引不变',
                '必和必拓 2027 财年一季度（7—9 月）铜产量 40.07 万吨，同比降 18.8%、环比降 18.5%，主因埃斯康迪达与 Spence 选厂给矿品位按计划下降，叠加检修、恶劣天气与临时停产。埃斯康迪达铜精矿应付铜降约 30% 至 19.79 万吨，阴极铜增 18% 至 5.47 万吨。公司维持 2027 财年铜产量指引 165 万至 180 万吨，后三季度需季均产 41.64 万至 46.64 万吨。',
                orig_title='[SMM Analysis] BHP\u2019s Copper Output Falls 19% in Q1 FY2027. Why Is Full-Year Guidance Unchanged?')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/kfjs/202610/t20261020_10339989.htm',
                '全球矿产资源信息系统', '10-20',
                '马拉维坎甘昆德稀土矿拟 12 月产出首批独居石精矿',
                '澳大利亚林甸资源公司（Lindian Resources）正按计划推进 12 月产出首批独居石精矿，马拉维坎甘昆德稀土矿建设、采矿和调试同步进行：矿石储备已由 9 月的 2.4 万吨增至 14.9 万吨，计划 11 月第一周实现场地通电。项目设计年产 TREO 品位 55% 的精矿 1.53 万吨，分阶段扩产至 12 万吨，第一阶段矿山寿命 45 年。')),
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
