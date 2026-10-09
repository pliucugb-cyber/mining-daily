# -*- coding: utf-8 -*-
"""
生成 2026-10-09 矿业资讯速览 index.html（周五）
- 10-08 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-10）回补历史条目
- 换入 10-09 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-08 收盘 + LME 10-09 收盘，全部由
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

REPORT = '2026-10-09'
GRAB = '2026-10-09'
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
                         r'\g<1>2026年10月09日 星期五', html)
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
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202610/t20261009_10330913.htm',
                '全球矿产资源信息系统', '10-09',
                '科特迪瓦邦杜库金矿钻探见富矿',
                '全球矿产资源信息系统援引 Miningnews.net 网站报道，达拉鲁金属公司（Dalaroo Metals）在科特迪瓦威尔弗雷德（Wilfred）靶区首次反循环钻探取得高品位基岩金矿发现。邦杜库金岭（BGR）项目头两个钻孔主要见矿情况：一个孔在 63 米深处见矿 18 米、金品位 7.31 克/吨，其中 78 米深处见矿 1 米、金品位 15.9 克/吨，113 米深处见矿 16 米余、金品位 1.46 克/吨；另一个孔自地表见矿 23 米、金品位 2.14 克/吨，为氧化矿。公司首席执行官约翰·摩根表示，沿相反方向钻探的两个孔都见到矿。截至目前仅完成 9 个孔、进尺 1,750 米，钻机正钻进第 10 个孔，初步计划 24 个孔、4,200 米，为后续 12,000 米钻探提供方向。该矿与硅化火山碎屑岩、石英—硫化物矿脉及黄铁矿有关，可指导沿长 7 公里矿带后续钻探。项目沿比里米安绿岩带分布，距因代沃矿业（Endeavour Mining）450 万盎司储量的坦达金矿约 35 公里，并含 9 公里手工采矿区域。',
                )),

    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474438',
                '中国有色金属报', '10-09',
                '江西地质八队以“就矿找矿”破解永平铜矿资源接续难题',
                '中国有色金属报刊发长篇纪实报道，江西省地质局第八大队六十年接续攻关永平铜矿，创新运用“顺藤摸瓜、主次转化、平行侧列”三大勘查方法实现多次增储。1963—1966 年，时任赣东北铜矿地质会战总工程师朱训提出“就矿找矿”理论，精准布置首批验证钻孔，单孔成功揭露 40 米厚工业铜矿体，推动主攻矿种由铁转为铜硫；1978—1982 年探明厚层铜钨共生矿体，1984 年提交勘探报告，将钨由伴生资源升级为主攻矿种；2016—2019 年启动全域深部扩界勘查，融合三维地质建模、高精度深部物探与系统化深部钻探，将矿山勘查最低标高拓展至 -255 米，新增大量铜、硫、钨资源储量。外围护驾山、龙头岗、王坞等片区亦有突破，王坞矿区通过“上铜下钼”复式成矿模式探明中型钼矿床；2023—2025 年江铜地勘公司联合第八大队完成十字头钼矿深部精细补充勘查并完成资源储量备案。永平矿田由此形成“铜硫为主、钨钼为辅”大型多金属综合格局。',
                )),

    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104146984-smm-flash-newssilver-x-advances-nueva-recuperada-expansion-targeting-1000-tonnes-per-day-in-q4',
                'SMM 国际站', '10-09',
                'Silver X 推进秘鲁 Nueva Recuperada 扩建，四季度目标日产千吨',
                'SMM 国际站报道，Silver X 于 10 月 8 日公布，其秘鲁 Nueva Recuperada 项目三季度处理矿石 54,681 吨，同比增长 63%、环比下降 12%，日均处理 594 吨。扩建设备安装制约了处理量，同时开采矿量增加令银、铅、锌入选品位下降。公司预计四季度达到日产 1,000 吨。入选矿石中的锌、铅金属量同比分别增长 42% 和 20%。',
                orig_title='Silver X Advances Nueva Recuperada Expansion, Targeting 1,000 Tonnes per Day in Q4')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474449',
                '中国有色金属报', '10-09',
                '各国关键矿产领域合作紧锣密鼓进行中',
                '中国有色金属报刊文梳理各国关键矿产领域合作动向。报道称，随着全球能源转型推进，铜、钴、锂、锡等战略性矿产需求持续攀升，主要资源国与消费国围绕关键矿产的政府间合作、产业链协同与供应保障明显提速，非洲、拉美等资源富集地区成为合作重点区域。',
                )),

    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474448',
                '中国有色金属报', '10-09',
                '印尼 2027 年设立矿产交易所，全球镍系定价或现“双基准”格局',
                '中国有色金属报发表分析文章称，印尼总统普拉博沃在国会公布 2027 年度预算时宣布设立矿产与战略大宗商品交易所（ICOMEX），由印尼金融服务管理局（OJK）监管，牌照 2027 年 1 月 1 日发放、1 月 4 日开启首单交易，首批挂牌品种为锡和镍铁，后续扩至棕榈油、动力煤、铝土矿、铜、橡胶、咖啡。报道认为，镍系现有基准为 LME 纯镍与 SMM 现货指数，印尼占全球镍供应 60% 以上，而 LME 对二级镍覆盖不足存在“基准真空带”，ICOMEX 最有希望率先形成“LME 一级镍、ICOMEX 二级镍”的双基准格局；锡短期更可能形成双轨报价但体量有限。ICOMEX 制度设计含分品种场内集中交易、OJK 监管并发布“印尼参考价”、初期以现货为主后续推期货、与国有资源出口结算企业（DSI）联动四点。中长期看，亚洲买家的不锈钢与电池原料采购将更多锚定 ICOMEX 实物价，弱化 LME 一级镍对二级镍的间接传导。',
                )),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202610/fb567ef86f8744b7a9ba5cd56ce6f45e.html',
                '长江有色网', '10-09',
                'LME 金属期货全线走弱，伦铝跌 2.7% 报近八个月低位',
                '长江有色网报道，伦敦金属交易所基本金属期货全线走弱，其中伦铝单日下跌 2.7%，报近八个月以来低位。报道分析，美国国债收益率高企与美元走强持续压制有色金属估值，叠加国内节后铝锭库存累积削弱价格支撑，市场对美联储年内加息预期反复扰动情绪，多空因素交织下短期基本金属承压运行。',
                )),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202610/9117a64b63264171a687d881a2c45551.html',
                '长江有色网', '10-09',
                '铜价单日下挫 940 元：通胀加息预期双升温，产业硬支撑难抵宏观抛压',
                '长江有色网报道，10 月 9 日国内铜价单日下挫 940 元/吨，通胀与加息预期同步升温带来的宏观抛压，压过了产业端供应偏紧的支撑。报道援引数据称 LME 铜与 COMEX 铜价差已追平，摩根士丹利将四季度铜价目标定在 14,800 美元/吨；供应“硬缺口”与需求“新引擎”之间的长期博弈仍在延续。同日长江有色金属现货行情同步发布。',
                )),

    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kydt/hyyxdt/202610/t20261009_10330911.htm',
                '全球矿产资源信息系统', '10-09',
                '津巴布韦前三季度锂出口额 21.6 亿美元，近乎去年全年 4 倍',
                '全球矿产资源信息系统援引矿业周刊（Miningweekly）报道，津巴布韦政府矿产销售公司（MMCZ）周三宣布，前三季度该国锂出口额达 21.6 亿美元，几乎是去年全年出口额的 4 倍。MMCZ 总经理诺穆萨·莫约称，增长主要因锂辉石价格上涨 283%。其中锂辉石出口额 18 亿美元，透锂长石 1.55 亿美元，硫酸锂 1.90 亿美元；前三季度硫酸锂出口量约 3.3 万吨。锂产品已替代铂族金属成为仅次于黄金的最大出口矿产品，前三季度铂族金属出口额 17.3 亿美元；不含黄金的矿产品出口额 47.4 亿美元，同比增长一倍。',
                )),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474455',
                '中国有色金属报', '10-09',
                '宝钛集团国产 EB 炉量产 12 吨超大单重纯镍铸锭',
                '中国有色金属报报道，宝钛集团依托下属宝钛装备设计制造公司自主研发、设计、制造的 3150kW 冷阴极电子束冷床炉（EB 炉），实现 12 吨超大单重纯镍铸锭稳定量产，标志国产 EB 炉在大吨位高端纯镍熔炼工艺与规模化量产技术领域取得实质性突破。纯镍熔点高、熔融态黏度大、流动性差，且在高真空下极易挥发，大吨位连续熔炼是行业公认难题；此前企业引进的德国热阴极 EB 炉存在灯丝易损耗、真空波动大等短板，无法实现大吨位连续稳定熔炼。宝钛集团 2023 年 12 月投产自主研制冷阴极 EB 炉全面替代进口设备，2025 年 3 月启动大吨位纯镍铸锭专项攻坚，通过自制专用打包工装解决异形返回炉料供料不稳定、设备卡滞等行业共性难题，并搭建全维度质量安全保障体系。该成果填补国内大单重纯镍量产技术空白，可直接轧制超宽超长整体镍板材，规避拼接焊缝缺陷。',
                )),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474444',
                '中国有色金属报', '10-09',
                '中矿资源中南部非洲运营管理中心在赞比亚卢萨卡揭牌',
                '中国有色金属报报道，当地时间 9 月 19 日，中矿资源集团股份有限公司中南部非洲运营管理中心揭牌仪式在赞比亚首都卢萨卡举行。中矿资源董事长、总裁王平卫出席仪式，该中心将作为中矿资源在非的“前沿阵地、管理平台和协同枢纽”，聚焦“区域统筹、业务协同、服务一线、共建共赢”四大职能。仪式上举行首批配套企业战略合作签约，中心总经理王治伟代表中心与 5 家服务型企业签署战略合作协议，通过构建上下游配套企业集群形成资源共享、优势互补的产业生态圈。报道称，此举标志中矿资源深化非洲本土化经营、构建区域协同发展新格局迈出关键一步。',
                )),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474456',
                '中国有色金属报', '10-09',
                '甬金股份年产 10 万吨精密金属新材料项目开工，占地 190 亩',
                '中国有色金属报报道，甬金科技集团股份有限公司子公司浙江甬金精密新材料有限公司年产 10 万吨精密金属新材料（超薄精密钛合金及金属复合材料）产业化项目开工建设。项目占地面积 190 亩，总建筑面积 86,503.10 平方米，将引进国际一流、国内领先的成套智能化生产设备，打造集研发、生产、贸易、配套服务于一体的现代化精密金属材料生产基地。项目建成后主要生产精密复合板、钛合金板带、高性能覆铜板、精密不锈钢等电子产业专用材料，形成年产 10 万吨超薄精密金属新材料生产能力。报道称，甬金股份目前兰溪市产能规模达 42 万吨、整体产值营收 426.46 亿元，已获评国家高新技术企业、国家专精特新“小巨人”企业。',
                )),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://news.smm.cn/news/104146824',
                '上海有色网', '10-09',
                '工会：罢工或致智利 Centinela 铜矿 11 月产量减半',
                '上海有色网报道，智利安托法加斯塔（Antofagasta）旗下 Centinela 铜矿 700 余名工人自 10 月 7 日起罢工，工会表示若罢工持续，11 月该矿产量可能减半。Minera Esperanza 工会和 Distrito Centinela 工会称，智利劳工监察局主持的调解未能解决薪酬争议。此前罢工引发的供应担忧曾抵消美元走强压力，推动 LME 铜价回升。',
                )),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104146986-rio-tinto-invests-15b-in-quebec-smelter-boosting-low-carbon-aluminum-output-by-2026',
                'SMM 国际站', '10-09',
                '力拓投资 15 亿美元扩建魁北克 AP60 冶炼厂',
                'SMM 国际站报道，力拓正投资 15 亿美元扩建位于魁北克的 AP60 冶炼厂，项目预计 2026 年底全面投产，向交通、建筑、电气与消费品领域客户供应低碳铝。投产后 AP60 原铝产能将增加约 16 万吨/年，使 Complexe Arvida 的 AP60 总产量达到约 22 万吨。与较旧的 Arvida 技术相比，扩建项目预计每年减少排放约 29 万吨，进一步凸显基于水电的能效型原铝生产优势。',
                orig_title='Rio Tinto Invests $1.5B in Quebec Smelter, Boosting Low-Carbon Aluminum Output by 2026')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104147143-florence-copper-holds-commercial-launch-ceremony-as-the-us-welcomes-its-first-major-new-copper-source-since-2008',
                'SMM 国际站', '10-09',
                'Florence Copper 商业化投产，美国迎来 2008 年以来首个大型新铜源',
                'SMM 国际站报道，Taseko Mines 旗下 Florence Copper 项目 10 月 6 日在亚利桑那州举行商业化投产仪式。项目已于 2026 年 2 月产出首批阴极铜，此次仪式标志其正式转入商业化运营，被描述为美国自 2008 年以来首个大型新建铜源。项目采用原地浸出（ISCR）结合溶剂萃取—电积（SX/EW）工艺，设计产能为年产 38,600 吨 LME A 级阴极铜（按原设计年产 8,500 万磅计），矿山寿命约 22 年、累计产量预计约 68 万吨，通过注入井与回收井提取铜而非传统露天开采。公司称 2026 年 2 至 6 月产出近 3,175 吨铜，目前仍处爬产阶段、预计 2027 年达产。项目产出的阴极铜将全部留在美国供应本土制造商及战略产业，已创造 200 多个直接就业岗位。',
                orig_title='Florence Copper Holds Commercial Launch Ceremony as the U.S. Welcomes Its First Major New Copper Source Since 2008')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104146971-cochilco-801-of-chilean-copper-mining-power-now-accredited-renewable',
                'SMM 国际站', '10-09',
                'Cochilco：智利铜矿业 80.1% 用电已获可再生认证',
                'SMM 国际站报道，智利铜业委员会（Cochilco）称，经认证的可再生电力已占该国铜矿业用电总量的 80.1%，显示该行业向清洁能源结构迈进的程度。Cochilco 指出，电力约占智利铜矿运营全国用电需求的 30%，在部分矿山最高占运营成本的 30%。随着矿石品位下降与海水淡化扩大，每吨铜的用电量持续攀升，使长期可再生电力购电协议（PPA）成为兼顾低碳资质与成本控制的关键。该数据强化了智利作为可溯源、低排放铜供应方的地位。',
                orig_title='Cochilco: 80.1% of Chilean copper mining power now accredited renewable')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.mining.com/levack-restart-puts-magna-on-two-mine-path',
                'MINING.COM', '10-09',
                'Magna Mining 批准重启 Ontario Levack 镍铜矿，目标 2028 年中投产',
                'MINING.COM 报道，Magna Mining 已正式批准重启位于安大略萨德伯里盆地的 Levack 镍铜矿，该矿自 2018 年起停产。公司将修复现有井下基础设施、重新启用提升系统，并在未来数月加快井下开拓与地表建设。新的初步经济评估（PEA）显示商业生产期约 7.3 年，投产目标为 2028 年年中，年均应付产量约 3,680 万磅铜当量；初始资本约 7,010 万加元，计入商业化生产前运营现金流与税收抵免后，Magna 测算的净融资需求明显更低。早期开采将优先选择高品位铜矿与富含贵金属的下盘矿带。同一事项中文报道见 SMM 国际站（目标 2028 年中商业化生产）。',
                orig_title='Levack restart puts Magna on two-mine track in Ontario')),

    (CAT_MA, ni('https://www.mining.com/sigrafi-raises-35m-to-connect-artisanal-gold-to-institutional-markets',
                'MINING.COM', '10-09',
                'SigraFi 融资 3,500 万美元，将手工采金接入机构市场',
                'MINING.COM 报道，SigraFi 完成 3,500 万美元融资，用于把手工与小规模（ASM）采金产出接入机构市场。公司称将通过可溯源采购、合规冶炼与标准化交割，提升手工采金的透明度与定价可得性，使这部分长期游离于正规市场之外的黄金能够进入机构交易与投资渠道。',
                orig_title='SigraFi raises $35M to connect artisanal gold to institutional markets')),

    (CAT_MA, ni('https://news.metal.com/en/newscontent/104146920-cameroon-announces-public-hearings-for-camalcos-proposed-alumina-refinery-oct-12',
                'SMM 国际站', '10-09',
                '喀麦隆就 Camalco 拟建氧化铝厂举行公众听证（10 月 12—17 日）',
                'SMM 国际站报道，喀麦隆环境部宣布就澳大利亚矿业公司 Canyon Resources 子公司 Camalco 拟建氧化铝厂的环境与社会影响评估举行公众咨询，听证将于 10 月 12—17 日在 Minim-Martap 铝土矿项目附近的 Ngaoundéré 与 Martap 举行。喀麦隆政府此前规划建设年产 240 万吨氧化铝厂，投资超 20 亿美元，可能于 2027 年开工，但项目最终产能与投资细节尚未确认。该厂拟处理本地开采的铝土矿，并可能供应喀麦隆唯一原铝生产商 Alucam（目前依赖进口氧化铝）。Canyon Resources 已于 8 月因融资与物流不确定性撤回 2026 年四季度首批铝土矿发运目标；本次听证意味着环境评估取得进展，而非开工获批，项目建设时间表仍不确定。',
                orig_title="Cameroon Announces Public Hearings for Camalco's Proposed Alumina Refinery, Oct 12-17")),

    # ── 💼 矿权交易（仅入 rightsSection 数据层，不进主列表） ───
    # ── 💼 矿权交易（仅入 rightsSection 数据层，不进主列表） ───
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
