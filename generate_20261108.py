# -*- coding: utf-8 -*-
"""
生成 2026-11-08 矿业资讯速览 index.html（周日）
- 11-07 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-10-10）回补历史条目
- 换入 11-08 采集的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 与 LME 均取 11-06 收盘（周末休市），
  全部由 price_history_detail.json / lme_data.json 现算（零手抄）；
  电解钴保留上日 SMM 值并标注
- 矿权条目：11-08 增补 11 宗（吉林临江六道沟铜、磐石茶尖岭铜镍挂牌；
  新疆阿图什阿克塔什山铅锌、吉勒根都布拉克铁多金属、皮山库尔良铜、
  富蕴也斯克铜、托克逊沙青岭金 5 宗成交；若羌胜利达坂石英岩协议出让；
  徐闻迈报玄武岩、茫崖鸭子沟铜多金属、百色世加那六钛铁砂 3 宗转让），
  已写入 data/news_2026-11.json，由 news-data.js 直出 #rightsCards，不进主列表
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

REPORT = '2026-11-08'
GRAB = '2026-11-08'
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
                         r'\g<1>2026年11月08日 星期日', html)
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
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202611/t20261106_2942008.html',
                '自然资源部', '11-06',
                '毛景文：十五五找矿首盯铜铝镍铬锰，最缺铬钴',
                '中国工程院院士、新一轮找矿突破战略行动全国技术组组长毛景文表示，十五五找矿首盯铜、铝、镍、铬、锰等大宗紧缺矿产，做强钨、锑、钼与稀土稀有矿产，非金属重点为高纯石英、石墨、磷、萤石、钾盐；最缺的是铬、钴，国内钴基本没有独立矿床。国内锂已备案资源量达 3000 多万吨氧化锂，西藏朱诺铜矿资源量达 500 多万吨、巨龙铜矿超过 3000 万吨。')),

    (CAT_ZC, ni('http://gi.mnr.gov.cn/202611/t20261105_2941940.html',
                '自然资源部', '11-05',
                '自然资源部公布非油气矿产勘查方案评审专家库名单',
                '自然资源部公告矿业权出让权限非油气矿产勘查方案评审专家库人员名单。此前该部于 2026 年 9 月 14 日至 18 日对拟入库人员进行公示，公示期间收到的反馈意见已按规定处理，名单以附件形式随公告发布。')),

    (CAT_ZC, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202611/t20261106_10356792.htm',
                '全球矿产资源信息系统', '11-06',
                '机构：美中期选举不改对拉美关键矿产政策',
                '据 BNAmericas 报道，美国中期选举结果不会改变其对拉美关键矿产的战略与政策。美国稀土公司已以 28 亿美元完成对巴西塞拉贝尔德矿业公司的收购，后者此前已获美国国际开发金融公司资金支持；金库计划包含美国进出口银行为购买关键矿产准备的 120 亿美元资金，用于降低供应中断风险与对外依赖。')),

    # ── 🔍 找矿成果与勘查技术 ────────────────────────────────────
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/kfjs/202611/t20261106_10356793.htm',
                '全球矿产资源信息系统', '11-06',
                '挪威稀土公司投 2,400 万欧元建芬恩项目中试厂',
                '挪威稀土公司（REN）批准投资 2,400 万欧元（2,700 万美元）在乌勒福斯建设芬恩稀土项目中试厂，计划 2027 年三季度投运，三年内加工 6,000 吨矿石验证工艺流程。芬恩矿床推定矿石资源量 1.23 亿吨、总稀土氧化物品位 1.35%（氧化物 170 万吨），推测资源量 10.8 亿吨、品位 1.31%（1,420 万吨），总资源量较 2024 年的 880 万吨增长 80%，目标 2030 年代初规模开采。')),

    (CAT_ZK, ni('https://www.cgs.gov.cn/ywdt/ddyw/202611/t20261106_871668.html',
                '中国地质调查局', '11-06',
                '我国初步建成全国地质灾害监测预警网络',
                '自然资源部中国地质调查局披露，截至 2026 年 9 月，全国在运行自动化监测台站超过 7.4 万个、各类监测设备 31 万台套，累计成功预报灾情 444 起、避免人员伤亡 8,027 人。地调局已将无人机自动巡航与 AI 智能分析结合，并基于北斗卫星开展区域短临降雨监测，可预测设备周边约 3 公里、未来 6 小时降雨。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.mining.com/copper-faces-further-slide-after-us-vote-td',
                'MINING.COM', '11-06',
                'TD 证券：中期选举后铜价或再跌 500 美元/吨',
                '民主党在中期选举获胜削弱美国关税预期，LME 三个月期铜上周五跌至约 13,779 美元/吨（每磅 6.25 美元），为 7 月以来最低。TD 证券认为铜价仍将下行，再跌 500 美元/吨不足为奇；美国铜库存约 160 万吨。BMI 预计今年铜均价 13,500 美元/吨、2027 年 12,900 美元/吨，并将 2026 年矿山产量增速由 2.4% 下调至 1.1%。',
                orig_title='Copper faces further slide after US vote: TD')),

    (CAT_SC, ni('https://news.smm.cn/news/104209848',
                '上海有色网', '11-06',
                '电解钴单周涨 2.5 万元/吨，硫酸钴均价回升至 4.41 万元/吨',
                'SMM 数据显示，11 月 6 日电解钴现货报价涨至 23 万至 24 万元/吨、均价 23.5 万元/吨，较 10 月 30 日累计上涨 2.5 万元/吨、涨幅 11.9%；硫酸钴均价 4.41 万元/吨，较 10 月 30 日上涨 100 元/吨。主流冶炼厂出厂价上调至 24 万元/吨，但下游仍按刚需采购，且 10 月以来电解钴产量快速恢复，反弹持续性待观察。')),

    (CAT_SC, ni('https://news.metal.com/newscontent/104210314-shanghai-spot-copper-premiums-surge-to-2615-yuanmt-the-highest-level-in-history-how-tight-is-supply-before-delivery',
                'SMM 国际站', '11-06',
                '上海现货铜升水飙至 2,615 元/吨，创历史新高',
                'SMM 11 月 6 日评估 1# 电解铜现货对沪铜 2611 合约升水 2,480 至 2,750 元/吨，均价 2,615 元/吨，较前一交易日上涨 515 元/吨、创历史纪录；现货均价下跌 605 元/吨至 109,600 元/吨。CU2611 与 CU2612 价差由周初的 900 至 1,000 元/吨扩大至 1,900 至 2,260 元/吨，主因美国方向分流货源与 10 月到货偏弱。',
                orig_title='Shanghai spot copper premiums surge to 2615 yuan/mt, the highest level in history')),

    (CAT_SC, ni('https://news.metal.com/newscontent/104210299-october-refined-zinc-production-fell-more-than-expected-what-are-the-expectations-for-november-smm-analysis',
                'SMM 国际站', '11-06',
                '10 月中国精炼锌产量环比降 3.5%、同比降 12%',
                'SMM 数据，2026 年 10 月中国精炼锌产量环比下降 3.5%、同比下降 12%，前十个月冶炼产量累计同比下降 1.5%、低于预期，其中锌合金产量环比减少 6,000 吨。10 月产量明显不及预期，主要因冶炼厂主动减产的规模大于此前估计。',
                orig_title='October refined zinc production fell more than expected; what are the expectations for November?')),

    (CAT_SC, ni('https://news.metal.com/newscontent/104209992-world-bank-sees-gold-holding-above-4000-through-2028-but-warns-silver-faces-steeper-correction',
                'SMM 国际站', '11-06',
                '世行：金价 2028 年前维持 4,000 美元/盎司上方',
                '世界银行 10 月《商品市场展望》预计今年金价均价 4,600 美元/盎司、较 2025 年上涨 33.6%，并判断金银价格 2027 年前仍处历史高位，但不会重现 2026 年的暴涨与剧烈波动；报告同时警告白银面临更大幅度的回调。',
                orig_title='World Bank sees gold holding above $4,000 through 2028, but warns silver faces steeper correction')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.mining.com/us-dla-commits-2-billion-to-acquire-critical-materials-for-national-defense-stockpile',
                'MINING.COM', '11-06',
                '美国 DLA 承诺 20 亿美元采购关键矿产充实国防储备',
                '美国国防后勤局（DLA）本财年承诺 20 亿美元采购战略与关键矿产，充实国家国防储备，涉及稀土、钨、钛、锑以及高纯铝、五氧化二钒等。DLA 战略材料主管 Eric Mata 称，多数合同意在向国内生产释放定向需求信号，并通过回收、再生、精炼等二次来源强化供应韧性。',
                orig_title='DLA commits $2 billion to acquire critical materials for National Defense Stockpile')),

    (CAT_MA, ni('https://news.smm.cn/news/104205134',
                '上海有色网', '11-06',
                'Pecoy 铜业获 Hudbay 等 4,980 万加元战略投资',
                '11 月 3 日，Pecoy 铜业与 Hudbay 矿业及另一名战略投资者签订认购协议，两家分别认购 1,491 万股和 976 万股，合计融资 4,980 万加元，用于推进秘鲁南部 Pecoy 铜金项目的勘探与开发。Hudbay 表示已在秘鲁运营超过十年，此项投资有助于项目降低风险。')),

    (CAT_MA, ni('https://news.smm.cn/news/104207631',
                '上海有色网', '11-06',
                'Appian 已部署 IFC 1 亿美元矿业承诺的约 70%',
                'Appian Capital Advisory 已将国际金融公司（IFC）矿业投资工具初始 1 亿美元承诺中的约 70% 投出，涉及加纳 Asante Gold 金矿、纳米比亚 Omico Copper 铜项目与巴西 Atlantic Nickel 镍铜钴项目。该工具是 IFC 首个新兴市场金属与矿产投资工具，双方合作规模 10 亿美元，Appian 计划年底前完成剩余资金部署。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475213',
                '中国有色金属报', '11-06',
                '新疆昆仑蓝钻矿业完成股份制改造并正式成立',
                '10 月 30 日，新疆昆仑蓝钻矿业股份有限公司在和田地区洛浦县召开成立大会暨第一次股东会、第一届董事会第一次会议，选举产生第一届董事会与高级管理人员；10 月 31 日取得和田地区市场监督管理局颁发的营业执照，由有限公司整体变更为股份有限公司，并将根据发展需要对接资本市场。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475145',
                '中国有色金属报', '11-06',
                '云南铝箔牵头的新能源车用铝板带轧制技术项目通过验收',
                '中铝铝箔（云南）有限公司牵头承担的云南省重大科技专项“新能源汽车用铝板带轧制技术研究”通过云南省科学技术厅组织的专家组验收。项目历经 3 年攻关，研发硅铁元素平衡调控、铸轧铸嘴小区布流、适应性板形控制 3 项核心工艺，实现铝板带稳定工业化量产，并产出专利、标准与论文等成果。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475206',
                '中国有色金属报', '11-06',
                '中信重工 220 吨刚性矿卡与 90 吨纯电宽体车下线',
                '10 月 20 日，中信重工联合中信装备研制的 220 吨刚性矿卡、90 吨纯电宽体车在河南洛阳下线，同日亮相铲运智能机器人作业系统。220 吨矿卡车高约 7.4 米、额定载重 220 吨、配 1,864 千瓦动力系统，使用年限 15 至 20 年；90 吨纯电宽体车额定载重 90 吨，预留标准化无人驾驶接口。')),

    (CAT_HY, ni('http://disc.szse.cn/download/disc/disk03/finalpage/2026-11-06/8c93ed50-b77b-4e48-8c86-b495ce65de4d.PDF',
                '深圳证券交易所', '11-06',
                '天赐材料子公司与亿纬锂能签 45 万吨电解液长期供货协议',
                '天赐材料公告，全资子公司九江天赐与惠州亿纬锂能签订《长期供货协议》，约定 2027 至 2029 年按预计需求向亿纬锂能供应 45 万吨电解液产品，具体采购量与单价以双方确认的订单、质量协议为准。该协议为框架性协议，若充分履行预计对 2027 至 2029 年度经营业绩产生积极影响。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/regis-resources-reports-fatal-accident-at-duketon-south-gold-operation-in-western-australia',
                'MINING.COM', '11-06',
                'Regis 西澳 Duketon South 金矿发生致命事故，作业暂停',
                'Regis Resources（ASX:RRL）11 月 6 日公告，一名合同制团队员工在西澳 Duketon South 金矿作业中受致命伤，家属已获通知；西澳警方与 WorkSafe 正在调查，公司全面配合。Duketon 矿区作业已暂时停止，公司启动员工援助计划并向受影响人员提供支持。',
                orig_title='Regis Resources reports fatal accident at Duketon South gold operation in Western Australia')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/104188620-smm-analysisvietnam-proposes-aluminium-export-duty-cuts-implications-for-southeast-asian-billet-and-extrusion-trade',
                'SMM 国际站', '10-30',
                '越南拟将铝及铝材出口关税由 5% 降至 1%',
                '据越南工商会（VCCI）披露的政府配套草案，越南拟将未锻轧铝（HS7601）、铝条杆型材（HS7604）与铝线（HS7605）的出口关税由 5% 降至 1%，VCCI 建议进一步降至 0%。若落地将改善越南铝坯与型材供应商的出口净收益，并影响其与中国、马来西亚等地供应商的竞争格局。',
                orig_title='Vietnam Proposes Aluminium Export Duty Cuts, Implications for Southeast Asian Billet and Extrusion Trade')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/104210258-smm-analysis-australian-lithium-miners-shift-focus-from-capacity-growth-to-cost-competition',
                'SMM 国际站', '11-06',
                '澳洲锂矿转向成本竞争，Greenbushes 现金成本约 418 澳元/吨',
                '澳洲锂矿最新季报显示成本分化加剧：Greenbushes 季度现金生产成本约 418 澳元/吨，稳居全球硬岩锂成本曲线低端；Pilgangoora 季度产量创 267.6 千吨纪录、单位 FOB 成本降至 539 澳元/吨（环比降 12%）；Wodgina 三条产线满负荷运行，季度产 102 千吨 SC6，FOB 成本约 674 澳元/吨。',
                orig_title='Australian Lithium Miners Shift Focus from Capacity Growth to Cost Competition')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/104210265-ex-china-rare-earth-supply-chain-acceleration-gains-pace-with-supply-disruptions-and-capacity-rollouts-in-parallel-smm-rare-earth-ex-china-weekly-review',
                'SMM 国际站', '11-06',
                '境外稀土供应链加速，DTEC 拟投 6 亿美元在马来西亚建两座精炼厂',
                'SMM 周报显示，Lynas 马来西亚厂检修约一个月、西澳 Kalgoorlie 厂检修约两周，12 月季度产量承压；美国背景的 DTEC 计划投资 6 亿美元在马来西亚建设两座精炼厂、合计年产能 1 万吨，美国 OSC 向 Phoenix Tailings 提供 5 亿美元贷款建设中间分离与金属化产能。',
                orig_title='Ex-China Rare Earth Supply Chain Acceleration Gains Pace, with Supply Disruptions and Capacity Rollouts in Parallel')),
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
    ('TD 证券', CAT_SC),
    ('毛景文', CAT_ZC),
    ('专家库', CAT_ZC),
    ('中期选举', CAT_ZC),
    ('芬恩', CAT_ZK),
    ('地质灾害', CAT_ZK),
    ('TD 证券', CAT_SC),
    ('电解钴', CAT_SC),
    ('上海现货铜升水', CAT_SC),
    ('精炼锌', CAT_SC),
    ('世行', CAT_SC),
    ('DLA', CAT_MA),
    ('Pecoy', CAT_MA),
    ('Appian', CAT_MA),
    ('昆仑蓝钻', CAT_HY),
    ('云南铝箔', CAT_HY),
    ('中信重工', CAT_HY),
    ('天赐材料', CAT_HY),
    ('Regis', CAT_GJ),
    ('越南', CAT_GJ),
    ('澳洲锂矿', CAT_GJ),
    ('境外稀土', CAT_GJ),
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
