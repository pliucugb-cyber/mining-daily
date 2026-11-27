# -*- coding: utf-8 -*-
"""
生成 2026-11-27 矿业资讯速览 index.html（周五）
- 11-26 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30）回补历史条目
- 换入 11-26/11-27 采集的条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 与 LME 均为最近已收盘交易日，全部由
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

REPORT = '2026-11-27'
GRAB = '2026-11-27'
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
                         r'\g<1>2026年11月27日 星期五', html)
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
    (CAT_ZC, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202611/t20261126_10375548.htm',
                '全球矿产资源信息系统', '11-26',
                '巴西加紧关键矿产国家管控，13部门委员会可否决并购交易',
                '巴西 9 月由总统卢拉签署实施《关键矿产法》，并据此设立由 13 个政府部门组成的委员会，该委员会有权否决各类并购交易及长期供应合同。目前至少有 18 家外国企业在巴西参与稀土项目，已投入及预计投入资金合计超过 35 亿美元；巴西能获得多少经济效益，取决于本土加工能力的建设规模。此外，厄尔尼诺带来的强降雨风险上升，国家矿业局（ANM）将加强对米纳斯吉拉斯州尾矿坝的检查。')),

    (CAT_ZC, ni('https://news.smm.cn/news/BM6LZESOWEFRMDMO3ALUDO6TX4BJUMXUOLQPSBQ',
                '上海有色网', '11-23',
                '印尼拟将国家矿业收益分成提至70%，仅适用新项目',
                '印尼能源与矿业部长巴希尔表示，政府正制定方案，通过国有持股 70% 或国家获得 70% 收入分成的方式提高国家从矿业公司获得的收益，具体方式仍在讨论。他强调将尊重现有合同，股权变化仅适用于未来新项目。印尼是全球最大的动力煤、镍和锡出口国，也是主要铜出口国；矿业专业人士协会称国家现有收益已远超企业利润，CreditSights 提示政策不确定性令板块需继续计入风险溢价。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://news.smm.cn/news/NFVL2UXAEQ3JAHEUEKLU3ITMKLGX5VSVUDN6PTA',
                '上海有色网', '11-27',
                'Nyrstar 11月30日起关停荷兰 Budel 锌冶炼厂',
                '托克集团旗下 Nyrstar 11 月 26 日表示，因运营在经济上已不可行，将从 11 月 30 日起停止荷兰 Budel 冶炼厂的锌生产。该厂锌产能为每年 31.5 万吨，因能源成本高企于 2024 年 1 月停产、当年 5 月重启；今年 9 月公司已对该厂区启动战略评估。首席执行官称冶炼厂市场条件仍极具挑战，呼吁政策制定者迅速行动以保留战略加工能力；公司预计停产不会直接导致正式员工裁员。')),

    (CAT_SC, ni('https://news.smm.cn/news/S6644ULLZHAZIKHWJDWY43YGQOSI5GFVXNLPJ4Y',
                '上海有色网', '11-25',
                '摩根大通下调2027年基本金属展望，铜价看至11000美元',
                '摩根大通 11 月 24 日发布最新展望，预计基本金属 2027 年进一步走弱：铜价将向每吨 11000 美元（约 7.8 万元/吨，不含税）回落，因美国去库存削弱关税驱动的溢价、美国以外供需转松；铝价 2027 年底前回落至每吨 2500 美元（约 1.8 万元/吨）。锌因精矿供应偏紧、库存偏低，2027 年均价有望维持在每吨 3400 美元左右，但 2028 年矿山供应复苏将施压；镍预计在每吨 15500—16500 美元区间运行。')),

    (CAT_SC, ni('https://news.metal.com/newscontent/OZTT3E5NE4M4VOC5DD5WR77CBUU4UC6Q6FS7PSI-codelco-asia-2027-copper-long-term-contract-premium-at-268mt',
                'SMM 国际站', '11-25',
                'Codelco 2027年亚洲铜长单溢价268美元/吨，同比降23.4%',
                '据市场消息，智利国家铜业公司（Codelco）已向部分中国和韩国买家口头报出 2027 年铜阴极长单溢价 268 美元/吨（约 1900 元/吨），较 2026 年的 350 美元/吨下降 82 美元，降幅约 23.4%。长单溢价是观察亚洲铜市供需松紧的先行指标，此次下调与市场对 2027 年全球铜市供应转松的预期一致。',
                orig_title='Codelco Asia 2027 copper long-term contract premium at $268/mt')),

    # ── 🔍 找矿成果与勘查技术 ────────────────────────────────────
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202611/t20261126_10375550.htm',
                '全球矿产资源信息系统', '11-26',
                '巴西圣弗朗西斯科钻探见10.02米厚、铜品位11.75%富矿',
                '前瞻资源公司（Prospectiva Resources）在巴西圣弗朗西斯科火山块状硫化物矿床的扩边孔 SF_26_006，于 104.98 米深处见矿 10.02 米，铜品位 11.75%、金 0.87 克/吨、锌 1.09%；其东北约 60 米的 SF_26_003 孔曾于 85.85 米深处见矿 7.15 米、铜品位 4.78%。公司正沿一条长 3 公里的远景带钻探，今年已完成 9 个孔，两台钻机预计 12 月 31 日前完工，计划明年初步估算资源量。')),

    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475614',
                '中国有色金属报', '11-26',
                '中国恩菲厄立特里亚Augaro金矿环评获批14项工作大纲',
                '中国恩菲承担的厄立特里亚 Augaro 金矿社会与环境影响评价，其范围界定报告及 14 项工作大纲获厄立特里亚水土环境部正式批准，项目取得重要阶段性进展。获批文件明确了评价边界、核心评价议题、技术路线、公众参与和利益相关方磋商方案，以及基线调查遵循的准则，为后续社会与环境影响评价、管理计划报告编制搭好技术框架。该项目是中国恩菲落地海外的首个环评项目。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://news.smm.cn/news/O7GIFZX7IFT7SMVBKRK25LSALZUMLUPYH24NHPY',
                '上海有色网', '11-27',
                '1—10月规上工业企业利润增16%，有色冶炼利润增71.7%',
                '国家统计局数据显示，1—10 月全国规模以上工业企业实现利润总额 67373.6 亿元，同比增长 16.0%；其中采矿业利润 9936.1 亿元、增长 38.8%，制造业利润 51137.5 亿元、增长 17.5%。有色金属矿采选业利润同比增长 60.2%、有色金属冶炼和压延加工业增长 71.7%，两者合计拉动规上工业利润增长 4.6 个百分点。统计局解读称，新能源和人工智能产业快速发展带动铜、铝等基础金属需求旺盛、价格上涨，是主要拉动因素。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475620',
                '中国有色金属报', '11-26',
                '中铝集团领航级智能工厂实现“零的突破”，包铝入选',
                '工信部等六部门联合发布 2026 年度领航级智能工厂培育名单，中铝集团所属包头铝业申报的“面向极致能效的高端电解铝智能工厂”入选，成为电解铝行业首家领航级智能工厂培育对象，中铝集团领航级智能工厂实现零的突破。领航级是四级培育体系的最高层级，要求企业已获评卓越级且人工智能应用场景比例不低于 60%。目前中铝集团已培育领航级、卓越级智能工厂 5 家，先进级 31 家、基础级 29 家。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/congo-closes-in-on-chiles-long-held-copper-crown',
                'MINING.COM', '11-26',
                '刚果（金）铜出口首破百万吨，逼近智利铜王座',
                '刚果（金）三季度铜出口首次突破 100 万吨，前三季度出口 270 万吨、同比增长 8%；同期智利出口 128 万吨，领先优势明显收窄。洛阳钼业旗下两座矿山前三季度出口近 55 万吨，嘉能可与 Sicomines 各 21.2 万吨，卡莫阿-卡库拉 18.7 万吨。智利今年产量预计跌破 500 万吨、为 2003 年以来最低，但随扩建项目投产有望在 2030 年前后回到 600 万吨/年；刚果（金）国有 Gécamines 另计划在瑞士设立铜交易台。',
                orig_title="Congo closes in on Chile's long-held copper crown")),

    (CAT_GJ, ni('https://www.mining.com/turkeys-copler-gold-mine-restarts-after-2024-fatal-landslide',
                'MINING.COM', '11-26',
                '土耳其Çöpler金矿重启，年底前目标产金1.3吨',
                '土耳其东部 Çöpler 金矿在 2024 年 2 月堆浸场垮塌事故两年多后恢复产金，运营商 Anagold 已于三季度在临时运营许可下开始处理库存矿石，目标年底前产出约 1.3 吨黄金。停产前该矿年产量约 6.9 吨，相当于土耳其 2023 年总产量的五分之一。原股东 SSR Mining 已将 80% 股权以 15 亿美元售予土耳其 Cengiz Holding；2024 年事故造成 9 名工人死亡，相关诉讼仍在审理。',
                orig_title="Turkey's Çöpler gold mine restarts after 2024 fatal landslide")),

    (CAT_GJ, ni('https://www.mining.com/ivanhoe-mines-taps-ai-to-unlock-angolas-geological-archives',
                'MINING.COM', '11-26',
                '艾芬豪用AI解锁安哥拉百年地质档案，锁定2.2万平方公里铜靶区',
                '艾芬豪矿业（Ivanhoe Mines）出资部署 GeoIntelX 地质智能平台，与安哥拉地质研究所（IGEO）合作，将安哥拉逾一个世纪的历史地质记录数字化并用 AI 分析，以加快绿地区铜矿发现。其全资子公司 Cuando-Recursos 将在莫希科、宽多两省逾 2.2 万平方公里范围内寻找沉积型铜矿。平台可将历史报告数字化、地质图配准并支持对话式检索，帮助团队把精力集中在最有前景的靶区。',
                orig_title="Ivanhoe Mines taps AI to unlock Angola's geological archives")),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-27/1225689811.PDF',
                '巨潮资讯网', '11-27',
                '金石资源拟缴3亿保证金，参与白乃庙铜业破产重整',
                '金石资源公告，拟报名参与乌兰察布市白乃庙铜业有限责任公司破产重整意向投资人公开招募，并按招募要求缴纳意向保证金 3 亿元；该事项已经公司第五届董事会第十五次会议审议通过。白乃庙铜业矿区开发始于上世纪六十年代，核心资产为 3 项采矿权、4 项探矿权，矿种以铜为主并伴生多种有价金属；四子王旗法院已于 2025 年 12 月 31 日裁定受理其破产重整，管理人 2026 年 10 月 30 日发布招募公告。公司能否取得参与资格、最终能否被确定为重整投资人尚存在不确定性。')),

    (CAT_MA, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202611/t20261126_10375551.htm',
                '全球矿产资源信息系统', '11-26',
                '托克全资收购智利法罗拉铜金矿，从贸易延伸至矿山开发',
                '托克集团 11 月 23 日完成对阿泰尔矿产公司剩余 50% 股权的收购（另一半 2021 年已购入），从而全资持有智利法罗拉铜金矿项目，购买价格未披露。该项目已获环境许可，设计在 15 年开采期内年产含金铜精矿 9 万吨，详细设计 2025 年 5 月启动、建设原计划 2027 年 6 月开工；但洛斯洛罗斯土著社区就环境审批提起的诉讼尚未裁决，开发时间表存在变数。此举标志托克从精矿贸易转向直接持有并运营矿山。')),

    # ── 💼 矿权交易（仅入月库 → 前端 #rightsCards，不进主列表）─────────
    (CAT_KQ, ni('https://ky.mnr.gov.cn/kyqcrgg/tkq/202611/t20261127_10375576.htm',
                '矿业权市场', '11-26',
                '吉林敦化腰甸子北山金及多金属矿勘查探矿权挂牌出让',
                '吉林省公共资源交易中心受省自然资源厅委托，以挂牌方式出让敦化市腰甸子北山金及多金属矿勘查探矿权（公告文号：吉公交矿探挂字〔2026〕25号），勘查矿种为金矿。竞买保证金人民币 300 万元，须通过吉林省公共资源交易一体化平台一次性足额交纳；竞买人须未被列入严重失信主体等名单。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/jggs/jjgs/202611/t20261127_10375561.htm',
                '矿业权市场', '11-26',
                '内蒙古林西边家大院北铅矿探矿权成交，利拓矿业竞得',
                '内蒙古自治区自然资源厅公示，林西县边家大院北铅矿勘查探矿权于 2026 年 11 月 6 日至 11 月 20 日以网上挂牌方式出让，竞得人为赤峰市利拓矿业有限公司（公示文号：赤自然资示字〔2026〕6号），勘查矿种为铅矿。矿权人须按经批准的勘查实施方案作业，并依出让合同约定办理后续手续。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/zrgs/tkzrgs/202611/t20261127_10375557.htm',
                '矿业权市场', '11-26',
                '江西上饶广信区周家铅锌矿详查探矿权转让至惟佳矿业',
                '江西省自然资源厅公示上饶市广信区周家铅锌矿详查探矿权转让事项（公示文号：赣自然探转公示〔2026〕69号），受让方为上饶市惟佳矿业有限公司，勘查矿种为铅矿。公示期 10 个工作日，异议可向省自然资源厅自然资源确权登记局书面提出。')),
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
    ('法国', CAT_ZC),
    ('刚果（金）', CAT_ZC),
    ('铜价跌至2026年新低', CAT_SC),
    ('国际矿产品价格', CAT_SC),
    ('硫磺', CAT_HY),
    ('Core Lithium', CAT_HY),
    ('必和必拓', CAT_HY),
    ('Trinity', CAT_ZK),
    ('Stratum', CAT_ZK),
    ('Namib', CAT_GJ),
    ('艾芬豪', CAT_GJ),
    ('ValOre', CAT_MA),
    ('南山铝业', CAT_MA),
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
