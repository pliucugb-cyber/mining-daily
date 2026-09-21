# -*- coding: utf-8 -*-
"""
生成 2026-09-22 矿业资讯速览 index.html
- 09-21 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-22）回补历史条目
- 换入 09-21~09-22 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 09-21 收盘 + LME 09-21 收盘（东财日K末点=09-21，卡片=走势图口径），
  全部由 price_history_detail.json / lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层，不进主页列表（ky.mnr 09-21 有新公告，另行注入）
- 保留：会展 IIFE / 搜索 / CSV / PDF / 防横跳 / 内联自愈引信
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

REPORT = '2026-09-22'
GRAB = '2026-09-22'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
# 站点名固定「矿业资讯速览」，标题统一写成「矿业资讯速览 · YYYY-MM-DD」。
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年09月\d{2}日 星期.',
                         r'\g<1>2026年09月22日 星期二', html)
assert _n_badge == 1, 'date-badge 替换次数异常: %d' % _n_badge
now = datetime.datetime.now().strftime('%H:%M')
html = re.sub(r'今日新增（2026-09-\d{2} 抓取）', '今日新增（%s 抓取）' % GRAB, html)
html = re.sub(r'id="priceStripNote"[^>]*>2026-09-\d{2} 更新',
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
# 单位同为「元/吨」= 国内盘分组单位 -> 走 unit_class 隐藏重复单位（2026-09-13 契约）
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
    # ---------- 💼 矿权交易 ----------
    (CAT_KQ, ni('http://static.cninfo.com.cn/finalpage/2026-09-22/1225575251.PDF',
                '巨潮资讯网', '09-22',
                '西部矿业全资子公司取得它温查汉铁多金属矿采矿许可证',
                '西部矿业（601168）公告，全资子公司青海淦鑫矿业近日取得青海省自然资源厅核发的采矿许可证，完成格尔木市它温查汉铁多金属矿「探转采」，矿区面积 3.0754 平方公里、地下开采，有效期自 2026 年 8 月 31 日至 2043 年 8 月 30 日。2024 年评审备案的勘探报告显示，该矿保有工业铁矿石资源量 3695.45 万吨、平均品位 mFe 30%，共伴生金 4 吨、铜 1.095 万吨、锌 2.9092 万吨、铅 1201 吨、钼 407 吨、银 770 千克。',
                embed='pdf')),

    # ---------- 🔍 找矿成果与勘查技术 ----------
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202609/t20260921_10319571.htm',
                '全球矿产资源信息系统', '09-21',
                '赞比亚卢安夏西铜矿启动钻探 计划验证 3—4 个靶区',
                '据矿业周刊报道，多伦多上市企业科瑞克斯铜业（Koryx Copper）宣布赞比亚卢安夏西与姆彭戈韦项目野外工作启动：卢安夏西 9 月底前开始初步金刚石钻探，计划以 2500 米钻探验证 3—4 个靶区，12 月中旬完成；钻孔为斜孔，用于验证地表地球化学异常与激发极化特征及 100—250 米深构造靶区。姆彭戈韦项目 11 月初前完成后续与加密土壤采样、约 3000 件样品。公司已把所持科瑞克斯铜业赞比亚公司股权由 51% 提升至 80%，该公司持有铜带省两个项目全部股权。')),
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202609/t20260921_10319572.htm',
                '全球矿产资源信息系统', '09-21',
                '大洋金属巴西塞拉内格拉稀土项目见矿 122 米 TREO 1.2%',
                '据矿业新闻网报道，大洋金属公司（Oceana Metals）对巴西塞拉内格拉项目历史钻孔岩心重新采样分析，已将已知稀土矿化面积扩大到 4.5 平方公里、较此前翻倍，认为项目可能达到「地区规模」。主要见矿结果为 50 米深处见矿 122 米、总稀土氧化物品位 1.2%，含 32 米厚、品位 2.7% 矿段，TREO 最高 4.79%、磁体稀土氧化物 1.19%；另一孔 18.9 米深处见矿 106 米、TREO 1%。公司已对 68 个老钻孔采样、完成 45 孔约 4750 米，另有两台钻机在 1.5 公里×1.5 公里中心区验证。')),
    (CAT_ZK, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0921/62048.html',
                '中国有色金属工业协会', '09-21',
                '中国恩菲难处理金矿提金技术突破 金浸出率升至 95% 以上',
                '中国恩菲工程技术有限公司自主开发的改进氧压（POX）预处理协同浸出技术在某项目应用后，将金浸出率提高至 95% 以上，使该项目每年可多回收 15% 的黄金。公司湿法冶炼研发团队构建了「POX+特效协浸」技术和药剂体系，攻克难处理包裹金的解离难题，工艺简单、能耗低、无危废产生，已在国内外多个矿源的小试及扩大试验中验证。全球三分之二以上金矿属难处理资源。')),
    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104126920-smm-news-argosy-minerals-completes-rincon-crystallisation-tests-lithium-chloride-yield-above-99',
                'SMM 国际站', '09-22',
                '阿根廷 Rincon 锂项目完成结晶试验 氯化锂收率超 99%',
                '阿根廷矿业公司 Argosy Minerals 宣布，其位于萨尔塔省、规划产能 1.2 万吨/年的 Rincon 锂项目完成结晶试验，工艺设计氯化锂收率超 99%，产品质量达到拟定指标，可产出规格级无水氯化锂。技术方将据此于 2026 年 10 月完成结晶单元的可行性基础工程包。项目仍需各主要工序经实验室与中试验证后方能完成最终可行性研究，1.2 万吨/年产能尚未进入建设阶段；公司持有 Rincon 77.5% 权益。',
                orig_title='[SMM News] Argosy Minerals Completes Rincon Crystallisation Tests, Lithium Chloride Yield Above 99%')),

    # ---------- 📜 政策与监管 ----------
    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474169',
                '中国有色金属报', '09-21',
                '南美四国签署战略矿产联合声明 锂储量占全球探明半数以上',
                '8 月 28 日，智利、阿根廷、玻利维亚与秘鲁在圣地亚哥签署战略矿产联合声明，标志南美核心资源国由分散经营转向区域协同，并设常设工作组推进地质资料互通、监管标准衔接与公共政策协调。四国涵盖「锂三角」主体及全球主要铜产带，锂储量占全球已探明半数以上；宣言未写入产量配额或出口禁运等强制条款，但把供应链安全议题提升至国家间层面。智利矿业部长马斯提出未来 10 年全球关键矿产需求将增长 400%~600%。')),
    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474087',
                '中国有色金属报', '09-17',
                '美国启动铟锰镁钛 4 种关键金属招标 覆盖采选冶全链条',
                '美国国防部下属国防工业基地联盟 8 月 21 日发布招标公告，面向国内企业征集铟、锰、镁、钛 4 种关键金属投资方案，提交截止日期为 2026 年 9 月 17 日，覆盖采矿、选冶、精炼、合金制造到回收全产业链；该联盟成员网络覆盖 1500 多家企业、大学和防务承包商。此前 2026 年 2 月该联盟曾就砷、铋、钆、锗、石墨等 13 种矿产征集提案，单个项目潜在开发资金规模为 1 亿至 5 亿多美元。')),
    (CAT_ZC, ni('https://news.metal.com/en/newscontent/104126927-india-eases-environmental-rules-for-mining-overburden-rejects-utilization-and-sale',
                'SMM 国际站', '09-22',
                '印度放宽矿山剥离物与表外矿的环保审批要求',
                '印度环境、森林与气候变化部放宽了矿山剥离物、废石与表外矿利用或销售的环保审批要求，矿企可申请对既有环评（EC）作修订，而无须重新申请环评。利用剥离物与废石须在既有 EC 容量内、具备批准的采矿计划与修订后的闭坑计划，并经印度矿业局核准与邦政府事先许可；采区内历史遗留表外矿存量亦可经 EC 修订后利用。该调整有望减少审批延误、提高资源回收率，但重新处理遗留剥离物可能产生无组织粉尘与废水，需相应修订环境管理计划。',
                orig_title='India Eases Environmental Rules for Mining Overburden, Rejects Utilization and Sale')),

    # ---------- 📊 市场与价格 ----------
    (CAT_SC, ni('https://news.smm.cn/news/104126905',
                '上海有色网', '09-21',
                'IAI：8 月全球原铝产量同比下降 1.7% 至 617.2 万吨',
                '国际铝业协会（IAI）9 月 21 日公布数据显示，8 月全球原铝产量同比下降 1.7% 至 617.2 万吨，日均产量 19.91 万吨；除中国和未报告地区外，8 月全球原铝产量 208.4 万吨、日均产量 6.72 万吨。')),
    (CAT_SC, ni('https://news.smm.cn/news/104126901',
                '上海有色网', '09-21',
                '智利海关：8 月铜出口量 11.90 万吨 其中对华 1.50 万吨',
                '智利海关公布数据显示，智利 8 月铜出口量为 119,044 吨，当月对中国出口铜 15,010 吨；8 月铜矿石和精矿出口量为 1,279,179 吨，其中对中国出口铜矿石和精矿 729,567 吨。')),
    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474168',
                '中国有色金属报', '09-21',
                '全球锌精矿供应进入收缩周期 加工费深度转负',
                '国际铅锌研究小组（ILZSG）数据显示，2025 年全球锌精矿产量 1258.6 万吨、同比增加 64.1 万吨（增速 5.4%），预计 2026 年为 1255 万吨、同比下降 0.3%。嘉能可将 2026 年锌产量指引下调至 70 万—74 万吨（2025 年实际 96.94 万吨），上半年自产锌 36.56 万吨、同比下降 21%。9 月初进口锌精矿 TC 为 -120 美元/吨、国内北方大区为 -1500 元/吨，多数冶炼厂加工环节由盈转亏；全球前十大锌矿中有 7 座将于 2029—2036 年陆续关闭，涉及产能约 216 万吨/年。')),
    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474167',
                '中国有色金属报', '09-21',
                '国际铜价「急刹车」 COMEX 与 LME 价差收敛约 92%',
                '受供给约束及潜在关税预期影响，8 月下旬以来 COMEX 铜期价持续走高，9 月 9 日盘中触及 689.4 美分/磅（约合 15197 美元/吨）历史新高，LME 三个月铜期价一度触及 14875 美元/吨。9 月 10 日以来国际铜价大幅回撤，COMEX 与 LME 价差自 8 月 25 日的 783 美元/吨收敛至 9 月 15 日的 62 美元/吨、收窄约 92%。美国 8 月 PPI 同比上涨 5.4%、核心 CPI 环比上涨 0.3%（高于预期 0.2%），加息预期增强压制大宗商品估值；截至 9 月 8 日当周 COMEX 铜非商业净多持仓升至 9 万手以上。')),
    (CAT_SC, ni('https://news.metal.com/en/newscontent/104126942-smm-chromium-flash-global-chrome-ore-departures-rise-3475-wow-to-624900-mt-maputo-extends-gains',
                'SMM 国际站', '09-22',
                '全球铬矿发运量周环比增 34.75% 至 62.49 万吨',
                'SMM 数据显示，截至 9 月 18 日当周全球主要出口港铬矿发运量合计 624,900 吨，周环比增长 34.75%，连续第二周回升。其中马普托港由 438,700 吨增至 555,600 吨、增长 26.65%，占总量约 89%；梅尔辛港由 25,200 吨增至 69,300 吨。理查兹湾与贝拉港当周零发运，区域出口进一步向马普托集中。',
                orig_title='[SMM Chromium Flash] Global Chrome Ore Departures Rise 34.75% WoW to 624,900 mt, Maputo Extends Gains')),

    # ---------- 🏭 行业动态 ----------
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0921/62049.html',
                '中国有色金属工业协会', '09-21',
                '北方矿业完成印尼 KSK 铜金锌多金属项目收购交割',
                '9 月 9 日，北方矿业有限责任公司与 Asiamet Resources Limited（AIM：ARS）正式完成印尼 KSK 铜金锌多金属项目收购交割。交割完成后交接团队已进场，开展公司流程、体系梳理及人员、财务、资产交接；北方矿业董事长耿一带队赴 KSK 项目现场调研，实地踏勘规划首采区、工业场地及其他潜力增储靶区。')),
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0921/62052.html',
                '中国有色金属工业协会', '09-21',
                '中铝科学院建成国内首台套短流程连续气雾化制粉生产线',
                '中铝科学技术研究院与威拉里股份公司联合开发国内首台套短流程连续气雾化制粉装备，已在重庆国创院完成生产线建设，通过「熔炼—保温—雾化」协同机制解决粉体批次稳定性差与工业化难以连续生产两大难题，粉材具备成分均匀、低空心粉率、高球形度等特点。中铝科学院已完成 100 千克 AlSi10Mg 合金粉体销售合同签订，并与威拉里共建「增材制造联合创新平台」。')),
    (CAT_HY, ni('https://www.chinania.org.cn/html/xiehuidongtai/xiehuidongtai/2026/0921/62053.html',
                '中国有色金属工业协会', '09-21',
                '葛红林：全球再生金属占比升至 36% 中国产量占 32%',
                '中国有色金属工业协会会长葛红林撰文指出，「十四五」期间全球再生铜、铝、铅产量累计达 2.6 亿吨、较「十三五」增长 24%，再生金属在有色金属总产量中的占比由 2020 年的 32% 提升至 2025 年的 36%，5 年间累计节约矿产资源 55 亿吨、减少二氧化碳排放 28 亿吨。中国产量占全球比重 32%，美国年废铜、废铝出口规模分别约 90 万吨和 200 万吨，东南亚崛起为全球再生原料核心中转枢纽。')),
    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-09-22/1225575856.PDF',
                '巨潮资讯网', '09-22',
                '中矿资源赞比亚 Kitumba 铜矿项目全线贯通投料试生产',
                '中矿资源（002738）公告，赞比亚当地时间 2026 年 9 月 21 日，中央省 Kitumba 铜矿项目采矿工程、选矿工程完成生产准备并正式全线贯通投料试生产，本阶段产品为铜精矿。项目位于蒙布瓦地区，矿权面积约 248.17 平方公里，采选设计产能年处理原矿 350 万吨、冶炼设计产能阴极铜 3.5 万吨/年，达产年平均产出阴极铜 3.3 万吨、铜精矿 5.5 万吨，设计运营期 15 年、总产铜 57.02 万吨；冶炼工程预计 2026 年四季度完成投产准备或试生产、2027 年一季度正式投产。',
                embed='pdf')),

    # ---------- 🌐 国际矿业动态 ----------
    (CAT_GJ, ni('https://www.mining.com/copper-prices-bounce-as-us-runs-out-of-warehouse-space',
                'MINING.COM', '09-22',
                '美铜库存告急 洋山铜溢价创近四年新高',
                '铜价周一连续第五个交易日上涨：COMEX 12 月期铜盘中最高涨 3.3% 至 6.8410 美元/磅（约合 14940 美元/吨），LME 三个月铜一度触及 14710.50 美元/吨。上周五洋山铜溢价收于 124 美元/吨、创近四年最高，周一回落至 119 美元/吨；LME 现货铜对三个月转为 26 美元/吨升水，一周前尚为贴水 86 美元。LME 库存 25.59 万吨中有 11.545 万吨（45%）为已注销仓单，实际可交易库存降至 13.3725 万吨；COMEX 仓库铜库存 69.6204 万吨，占全球交易所监测铜库存约 69%，新奥尔良港库容基本用满，9—10 月还有约 10 万吨非洲与南美铜到货。',
                orig_title='Copper prices bounce as US runs out of warehouse space')),
    (CAT_GJ, ni('https://www.mining.com/almonty-clears-final-hurdle-to-start-producing-tungsten-at-south-korea-mine',
                'MINING.COM', '09-22',
                'Almonty 韩国桑东钨矿获批商业生产 年产能约 20 万 MTU',
                'Almonty Industries（NASDAQ: ALM）获韩国政府批准，可在桑东钨矿商业加工钨精矿，预计年产约 20 万公吨度（MTU）。韩国主管部门 9 月 17 日签发矿业设施检查证书，授权其运营破碎与加工设施并在境内外销售钨精矿，这是一期投产前最后一道监管门槛。桑东钨矿 1990 年代初因价格低迷停产，公司自 2015 年收购项目以来已投入逾 1 亿美元重建；一期逾 90% 产量已与奥地利 Plansee 集团旗下 Global Tungsten & Powers 签订 21 年承购协议，合计 441 万 MTU、每年不低于 21 万 MTU。',
                orig_title='Almonty clears final hurdle to start producing tungsten at South Korea mine')),
    (CAT_GJ, ni('https://www.mining.com/larvotto-begins-gold-antimony-production-at-hillgrove',
                'MINING.COM', '09-22',
                'Larvotto 澳洲 Hillgrove 金锑矿投产 可供全球约 7% 锑需求',
                'Larvotto Resources（ASX: LRV）位于新南威尔士州的 Hillgrove 矿产出首批金锑精矿，预计在 8 年初始矿山寿命内年均产锑约 4900 吨、黄金约 4.05 万盎司，有望贡献全球约 7% 的锑需求。公司已就锑与 Wogen Resources、就金精矿与嘉能可签订具约束力承购协议，当前重点是将其产能爬坡至铭牌产能并延长矿山寿命。',
                orig_title='Larvotto begins gold, antimony production at Hillgrove')),
    (CAT_GJ, ni('https://www.mining.com/greenland-mines-says-us-pact-could-strengthen-mineral-supply',
                'MINING.COM', '09-22',
                'Greenland Mines 提议建「北大西洋关键金属走廊」',
                'Greenland Mines（NASDAQ: GRML）称美国、丹麦与格陵兰新达成的安全协议凸显该地区关键矿产的重要性，并提出建设「北大西洋关键金属走廊」，把格陵兰资源与盟国下游加工及工业基础设施衔接。公司称其西南部 Sarfartoq 项目含钕镨稀土，在 2025 年消费水平下可提供中国以外精炼钕镨氧化物需求的 34%；东南部 Skaergaard 项目含钯、铂、金与钒。公司已就 Sarfartoq 申请新增许可，若获批其在稀土碳酸岩区的面积将增加一倍以上。',
                orig_title='Greenland Mines says US pact could strengthen mineral supply')),

    # ---------- 💰 并购与投资 ----------
    (CAT_MA, ni('https://www.mining.com/capstone-copper-to-sell-mexican-mine-to-luca-mining-for-up-to-385m',
                'MINING.COM', '09-21',
                'Capstone 至多 3.85 亿美元出售墨西哥 Cozamin 铜矿',
                'Capstone Copper（TSX: CS）将墨西哥 Cozamin 铜银锌铅矿出售给 Luca Mining（TSX-V: LUCA），总对价至多 3.85 亿美元，含交割时现金 2.75 亿美元、Luca 股票 1500 万美元、交割一周年递延对价 3500 万美元，以及挂钩 2027—2029 年铜价的至多 6000 万美元或有对价。Cozamin 位于萨卡特卡斯州，2023—2027 年预计年均产铜 2.4 万吨、白银 170 万盎司，C1 成本 1.46 美元/磅。交易预计第四季度完成，仍需交易所与墨西哥国家反垄断委员会批准。',
                orig_title='Capstone Copper to sell Mexican mine to Luca Mining for $385M')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-22/1225575158.PDF',
                '巨潮资讯网', '09-22',
                '藏格矿业收购刚果（布）Kanga Potash 92% 股权签署买卖协议',
                '藏格矿业（000408）公告，全资子公司藏格矿业发展与应城市新都化工有限责任公司出资设立藏格联合资源有限公司，后者以 171,046,592 美元（折合人民币约 11.57 亿元，不含交易税费）收购 Kanga Potash 92% 股权，近日已与 Kanga Investments Ltd.、Sarmin Group Inc. 等 12 名卖方签署《股份买卖协议》。按 75% 持股比例测算公司需承担投资额 128,284,944 美元（约 8.68 亿元），交易完成后将间接持有 KP 公司 69% 股权并纳入合并报表；尚需通过刚果共和国矿业部审查及国家发改委、商务部等审批。',
                embed='pdf')),
    (CAT_MA, ni('https://news.metal.com/en/newscontent/104126912-smm-chromium-flash-fs-mining-breaks-ground-on-500m-chrome-smelter-and-power-project-in-zimbabwe',
                'SMM 国际站', '09-22',
                '南非投资者在津巴布韦开建 5 亿美元铬铁冶炼及电力项目',
                '南非投资者 FS Mining 在津巴布韦南马塔贝莱兰省 Insiza 地区启动 5 亿美元铬项目，分阶段建设冶炼厂、配套发电与大型选矿设施，一期目标为 16.5 兆瓦冶炼厂及配套 25 兆瓦电厂。项目采用自备电力方案以绕开当地电网对冶炼产能的约束；冶炼目标产能、建设周期与融资结构暂未披露。此前该公司已与 Tofee Mining 等合作完成同区约 240 万美元、22 公里道路修复工程。',
                orig_title='[SMM Chromium Flash] FS Mining Breaks Ground on $500m Chrome Smelter and Power Project in Zimbabwe')),
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

# ============ 3.6 数字落地校验（2026-09-14 新增，复用 verify_numbers） ============
# 每条摘要的数字须能在源文（候选池/月库）找到，防 LLM 抄错数字。
# 候选池未落盘或未开 --fetch-detail 时源文基准为空 -> 自动 skip（不阻断生成）。
# 生产守门：置 VERIFY_NUMBERS_STRICT=1 时未落地即抛异常（CI / 上线前卡点）。
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

# ============ 7. div 收支自检（2026-09-11 破损教训） ============
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
