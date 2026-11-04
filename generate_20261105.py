# -*- coding: utf-8 -*-
"""
生成 2026-11-05 矿业资讯速览 index.html（周四）
- 11-04 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-10-07）回补历史条目
- 换入 11-05 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所/GFEX 11-04 收盘 + LME 11-04 收盘，全部由
  price_history_detail.json / lme_data.json 现算（零手抄）；电解钴保留上日 SMM 值并标注
- 矿权条目：11-05 增补 7 宗（四川 4 宗成交 + 吉林 2 宗出让 + 湖北大冶张海金矿转让），
  已写入 data/news_2026-11.json，由 news-data.js 直出 #rightsCards，不进主列表
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

REPORT = '2026-11-05'
GRAB = '2026-11-05'
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
                         r'\g<1>2026年11月05日 星期四', html)
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
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202611/t20261104_10354381.htm',
                '全球矿产资源信息系统', '11-04',
                '西澳州纳纳迪铜金矿钻探见富矿，北部过渡带铜品位达 9.4%',
                '纳纳迪（Nanadi）项目钻探在北部过渡带 44 米深处见矿 10 米，铜品位 9.4%、金 2.13 克/吨、银 23.4 克/吨；19 米深处见矿 41 米，铜品位 2.79%、金 0.7 克/吨；77 米深处见矿 56 米，铜品位 0.62%、金 0.19 克/吨。北部采样显示矿体厚 89 米、铜品位 0.93%，其中含 11 米厚、铜品位 2.67% 的高品位段。项目现有矿石资源量 4,040 万吨，铜品位 0.4%、金 0.1 克/吨；另一孔在 137 米深处见矿 256 米，铜品位 0.36%、金 0.21 克/吨，终孔未穿透矿体。长 1.5 公里矿带的资源量更新将于 2027 年完成。')),

    (CAT_ZK, ni('https://news.metal.com/newscontent/104205218-tusker-advances-9152-km2-central-rutile-project-in-cameroon-towards-exploration-licences',
                'SMM 国际站', '11-05',
                'Tusker 喀麦隆 9,152 平方公里金红石项目获探矿权推荐授予',
                'Tusker Minerals 10 月 30 日公告，喀麦隆部际委员会已建议授予其 Central Rutile 项目探矿权申请，申请范围约 9,152 平方公里，含公司瞄准残余天然金红石的雅温得西部项目区。公司同时在雅温得实验室处理早期土壤与螺旋钻样品，Mineral Technologies 提供矿物分离与质量控制支持。该推荐仍属许可里程碑，其余申请尚需更新资料、签署勘查合同并取得部长级批文，公司尚未建立商业资源量或产量预测。',
                orig_title='Tusker advances 9,152 km² Central Rutile project in Cameroon towards exploration licences')),

    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475155',
                '中国有色金属报', '11-03',
                '铜绿山矿伴生金银回收率提升至 79.54%，年增效益超 1,000 万元',
                '大冶有色铜绿山铜铁矿通过优化磨矿分级与浮选药剂制度，截至 9 月底伴生金银回收率由长期徘徊的 75% 提升至 79.54%，矿山金产量同比增长 15.09%、银产量增长 11.04%，预计增加效益超 1,000 万元。该矿 2025 年伴生金银创造效益约 3.69 亿元、占矿产品总效益的 37.83%；矿石中金、银平均品位仅 0.5 克/吨和 3 克/吨。攻关查明中等粒级（0.025 至 0.12 毫米）回收率在 96% 以上，据此调整磨矿分级参数，旋流器分级效率提升超 5%。')),

    # ── 📜 政策与监管 ───────────────────────────────────────────
    (CAT_ZC, ni('https://www.mnr.gov.cn/dt/ywbb/202611/t20261104_2941786.html',
                '自然资源部', '11-04',
                '自然资源部规范煤层气勘查开采管理，出让权限统一上收',
                '自然资源部印发《关于煤层气资源管理有关事项的通知》，明确煤层气矿业权出让由自然资源部统一负责，登记、勘查采矿许可、储量审核与探采合一计划管理一并上收。煤炭和油气矿业权人均可综合勘查开采煤层气：煤炭矿业权人开采最低可采煤层以上的浅层煤层气，作为煤炭共伴生矿种由省级自然资源主管部门管理；开采最低可采煤层以下的深层煤层气由自然资源部管理。通知同时细化矿业权重叠处理，鼓励通过合资、技术合作等方式综合勘查开采。')),

    (CAT_ZC, ni('https://www.ccmn.cn/news/ZX006/202611/e12afd4240b94028a2b66c2381ba9d80.html',
                '长江有色网', '11-04',
                '印尼国家经济委员会支持按 RKAB 配额削减镍产量',
                '印尼国家经济委员会（DEN）表态，明确支持能源与矿产资源部（ESDM）依托 RKAB 开采配额机制削减镍产量，该国镍供给调控政策进入跨部门协同落地阶段。此前市场已因配额收紧消息带动镍价上涨近 20%，政策落地意味着印尼对镍供应的行政调节从部门层面上升到跨部门协同。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.ccmn.cn/news/ZX018/202611/1a310d407a7c43cc9d9efcb7b74ba667.html',
                '长江有色网', '11-04',
                '花旗下调锂价预测，碳酸锂目标价降至 1.2 万美元',
                '花旗集团发布锂市场最新研判，大幅下调未来两年锂系产品价格预测，最高降幅达 40%，覆盖碳酸锂、氢氧化锂与锂辉石精矿三大上游原料，并将价格预估延伸下调至 2028 年底。其中碳酸锂目标价下探至 1.2 万美元，给本就偏弱的锂市场再添悲观预期。')),

    (CAT_SC, ni('https://news.smm.cn/news/104202735',
                '上海有色网', '11-04',
                '沪锡主力盘中跌超 3%，期价落至逾七个月低位',
                '11 月 4 日沪锡夜盘大幅下跌、早间延续弱势，主力合约跌幅超过 3%，期价落至逾七个月低位。市场持续担心 AI 硬科技投资回报率，海外科技股偏弱运行，利空锡需求预期；同时海外流动性收紧压力仍在，多项风险事件即将落地，市场不确定性较强、风险偏好偏弱。')),

    (CAT_SC, ni('https://news.smm.cn/news/104202723',
                '上海有色网', '11-04',
                '沪铝库存连降二十周至 191,018 吨，创逾九个月新低',
                '上期所数据显示，10 月 30 日当周沪铝库存继续下降，已连降二十周，周度库存减少 10.26% 至 191,018 吨，降至逾九个月新低。库存持续去化反映节后消费与到货节奏偏紧，为铝价提供一定支撑。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475144',
                '中国有色金属报', '11-03',
                '云铝股份 6 项科技成果通过评价，3 项达国际领先水平',
                '10 月 23 日，云铝股份委托中国有色金属工业协会召开科技成果评价会，对申报的 6 项科技成果开展评价鉴定。经专家组综合评价，3 项达到国际领先水平、3 项达到国际先进水平，成果覆盖绿色铝电解节能降碳、交通结构件用高强铝合金与锻造轮毂、超大规格扁锭绿色智造、铝电解槽底清渣机器人等方向。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475113',
                '中国有色金属报', '11-02',
                '株冶锃科首批压铸锌合金发往东南亚，出口实现零突破',
                '株洲冶炼集团全资子公司深圳市锃科合金有限公司首批压铸锌合金产品启运发往东南亚市场，实现火炬牌锌合金出口零的突破。锃科公司 1994 年成立于深圳宝安沙井，压铸锌合金年产能已从初创的 2,000 吨增至 5 万吨、营收超 10 亿元，此次订单标志其正式构建「国内+海外」双市场格局。')),

    (CAT_HY, ni('https://www.mining.com/freeport-approves-4-5-billion-bagdad-copper-expansion',
                'MINING.COM', '11-04',
                'Freeport 批准 45 亿美元扩建 Bagdad 铜矿，年产铜将翻倍以上',
                'Freeport-McMoRan 批准对亚利桑那州 Bagdad 铜矿 45 亿美元扩建，投产后该矿年产铜将超过 4 亿磅、较当前增加约 2.25 亿磅，成为美国第二大铜矿；钼产量每年增加 1,200 万磅至 2,000 万磅以上。项目将新建日处理 11.5 万吨矿石的选矿设施及破碎、输送与配套基础设施，建设期约三年半，首批产量目标为 2030 年中，公司预计长期单位净现金成本下降约 20%。此次资本开支较 2023 年 35 亿美元的估算高出约 10 亿美元、即 29%。',
                orig_title='Freeport approves $4.5 billion Bagdad copper expansion')),

    (CAT_HY, ni('https://news.metal.com/newscontent/104205217-montage-gold-reports-23460-ounces-from-october-ramp-up-at-c',
                'SMM 国际站', '11-05',
                'Montage Gold 科特迪瓦 Koné 矿 10 月产金 23,460 盎司',
                'Montage Gold 公告，其科特迪瓦 Koné 矿 10 月处理约 88 万吨氧化矿，产金约 23,460 盎司；选厂平均运行在 1,100 万吨/年名义产能的 90% 以上，10 月最后一周达到 104%，入选品位 0.82 克/吨、回收率约 95%。该矿 9 月 26 日完成首次浇金，预计四季度宣布商业化生产；勘查钻探已圈定 12 个矿床（2024 年可研时为 2 个），年内钻探进尺超过 12 万米。',
                orig_title='Montage Gold reports 23,460 ounces from October ramp-up at Côte d’Ivoire’s Koné mine')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('https://www.mining.com/gordon-mining-acquires-tungsten-tail-project-in-new-mexico',
                'MINING.COM', '11-04',
                'Gordon Mining 完成收购美国新墨西哥州 Tungsten Tail 钨项目',
                'Gordon Mining Group（CSE: GORD）完成收购新墨西哥州 Sierra 县 Tungsten Tail 钨项目，该矿权共 41 个单元、约 847 英亩。交割时公司向卖方支付现金 12.5 万加元（约 8.9 万美元）并向 Strata Mine Technologies 发行 150 万股普通股，同时授予其 2.0% 净冶炼收益权，公司可以 100 万美元回购其中 1.0%。项目历史上曾在 1942 年与 1955 年有白钨矿小规模出货记录，公司计划以 AI 辅助靶区圈定结合 USGS 地球物理与紫外白钨矿测量确定首批钻孔。',
                orig_title='Gordon Mining acquires Tungsten Tail project in New Mexico')),

    (CAT_MA, ni('https://news.metal.com/newscontent/104205216-appian-deploys-70-of-ifcs-initial-us100-million-mining-commitment-across-ghana-and-namibia',
                'SMM 国际站', '11-05',
                'Appian 已部署 IFC 首期 1 亿美元矿业投资承诺的约 70%',
                '据路透社 11 月 4 日报道，Appian Capital Advisory 已部署国际金融公司（IFC）首期 1 亿美元矿业投资承诺的约 70%，投向三个项目：加纳 Asante Gold 金矿、纳米比亚 Omico Copper 铜矿以及巴西 Atlantic Nickel 的镍铜钴资产。Appian 与 IFC 的合作总额宣布为 10 亿美元，公司预计 2026 年底前投完首期余额，并继续在非洲与拉美寻找机会。',
                orig_title="Appian deploys 70% of IFC’s initial US$100 million mining commitment across Ghana and Namibia")),

    (CAT_MA, ni('http://disc.szse.cn/download/disc/disk03/finalpage/2026-11-03/77726d76-b520-4179-8e4a-2f2e686b5066.PDF',
                '深圳证券交易所', '11-03',
                '盛达资源与富宁方鑫黄金矿业及相关方签署框架合作协议',
                '盛达资源公告，公司与富宁县方鑫黄金矿业有限责任公司及相关方签署《框架合作协议》，就黄金矿业项目合作达成初步意向。框架协议不构成正式交易安排，具体合作方式、对价与实施进度尚待后续正式协议约定，以公司后续公告为准。',
                embed='pdf')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/coppers-biggest-new-mine-stumbles-again-as-costs-soar',
                'MINING.COM', '11-05',
                'Ivanhoe 下调 Kamoa-Kakula 2027 年产量指引至 30 万至 35 万吨',
                'Ivanhoe Mines 将刚果（金）Kamoa-Kakula 铜矿 2027 年产量指引由 38 万至 42 万吨下调至 30 万至 35 万吨，中点减少 7.5 万吨，远低于 3 月谨慎采矿计划前的 50 万至 54 万吨目标；2027 年现金成本（C1）指引由 2.10 至 2.50 美元/磅上调至 2.50 至 3.00 美元/磅，主因柴油价格高企、矿石品位下降与产量减少。公司计划 2027 年一季度启动第四期选厂扩建详细设计，目标将年产能提升至约 50 万吨，但项目尚未获批，获批后建设需 18 至 24 个月。',
                orig_title="Copper's biggest new mine stumbles again as costs soar")),

    (CAT_GJ, ni('https://www.mining.com/western-tungsten-prices-nearly-quadruple-chinas-report',
                'MINING.COM', '11-05',
                '西方钨价接近中国四倍，10 月鹿特丹 APT 价差达 3.74 倍',
                'MetalMiner 报告显示，受出口管制与美国供应链政策影响，西方钨价已升至接近中国的四倍：10 月鹿特丹仲钨酸铵（APT）成交价 278.22 美元/公斤，中国出厂价为 74.43 美元/公斤，价差 3.74 倍；而 2021 年 9 月至 2025 年 6 月的平均价差仅 1.24 倍。报告认为价差扩大反映市场按合规、地理可获得性与加工能力分层，而非全球性短缺；经历 14 轮关税措施后，西方溢价在 12 个月内扩大约 11%，常规时段约为 7%。',
                orig_title='Western tungsten prices nearly quadruple China’s: report')),

    (CAT_GJ, ni('https://www.mining.com/democrats-win-puts-us-mining-agenda-under-scrutiny',
                'MINING.COM', '11-04',
                '民主党赢下中期选举，美国矿业议程面临更严审视',
                '民主党在中期选举中赢得众议院与参议院控制权，明年 1 月起形成分治政府，美国矿业与能源议程面临更严格审视。BMO 与伍德麦肯兹认为，投资者需面对数据中心建设监管收紧、联邦投资被更仔细审查的可能，同时审批改革仍可能成为两党在能源可负担性上的共识议题；民主党此前已质疑联邦政府在矿业公司的持股与相关交易条款。',
                orig_title="Democrats' win puts US mining agenda under scrutiny")),

    (CAT_GJ, ni('https://www.mining.com/colombias-mining-rules-reset-puts-billions-back-in-play',
                'MINING.COM', '11-04',
                '哥伦比亚撤销两项矿业限制，或解锁 47 亿美元矿山建设投资',
                '哥伦比亚撤销前总统佩特罗时期的两项主要矿业限制，10 月 22 日解除覆盖 530 万公顷（近 5% 国土）的禁令，农业部另于 10 月撤销四个大区的粮食生产保护区，为矿产开发移除障碍。哥伦比亚矿业协会估计，更友好的投资环境可解锁 47 亿美元矿山建设投资、每年吸引 3.5 亿美元勘查支出，支撑行业年增速最高达 10%；但取消限制并不等于自动获批，企业仍须满足环境与用地审批要求。',
                orig_title="Colombia's mining rules reset puts billions back in play")),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kydt/hyyxdt/202611/t20261104_10354379.htm',
                '全球矿产资源信息系统', '11-04',
                '安永：运营复杂性成为 2027 年矿企最大风险',
                '安永《采矿与金属行业十大商业风险与机遇》报告将运营复杂性列为行业 2027 年最大风险，其后依次为资本可得性、供应链中断、成本上升与地缘政治，结论基于对全球 400 位采矿与金属高管的调查。监管审批滞后是造成运营复杂性的首要因素（29% 受访者），矿石品位不稳居次；44% 企业寻求设备制造商资本，39% 寻求主权财富基金与政府投资。为降低风险，53% 矿企投入技术提升供应链透明度、52% 通过增加库存保障运营；67% 的矿业与金属资产处于网络安全「脆弱地带」。')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kydt/hyyxdt/202611/t20261103_10353111.htm',
                '全球矿产资源信息系统', '11-03',
                'Cochilco 下调智利铜产量预期，2026 年料降至 494 万吨',
                '智利铜业委员会（Cochilco）大幅下调 2026 年该国铜产量预期：预计下降 8.4%（此前预测降幅 2.6%），产量降至 494 万吨，8 月时预计为 527 万吨。前三季度智利铜产量 363 万吨、同比下降 8.5%，要达成全年目标，四季度需月产 43.4 万吨、比前九个月均值高 7.6%。Cochilco 指出必和必拓埃斯康迪达等矿山净减产占全国减产量的 77%，同时将 2026、2027 年铜均价预期分别上调至 6.18 美元/磅和 5.95 美元/磅。')),

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
    ('纳纳迪', CAT_ZK),
    ('Tusker', CAT_ZK),
    ('铜绿山', CAT_ZK),
    ('煤层气', CAT_ZC),
    ('印尼国家经济委员会', CAT_ZC),
    ('花旗', CAT_SC),
    ('沪锡主力', CAT_SC),
    ('沪铝库存', CAT_SC),
    ('云铝股份', CAT_HY),
    ('锃科', CAT_HY),
    ('Bagdad', CAT_HY),
    ('Montage', CAT_HY),
    ('Gordon', CAT_MA),
    ('Appian', CAT_MA),
    ('盛达资源', CAT_MA),
    ('Kamoa', CAT_GJ),
    ('西方钨价', CAT_GJ),
    ('民主党', CAT_GJ),
    ('哥伦比亚撤销', CAT_GJ),
    ('安永', CAT_GJ),
    ('Cochilco', CAT_GJ),
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
