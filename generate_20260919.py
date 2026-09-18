# -*- coding: utf-8 -*-
"""
生成 2026-09-19 矿业资讯速览 index.html
- 09-18 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-21）回补历史条目
- 换入 09-18~09-19 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 09-18 收盘 + LME 09-16 收盘（东财日K末点滞后，卡片=走势图口径），
  全部由 price_history_detail.json / lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
- 矿权条目仅入 rightsSection 数据层，不进主页列表
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

REPORT = '2026-09-19'
GRAB = '2026-09-19'
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
                         r'\g<1>2026年09月19日 星期六', html)
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

# ============ 4. 今日新增条目（09-18~09-19 抓取，均逐源核实真实发布日期） ============
# 09-19 为周六：cnmn 列表日期失真现象延续（沿用历史结论，逐条核详情页后再选），本日 cnmn 一条未收；
# geoglobal / chinania / cgs 日期取自 URL 路径或页面，SMM 国际站为当日英文稿，mining.com 为 RSS 日期。
new_items = [
    # ---------- 📜 政策与监管 ----------
    (CAT_ZC, ni('https://news.smm.cn/news/104123436',
                '上海有色网', '09-19',
                '广期所调整碳酸锂期货最小开仓下单量与手续费标准',
                '9 月 18 日，广州期货交易所发布公告，对碳酸锂期货 LC2610、LC2611、LC2612 及 LC2701 至 LC2709 共 12 个合约调整交易参数，自 2026 年 9 月 22 日交易时起实施：每次最小开仓下单数量由 1 手调整为 2 手，每次最小平仓下单数量维持 1 手；交易手续费标准与日内平今仓手续费标准均调整为成交金额的万分之零点八；非期货公司会员或客户在上述合约上单日开仓量分别不得超过 800 手，套期保值与做市交易不受该标准限制。')),
    (CAT_ZC, ni('http://gi.mnr.gov.cn/202609/t20260918_2938665.html',
                '自然资源部', '09-18',
                '「十五五」历史遗留废弃矿山生态修复工程项目审核结果公示',
                '自然资源部国土空间生态修复司公示「十五五」历史遗留废弃矿山生态修复工程项目实施方案审核结果，22 个项目拟通过审核，公示期为 2026 年 9 月 18 日至 9 月 23 日。公示指出，上述项目可按专家审核意见与负面清单复核意见修改完善实施方案后及时开展工程设计，并一并上报复核。')),

    # ---------- 🔍 找矿成果与勘查技术 ----------
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202609/t20260918_10317041.htm',
                '全球矿产资源信息系统', '09-18',
                '南澳州奥弗兰碳酸岩型铌稀土矿取得新发现',
                '澳洲稀土公司（AR3）在南澳州奥弗兰（Overland）碳酸岩型铌稀土矿扩边钻探取得新发现：最南端最佳见矿孔 OV176 在 68 米深处见到 130 米厚碳酸岩体，终孔 201 米仍未穿透；距其 5 公里的发现孔在 86 米深处见矿 19 米、总稀土氧化物（TREO）品位 0.61%，其中 96 米深处 3 米厚段品位 1.16%，镨钕品位最高 22%、镝铽 2.3%、铌 0.53%。磁测显示沿 10 公里走廊分布一个大型碳酸岩杂岩体，公司称这是迄今最重要的地质结果，下周将继续钻探。')),
    (CAT_ZK, ni('https://www.cgs.gov.cn/ywdt/ddyw/202609/t20260918_869235.html',
                '中国地质调查局', '09-18',
                '我国矿产资源家底更加厚实 14 种矿产储量居世界第一',
                '《中国矿产资源报告（2026）》显示，「十四五」找矿突破战略行动目标任务圆满完成。截至「十四五」末，我国稀土、钨、锡、钼等 14 种矿产储量居世界第一位，煤、铁、锰、钛等 9 种居世界前四位；2025 年全国新发现非油气矿产地 200 处，其中大型 63 处、中型 57 处，新发现数量居前的矿种为金矿 16 处、铁矿 11 处、煤矿 9 处。2025 年地质勘查投资与采矿业固定资产投资均连续第五年正增长，10 种有色金属产量 8175.0 万吨、增长 3.9%。')),
    (CAT_ZK, ni('https://www.mining.com/aya-logs-high-grade-shallow-silver-in-morocco',
                'MINING.COM', '09-18',
                'Aya 摩洛哥 Zgounder 银矿坑边与深部均见高品位矿化',
                'Aya Gold & Silver（TSX、Nasdaq: AYA）公布摩洛哥 Zgounder 银矿 97 个钻孔结果：露天采坑区钻孔 ZG-RC-24-155 自地表见矿 13 米、银品位 783 克/吨，ZG-RC-24-354 自 2 米深处见矿 11 米、银品位 501 克/吨；另有 T28-26-1404 自 7 米深处见矿 12 米、品位 762 克/吨。公司 3 万米钻探计划已完成过半。Zgounder 今年计划产银 520 万至 580 万盎司，平均现金成本 21.50 美元/盎司。',
                orig_title='Aya logs high-grade, shallow silver in Morocco')),
    (CAT_ZK, ni('https://news.metal.com/en/newscontent/104123591-smm-news-lithium-africa-samples-198-lithium-oxide-at-agbovilles-kanien-trend',
                'SMM 国际站', '09-19',
                'Lithium Africa 科特迪瓦 Agboville 项目见 1.98% 氧化锂',
                'Lithium Africa 在科特迪瓦 Agboville 项目圈定第二条锂辉石矿带 Kanien：19 件含锂辉石伟晶岩样品中有 14 件氧化锂品位高于 1%，最高达 1.98%，矿化沿一条剪切白云母花岗岩延伸 2.8 公里。该矿带与邻近矿权上 1.36% 的氧化锂样品同向，共同构成跨矿权边界约 7 公里长的锂辉石伟晶岩走廊。公司通过 50/50 合资持有约 485 平方公里矿权，并已申请相邻 368 平方公里的 Sikensi 矿权；Saby 矿带 2000 米反循环钻探因雨季在 1137 米处暂停，结果预计 2026 年四季度公布。',
                orig_title="[SMM News] Lithium Africa Samples 1.98% Lithium Oxide at Agboville's Kanien Trend")),

    # ---------- 📊 市场与价格 ----------
    (CAT_SC, ni('https://news.smm.cn/news/104123021',
                '上海有色网', '09-19',
                'SMM 日评：基本金属普涨 沪铅领涨 2.03% 沪银涨近 4%',
                'SMM 9 月 18 日数据显示，内盘基本金属集体上涨，沪铅涨 2.03% 领涨，沪锡涨 1.97%、沪锌涨 1.59%、沪铜涨 1.4%、沪镍涨 0.98%、沪铝涨 0.74%；贵金属明显走强，沪金涨 1.41%、沪银涨 3.98%，铂、钯主连分别涨 2.09% 和 2.37%。外盘基本金属集体飘红，伦锡涨 1.31% 领涨。碳酸锂主连跌 2.27%，黑色系双焦大幅下挫，焦煤跌 7.78%、焦炭跌 5.45%。')),
    (CAT_SC, ni('https://news.smm.cn/news/104123213',
                '上海有色网', '09-19',
                '本周钴系产品报价继续承压 氯化钴单周跌 7.32%',
                'SMM 周度观察显示，截至 9 月 18 日，电解钴现货均价 28 万元/吨，较 9 月 11 日的 28.25 万元/吨下跌 2500 元/吨、跌幅 0.88%；钴中间品（CIF 中国）均价 16 美元/磅，下跌 4.48%；硫酸钴均价 6.25 万元/吨，下跌 5.66%；氯化钴连跌五个交易日，均价 7.6 万元/吨，单周下跌 6000 元/吨、跌幅 7.32%。下游减产与终端消费不振，钴盐价格仍未止跌。')),
    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202609/t20260918_10317043.htm',
                '全球矿产资源信息系统', '09-18',
                '周四国际有色价格回升 伦铜涨 1.67% 纽约金涨 1.82%',
                '据自然资源部全球矿产资源信息系统，周四国际有色金属价格回升：LME 铜收于 14464.00 美元/吨、涨 1.67%，铝 3288.50 美元/吨、涨 0.57%，铅 1909.50 美元/吨、涨 1.49%，锌 3880.50 美元/吨、涨 1.84%，镍 16250.00 美元/吨、涨 0.93%，锡 53000.00 美元/吨、涨 1.34%。纽约商品交易所金价收于 4341.4 美元/盎司、涨 1.82%，银 65.19 美元/盎司、涨 3.55%。62% 品位铁矿粉 96.95 美元/吨、涨 0.27%；铀收于 89.75 美元/磅，持平。')),

    # ---------- 🏭 行业动态 ----------
    (CAT_HY, ni('https://www.ccmn.cn/news/ZX018/202609/32964adbf08a459ba578caa500979ac9.html',
                '长江有色网', '09-18',
                '中企联合体几内亚大走廊矿业物流项目推进 铝土矿年外运 7700 万吨',
                '9 月 16 日，几内亚总理巴·乌里会见由国家电投、中国铝业牵头的中企联合体代表团，代表团向几内亚政府介绍了几内亚大走廊矿业物流项目整体规划。该项目为非洲铝土矿领域又一重大矿港一体化基建工程，总投资超 30 亿美元，规划铝土矿年外运能力 7700 万吨。')),
    (CAT_HY, ni('https://www.chinania.org.cn/html/xiehuidongtai/xiehuidongtai/2026/0918/62039.html',
                '中国有色金属工业协会', '09-18',
                '有色协会敖宏到铜陵有色集团调研 强调稳妥推进海外资源布局',
                '9 月 16 日，中国有色金属工业协会党委书记敖宏一行到铜陵有色金属集团控股有限公司调研座谈，先后参观金新铜业分公司智慧控制大厅、电解车间与铜陵有色展示馆。敖宏指出，新能源汽车、储能电站、算力基础设施等领域对铜消费拉动作用持续增强，企业要坚持稳中求进，持续推进技术创新和产品升级，稳妥推进海外资源布局，提升产业链供应链韧性和安全水平。铜陵有色集团已构建从矿山开采、冶炼到铜加工的完整产业链，并在高频高速铜箔等中高端领域持续发力。')),

    # ---------- 🌐 国际矿业动态 ----------
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202609/t20260918_10317039.htm',
                '全球矿产资源信息系统', '09-18',
                '韩国与中亚五国签署关键矿产协议 达成 70 余项合作文件',
                '据矿业周刊援引路透社报道，韩国总统李在明在首尔主持韩国—中亚五国领导人首次峰会，核心议题为关键矿产、能源与供应链。三天会晤期间，韩国同哈萨克斯坦、乌兹别克斯坦、土库曼斯坦、吉尔吉斯斯坦和塔吉克斯坦达成 70 多项协议与谅解备忘录，涵盖能源、矿业、基础设施、技术与投资。李在明表示合作将从单一原材料贸易扩展到从勘探、冶炼到高价值材料加工的整个关键矿产价值链，双方还确立两年一度领导人峰会机制，下届峰会 2028 年在阿斯塔纳举行。')),
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202609/t20260918_10317040.htm',
                '全球矿产资源信息系统', '09-18',
                '美国为尼日尔达萨铀矿提供 4.14 亿美元资金支持',
                '据矿业周刊援引路透社报道，美国开发融资公司（DFC）批准向加拿大矿企环球原子能公司（Global Atomic）的尼日尔达萨（Dasa）铀矿项目提供 4.14 亿美元贷款，环球原子能称该项目是非洲品位最高的铀矿。尼日尔是世界第七大产铀国，此前长期由法国奥拉诺公司控制，双方现存在纠纷。项目仍面临安全与物流风险，公司正寻找经阿尔及利亚北上穿越撒哈拉沙漠的出口替代路线。')),
    (CAT_GJ, ni('https://www.mining.com/copper-mine-supply-risks-first-decline-since-2017-sprott',
                'MINING.COM', '09-19',
                'Sprott：全球铜矿产量或出现 2017 年以来首次下降',
                'Sprott 资产管理公司报告称，2026 年上半年全球铜矿产量同比下降 1.1%，全年或出现近十年来首次下滑。印尼格拉斯伯格与刚果（金）卡莫阿—卡库拉两处矿山的扰动合计减少约 60 万吨预期产量，相当于全球矿供应的 2.5%。智利上半年产量下降 6.6%、7 月同比降 9.4%，该国铜业委员会已将 2026 年产量预测下调至 527 万吨。报告称铜项目从发现到投产平均需 17.5 年，高价格难以快速补充新矿供应。',
                orig_title='Copper mine supply risks first decline since 2017: Sprott')),
    (CAT_GJ, ni('https://www.mining.com/gold-is-tariff-proof-canada-has-11-billion-a-year-of-it-stuck-in-permitting',
                'MINING.COM', '09-19',
                '加拿大 15 个金矿项目受困审批 年潜在收入约 110 亿美元',
                'MINING.COM 统计显示，加拿大 15 个已完成可行性研究、已宣告储量但尚未作出建设决策的金矿项目，合计储量 3660 万盎司，达产后年产量约 250 万盎司（约 78 吨），较当前产量提升 35% 至 40%。按 4300 美元/盎司金价测算，年收入接近 110 亿美元，初始资本支出 94 亿美元；按行业平均成本 1800 美元/盎司推算，每年可为联邦与省级财政贡献约 24 亿美元。S&P Global 数据显示，加拿大矿山从发现到投产平均耗时 20 至 27 年。',
                orig_title='Gold is tariff-proof. Canada has $11 billion a year of it stuck in permitting')),

    # ---------- 💰 并购与投资 ----------
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-19/1225571327.PDF',
                '巨潮资讯网', '09-19',
                '中国五矿拟增资广西关键金属集团 华锡有色实控人将变更',
                '华锡有色（600301）公告，2026 年 9 月 18 日间接控股股东广西关键金属产业发展集团及其股东北部湾港集团、关键金属股权基金与中国五矿共同签署《合作框架协议》，中国五矿拟以现金或现金与非现金资产组合方式增资，取得广西关键金属集团 51% 股权并将其纳入合并报表范围。交易完成后公司间接控股股东调整为广西关键金属集团，实际控制人由广西壮族自治区国资委变更为中国五矿；中国五矿间接持有华锡有色权益将超过 30%，触发全面要约收购义务。公司股票自 9 月 21 日开市起复牌。',
                embed='pdf')),
    (CAT_MA, ni('https://news.metal.com/en/newscontent/104123584-smm-news-lithium-argentina-closes-180m-strategic-investment-from-ganfeng-lithium',
                'SMM 国际站', '09-19',
                '赣锋锂业 1.8 亿美元战略投资 Lithium Argentina 完成交割',
                'Lithium Argentina 宣布完成赣锋锂业集团 1.8 亿美元战略投资，形式为六年期无抵押可转债。Lithium Argentina 与赣锋分别持有阿根廷 Cauchari-Olaroz 锂项目 44.8% 和 46.7% 权益，资金将连同该项目现金分红用于其资产负债表优化，并支持 Cauchari-Olaroz 二期与 Pozuelos-Pastos Grandes（PPG）项目的分阶段推进。若可转债全额转股，赣锋在 Lithium Argentina 的持股将从 9.6% 提升至 16.1%（完全稀释后）。',
                orig_title='[SMM News] Lithium Argentina Closes $180M Strategic Investment From Ganfeng Lithium')),
    (CAT_MA, ni('https://news.metal.com/en/newscontent/104123586-smm-news-critical-metals-confirms-european-lithium-merger-can-proceed-to-vote-closing-expected-in-november',
                'SMM 国际站', '09-19',
                'Critical Metals 8.35 亿美元收购欧洲锂业进入表决阶段',
                '纳斯达克上市的 Critical Metals 确认以全股票方式收购上市欧洲锂业（European Lithium）的交易进入最后阶段，预计 11 月交割。西澳大利亚最高法院 9 月 15 日确认欧洲锂业可召开股东大会就该项安排方案进行表决，交易估值 8.35 亿美元，交易完成后欧洲锂业股东将持有合并后公司 41% 股份。并购将为合并公司纳入欧洲锂业位于奥地利的 Wolfsberg 锂项目。',
                orig_title='[SMM News] Critical Metals Confirms European Lithium Merger Can Proceed to Vote, Closing Expected in November')),
    (CAT_MA, ni('https://www.mining.com/china-rare-earth-eyes-indirect-stake-in-mp-materials',
                'MINING.COM', '09-18',
                '中国稀土集团洽购盛和资源 或间接持有 MP Materials 权益',
                '据路透社报道，国有的中国稀土集团正就收购盛和资源（SHA: 600392）进行谈判，交易若达成，将使中方间接持有美国稀土生产商 MP Materials（NYSE: MP）约 3% 的权益——美国国防部去年已成为 MP Materials 最大股东。消息公布后 MP Materials 股价下跌 2.35% 至 48.22 美元/股，市值 86 亿美元。报道称，该项收购将使中国稀土行业进一步集中，并可能使盛和资源获得更多稀土开采、冶炼分离配额。',
                orig_title='China Rare Earth eyes indirect stake in MP Materials')),
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
