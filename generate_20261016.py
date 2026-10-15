# -*- coding: utf-8 -*-
"""
生成 2026-10-16 矿业资讯速览 index.html（周五）
- 10-15 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-16）回补历史条目
- 换入 10-15 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-15 收盘 + LME 10-15 收盘（10-16 05:30 国内未开盘），全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层（月库 category=矿权交易，tmp/add_rights_1015.py 注入），不进主页列表
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

REPORT = '2026-10-16'
GRAB = '2026-10-16'
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
                         r'\g<1>2026年10月16日 星期五', html)
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
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kydt/hyyxdt/202610/t20261015_10336487.htm',
                '全球矿产资源信息系统', '10-15',
                '2026年全球矿产勘查预算强劲回升',
                '全球矿产资源信息系统援引标普全球市场财智调查数据，2026 年全球有色金属矿产（不含油气、煤）勘查投资较 2025 年增长三成，为经历三年萎缩后的 10 年来最大增幅；金和铜仍是主要勘查矿种，弥补锂矿勘查投资下降带来的缺口，拉丁美洲、加拿大、澳大利亚仍为预算最多的地区。2026 年预算为该调查开展以来第三高年份，仅次于 2012 年的 205 亿美元和 2011 年的 172 亿美元。')),

    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/resources_update/202610/t20261015_10336489.htm',
                '全球矿产资源信息系统', '10-15',
                '布拉马德罗斯铜金矿资源量增长 72%',
                '全球矿产资源信息系统援引 Miningnews.net 报道，太阳石金属公司（Sunstone Metals）在厄瓜多尔南部的布拉马德罗斯（Bramaderos）斑岩铜金矿项目资源量增长 72%，露天采坑资源量达 620 万盎司金当量，其中推定资源量增长 450% 至 330 万盎司；公司称该矿 4 平方公里范围内有望再增 1100 万盎司金当量，选冶试验显示铜回收率可超 80%、金回收率 93%。')),

    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474633',
                '中国有色金属报', '10-15',
                '江西省地调院新疆分院帕米尔高原找矿 3 个项目落地',
                '中国有色金属报报道，江西省地调院基础所新疆分院 23 年扎根平均海拔 4200 米的帕米尔高原开展地质找矿；2024 年底该分院系统梳理多年积累的区域地质认识后，向新疆维吾尔自治区申报 3 个勘查区块，2025 年 7 月库尔勒格热木艾肯钨多金属矿、阿克陶琼让北铜金多金属矿、阿克陶巴牙斯坦铬铁矿 3 个调查评价项目相继落地，为分院成立以来首次同时承担 3 个自主项目，目前 15 名队员分布于 2 个州、3 条线作业。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202610/t20261014_2939990.html',
                '自然资源部', '10-14',
                '《矿产资源目录》发布，含 174 个矿种、119 个亚矿种',
                '自然资源部网站消息，经国务院批准，自然资源部会同国家发展改革委于 10 月 12 日发布《矿产资源目录》，将矿产资源划分为能源矿产、金属矿产、非金属矿产和水气矿产 4 类，共 174 个矿种、119 个亚矿种；目录是制定矿产资源规划、实施矿业权管理、征缴矿产资源税费等工作的依据，自然资源部正研究制定规范新矿种报批的标准文件。')),

    (CAT_ZC, ni('https://www.cgs.gov.cn/ywdt/dwdt/202610/t20261015_870450.html',
                '中国地质调查局', '10-14',
                '智能地质填图技术培训班在廊坊举办',
                '中国地质调查局网站消息，为期 2 天的智能地质填图技术培训班于 10 月 13 日在河北廊坊开班，由中国地质调查局自然资源综合调查指挥中心主办、廊坊自然资源综合调查中心协办；培训围绕地质调查智能空间平台、AI 地质图生成技术方法与系统应用流程、终端 DGSS 野外数据采集处理与成图等新功能展开，来自二十余家局直属单位以及部分省地勘单位的 100 余名技术人员参加。')),

    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474504',
                '中国有色金属报', '10-12',
                '新版国标《锌锭》将于 12 月 1 日实施',
                '中国有色金属报报道，新版国标 GB/T 470—2026《锌锭》将于 2026 年 12 月 1 日正式实施，主要起草单位安徽九华新材料公司以 30 年锌锭生产积累的杂质波动数据与检测记录支撑指标修订；该公司锌锭主品位稳定在 99.997% 以上，内控标准严于新国标，此前已参与《锌及锌合金术语》《压铸锌合金锭》等多项国家标准编制。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/104156526',
                '上海有色网', '10-16',
                '海关总署：前三季度铜材进口降 6.5%、铝材出口增 17.8%',
                '上海有色网援引海关总署数据，2026 年前三季度我国未锻轧铜及铜材累计进口 375.8 万吨、同比减少 6.5%，稀土累计进口 76982.5 吨、同比减少 2.4%，未锻轧铝及铝材累计出口 532.0 万吨、同比增长 17.8%；9 月单月未锻轧铝及铝材出口 65.6 万吨、同比增加 25.9%，铜矿砂及其精矿进口 248.2 万吨、同比减少 4.1%。')),

    (CAT_SC, ni('https://news.smm.cn/news/104159742',
                '上海有色网', '10-16',
                '内盘金属集体下挫，碳酸锂跌破 10 万元关口',
                '上海有色网日评显示，10 月 15 日国内基本金属集体下挫、跌幅多在 1% 以上，沪锡跌 3.28% 领跌，沪镍跌 2.14%，沪铜跌 1.86%，沪铝跌 1.31%，沪锌跌 1.05%，沪铅跌 0.7%；碳酸锂主连跌 3.87%、跌破 10 万元/吨整数关口，多晶硅跌 4.58%，沪银跌 5.34%。外盘伦锡跌 1.24%、伦镍跌 1.74%、伦铜跌 1.21%。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474554',
                '中国有色金属报', '10-13',
                '1—8 月我国钴产品进出口格局分化',
                '中国有色金属报分析，2026 年 1—8 月我国累计进口钴湿法中间品仅 1.2 万吨、同比大降 85.4%，预计 9—12 月进口可达 4 万吨以上；金属钴 1—8 月累计进口 9777 吨、同比增长 115.3%，累计出口 3463 吨、同比下滑 72.7%；硫酸钴累计进口 2.5 万吨、同比暴涨 234.9%，累计出口 6981 吨、同比下降 27.1%。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474567',
                '中国有色金属报', '10-13',
                '镁价创近 19 个月新低，供需双弱拖累行情',
                '中国有色金属报报道，截至 10 月 10 日陕西府谷 99.9% 镁锭主流出厂含税现金报价回落至 1.545 万~1.55 万元/吨，市场主流成交价 1.54 万元/吨，较国庆节前下调约 200 元/吨，创 2025 年 3 月 12 日以来近 19 个月新低；9 月镁锭价格累计下跌约 800 元/吨，多数镁厂陷入深度亏损。')),

    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202610/t20261015_10336491.htm',
                '全球矿产资源信息系统', '10-15',
                '周三国际银价大幅下跌 6%，LME 锡跌 2.22%',
                '全球矿产资源信息系统数据显示，周三国际矿产品价格多数下跌，纽约商品交易所白银收于 55.60 美元/盎司、下跌 6.03%，黄金收于 4105.6 美元/盎司、下跌 1.34%，铂、钯分别跌 3.39% 和 2.75%；LME 铜收于 14436.00 美元/吨、下跌 0.82%，锡收于 50215.00 美元/吨、下跌 2.22%，镍收于 15530.00 美元/吨、下跌 0.03%。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474502',
                '中国有色金属报', '10-12',
                '高库存叠加弱需求，镍价预计震荡偏弱运行',
                '中国有色金属报援引华泰期货分析，9 月沪镍主力结算价运行区间为 12.05 万~12.98 万元/吨、较月初下跌约 4.39%；截至 9 月 30 日 LME 镍库存约 28.49 万吨、较 8 月底增加约 1.65 万吨，SMM 六地纯镍社会库存由 8 月底约 13.03 万吨降至 12.38 万吨；预计 10 月沪镍主力核心运行区间为 11.8 万~12.8 万元/吨。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/1015/62167.html',
                '中国有色金属工业协会', '10-15',
                '赤峰金通铜业铜冶炼二期工程投产，达产后年产值超 500 亿元',
                '中国有色金属工业网报道，赤峰金通铜业铜冶炼工艺升级搬迁改造项目二期工程于 9 月 13 日产出第一块合格阴极铜、实现全流程贯通；该项目达产后公司预计年产值超 500 亿元、年产硫酸可达 200 万吨，采用「富氧侧吹熔炼炉+多枪顶吹吹炼炉+回转式阳极炉」连续炼铜工艺，公司厂区总占地 1042 亩。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474541',
                '中国有色金属报', '10-13',
                '五矿山达克铜矿光伏项目支架安装完成 75%',
                '中国有色金属报报道，五矿中亚南亚山达克铜矿光伏项目国庆期间加速推进支架安装，本次共安装支架 531 套、最长支架檩条约 14 米，组建 5 支骨干突击队分区包干；项目自 9 月 26 日正式启动攻坚以来严格执行样板先行与自检联合验收制度，截至目前已完成支架安装整体进度的 75%。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=474565',
                '中国有色金属报', '10-13',
                '洛阳迈格镁业高端镁合金材料出口 20 多个国家和地区',
                '中国有色金属报报道，河南省「专精特新」企业洛阳迈格镁业有限公司专注高端镁合金材料研发与生产，通过与高校建立产学研合作机制推进技术创新，目前已获得数十项自主研发专利；其核心产品广泛应用于航空航天、精密机械等高端制造领域，远销美国、日本、德国等 20 多个国家和地区。')),

    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyetongji/tongji/2026/1015/62175.html',
                '中国有色金属工业协会', '10-15',
                '中国设定 2030 年钨回收率提高至 45% 目标',
                '中国有色金属工业网报道，9 月柏林国际钨业协会会议上中方代表披露，中国已设定到 2030 年将钨回收率提高至 45% 的目标，标志钨产业重心从依赖矿山开采转向原生与再生资源并重；国际钨业协会测算，按报废回收率口径全球钨回收率约三成，其中欧美国家接近五成、日本约三成、中国约二成。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/tech-giants-come-knocking-for-a-piece-of-anglo-american-as-copper-scarcity-bites-wanblad-tells-ft',
                'MINING.COM', '10-16',
                '英美资源：科技公司洽谈入股以锁定金属供应',
                'MINING.COM 报道，英美资源（Anglo American）首席执行官邓肯·万布拉德在伦敦金融时报金属与矿业峰会上表示，公司已与有意入股的科技公司进行商谈，科技方关注的是直接锁定长期包销还是入股锁定未来供应，目前尚无科技公司持股；英美资源与泰克资源（Teck）合并后年铜产量约 120 万吨，仍在等待中国国家市场监督管理总局的最终批准。',
                orig_title='Tech giants come knocking for a piece of Anglo American as copper scarcity bites, Wanblad tells FT')),

    (CAT_GJ, ni('https://www.mining.com/energy-transition-faces-critical-minerals-crunch-by-2035-report',
                'MINING.COM', '10-15',
                'GEM：到 2035 年锂铜钴供给缺口显著',
                'MINING.COM 援引智利 GEM 矿业咨询公司报告，预计到 2035 年全球供给仅能满足锂需求的 68%、钴需求的 74%、铜需求的 75%；矿产体积稀缺指数中锂以 80 分居首，供应链脆弱性指数中稀土磁材 95 分、电池级石墨 89 分居前，主因加工产能高度集中于中国；报告还测算设计年产 10 万吨的项目实际可靠可售产量仅约 6.02 万吨。',
                orig_title='Energy transition faces critical minerals crunch by 2035: report')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104160266-antofagasta-reports-7-rise-in-q3-copper-production-maintains-annual-guidance',
                'SMM 国际站', '10-16',
                '安托法加斯塔三季度铜产量增 7%，维持全年指引',
                'SMM 国际站报道，智利安托法加斯塔（Antofagasta）三季度铜产量环比增长 7% 至 15.19 万吨，前三季度累计产量 43.69 万吨、同比减少 8.3%；公司维持 2026 年产量指引 62.5 万至 65.5 万吨不变，寄望年内最后几个月产量走强，以抵消一季度 Centinela 品位与回收率下降造成的下滑。',
                orig_title='Antofagasta Reports 7% Rise in Q3 Copper Production, Maintains Annual Guidance')),

    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104160267-perus-august-2026-exports-copper-gold-and-other-metals-see-strong-figures',
                'SMM 国际站', '10-16',
                '秘鲁 8 月铜出口 24.2 万吨、黄金 68.8 万盎司',
                'SMM 国际站援引秘鲁中央储备银行数据，2026 年 8 月秘鲁出口铜 24.2 万吨、锡 2200 吨、黄金 68.8 万盎司、精炼银 50 万盎司、铅 11.98 万吨、锌 8.78 万吨。',
                orig_title="Peru's August 2026 Exports: Copper, Gold, and Other Metals See Strong Figures")),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202610/t20261015_10336490.htm',
                '全球矿产资源信息系统', '10-15',
                '埃尔多拉多希腊铜金矿列入欧盟战略项目',
                '全球矿产资源信息系统援引 Mining.com 报道，欧盟委员会授予埃尔多拉多黄金公司（Eldorado Gold）希腊斯科里斯（Skouries）铜金矿战略地位，该项目是《欧盟关键原材料法案》筛选的 46 个项目之一，可享加快审批与融资便利；项目投资超 20 亿美元、设计运营 20 年，目标年产金 14 万盎司、铜 6700 万磅，预计 2026 年底前正式投产，目前矿石库存超 460 万吨。')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-16/1225606584.PDF',
                '巨潮资讯网', '10-16',
                '中金黄金预计前三季度净利润 55.2 亿至 58 亿元',
                '巨潮资讯网披露，中金黄金预计 2026 年前三季度实现归属于母公司所有者的净利润 55.2 亿元到 58 亿元、同比增加 50.05% 到 57.66%，扣除非经常性损益的净利润 55 亿元到 58 亿元、同比增加 30.53% 到 37.65%；业绩增长主要归因于金铜等主营产品盈利能力明显增强以及硫酸等副产品增收。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-16/1225606275.PDF',
                '巨潮资讯网', '10-16',
                '华友钴业完成回购 1653.07 万股，耗资 6.01 亿元',
                '巨潮资讯网披露，华友钴业于 2026 年 10 月 14 日完成股份回购，累计回购 1653.07 万股、占公司总股本的 0.87%，回购成交最高价 39.95 元/股、最低价 33.16 元/股、均价 36.35 元/股，支付资金总额 6.01 亿元，回购股份存放于公司回购专用证券账户。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-10-14/1225603240.PDF',
                '巨潮资讯网', '10-14',
                '金岭矿业前三季度拟每 10 股派现 0.20 元',
                '巨潮资讯网披露，金岭矿业董事会审议通过 2026 年前三季度利润分配方案，以当前总股本 5.95 亿股为基数，向全体股东每 10 股派发现金股利 0.20 元（含税），共计派发现金 1190.68 万元；公司前三季度合并报表实现归属于母公司所有者净利润 1.67 亿元，截至 9 月 30 日合并报表累计可供股东分配的利润 21.46 亿元。',
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
