# -*- coding: utf-8 -*-
"""
生成 2026-11-28 矿业资讯速览 index.html（周六）
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

REPORT = '2026-11-28'
GRAB = '2026-11-28'
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
                         r'\g<1>2026年11月28日 星期六', html)
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
    (CAT_ZC, ni('https://news.smm.cn/news/3GFELUXPDFR5IT25ELDCFKEFRCFTHGSIP6KZMEI',
                '上海有色网', '11-27',
                '广期所将多晶硅期货单日开仓限额下调至600手',
                '广州期货交易所 11 月 27 日发布公告，自 2026 年 12 月 1 日交易时起，非期货公司会员或客户在多晶硅期货 PS2612 至 PS2711 共 12 个合约上的单日开仓量分别不得超过 600 手；单日开仓量按当日单个合约买开仓与卖开仓数量之和计算。套期保值交易、做市交易不受该标准限制，具有实际控制关系的账户按一个账户管理。')),

    (CAT_ZC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475629',
                '中国有色金属报', '11-26',
                '广东推进碳排放权、绿电绿证等期货期权品种上市',
                '广东省人民政府办公厅 11 月 23 日印发《广东省推进粤港澳大湾区世界级绿色低碳产业集群建设实施方案》，提出到 2030 年粤港澳大湾区绿色低碳产业集群产值超 6 万亿元。方案明确推进碳排放权、绿电绿证等期货期权品种上市，健全绿色低碳发展机制，布局一批绿色科技创新平台并培育具有国际竞争力的绿色低碳企业。')),

    (CAT_ZC, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202611/t20261127_10376799.htm',
                '全球矿产资源信息系统', '11-27',
                '博茨瓦纳将无偿持有新设勘探企业5%股份',
                '博茨瓦纳能矿部长克内文多表示，国家将无偿持有新成立勘探企业矿山 5% 的股份，由今年 2 月成立的勘探公司代表国家行使；采矿许可证颁发后，政府另有权购买项目 24% 股权。她称此举不是排挤私企，而是确保国家能从资产中获益。钻石市场低迷令该国经济连续两年萎缩，正寻求扩大铜、金、铂、铬、铁矿等非钻石矿业。')),

    # ── 📊 市场与价格 ───────────────────────────────────────────
    (CAT_SC, ni('https://www.mining.com/copper-price-jumps-most-since-january-as-short-sellers-retreat',
                'MINING.COM', '11-28',
                '铜价创1月以来最大单日涨幅，空头回补主导反弹',
                '伦敦金属交易所三个月期铜盘中一度上涨 6.5% 至每吨 12,600 美元上方，为今年 1 月以来最大单日涨幅，并有望录得 10 月初以来首个周度上涨；纽约商品交易所 3 月合约一度涨 6.3% 至每磅 5.76 美元。交易员称此轮上涨主要来自美股反弹触发的集中空头回补，中国库存偏紧放大了弹性；LME 铜库存升至 337,925 吨、周增约 3%，洋山铜溢价在创下每吨 500 美元纪录后回落至约 320 美元。',
                orig_title='Copper price jumps most since January as short sellers retreat')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202611/eeac448cb45b4ae39ec05749dd325a1e.html',
                '长江有色网', '11-27',
                '沪银单日大涨12.33%，贵金属超跌修复行情启动',
                '长江有色金属网称，沪银 11 月 27 日大涨 12.33%，沪金、铂、钯同步拉升，空头回补助推盘面走强。本轮上涨在前期贵金属持续大幅回调之后启动，价格下行带动技术指标进入超卖区间，叠加外围市场情绪修复，盘面迎来集中反弹。该机构提示内容仅供行业参考，不构成投资建议。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202611/62412266878948c09054eee14c8709e9.html',
                '长江有色网', '11-27',
                '锡价周内剧烈回调后强势反弹，三重因素共振',
                '长江有色金属网周评显示，11 月 23 日至 27 日金属市场剧烈回调，锡价单周大幅下挫成为核心焦点。美国核心 PCE 通胀超预期反弹推升美联储 12 月加息预期，叠加美方拟对多经济体加征关税、美元走强，压制大宗商品风险偏好；周内锡价抛售是宏观紧缩、冶炼产能复产、电子需求淡季三重因素共振的结果，周尾强势反弹。')),

    (CAT_SC, ni('https://www.ccmn.cn/news/ZX003/202611/f6be9ec88e654a0dbc1165838e475158.html',
                '长江有色网', '11-27',
                '碳酸锂逼近成本线，锂盐进入底部博弈阶段',
                '长江有色金属网指出，供给放量、淡季需求偏弱的基本面尚未扭转，碳酸锂现货价格仍存承压可能；但价格已靠近成本区间，高成本产能出清预期形成底部支撑，大幅下行空间有限，短期大概率维持区间震荡。锂盐行业由此进入底部博弈阶段。')),

    (CAT_SC, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475627',
                '中国有色金属报', '11-26',
                '氧化铝：几内亚配额悬而未决，2027年国内产量预计增7.6%',
                '中国有色金属报分析称，2027 年国内氧化铝产量预计由 2026 年的 9539 万吨升至 10263 万吨、同比增长 7.6%，海外产量 6455 万吨、增长 3.2%，国内供应过剩仍是共识。矿端方面，几内亚 3 月提出削减出口、5 月明确将出台配额制，市场普遍预期 2026 年出口上限降至 1.5 亿吨、较 2025 年实际出口 1.83 亿吨下降约 18%，但政策持续延期；11 月中旬几内亚表示将在 11 月底前发布生产监管文件，未明确提及配额制。')),

    # ── 🔍 找矿成果与勘查技术 ────────────────────────────────────
    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475524',
                '中国有色金属报', '11-24',
                '西北有色七一七总队中标内蒙达茂旗铜镍矿详查钻探',
                '西北有色地矿集团七一七总队公司地质勘查院先后中标“内蒙古自治区达茂旗某铜镍矿详查钻探技术服务”和“陕西省某耕地提质增效”两个项目。前者设计钻探总进尺 1500 米、单孔孔深 500 米，是該院近年来在内蒙古承接的首个钻探施工项目，已于 10 月 30 日开钻；后者为渭河中上游山水林田湖草沙一体化保护和修复工程子项目。')),

    (CAT_ZK, ni('https://www.cgs.gov.cn/ywdt/dwdt/202611/t20261127_873470.html',
                '中国地质调查局', '11-27',
                '青岛海洋所重建贵州西部3400年生态演化史',
                '中国地质调查局青岛海洋地质研究所联合广西大学、中山大学等，对贵州西部娘娘山泥炭湿地岩心开展高分辨率多指标分析，重建过去 3400 年植被演替、火事件与人类活动的耦合过程。研究发现距今约 3400—3200 年乔木花粉占比高达 92.05%、火活动微弱；近 600 年松属花粉升至 40.37%、常绿阔叶树种骤降至 9.64%，与明清毁林开垦记载吻合，揭示生物多样性对气候与人为扰动呈非线性响应。')),

    # ── 🏭 行业动态 ─────────────────────────────────────────────
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475616',
                '中国有色金属报', '11-26',
                '五矿山达克铜矿转炉电仪改造通过半年实战检验',
                '五矿中亚南亚资源所属山达克铜矿冶炼厂首期两台转炉电仪系统自动化升级改造项目经近半年稳定运行通过检验，实现全程零控制系统故障。改造后 PLC、HMI 及智能监控系统全面应用，双炉热互换生产每日节约操作时间 15 分钟、全年累计超 40 小时，年新增综合经济效益超 10 万美元；二期技改计划 2027 年停产窗口期实施，覆盖反射炉、锅炉、电收尘等核心设备。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475566',
                '中国有色金属报', '11-26',
                '新疆昆仑蓝钻2000公里远程集控系统完成联调',
                '新疆昆仑蓝钻矿业以“揭榜挂帅”模式牵头攻坚的高海拔超长链路远程集控系统，11 月 13 日完成为期 9 天的不间断联调测试。乌鲁木齐远控中心可远程启动 2000 公里外、海拔 4600 米的大红柳滩矿区破碎机，全程通讯延迟保持在 0.3 秒以内，728 台（套）设备控制指令执行正常、1572 个现场数据点读取准确，填补国内空白。')),

    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=475505',
                '中国有色金属报', '11-26',
                '中铝国际贵阳院锂电负极石墨化技术推广至1200余台炉',
                '中铝国际贵阳铝镁设计研究院牵头完成的“基于智能调控的锂离子电池负极材料均质石墨化关键技术与装备”项目取得突破，成果已在 30 余家企业的 1200 余台石墨化炉推广应用。应用数据显示，石墨化炉寿命提升 50%、达 75 炉次以上，产品石墨化度偏差由行业平均 3%—4% 降至 2% 以内，吨产品电耗降至约 7000 千瓦时、降幅 22%，累计直接经济效益超 5 亿元、年减二氧化碳 471.3 万吨。')),

    # ── 🌐 国际矿业动态 ─────────────────────────────────────────
    (CAT_GJ, ni('https://www.mining.com/ero-copper-halts-brazil-mine-after-water-overflows',
                'MINING.COM', '11-27',
                'Ero Copper巴西Tucumã铜矿因溢流水暂停采选',
                'Ero Copper 因强降雨冲垮集水系统、帕拉州环境机构在附近检出异常 pH 值，暂停巴西 Tucumã 铜矿的采矿与选矿。该矿 2025 年 7 月投产，今年原计划产铜 3.25 万至 3.75 万吨，约占公司 2026 年目标中值的 48%；11 月前 20 天降雨 275 毫米，比常年全月总量多 170%。公司须待 SEMAS 批准最终清理方案后方可复产，未给出复产时间与产量修正，多伦多股价当日跌 6.7%。',
                orig_title='Ero Copper halts Brazil mine after water overflows')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/Z2O6ZAA7JWBKFXKIURY3EIMIAPFPKNKUZG4U5HA-albemarle-idles-lithium-plant-highlighting-critical-minerals-refinery-challenges',
                'SMM 国际站', '11-27',
                'Albemarle关停西澳最后一条氢氧化锂产线',
                'Albemarle 决定关停其位于西澳大利亚 Kemerton 工厂最后一条在运氢氧化锂加工线。公司早在 2026 年 2 月即宣布，尽管锂价有所反弹，仍不足以抵消该厂转化环节的成本劣势，即便其可获得 Greenbushes 锂辉石供应；此前已在 2024 年关停另一条产线。SMM 认为，运营成本上升、原料竞争与客户认证正考验新建关键矿产精炼厂的商业可行性。',
                orig_title='Albemarle Idles Lithium Plant, Highlighting Critical Minerals Refinery Challenges')),

    (CAT_GJ, ni('https://news.metal.com/newscontent/432LR36T2J4C7GGQPZDGTA4ZL4KP7DGTBQIPE3I-chile-approves-early-construction-for-marimaca-copper-mine-near-antofagasta',
                'SMM 国际站', '11-27',
                '智利批准Marimaca铜矿早期施工，全面开建仍待董事会',
                '智利国家地质矿业局向 Marimaca Copper 子公司 Compania Minera Cielo Azul 颁发采矿方法许可，允许其在安托法加斯塔附近的 Marimaca 氧化矿床开展场地准备与大规模土方工程，时点为 Sprott 旗下单位支持一项建设融资方案两天后。公司表示全面施工仍须等待董事会批准。',
                orig_title='Chile Approves Early Construction for Marimaca Copper Mine Near Antofagasta')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202611/t20261127_10376801.htm',
                '全球矿产资源信息系统', '11-27',
                '峡谷资源拟融资7000万澳元开发喀麦隆铝土矿',
                '澳交所上市的峡谷资源公司（Canyon Resources）拟融资 7000 万澳元，为其喀麦隆米宁马塔普（Minim Martap）铝土矿项目建设提供资金，未来运营与扩产还需额外投入。公司称现有火车机组月运输能力仅 3.5 万吨，短期内难以支撑扩大开采；经审查开发进度与资金需求后，决定撤回最终可行性研究结果，并预计今年余下时间及 2027 年建设资金难以到位。')),

    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202611/t20261127_10376802.htm',
                '全球矿产资源信息系统', '11-27',
                '日本与智利、秘鲁深化铜锂锌等关键矿产合作',
                '据 BNAmericas 报道，智利总统卡斯特与日本首相高市早苗在东京会晤后发表联合声明，同意深化包括铜在内的关键矿产合作，以增强全球供应链韧性，日本有意扩大在智利投资。双方举例称，NTT Docomo Business 正与智利国家铜业公司（Codelco）在埃尔特尼恩特铜矿开展远程设备操作计划；高市早苗会见秘鲁总统藤森庆子时亦强调秘鲁铜、锌资源的重要性，双方拟就经济安全事宜签署谅解备忘录。')),

    # ── 💰 并购与投资 ───────────────────────────────────────────
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-28/1225693299.PDF',
                '巨潮资讯网', '11-28',
                '中国铝业几内亚120万吨氧化铝EPC签约，合同额65.56亿元',
                '中国铝业公告，其附属公司中国铝业几内亚有限公司与中铝国际于 11 月 27 日正式签订附带生效条款的《中国铝业几内亚氧化铝项目 EPC 总承包合同》，合同总价款 65.5557 亿元，服务范围包括年产 120 万吨氧化铝生产线及配套重油热电、公用辅助系统、赤泥堆场和取水、路桥、码头设施的设计、采购与施工。项目须于 2028 年 9 月 15 日前投产、2029 年 3 月 15 日前通过性能考核，缺陷责任期 12 个月；该关联交易尚待公司股东会审议批准。')),

    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-11-28/1225693151.PDF',
                '巨潮资讯网', '11-28',
                '贵研铂业向贵研化学材料增资1亿元',
                '贵研铂业公告，公司第八届董事会第三十一次会议于 11 月 27 日审议通过向贵研化学材料（云南）有限公司增资 1 亿元的议案。此前公司已将持有的贵研工业催化剂（云南）有限公司 100% 股权以非公开协议方式转让给贵研化学公司，本次增资旨在保障该项目顺利实施、优化贵研化学公司资本结构，落实公司“十五五”规划和化工新材料产业板块整合部署。')),

    # ── 💼 矿权交易（仅入月库 → 前端 #rightsCards，不进主列表）─────────
    (CAT_KQ, ni('https://ky.mnr.gov.cn/jggs/jjgs/202611/t20261128_10376804.htm',
                '矿业权市场', '11-27',
                '内蒙古阿拉善右旗巴拉干特铜多金属矿探矿权成交，蒙亿实业竞得',
                '阿拉善盟自然资源局公示，内蒙古自治区阿拉善右旗巴拉干特铜多金属矿勘查探矿权挂牌出让于 2026 年 11 月 24 日成交，竞得人为内蒙古蒙亿实业集团有限公司（公示文号：AZRZYKYQCR〔2026〕03号）。勘查矿种为铜矿，区块面积 25.0454 平方千米，位于阿拉善右旗阿拉腾朝格苏木。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/jggs/jjgs/202611/t20261127_10375559.htm',
                '矿业权市场', '11-26',
                '重庆酉阳毛家锑矿探矿权成交，市矿产资源开发公司竞得',
                '重庆市规划和自然资源局公示，重庆市酉阳县毛家锑矿勘查探矿权挂牌出让于 2026 年 11 月 19 日成交，竞得人为重庆市矿产资源开发有限公司（公示文号：ZRZYBKYQCR〔2026〕12-1号）。勘查矿种为锑矿，区块面积 6.6944 平方千米，位于酉阳县毛家。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/zrgs/tkzrgs/202611/t20261127_10375554.htm',
                '矿业权市场', '11-26',
                '江西德兴前山—上饶富足洋铅锌矿详查探矿权转让',
                '江西省自然资源厅公示江西省德兴市前山—上饶县富足洋铅锌矿详查探矿权转让事项（公示文号：赣自然探转公示〔2026〕65号），转让人为江西省地质局第八地质大队，受让人为江西赣东北地质调查有限公司，勘查矿种为铅矿，勘查许可证号 DT3600002009043010027678。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/xycrgs/ckq/202611/t20261126_10374212.htm',
                '矿业权市场', '11-26',
                '云南协议出让师宗五一煤矿上部深部采矿权',
                '云南省自然资源厅公示，以协议方式向师宗县五一煤矿有限责任公司出让其师宗县五一煤矿上部及深部采矿权（公示文号：云自然资出让〔2026〕5号）。矿山位于曲靖市师宗县雄壁镇，开采矿种为煤，矿区面积 5.5056 平方千米。')),

    (CAT_KQ, ni('https://ky.mnr.gov.cn/xycrgs/tkq/202611/t20261127_10375604.htm',
                '矿业权市场', '11-26',
                '巴彦淖尔瑞和矿业红石岩硅石矿上部探矿权协议出让',
                '巴彦淖尔市自然资源局公示，以协议方式向巴彦淖尔市瑞和矿业有限公司出让乌拉特前旗大佘太红石岩硅石矿上部勘查探矿权（公示文号：巴自然探协公示〔2026〕29号），勘查矿种为石英岩，受让人位于乌拉特前旗巴彦淖尔市农垦大佘太牧场。')),
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
    ('博茨瓦纳', CAT_ZC),
    ('几内亚配额', CAT_SC),
    ('Ero Copper', CAT_GJ),
    ('Albemarle', CAT_GJ),
    ('Marimaca', CAT_GJ),
    ('峡谷资源', CAT_GJ),
    ('日本与智利', CAT_GJ),
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
