# -*- coding: utf-8 -*-
"""
生成 2026-11-09 矿业资讯速览 index.html（周一）
- 11-08 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-10-11）回补历史条目
- 换入 11-09 采集的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 与 LME 均为 11-06 收盘（周末休市），
  全部由 price_history_detail.json / lme_data.json 现算（零手抄）；
  电解钴保留上日 SMM 值并标注
- 矿权条目：11-09 无新增出让/成交公告（周末自然资源部未更新），
  #rightsCards 沿用 14 日窗口既有数据，不进主列表
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

REPORT = '2026-11-09'
GRAB = '2026-11-09'
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
                         r'\g<1>2026年11月09日 星期一', html)
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
    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/DLNYNHMH22ZLIY2PPJIMU3V62JWPGZTPZECXSIQ',
                '上海有色网', '11-08',
                '花旗下调 3 个月铜价目标至 13,300 美元/吨',
                '花旗将 0 至 3 个月铜价预测由每吨 14,500 美元下调至 13,300 美元，并称按当前价格 2027 年、2028 年预计出现铜过剩。该行认为高利率压制周期性铜需求与库存持有，美国铜关税预期回落可能引发避险行为；2027 年供应增长或超预期，能源转型需求增速则因出口激励取消、税收上升与贸易壁垒增加而放缓。')),

    (CAT_SC, ni('https://news.smm.cn/news/CYFXJI3UJAXL6XN7QRX6JSQYXEDPXZG7ZKSPT3A',
                '上海有色网', '11-07',
                'LME 期铜周跌 2.73%，创 3 月以来最大单周跌幅',
                '11 月 6 日 LME 三个月期铜连续第四个交易日下跌，本周累计下跌 2.73%，创截至 3 月 20 日当周以来最大单周跌幅；盘中一度跌 1.5% 至每吨 13,636 美元，为 7 月 30 日以来最低。民主党掌控国会后市场下调美国精炼铜关税预期，COMEX 铜较 LME 溢价一度短暂转为贴水，随后回升。')),

    (CAT_SC, ni('https://news.smm.cn/news/URJFHFTYWHEABCP255QM3G4FCZUXYCIQGD4IF6A',
                '上海有色网', '11-07',
                'SMM：北美云厂商 AI 资本开支超 7,000 亿美元，数据中心拉动铜基材料需求',
                '在 2026 SMM 电工材料产业年会上，SMM 分析师测算，北美四大云厂商 2026 年 AI 相关资本开支合计约超 7,000 亿美元、同比增长约 95%，三年累计扩张接近五倍，资本开支是这条产业链最前置的领先指标；数据中心用铜集中于电力分配、母线与连接器、散热与接地等环节，是铜基材料需求的主要增量来源。')),

    (CAT_SC, ni('https://news.smm.cn/news/QF6EI75WZ3WVSJP3FQTUAGKTQCKEAVQAHU4DZOQ',
                '上海有色网', '11-06',
                'SMM：2026 年铅锭转小幅过剩，2027 年铅精矿紧平衡转为小幅过剩',
                'SMM 在 2026 铅锌年会上预计，2026 年铅锭供应转为小幅过剩、过剩预期前高后低；三、四季度消费旺季叠加冶炼端集中检修对铅价形成阶段性支撑，但旺季不旺与铅锭进口预期制约国内价格上行空间，海外需关注东南亚新建铅消费产能释放。2027 年全球及中国铅精矿由紧平衡转为小幅过剩，高富含矿仍稀缺。')),

    (CAT_SC, ni('https://news.smm.cn/news/GQS6PYP7YEDGD2OUGZEPWTJBF3ANCUXPLCTI2LA',
                '上海有色网', '11-06',
                'SMM：2027 年硫酸价格回归常态波动，炼厂利润缓冲缩水',
                'SMM 在铅锌年会上预计，2027 年硫酸行情由前期大幅震荡回归常态波动，价格呈年初偏弱、年中平稳、年末走强，仍可为炼厂提供利润缓冲但空间明显小于 2026 年上半年；需重点跟踪硫酸出口能否放开及配额政策、2027 年下半年磷石膏两条变量的影响。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://news.metal.com/newscontent/XYUOT2BQ5KBCG5XOXNRMWGJ4DBYALA4JNUCGCBY-malaysia-imposes-provisional-anti-dumping-duties-of-up-to-3506-on-aluminium-zinc-coated-flat-rolled-imports-from-china-taiwan-and-vietnam',
                'SMM 国际站', '11-07',
                '马来西亚对铝锌镀层钢板征最高 35.06% 临时反倾销税',
                '马来西亚投资、贸易和工业部对原产或出口自中国、中国台湾和越南的合金及非合金钢铝锌镀层平轧产品征收 4.41% 至 35.06% 的临时反倾销税，措施自 11 月 7 日起生效、最长执行 120 天。',
                orig_title='Malaysia imposes provisional anti-dumping duties of up to 35.06% on aluminium-zinc coated flat-rolled imports from China, Taiwan and Vietnam')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/brazil-picks-27-critical-minerals-in-push-for-local-supply-chain',
                'MINING.COM', '11-08',
                '巴西圈定 27 种关键矿产，分三档支持本土产业链',
                '巴西关键与战略矿产工业化全国委员会 11 月 5 日批准 27 种关键矿产清单并分三档：高优先级九种为稀土、石墨、锂、镍、钴、铜、锰、硅、铀；中优先级八种为钨、铬、钒、钽、钛、磷、钾、硫；低优先级十种为铌、锡、铁、锌、金、镁、钼、钍、铝与铂族金属。仅清单内且完成国家登记的项目可获联邦支持，分类每 4 年复核一次。',
                orig_title='Brazil picks 27 critical minerals in push for local supply chain')),

    (CAT_GJ, ni('https://www.mining.com/australian-miners-rail-against-looming-tax-changes/',
                'MINING.COM', '11-08',
                '澳矿企反对资本利得税改革，称将削弱勘查投入',
                '澳大利亚 2026 年 5 月预算提出自 2027 年 7 月 1 日起，以成本基础指数化加 30% 最低税率替代现行 50% 资本利得税折扣，并确认矿产勘查企业不享受科技初创企业同等豁免。Evolution Mining 董事长 Jake Klein 在悉尼 IMARC 会上称该税「很糟」；澳大利亚矿业委员会首席经济学家 Ross Lambie 认为改革忽视勘查高风险、低成功率的特征，将削弱投资者支持早期发现的意愿。',
                orig_title='Australian miners rail against looming tax changes')),

    (CAT_GJ, ni('https://news.smm.cn/news/64T6UNPBCZ75R7U3XW2KFH4KNP3GS7TLP2UNGJI',
                '上海有色网', '11-08',
                '刚果（金）要求美国把战略矿产伙伴关系落到具体投资',
                '刚果（金）经济部长 Daniel Mukoko Samba 11 月 6 日表示，刚美 2025 年签署的战略矿产伙伴关系应以已完成项目而非签署协议来衡量，双方已审查 Lobito 走廊、推动更多刚果铜钴进入美国市场等优先项目；矿业部长 Louis Watum Kabamba 强调创造就业、技能转移与遵守当地矿业法。美方支持的铜钴矿商 Virtus Minerals 已增加对美铜供应。')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/BKPZIAYHVVDTG2C7QMGIEXZYEW5LDU34ZVW6DEI-bougounis-5th-lithium-concentrate-cargo-reaches-hainan',
                'SMM 国际站', '11-08',
                '布古尼第 5 船 1.74 万吨锂精矿运抵海南洋浦港',
                '海南矿业披露，马里布古尼（Bougouni）锂矿生产的 1.74 万吨锂精矿近日运抵海南洋浦港，为该矿发运的第 5 批锂精矿；2026 年以来布古尼累计发运锂精矿 9.33 万吨，另有 3 万吨锂精矿待装船出口。',
                orig_title='Bougouni’s 5th Lithium Concentrate Cargo Reaches Hainan')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://disc.szse.cn/download/disc/disk03/finalpage/2026-11-06/22f9ff29-8d92-4ac6-a5b1-dfb62f82bc13.PDF',
                '深圳证券交易所', '11-06',
                '湖南黄金回复深交所问询，重组报告书草案修订稿披露',
                '湖南黄金拟发行股份购买湖南黄金集团、湖南天岳投资集团合计持有的湖南黄金天岳矿业 100% 股权，以及湖南黄金集团持有的湖南中南黄金冶炼 100% 股权，并发行股份募集配套资金。公司于 2026 年 10 月 9 日收到深交所审核问询函，已逐项核查回复并修订重组报告书草案，新增与湖南黄金集团的《减值承诺补偿协议》等安排。',
                embed='pdf')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-07/1225662663.PDF',
                '巨潮资讯网', '11-07',
                '中铝国际 1.0008 亿元转让九冶三维 60% 股权',
                '11 月 6 日，中铝国际非全资附属公司九冶与沈阳院签订股权转让协议，九冶以人民币 1.000812 亿元（100.0812 百万元）向沈阳院转让其持有的九冶三维 60% 股权。以 2026 年 3 月 31 日为评估基准日，九冶三维全部股东权益收益法评估值为 1.66802 亿元（166.802 百万元）。交易完成后中铝国际持股比例下降 7.7676%，九冶三维仍为间接非全资附属公司。',
                embed='pdf')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475226',
                '中国有色金属报', '11-05',
                '宏旺钛材 TA1 工业纯钛卷材下线',
                '湖南宏旺钛材科技有限公司 TA1 工业纯钛卷材顺利下线，采用成套精密冷轧工艺，产品耐腐蚀性突出、塑性与焊接加工性能优异，可满足折弯、成型、分切等深加工需求，适用于化工防腐、环保设备、电镀工装与通用钣金领域，并填补中部地区钛材配套供应的产能缺口。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475246',
                '中国有色金属报', '11-06',
                '第二十九届中国国际铅锌年会在东莞召开',
                '11 月 4 日，由中国有色金属工业协会主办的第二十九届中国国际铅锌年会在广东东莞召开，主题为「新质赋能 韧性共生——夯实战略产业根基」，聚焦技术创新、新兴场景、产业链协同、战略金属回收及资源综合利用等议题；国际锌协会、国际铅锌研究组代表出席会议并致辞。')),
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
    ('花旗', CAT_SC),
    ('LME 期铜', CAT_SC),
    ('AI 相关资本开支', CAT_SC),
    ('铅锭', CAT_SC),
    ('硫酸', CAT_SC),
    ('马来西亚', CAT_ZC),
    ('巴西', CAT_GJ),
    ('澳矿企', CAT_GJ),
    ('刚果', CAT_GJ),
    ('布古尼', CAT_GJ),
    ('湖南黄金', CAT_MA),
    ('中铝国际', CAT_MA),
    ('宏旺钛材', CAT_HY),
    ('铅锌年会', CAT_HY),
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
