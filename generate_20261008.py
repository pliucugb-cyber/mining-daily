# -*- coding: utf-8 -*-
"""
生成 2026-10-08 矿业资讯速览 index.html（周四 · 国庆假期后首个交易日）
- 10-07 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-09-09）回补历史条目
- 换入 10-08 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 10-08 收盘（节后首日，现算）
  + LME 卡片=走势图末点口径 10-07 收盘（10-08 电子盘未收盘，沿用 10-07 收盘价），
  全部由 price_history_detail.json / lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
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

REPORT = '2026-10-08'
GRAB = '2026-10-08'
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
                         r'\g<1>2026年10月08日 星期四', html)
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
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202610/t20261008_10329510.htm',
                '全球矿产资源信息系统', '10-08',
                '格陵兰斯卡尔加德项目完成野外工作，评价镓与钒钛磁铁矿潜力',
                '全球矿产资源信息系统援引 Mining.com 报道，格陵兰矿业公司（Greenland Mines）宣布其格陵兰东南部斯卡尔加德（Skaergaard）项目 2026 年野外工作已完成，正在评价钒钛磁铁矿、铁与镓的潜力。本季 4,480 米金刚石钻探取得该项目首个大直径岩心，将用于选冶加工试验；已在铂钯金矿段刻槽取样采集逾 105 吨大样，远超此前两个 800 公斤小样。7 月更新的 S-K 1300 技术报告将各级钯当量资源量提高 50%、品位提高 80%，现有矿石资源量 1.536 亿吨，钯品位 1.53 克/吨、金 0.65 克/吨、铂 0.12 克/吨。公司称同时推进东格陵兰斯卡尔加德与西格陵兰萨法托克两个项目。',
                )),

    (CAT_ZK, ni('https://www.mining.com/uk-scientists-turn-to-biology-to-unlock-cleaner-lithium',
                'MINING.COM', '10-08',
                '英国团队研发蛋白基膜材料，攻关锂钠分离与低能耗提锂',
                'MINING.COM 报道，英国伯明翰大学正牵头一项 620 万英镑（约 820 万美元）的三年期项目，开发基于蛋白质的膜材料，目标是提高锂提取的选择性并降低能耗。项目由英国先进研究与发明署（ARIA）资助，首期聚焦直接提锂（DLE）中最棘手的环节——把锂与钠分离以制取电池级高纯锂化合物；团队联合阿斯顿大学及三家产业伙伴，拟利用可在微生物表面自组装成高度有序二维晶格的 S 层蛋白，工程化为大面积、孔径均一、能区分锂钠离子的膜。该研究属 ARIA「通用制造者（Universal Fabricators）」计划。',
                orig_title='UK scientists turn to biology to unlock cleaner lithium')),

    (CAT_ZK, ni('https://www.mining.com/vizsla-copper-logs-high-grade-silver-at-alaska-project',
                'MINING.COM', '10-07',
                'Vizsla Copper 阿拉斯加 Palmer 项目 AG 矿床钻获高品位银',
                'MINING.COM 报道，Vizsla Copper（TSXV: VCU；US-OTC: VCUFF）称其阿拉斯加东南部 Palmer 铜锌项目新钻探揭示高品位银矿化潜力：AG 矿床代表孔 CMR26-215 自 180.3 米深处见矿 21 米，品位锌 4.79%、铜 0.14%、银 116.9 克/吨、金 0.27 克/吨；其中 182 米以下 7 米更高品位段为锌 5.46%、铜 0.17%、银 207.5 克/吨、金 0.45 克/吨。Palmer 为火山成因块状硫化物（VMS）项目，面积约 330 平方公里，距美加边境不远、距水路约 60 公里。',
                orig_title='Vizsla Copper logs high-grade silver at Alaska project')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://www.mnr.gov.cn/gk/tzgg/202610/t20261008_2939647.html',
                '自然资源部', '10-08',
                '自然资源部就规范探矿权招标出让公开征求意见',
                '自然资源部 10 月 8 日发布公告，就《自然资源部关于规范探矿权招标出让的通知（征求意见稿）》公开征求意见，目的是贯彻落实《矿产资源法》《矿产资源法实施条例》，规范探矿权招标出让，助推新一轮找矿突破、支撑战略性矿产增储上产。意见反馈截止 2026 年 10 月 23 日，可通过电子邮件发送至 yizhang@mail.mnr.gov.cn。',
                )),

    (CAT_ZC, ni('https://news.smm.cn/news/104146599',
                '上海有色网', '10-08',
                '广期所就氢氧化锂期货和期权合约及相关规则公开征求意见',
                '10 月 8 日，广州期货交易所发布关于就氢氧化锂期货和期权合约及相关规则公开征求意见的公告。征求意见稿显示，氢氧化锂期货合约交易单位为 1 吨/手，报价单位为元（人民币）/吨，最小变动价位 20 元/吨，每次最大下单数量 1,000 手、最小 1 手；一般月份涨跌停板幅度为上一交易日结算价的 5%，交割月份为 7%。',
                )),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202610/t20261008_10329512.htm',
                '全球矿产资源信息系统', '10-08',
                '国际贵金属价格深度调整，铂钯领跌',
                '全球矿产资源信息系统报道，周三国际矿产品价格多数下跌，铂钯跌幅居前。伦敦金属交易所铜收于 14,438.50 美元/吨、涨 0.21%，铝 3,121.50 美元/吨、跌 0.65%，铅 1,890.00 美元/吨、涨 1.02%，锌 3,762.00 美元/吨、跌 0.25%，镍 15,720.00 美元/吨、涨 0.32%，锡 54,250.00 美元/吨、涨 0.21%。纽约商品交易所黄金收于 4,111.0 美元/盎司、跌 1.29%，银 59.75 美元/盎司、跌 2.59%，铂 1,649.8 美元/盎司、跌 3.48%，钯 1,127.0 美元/盎司、跌 4.04%；报道称银、铂、钯价格较 1 月高点跌幅已近 50%。',
                )),

    (CAT_SC, ni('https://news.smm.cn/news/104146740',
                '上海有色网', '10-08',
                '科法斯报告：铜、镍价格到 2035 年可能翻倍',
                '上海有色网援引文华财经报道，全球金融服务机构科法斯（Coface）10 月 7 日发布工业金属报告称，受建筑、能源转型和电气化需求推动，铜价和镍价未来十年可能翻倍；到 2035 年，铝、铜、镍的供应缺口平均或达到需求的约 10%，原因是矿企难以把足够的新增产量投入市场。报告依据伦敦金属交易所、美国地质调查局、世界银行和国际能源署的产量、消费和价格数据编制。该机构北美经济学家称，美国关税是金属贸易方式更大转变的一部分，在供应已经落后于需求时又加了一层压力。',
                )),

    (CAT_SC, ni('https://www.mining.com/dutch-central-bank-transfers-86-tonnes-of-gold-closer-to-home',
                'MINING.COM', '10-07',
                '荷兰央行将 86 吨黄金从北美转运至伦敦',
                'MINING.COM 报道，荷兰央行（DNB）在 2026 年 3 月至 8 月间将约 86 吨黄金从北美移至伦敦，以增强危机应对能力、把黄金存放在地缘政治上更近的金融枢纽。此举使其黄金储备中伦敦占比由 18.1% 升至 32.1%，纽约和渥太华各降至 18.5%，荷兰宰斯特的存放比例维持 30.8%。具体操作为在纽约卖出约 59 吨、在伦敦买入等量黄金，另有 27 吨从渥太华和纽约押运回宰斯特。截至 2025 年底 DNB 持有 612.4 吨黄金，价值 722 亿欧元（约合 807 亿美元）。',
                orig_title='Dutch central bank transfers 86 tonnes of gold closer to home')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/1008/62118.html',
                '中国有色金属工业协会', '10-08',
                '贵州鼎盛鑫锌锗新材料绿色智造项目设计签约，总投资 62.5 亿元',
                '中国有色金属工业协会网站刊发中国有色金属报报道，贵州鼎盛鑫锌锗新材料绿色智造项目工程设计签约仪式 9 月 23 日在赫章鼎盛鑫矿业发展有限公司举行，项目总投资 62.5 亿元。',
                )),

    (CAT_HY, ni('https://news.metal.com/en/newscontent/104146694-east-china-smelter-resumes-at-half-capacity-after-holiday-equipment-failure',
                'SMM 国际站', '10-08',
                '华东一大型再生铅冶炼厂因设备故障节后半负荷复产',
                'SMM 国际站报道，华东地区一家大型再生铅冶炼厂在国庆假期期间因设备故障产量下降，已于昨晚恢复生产，目前以约半负荷运行，日产量约 600 吨。',
                orig_title='East China Smelter Resumes at Half Capacity After Holiday Equipment Failure')),

    (CAT_HY, ni('https://news.smm.cn/news/104146746',
                '上海有色网', '10-08',
                '德福科技：9 月 HVLP 铜箔出货 699.7 吨，其中 HVLP4 为 187 吨',
                '上海有色网报道，德福科技 10 月 8 日在投资者互动平台回应称，公司 HVLP 系列铜箔产能正有序释放，9 月 HVLP 铜箔出货量为 699.7 吨，其中 HVLP4 铜箔出货量 187 吨，较前期有所提升；此前公司披露 8 月 HVLP 系列铜箔月产量为 500 吨、其中 HVLP4 为 70 吨。',
                )),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202610/t20261008_10329508.htm',
                '全球矿产资源信息系统', '10-08',
                '美国拟借助国际开发融资机构助智利提升铜冶炼能力',
                '全球矿产资源信息系统援引 BNAmericas 网站报道，美国国际开发融资公司（IDFC）正在评估在智利建设新铜精炼厂的可行性，以推进新建关键矿产供应链。美国驻智利大使布兰登·贾德在智利太平洋基金会线上会议上称，IDFC 正同多个实体磋商在智利建设炼厂的可行性，以便该国冶炼更多铜并控制供应链关键环节；2026 年中以来 IDFC 一直在智利寻找能提高铜附加值的可行项目。报道称，因成本高昂智利铜冶炼能力有限，IDFC 的参与有助于降低精炼环节风险，其方式可包括持有项目股权。',
                )),

    (CAT_GJ, ni('https://news.smm.cn/news/104146739',
                '上海有色网', '10-08',
                '智利 Centinela 铜矿 700 余名工人罢工，铜供应风险上升',
                '上海有色网援引文华财经报道，10 月 7 日智利安托法加斯塔（Antofagasta）旗下 Centinela 铜矿 700 多名工人开始罢工，令全球最大产铜国再添一层供应威胁。Minera Esperanza 工会和 Distrito Centinela 工会称，智利劳工监察局主持的调解未能解决薪酬争议。当日伦敦金属交易所铜价回升，罢工引发的供应担忧抵消了美元走强的压力；今年以来 LME 三个月期铜涨幅已超过 16%。',
                )),

    (CAT_GJ, ni('https://www.mining.com/ame-report-sees-23b-economic-boost-from-new-canadian-mines',
                'MINING.COM', '10-07',
                'AME 报告：加拿大扩大勘查税收优惠或带来 330 亿加元经济增量',
                'MINING.COM 报道，加拿大矿产勘查协会（AME）就联邦政府承诺扩大「加拿大勘查支出（CEE）」适用范围、拓宽关键矿产勘查税收抵免（METC）发布经济影响评估。据安永报告，该承诺未来十年可创造最多 34,000 个全职岗位、每年新增 16 亿加元矿产勘查支出；若推动 3 至 5 座矿山投产，连同更高的勘查支出，预计带来最多 330 亿加元（约 231 亿美元）经济增量，政府每投入 1 加元可获 5 倍 GDP 回报。AME 称全国有 171 座矿山等待商业化生产。',
                orig_title='AME report sees $23B economic boost from new Canadian mines')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202610/t20261008_10329509.htm',
                '全球矿产资源信息系统', '10-08',
                '刚果（金）启动全国航空地质填图计划',
                '全球矿产资源信息系统援引矿业周刊（Miningweekly）转路透社报道，刚果（金）国家地质调查局（SGNC）周一宣布启动全国性航空地质填图计划，以加深对本国矿产资源的认识、降低勘查风险并为勘查程度不高地区吸引投资。该国是世界最大产钴国和非洲最大产铜国，但详查区域占国土面积不足十分之一。这项名为 PC2G-RDC 的计划将开展高精度航空物探调查，由西班牙物探公司艾克斯卡利伯（Xcalibur）提供支持，重点区域包括中刚果省、宽果省、奎卢省和大开赛地区，并继续推进大加丹加地区已有工作。',
                )),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.mining.com/cleantech-lithium-expands-foothold-in-argentina',
                'MINING.COM', '10-08',
                'CleanTech Lithium 拟收购阿根廷 Salar de Antofalla 两处锂卤水资产',
                'MINING.COM 报道，CleanTech Lithium（LON: CTL）已签署协议，拟收购阿根廷 Salar de Antofalla 的 Genoveva 与 Sal de Litio 1 两处锂卤水资产 100% 权益（合称 Antofalla 项目），该区域距其旗舰项目 Laguna Verde 约 80 公里，紧邻全球最大锂生产商雅保（Albemarle）持有的勘查区块。交易对价为首年支付 52.5 万美元，另于 2027 年 10 月至 2031 年 5 月间分期支付 140 万美元，合计约 193 万美元，拟以现有现金支付。消息公布后公司伦敦股价上涨 7.4% 至 7.25 便士，市值约 2,550 万英镑（3,400 万美元）；公司计划 2027 年启动 Antofalla 勘查，Laguna Verde 仍是开发优先项。',
                orig_title='CleanTech Lithium expands foothold in Argentina')),

    (CAT_MA, ni('https://www.mining.com/namibia-diamond-mine-revival-draws-50m-investment',
                'MINING.COM', '10-07',
                '纳米比亚 Elizabeth Bay 钻石矿重启，计划投资 5,000 万美元',
                'MINING.COM 报道，荷兰私募投资机构 Kenzoll Capital 与纳米比亚注册的 MSF Commercials 合作，重启 Elizabeth Bay 钻石矿，计划投资 5,000 万美元，部分资金还将用于其他矿种的勘查。该矿（原名 Elizabeth Bay，位于 Sperrgebiet 禁区）拥有 1,050 万克拉陆上与海上钻石资源量。重启之际纳米比亚钻石出口大幅下滑：由 2022 年的 51 亿纳米比亚元（约 3.069 亿美元）降至 2025 年的 17 亿纳米比亚元（约 1.023 亿美元），降幅约 67%。Kenzoll Capital 在纳米比亚累计投资已超过 1,000 万美元。',
                orig_title='Namibia diamond mine revival draws $50M investment')),

    (CAT_MA, ni('https://www.mining.com/gold-mountain-weighs-revival-of-wartime-brazil-tungsten-mine',
                'MINING.COM', '10-07',
                'Gold Mountain 拟重启巴西二战时期钨矿，对价至多 300 万雷亚尔',
                'MINING.COM 报道，Gold Mountain（ASX: GMN）正考虑重启巴西一座二战时期开采过的钨矿。公司本周表示，已取得收购巴西东北部 Seridó 钨矿区前 Malhada do Angico 矿约 858 公顷采矿申请权的独家权利；与 Emprogeo Mining Business EPP 达成为期 12 个月的协议，将在尽职调查后决定是否推进，交易对价最高可达 300 万雷亚尔（约 60 万美元）。Malhada do Angico 二战期间由 Mineração Fluminense 开采，矿体赋存于含白钨矿的矽卡岩中，与巴西最大钨矿之一 Brejuí 矿处于同一构造—地层背景。',
                orig_title='Gold Mountain weighs revival of wartime Brazil tungsten mine')),

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
