# -*- coding: utf-8 -*-
"""
生成 2026-11-06 矿业资讯速览 index.html（周五）
- 11-05 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-10-08）回补历史条目
- 换入 11-06 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 11-05 收盘 + LME 11-05 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目：11-06 增补 9 宗（广西 3 宗成交 + 云南 2 宗转让 + 湖北 1 宗转让
  + 江西 2 宗协议出让 + 宜宾 1 宗拍卖），已写入 data/news_2026-11.json，
  由 news-data.js 直出 #rightsCards，不进主列表
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

REPORT = '2026-11-06'
GRAB = '2026-11-06'
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
                         r'\g<1>2026年11月06日 星期五', html)
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
    # ── 🔍 找矿成果与勘查技术 ────────────────────────────────────
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/resources_update/202611/t20261105_10355593.htm',
                '全球矿产资源信息系统', '11-05',
                '澳大利亚斯珀金矿首个资源量 310 万盎司，品位 1.2 克/吨',
                '瓦拉塔矿产公司（Waratah Minerals）新南威尔士州斯珀（Spur）项目首个资源量公布：金 310 万盎司、平均品位 1.2 克/吨，另有 1000 万盎司勘探潜力。露天坑采资源量约 230 万盎司、地下 76 万盎司，资源量仅覆盖 6 公里矿带中的 2 公里；发现成本 14.62 澳元/盎司，27% 属推定资源量。公司勘探目标为 500 万至 1000 万盎司、品位 0.6 至 0.9 克/吨。')),

    (CAT_ZK, ni('https://news.smm.cn/news/104200436',
                '上海有色网', '11-03',
                '加拿大奥佩米斯卡等铜矿启动 6.5 万米钻探',
                '廿九金属公司（XXIX Metal）启动 6.5 万米钻探计划，覆盖魁北克奥佩米斯卡（Opemiska）、库克（Cooke）与安大略蒂埃里（Thierry）三个铜矿项目；其中奥佩米斯卡详勘约 2 万米。7 月以来已有 2 台钻机在蒂埃里施工，12 月至次年 1 月初将在奥佩米斯卡和库克再增 4 台。公司称这是其历史上规模最大的一次钻探。')),

    (CAT_ZK, ni('https://news.metal.com/newscontent/104207701-cora-identifies-new-oxide-gold-mineralisation-near-planned-sanankoro-plant',
                'SMM 国际站', '11-05',
                'Cora 在马里 Sanankoro 发现 500 米长氧化金矿化带',
                'Cora Gold 公告，马里南部 Sanankoro 项目 Dakounkoura South 踏勘钻探发现走向长约 500 米的氧化金矿化带，4 个钻孔见矿，其中 16 米见矿段金品位 0.85 克/吨（自 20 米起）、35 米段 0.40 克/吨（自 5 米起）。靶区紧邻规划选厂且在现有资源量之外；公司已累计完成 14,081 米反循环钻探，现有资源量 104.4 万盎司、品位 1.04 克/吨。',
                orig_title='Cora identifies new oxide gold mineralisation near planned Sanankoro plant')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('http://gi.mnr.gov.cn/202611/t20261105_2941942.html',
                '自然资源部', '11-05',
                '规范探矿权招标出让征求意见结束，共收到 107 条建议',
                '自然资源部公告，《关于规范探矿权招标出让的通知（征求意见稿）》于 2026 年 10 月 8 日至 10 月 23 日向社会公开征求意见，共收到意见建议 107 条，将认真研究并最大程度吸收采纳。该通知为落实《矿产资源法》及实施条例、助推新一轮找矿突破、支撑战略性矿产增储上产而起草。')),

    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475202',
                '中国有色金属报', '11-05',
                '第二十一届全国地质勘查行业改革与发展大会在西安召开',
                '10 月 28 日至 29 日，第二十一届全国地质勘查行业改革与发展大会在陕西西安召开，主题为“深耕地勘改革攻坚，协同创新开发资源”。大会聚焦地勘行业改革发展面临的新形势、新任务，交流改革创新经验，为保障国家能源资源安全、推动地质勘查行业高质量发展提供支撑。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202611/fe52a954a9de42e38f32d157e5f2558c.html',
                '长江有色网', '11-05',
                '伦镍单日涨近 3%，伦铜跌至两个半月低位',
                'LME 基本金属涨跌不一：伦镍涨幅近 3% 领涨，伦锡进一步下跌，伦铜收于两个半月低位。市场在宏观情绪与产业基本面之间反复定价，镍价受印尼供给端扰动支撑明显强于铜。')),

    (CAT_SC, ni('https://news.metal.com/newscontent/104205168-flash-rotterdam-and-busan-molybdenum-oxide-prices-converge-above-3360lb-mo',
                'SMM 国际站', '11-04',
                '鹿特丹与釜山钼氧化物价格趋同，均站上 33.60 美元/磅',
                '11 月 3 日鹿特丹仓库钼氧化物报 33.65 美元/磅（EXW），11 月 4 日釜山报 33.60 美元/磅，折人民币约 5,598 元/吨度；两地价差收窄至 0.05 美元/磅，欧洲与亚洲现货基本并轨。欧洲钼铁报 78.30 美元/公斤钼，成交与付款条件尚未披露。',
                orig_title='Rotterdam and Busan Molybdenum Oxide Prices Converge Above $33.60/lb Mo')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202611/03eef9f7d2864be6b54c6c5bf1f01990.html',
                '长江有色网', '11-04',
                '供给修复需求转弱，碳酸锂震荡偏弱、去库仅能放缓跌势',
                '碳酸锂期货震荡偏弱运行：供给端修复叠加需求转弱，社会库存虽仍在下降，但去库节奏仅能放缓跌势，难以扭转价格重心下移的格局。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.smm.cn/news/104203989',
                '上海有色网', '11-04',
                '金力永磁前三季度净利增 47.48%，机器人电机转子爬坡上量',
                '金力永磁 2026 年前三季度净利润同比增长 47.48%，公司称具身机器人电机转子按客户订单爬坡上量，并按期新建 2 万吨磁材产能。11 月 4 日公司股价收涨 3.81% 至 24.22 元/股。')),

    (CAT_HY, ni('https://news.smm.cn/news/104202782',
                '上海有色网', '11-04',
                '中信戴卡与有色网交易中心启动 2027 年度铝锭长协线上竞价',
                '中信戴卡携手上海有色网交易中心启动 2027 年度铝锭长协线上竞价，将年度长单采购移至线上平台集中竞价，以市场化方式形成长协价格，为铝锭长单定价提供新的交易场景。')),

    (CAT_HY, ni('https://news.smm.cn/news/104202309',
                '上海有色网', '11-05',
                '全球锌精矿加工费刷新低，SMM 预计 2027 年供应紧张缓解',
                'SMM 高级分析师李函玉在 2026 SMM 铅锌年会上表示，全球锌精矿加工费已刷新低点；随着国内外矿山进入投产高峰、海外新增产能体量更大，2027 年锌精矿供应紧张局面将相对缓解，2027 至 2030 年维持紧平衡，但矿端扰动增多、波动风险仍存。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-06/1225660317.PDF',
                '巨潮资讯', '11-06',
                '兴业银锡取得威领股份控制权，收购进展落地',
                '兴业银锡披露对外投资收购威领股份的进展公告：公司已取得威领股份控制权，本次收购由此进入实质控制阶段。')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-06/1225659647.PDF',
                '巨潮资讯', '11-06',
                '天赐材料与亿纬锂能签订长期供货协议',
                '天赐材料公告与亿纬锂能签订长期供货协议，双方就锂电材料长期供应达成合作，锁定下游客户长单需求。')),

    (CAT_MA, ni('https://www.mining.com/rio-tinto-injects-144m-into-resolution-copper-after-land-battle-win',
                'MINING.COM', '11-05',
                '力拓向 Resolution Copper 追加 1.44 亿美元，推进井下开拓',
                '力拓向美国亚利桑那州 Resolution Copper 项目追加 1.44 亿美元，资金将用于推进工程设计与井下开发。该项目在土地交换获批后重启推进，但法律与人文争议仍未平息。',
                orig_title='Rio Tinto injects $144M into Resolution Copper after land battle win')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/codelco-halts-andina-mine-as-tailings-spill-threaten-river',
                'MINING.COM', '11-05',
                'Codelco 因尾矿泄漏暂停 Andina 选厂，河水取水口关闭',
                'Codelco 因尾矿输送系统发生部分泄漏、可能进入布兰科河，暂停 Andina 分部选厂作业与尾矿输送，将水改道至 Piuquenitos 水库并持续监测水质。智利水务公司 Esval 预防性关闭阿空加瓜河地表取水口、启用地下水源与备用系统。事故原因与下游环境影响仍在调查，复产时间未定。',
                orig_title='Codelco halts Andina mine as tailings spill threatens river')),

    (CAT_GJ, ni('https://www.mining.com/codelcos-inflated-copper-output-scandal-hits-42100-tonnes',
                'MINING.COM', '11-05',
                'Codelco 虚增铜产量 42,100 吨，已解雇 9 名员工',
                'Codelco 董事长在向股东通报的临时会议上披露，报表中被人为虚增的铜产量达 42,100 吨，另有 17,000 吨铜库存存在核算偏差。公司将在产品错列为产成品以完成指标，已对 3 座矿山及总部启动审计并解雇 9 名员工；过去八年投入 320 亿美元，年产量却由约 160 万吨降至 120 万吨。',
                orig_title="Codelco's inflated copper output scandal hits 42,100 tonnes")),

    (CAT_GJ, ni('https://www.mining.com/anglogold-plans-900-million-mine-expansion-amid-stronger-profit',
                'MINING.COM', '11-05',
                'AngloGold 拟投 9 亿美元扩产，2030 年前增产 30 万至 45 万盎司',
                'AngloGold Ashanti 计划投资至多 9 亿美元扩建既有矿山，目标 2030 年前增产 30 万至 45 万盎司，项目实际内部收益率预计超 35%。其中坦桑尼亚 Geita 获投至多 5.8 亿美元、产量提升至 60 万盎司；巴西 Cuiabá 投资 2 亿至 2.5 亿美元、增产约 7.5 万盎司；几内亚 Siguiri 投入 7000 万美元、增产 10 万盎司。三季度 EBITDA 同比增 12% 至 15.68 亿美元。',
                orig_title='AngloGold plans $900 million mine expansion amid stronger profit')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202611/t20261104_10354380.htm',
                '全球矿产资源信息系统', '11-04',
                '刚果（金）查扣数千吨铜钴，对非法采矿展开调查',
                '刚果（金）司法部称，警方、军方与矿业部组成的联合工作组在卢阿拉巴省和上加丹加省调查后，查扣 500 多辆卡车及其他车辆机械、数千吨铜和钴，司法部长已下令深入调查，最终可能指向欺诈、非法采矿与矿产品走私。此前联合国电台报道称 60 多名外国公民在卢阿拉巴门达被拘留。')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/104205215-smm-analysis-implats-q1-fy2027-production-falls-3-as-processing-disruptions-lift-inventories',
                'SMM 国际站', '11-04',
                'Implats 新财年一季度 6E 产量降 3%，成品库存上升',
                'Implats 2027 财年开局产量下滑：2026 年 7 至 9 月集团 6E 产量同比下降 3% 至 85.4 万盎司，精炼及可售产量下降 8% 至 76.3 万盎司。当季发生五起死亡事故、安全停产及加工中断，导致在制品与成品库存上升。',
                orig_title='Implats Q1 FY2027: Production Falls 3% as Processing Disruptions Lift Inventories')),

    (CAT_GJ, ni('https://www.ccmn.cn/news/ZX018/202611/69d7ab99aec542c69954486dce1f4c0d.html',
                '长江有色网', '11-04',
                '摩根大通：美国铜矿产量有望翻倍，新增 130 万吨产能',
                '摩根大通研判，在本土关键矿产保供政策推动下，依托新建矿山与现有产能扩建，美国年度矿产铜产量具备翻倍以上潜力，有望扭转数十年下滑趋势；新增产能约 130 万吨，但多数项目 2030 年前难以落地。')),

    (CAT_GJ, ni('https://www.mining.com/faster-mine-approvals-start-with-better-project-planning-bba-says',
                'MINING.COM', '11-06',
                '矿业审批提速始于更优前期规划，BBA 称',
                '工程咨询机构 BBA 指出，尽管监管审批流程的不确定性仍是行业痛点，矿业企业可通过更早厘清关键问题、让技术、环境与社会（社区）团队尽早协同介入，改善项目获批前景、缩短矿山建设核准周期。',
                orig_title='Faster mine approvals start with better project planning, BBA says')),
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

# —— 分桶 PIN（按内容口径：技改扩产属 🏭、勘查投入属 🔍，勿被 _reclassify_ma 依「投资」二字拉到 💰）——
_PIN_CAT = [
    ('斯珀', CAT_ZK),
    ('奥佩米斯卡', CAT_ZK),
    ('Cora', CAT_ZK),
    ('探矿权招标', CAT_ZC),
    ('地勘行业', CAT_ZC),
    ('伦镍', CAT_SC),
    ('钼', CAT_SC),
    ('碳酸锂', CAT_SC),
    ('金力永磁', CAT_HY),
    ('中信戴卡', CAT_HY),
    ('锌精矿', CAT_HY),
    ('威领', CAT_MA),
    ('天赐材料', CAT_MA),
    ('力拓', CAT_MA),
    ('Codelco', CAT_GJ),
    ('AngloGold', CAT_GJ),
    ('刚果', CAT_GJ),
    ('Implats', CAT_GJ),
    ('美国铜矿', CAT_GJ),
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
