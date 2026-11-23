# -*- coding: utf-8 -*-
"""
生成 2026-11-23 矿业资讯速览 index.html（周一）
- 11-21 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30）回补历史条目
- 换入 11-23 采集的条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 与 LME 均为 11-20 收盘，全部由
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

REPORT = '2026-11-23'
GRAB = '2026-11-23'
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
                         r'\g<1>2026年11月23日 星期一', html)
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
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202611/t20261123_2943092.html',
                '自然资源部', '11-23',
                '自然资源部规范矿业权管理全流程，明确42条政策措施',
                '自然资源部 11 月 19 日发布《关于规范矿业权管理有关事项的通知》，围绕矿业权出让、矿业权设立与变更、勘查采矿许可管理等 8 个方面明确 42 条政策措施，自 2026 年 12 月 15 日起施行、有效期 5 年。通知首次建立战略性矿产探矿权出让计划制度，要求依据矿产资源规划、结合战略性矿产新增资源量任务制定年度出让计划，并细化部省两级出让登记权限、完善油气矿产探矿权续期与探采合一政策。')),

    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475404',
                '中国有色金属报', '11-18',
                '再生铅纳入上期所铅期货交割，PB2703成首个参与合约',
                '上期所修订铅期货合约及业务细则，将再生铅正式纳入期货交割体系：PB2702 合约交割完成后，符合标准的再生铅锭可注册为替代交割品仓单，PB2703 成为再生铅参与交割的首个合约，替代交割品贴水 150 元/吨。再生铅目前约占国内铅产能 50%，「十四五」以来累计产量 1435 万吨、较「十三五」增长 34%。')),

    # ── 🔍 找矿成果与勘查技术 ───────────────────────────────────
    (CAT_ZK, ni('https://www.mnr.gov.cn/dt/ywbb/202611/t20261118_2942791.html',
                '自然资源部', '11-18',
                '「梦想」号完成2000米级深海无隔水管泥浆回收系统海试',
                '「梦想」号大洋钻探船历时 33 天完成我国首套 2000 米级深海无隔水管泥浆回收循环钻井系统海试，在南海北部 142.7 米与 2004.8 米水深完成全流程作业和 5 个回次取心，刷新同类系统 1419 米的国际最大作业水深纪录。至此该船 4 种钻探模式全部通过功能验证，形成自主超深水钻探技术体系，深海取心能力提升至 5000 米级。')),

    (CAT_ZK, ni('https://news.smm.cn/news/PDGZJFOJDRLGERRR6552D445GUEGUA4IMNWOWBY',
                '上海有色网', '11-22',
                '巴西佩莱南稀土项目地表见富矿，TREO品位最高16.6%',
                '巴西稀土公司（BRE）佩莱南（Pele South）项目初步钻探自地表见矿 6 米、总稀土氧化物（TREO）品位 13.2%，其中含 4 米厚、品位 16.6% 的富矿体；另见矿 14.3 米、品位 11.2%。矿带沿走向长至少 2.5 公里，镝铽钆钇等重稀土含量高并伴生钪，矿化集中于风化层、开发条件较好，公司正施工金刚石钻探验证基底岩，勘探目标接近或超过阿尔托山矿床（浅部资源量 2520 万吨、TREO 品位 1%）。')),

    (CAT_ZK, ni('https://news.smm.cn/news/3NMUC4OOWE72LHB3U3J35Y6TFYEPNJVHFGBVTCI',
                '上海有色网', '11-19',
                'Phoenix在加拿大BC省Lexington老矿区钻遇169米铜金矿体',
                'Phoenix Metals 在不列颠哥伦比亚省南部 Lexington 矿区施工的 LXDDH-26-001 孔自 41 米见矿 169 米，金品位 1.02 克/吨、铜 0.22%、银 3.79 克/吨；另一孔自 8.5 米见矿 233.5 米，金 0.26 克/吨、铜 0.14%。公司正评估这处老旧地下采区是否具备露天开采条件，矿体真实厚度尚未确定。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/4HRBNX4WS5GIRVDZ6JOJQJI4G5XMO72LQCZPUJY',
                '上海有色网', '11-21',
                '伦铜周线六连跌、周跌幅9.23%，金银铜锡集体重挫',
                '上周五（11 月 20 日）LME 六金属全线下跌，伦铜跌 2.9%、周线六连跌累计 9.23%，伦锡周线跌 12.21%，COMEX 白银周线跌 16.37%、盘中最低触及 40.615 美元/盎司，COMEX 黄金周线跌 8.94%。国内沪铜周线跌 12.03%、沪锡跌 8.84%、沪银跌 16.77%，主因 AI 板块交易降温叠加美联储 12 月加息预期升温。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475386',
                '中国有色金属报', '11-17',
                '高盛：2027年铜价15400美元/吨的预测面临下行风险',
                '高盛 11 月 13 日报告表示，美国中期选举后 AI 板块相关持仓下跌、美国关税预期下调，其 2027 年铜价 15400 美元/吨的预测面临下行风险，主要风险源于市场头寸而非实物需求。若持仓维持当前水平，2027 年铜价均值或在 14600 美元/吨左右；若今年美国累积的大部分库存回流全球其他地区，铜价还存在进一步下行空间。')),

    # ── 💼 矿权交易 ─────────────────────────────────────────────
    (CAT_KQ, ni('https://ky.mnr.gov.cn/xycrgs/tkq/202611/t20261121_10370000.htm',
                '矿业权市场', '11-20',
                '内蒙古乌拉特前旗邬二湾铁矿深部及上部探矿权拟协议出让，面积0.4224平方公里',
                '巴彦淖尔市自然资源局公示，拟以协议方式向乌拉特前旗大佘太牧场鑫正矿业有限责任公司出让邬二湾矿区（白山沟、召沟、花栏墙）铁矿深部及上部勘查探矿权，面积 0.4224 平方千米，勘查矿种为铁矿。协议出让理由为矿权人利用原有生产系统进一步勘查开采已设采矿权深部或上部资源，公示期 11 月 23 日至 12 月 4 日。')),

    (CAT_KQ, ni('http://static.cninfo.com.cn/finalpage/2026-11-21/1225680978.PDF',
                '巨潮资讯网', '11-21',
                '白银有色郝泉沟金矿采矿权转让全资子公司进入公示',
                '白银有色公告，将郝泉沟金矿采矿权转让给全资子公司甘肃红鹭黄金的事项已获董事会审议通过，相关信息近期正在公示。经多年合作勘查，矿区保有金矿石量 284.54 万吨、金金属量 15.72 吨、伴生银金属量 12.28 吨，采选生产规模提升至 30 万吨/年、采矿权面积增至 0.6811 平方公里，有效期至 2036 年 2 月。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475481',
                '中国有色金属报', '11-23',
                '2026亚洲铜业周在沪举行，聚焦铜市结构性再平衡',
                '11 月 17 日，由智利铜与矿业研究中心与中国有色金属工业协会共同主办的 2026 亚洲铜业周在上海举行，聚焦铜价高位运行下的矿山扰动、铜加工费负值、下游成本上升与替代加速等结构性问题。会议同期举办 CRU 铜业会议、CEO 圆桌与亚洲铜晚宴，中国铝业、中国五矿、江铜、紫金矿业、自由港、英美资源、嘉能可等国内外企业参与。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475392',
                '中国有色金属报', '11-17',
                '前10月国内原镁产量96.12万吨，同比增长17.51%',
                '中国有色金属工业协会镁业分会统计，10 月国内原镁产量约 9.1 万吨、环比增 5.69%、同比微降 0.2%；1—10 月累计 96.12 万吨、同比增 17.51%。区域分化明显：陕西累计 66.82 万吨、同比增 28.65%，为全国主力产区；山西 13.25 万吨、降 16.98%，内蒙古 2.65 万吨、降 16.93%，新疆 4.84 万吨、增 5.68%。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://news.smm.cn/news/J6QR6GNJJBQVMCURMMDHWMURQWW3VXRFKLR7PJA',
                '上海有色网', '11-22',
                '罗马资源刚果（金）Kalayi锡矿投产，锡石精矿品位75%',
                '伦敦上市企业罗马资源（Rome Resources）宣布，其在刚果（金）的 Kalayi 锡矿项目已初步投产，累计产出约 2000 公斤锡品位 58.5%（相当于锡石品位 75%）的锡石精矿，将在瓦利卡莱当地设施销售。选矿仅需简单分选与溜槽洗选、无需浮选；矿化自地表开始，公司已启动首批四个钻场向深部延伸，此前 KBDD025、KBDD033 孔分别见矿 9.5 米和 19.5 米。')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/7LDZQNY5YY26UK7JI6XH4EOBMNLFESHOJQCGHDY-vale-indonesia-targets-mechanical-completion-of-bahodopi-hpal-project-in-q1-2027',
                'SMM 国际站', '11-20',
                '淡水河谷印尼Bahodopi HPAL项目目标2027年一季度机械竣工',
                '淡水河谷印尼公司首席执行官 11 月 20 日表示，中苏拉威西莫罗瓦利 Bahodopi 高压酸浸（HPAL）项目目标 2027 年一季度实现机械竣工。项目由该公司与 GEM、韩国 EcoPro 合资的 BNSI 建设，处理 Bahodopi 矿山褐铁矿生产镍钴混合氢氧化物沉淀（MHP），综合项目完成率 42.67%、HPAL 装置完成率 43.70%。此外 Pomalaa HPAL 项目拟于 2026 年 12 月举行投产仪式。',
                orig_title='Vale Indonesia Targets Mechanical Completion of Bahodopi HPAL Project in Q1 2027')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/EPEZYVMFXGLRWHO7LQ47QJ5BJWKKNRCBVOLKSNA-indonesias-merdeka-battery-materials-posts-record-q3-revenue-and-attributable-net-profit',
                'SMM 国际站', '11-20',
                '印尼Merdeka Battery三季度营收7.32亿美元创纪录',
                '印尼 Merdeka Battery Materials（MBMA）三季度营收同比增 138% 至 7.32 亿美元，归母净利润增 372% 至 0.92 亿美元，EBITDA 增 276% 至 2.38 亿美元，主因 SCM 镍矿产量创纪录及硫酸业务贡献提升。ESG 项目前 9 个月产出 MHP 含镍 19767 吨、9 月产能利用率达 96%；设计年产 9 万吨镍的 SLNC 高压酸浸项目三季度完成调试、9 月底首次投料。',
                orig_title='Indonesia\u2019s Merdeka Battery Materials Posts Record Q3 Revenue and Attributable Net Profit')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://news.metal.com/newscontent/TWDKVECFKHIAKYIJ4QO4EAILUPRTUSZAHMWFGEQ-cmoc-completes-installation-of-two-autoclaves-at-kfm-copper-cobalt-mine-phase-ii-in-the-drc',
                'SMM 国际站', '11-20',
                '洛阳钼业刚果（金）KFM铜钴矿二期两台高压釜安装完成',
                '洛阳钼业（CMOC）11 月 20 日表示，刚果（金）KFM 铜钴矿二期两台高压釜已运抵现场并完成安装。二期建设投资预算 10.84 亿美元，计划 2027 年投产、服务年限 15 年，年采选硫化矿 726 万吨，满产后年均新增铜产能约 10 万吨。公司持有 KFM 71.25% 权益，一期已于 2023 年达产，二期配套的 N\u2019zilo II 水电站大坝已开始首仓混凝土浇筑。',
                orig_title='CMOC Completes Installation of Two Autoclaves at KFM Copper-Cobalt Mine Phase II in the DRC')),
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
