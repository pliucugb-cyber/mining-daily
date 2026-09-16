# -*- coding: utf-8 -*-
"""
生成 2026-09-16 矿业资讯速览 index.html
- 09-15 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-18）回补历史条目
- 换入 09-16 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所 09-15 收盘 + LME 09-15 收盘，全部由 price_history_detail.json /
  lme_data.json 现算（零手抄）；电解钴无当日源保留上日 SMM 值并标注
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

REPORT = '2026-09-16'
GRAB = '2026-09-16'
ARCHIVE_DAYS = 30
REPORT_DT, CUTOFF_DT = window(REPORT, ARCHIVE_DAYS)
item_after_cutoff = partial(_item_after_cutoff, report_dt=REPORT_DT, cutoff_dt=CUTOFF_DT)
DATA_ASOF = '09-09'   # 电解钴：SMM 无连续日K，保留最近一次人工值

# ============ 1. 标题 / 日期 / build-version ============
# 站点名固定「矿业资讯速览」，标题统一写成「矿业资讯速览 · YYYY-MM-DD」。
# 用宽松匹配吃掉落点前的任意旧标题，可覆盖三种历史写法：
#   纯日期（2026-09-07~09-12，站名丢失）／「站名 日期」（09-04~09-06）／「站名 · 日期」。
# 2026-09-12 修复：此前 09-07 起写成纯日期，浏览器标签页只剩一个光秃秃的日期，看不出是什么站。
html, _n_title = re.subn(r'<title>[^<]*</title>',
                         '<title>%s · %s</title>' % (SITE_NAME, REPORT), html, count=1)
assert _n_title == 1, 'title 替换次数异常: %d' % _n_title
assert '<title>%s · %s</title>' % (SITE_NAME, REPORT) in html, '站点标题格式不符'

html, _n_badge = re.subn(r'(<span class="date-badge"[^>]*>)2026年09月\d{2}日 星期.',
                         r'\g<1>2026年09月16日 星期三', html)
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

# ============ 4. 今日新增条目（09-15~09-16 抓取，均逐源核实真实发布日期） ============
# cnmn 列表日期仍失真（第 5 次复现）：本批 474045=09-16、474000/474005/473992/474003/474002/474001/
# 473993/473991/473996=09-15，但 473821/473816/473833=09-08、473955/473957/473954/473948=09-14，
# 故选条前逐条抓详情页核过真实日期。
new_items = [
    # ---------- 📜 政策与监管 ----------
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260914_2938258.html',
                '自然资源部', '09-14',
                '自然资源部公示矿业权出让权限非油气矿产勘查方案评审专家库名单',
                '自然资源部 9 月 14 日公示矿业权出让权限非油气矿产勘查方案评审专家库人员名单，公示期内接受社会监督。该专家库服务于部级矿业权出让权限内的非油气矿产勘查方案评审，是规范矿业权出让审批、强化勘查方案技术把关的配套制度建设。名单及公示说明详见自然资源部官网。')),
    (CAT_ZC, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=474005',
                '中国有色金属报', '09-15',
                '《矿产资源对外合作可持续发展自律倡议》发布',
                '9 月 10 日，中国五矿化工进出口商会在 2026 中国国际矿业大会「绿色矿产国际经贸合作交流活动」上发布《矿产资源对外合作可持续发展自律倡议》。该倡议由中国五矿化工进出口商会、中国矿业联合会、中国钢铁工业协会及近 30 家行业企业共同发起，覆盖境外投资贸易、勘探开发、冶炼加工、再生矿产回收及上下游供应商，旨在形成中国矿产供应链对外合作共同遵循的行业行为规范。')),
    (CAT_ZC, ni('https://www.chinania.org.cn/html/hangyetongji/tongji/2026/0915/62001.html',
                '中国有色金属工业协会', '09-15',
                '秘鲁推出矿业政务改革 未来 5 年力争 330 亿美元投资',
                '秘鲁新一届政府 8 月下旬正式推出矿业政务改革，明确精简审批流程、消除重复办理程序，同时重申不放宽环境与社会监管标准。政府同步公布未来 5 年矿业投资规划，力争实现至少 330 亿美元投资规模，并于 2026 年内审批通过 240 个矿业勘探与开采项目。作为全球第三大产铜国，秘鲁正通过稳定法律政策、标准化审批流程为矿企营造可预期投资环境。')),

    # ---------- 🔍 找矿成果与勘查技术 ----------
    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473992',
                '中国有色金属报', '09-15',
                '嘉能可科技重启中国本土化运营 亮出三大矿物加工核心技术',
                '在 9 月 10—12 日举行的 2026 中国国际矿业大会期间，嘉能可科技（Glencore Technology）宣布重启中国本土化运营，将矿物加工全套技术方案引入国内，助力国内矿山破解矿石品位下降、能耗管控等难题。本次集中展示超细研磨、高效浮选、难处理矿氧化浸出三大旗舰技术，含 IsaMill 艾萨磨机、Jameson Cell 詹姆森浮选机及 Albion Process 阿尔比恩工艺。其中艾萨磨机已在 23 个国家实现 144 套金属矿工业应用，詹姆森浮选机全球累计装机 500 台，阿尔比恩工艺对难处理硫化精矿浸出回收率可达 99% 以上。')),
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsyj/202609/t20260915_10313842.htm',
                '全球矿产资源信息系统', '09-15',
                '阿尔卡尼资源公司更新资源量 金资源量增至 862 万盎司',
                '阿尔卡尼资源公司（Alkane Resources）更新旗下矿山资产资源量，涵盖澳大利亚东部的博达-凯撒、托明格利、科斯特菲尔德项目及瑞典比尤克道尔金矿。目前公司总矿石资源量 5.79 亿吨，金品位 0.46 克/吨、铜 0.19%、锑 2.1%，即金资源量 862 万盎司、铜 101 万吨、锑 4.2 万吨；矿石储量 2500 万吨，金品位 1.7 克/吨、锑 1.6%，即金储量 137 万盎司、锑 1.5 万吨。托明格利和比尤克道尔储量增长 3%~4%，科斯特菲尔德金资源量增长 13%、锑增长 40%。')),
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/xfx/202609/t20260915_10313840.htm',
                '全球矿产资源信息系统', '09-15',
                '沙特麦地那地区圈定 1.1 亿吨含铀矿石 伴生重稀土',
                '沙特阿拉伯在麦地那地区圈定约 1.1 亿吨含铀矿石，能源部长阿卜杜勒阿齐兹·本·萨勒曼亲王在维也纳国际原子能机构第 70 届大会上公布该估算结果，称沙特正继续推进铀勘查并试验其作为化肥生产副产品的回收潜力。勘查与地质研究显示，矿石高富集稀土（特别是重稀土），同时亦有可观的铀富集。该发现为沙特增加重要国内铀来源，该国正寻求将核电纳入以油气为主的能源体系；目前品位与铀金属量尚未公布。')),

    # ---------- 📊 市场与价格 ----------
    (CAT_SC, ni('https://news.smm.cn/news/104115891',
                '上海有色网', '09-15',
                'SMM 日评：金属近全线下跌 沪锡跌 2.67% 领跌 碳酸锂跌逾 3%',
                '9 月 15 日国内基本金属普跌，仅沪铝飘红、涨幅 0.46%；沪锡以 2.67% 的跌幅领跌，沪铜跌 1.07%、沪铅跌 1.16%、沪锌跌 1.43%、沪镍跌 0.9%。碳酸锂主连跌 3.32%，多晶硅主连跌 1.21%，工业硅主连跌 1.57%，欧线集运主连跌 3.78%。外盘基本金属集体飘绿，伦镍以 0.94% 的跌幅领跌，伦锌跌 0.64%，伦铅、伦锡跌幅均在 0.22% 左右；贵金属方面 COMEX 黄金跌 0.44%、COMEX 白银跌 0.89%，沪金跌 1.55%、沪银跌 1.93%。')),
    (CAT_SC, ni('https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202609/t20260915_10313843.htm',
                '全球矿产资源信息系统', '09-15',
                '国际锡价持续下跌 伦锡收于 51,825 美元/吨',
                '周一国际原油价格上涨，其他矿产品价格多数下跌，其中锡价跌幅居前。伦敦金属交易所（LME）铜期货收于 14,023.00 美元/吨、下跌 1.42%，铝 3,248.50 美元/吨、下跌 0.25%，铅 1,879.00 美元/吨、下跌 0.69%，锌 3,803.00 美元/吨、下跌 1.54%，镍 16,420.00 美元/吨、下跌 0.55%，锡 51,825.00 美元/吨、下跌 2.58%。62% 品位铁矿粉收于 96.75 美元/吨、下跌 0.62%；铀（U3O8）收于 90.15 美元/磅、持平。')),
    (CAT_SC, ni('https://www.chinania.org.cn/html/hangyetongji/tongji/2026/0915/62000.html',
                '中国有色金属工业协会', '09-15',
                '多重因素影响 机构提示锌价回落风险加大',
                '协会行业分析指出，全球锌矿供应紧缺、加工费深度负值，冶炼亏损减产、精炼锌供给收缩，截至 9 月初国产 TC 跌至 -2100 元/金属吨、进口 TC 跌至 -125 美元/干吨；精炼锌周产量自二季度高位 10.52 万吨降至 9.01 万吨。需求端下游初端加工企业加权开工率 51.44%、处近 5 年低位，锌价站上 26,000 元/吨后下游畏高慎采。分析提示锌期货交易重心仍是 LME 市场结构性风险，锌价回落风险加大。')),
    (CAT_SC, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=473948',
                '中国有色金属报', '09-14',
                '8月中国有色金属产业景气指数 46.5 先行指数继续回升',
                '中国有色金属工业协会发布 8 月中国有色金属产业月度景气指数：产业景气指数 46.5，较上月下降 0.8 个百分点，仍处「正常」区间中部，构成指数 12 项指标全部位于「正常」区间；先行合成指数 92.7、较上月上升 1.0 个百分点，一致合成指数 80.8、较上月下降 5.4 个百分点。当月国内有色行业主要产品产量保持增长、投资微弱增长、行业利润实现跨越式提升。')),

    # ---------- 🏭 行业动态 ----------
    (CAT_HY, ni('https://news.smm.cn/news/104116146',
                '上海有色网', '09-15',
                '印尼新建商品交易所计划 2027 年 1 月开市 首批含锡和镍铁',
                '9 月 15 日，印尼商品交易所首席监督官 Sarjito 表示，印尼新建的 ICOMEX 大宗商品交易所计划于 2027 年 1 月 4 日开市交易，首批上市交易品种包含锡和镍铁，国有矿业企业预计将成为交易所首批参与主体。该交易所是印尼总统普拉博沃加强对本国丰富自然资源及收益管控举措的一环。印尼金融服务管理局（OJK）主席表示，交易所将有助于打击出口低报发票、终结大宗商品出口中的转让定价行为；OJK 预计 9 月 17 日出台交易所相关监管规则，交易所同日完成设立。')),
    (CAT_HY, ni('http://www.cnmn.com.cn/ShowNews1.aspx?id=474003',
                '中国有色金属报', '09-15',
                '阳光电源发布《矿区微电网白皮书》 助力绿色矿山转型',
                '9 月 10—12 日，阳光电源亮相 2026 中国国际矿业大会，并联合长沙有色冶金设计院、德国莱茵 TÜV 发布《矿区微电网白皮书》。白皮书提出，阳光电源深耕微电网近 30 年，拥有风、光、储、充、碳、控全域自研设备；针对不同矿区容量需求，方案覆盖小型（500kW—2.5MW）、中型（2.5MW—20MW）、大型（20MW—100MW）及微网群（100MW 以上）的梯度配置，并提供并网/离网、直流耦合/交流耦合等差异化部署，配套全周期服务。')),
    (CAT_HY, ni('https://www.chinania.org.cn/html/xiehuidongtai/xiehuidongtai/2026/0916/62008.html',
                '中国有色金属工业协会', '09-16',
                '铝用炭素分会年度工作会议在济南召开 石油焦期货开发受关注',
                '9 月 14 日，中国有色金属工业协会铝用炭素分会 2025—2026 年度工作会在济南召开，分会副主任委员、委员及会员单位代表 70 余人参加。会议听取年度工作报告，上海期货交易所副总经理杨柯介绍石油焦期货品种开发研究进展；与会代表围绕行业现状与市场变化、标准化工作、装备研发应用、绿色工厂建设、产学研协同创新、数智化转型等议题交流研讨。协会党委副书记、分会主任委员范顺科作总结讲话。')),
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0915/62005.html',
                '中国有色金属工业协会', '09-15',
                '西部镁业技术研究院以科技创新推动盐湖镁资源高值化利用',
                '青海西部镁业有限公司技术研究院常年扎根柴达木盆地，专攻盐湖镁资源绿色高值化利用领域，围绕盐湖卤水预处理、原料提纯到成品产出全链条开展技术攻关，承担盐湖卤水、氢氧化镁、氧化镁、高端镁基材料等检测与工艺优化工作。研究院把科技创新作为突破口，用科技成果为盐湖产业提质增效注入动力，是行业以技术攻关推动镁资源高值化利用的典型案例。')),

    # ---------- 🌐 国际矿业动态 ----------
    (CAT_GJ, ni('https://www.mining.com/red-sea-disruption-puts-global-mining-supplies-at-risk',
                'MINING.COM', '09-15',
                '红海航运受阻或冲击全球矿业供应链 酸类与电池原料成本承压',
                '咨询机构 GEM 建模显示，若曼德海峡周边扰动长期持续，冲击将远超油气领域，波及全球矿业供应链。酸类、化肥、电池原料（钴、铜、石墨、锂、镍）及燃料等被列为对成本上升与航运延误最敏感的大宗商品，相关矿业投入品价格与到货周期面临上行与延后风险。曼德海峡是红海航运的南向门户，为全球关键航运咽喉要道。',
                orig_title='Red Sea disruption puts global mining supplies at risk')),
    (CAT_GJ, ni('https://www.mining.com/us-department-of-war-commits-450-million-to-tungsten-supply-chain',
                'MINING.COM', '09-14',
                '美国国防部 4.5 亿美元投资钨供应链 1.5 亿定向内华达项目',
                '美国国防部（DoW）同意向 Elmet Group 投资 4.5 亿美元，其中 1.5 亿美元定向用于 Blue Moon Metals 位于内华达州的 Springer 钨矿综合体，这是华盛顿重建战略金属本土供应链的最新动作。根据与 Elmet 及澳大利亚 EQ Resources 达成的具约束力协议，Blue Moon 将获得 5000 万美元钨精矿预付款。美国正寻求降低在关键矿产上对中国的依赖。',
                orig_title='Pentagon backs $150M Blue Moon tungsten restart')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104116226-trump-administration-poised-to-approve-deep-sea-mining-permits',
                'SMM 国际站', '09-15',
                '美国拟批准深海采矿许可 加速获取关键矿产',
                '美国内政部长 Doug Burgum 在休斯敦 G20 能源部长会议上表示，深海采矿许可「可能在数月内」发放，这是特朗普政府扩大美国关键矿产获取渠道的举措之一，旨在为美国及其盟友拓展供应链。深海多金属结核富含锰、镍、钴、铜等关键金属，相关许可审批长期受国际海底管理局规则争议牵制。',
                orig_title='Trump Administration Poised to Approve Deep-Sea Mining Permits for Critical Minerals')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104116145-flash-a-perfect-storm-of-supply-risks-keeps-molybdenum-oxide-n',
                'SMM 国际站', '09-15',
                '多重供应风险叠加 氧化钼价格逼近近期高位',
                'SMM 获悉，海外矿山减产、南美极端天气以及矿石品位与回收率下降等问题在近期行业协会会议上被集中讨论，强化了海外钼供应收紧预期，刺激部分买方采购，推动氧化钼价格升至约 34 美元/磅钼。供应侧预期继续支撑价格，部分矿山产量、品位与回收率问题可能要到 2028 年前后才实质性改善。中国市场同样坚挺，但高价抑制追涨，资金充裕买家、低库存用户及订单确定的生产商仍在按需采购。',
                orig_title='[Flash] A Perfect Storm of Supply Risks Keeps Molybdenum Oxide Near Recent Highs')),
    (CAT_GJ, ni('https://www.mining.com/billionaire-rineharts-hancock-takes-stake-in-nunavut-copper-explorer',
                'MINING.COM', '09-15',
                '澳洲富豪莱因哈特旗下 Hancock 入股加拿大努纳武特铜矿勘查公司',
                '澳大利亚矿业富豪吉娜·莱因哈特旗下 Hancock Prospecting 向专注加拿大努纳武特地区的早期铜矿勘查公司 White Cliff Minerals 投资 870 万澳元（约 620 万美元），取得 13.5% 股权，消息公布后该公司股价上涨。White Cliff 正推进其 Rae 项目，该项目目前尚无资源量或经济研究，过去一年的钻探取得强劲成果。',
                orig_title="Billionaire Rinehart's Hancock takes stake in Nunavut copper explorer")),

    # ---------- 💰 并购与投资 ----------
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-16/1225565034.PDF',
                '巨潮资讯网', '09-16',
                '国城矿业子公司签署合作框架协议暨关联交易进展',
                '国城矿业（000688）公告，其子公司签署合作框架协议暨关联交易的进展事项。该框架协议涉及子公司层面的合作安排，属关联交易范畴，公司已按信息披露要求履行相关程序并披露进展，具体合作内容与交易细节详见巨潮资讯网公告原文。',
                embed='pdf')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-16/1225564648.PDF',
                '巨潮资讯网', '09-16',
                '明泰铝业出售参股公司股权事项终止',
                '明泰铝业（601677）公告，公司此前筹划的出售参股公司股权事项终止，交易未能按原方案推进。公司按信息披露要求就该事项终止情况予以公告，具体原因及后续安排详见巨潮资讯网公告原文。',
                embed='pdf')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-15/1225563600.PDF',
                '巨潮资讯网', '09-15',
                '赤天化子公司安佳矿业花秋二矿扩建项目获批复',
                '赤天化（600227）公告，其全资子公司安佳矿业花秋二矿扩建项目获得主管部门批复，项目扩建获准推进，有利于提升子公司煤炭产能与经营规模。具体批复内容与产能规模详见公司公告原文（巨潮资讯网 PDF）。',
                embed='pdf')),

    # ---------- 💼 矿权交易 ----------
    (CAT_KQ, ni('http://static.cninfo.com.cn/finalpage/2026-09-15/1225563925.PDF',
                '巨潮资讯网', '09-15',
                '盛达资源子公司光大矿业完成采矿权延续登记',
                '盛达资源（000603）公告，其子公司光大矿业已完成采矿权延续登记。采矿权延续完成后，相关矿业权可依法继续持有，有利于子公司维持正常生产经营，具体登记信息详见公司公告原文（巨潮资讯网 PDF）。',
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

# ============ 3.6 数字落地校验（2026-09-14 新增，复用 verify_numbers） ============
# 每条摘要的数字须能在源文（候选池/月库）找到，防 LLM 抄错数字（如 113米看成别的）。
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
