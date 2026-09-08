# -*- coding: utf-8 -*-
"""
生成 2026-09-08 矿业新闻日报 index.html（原地更新）
- 09-07 的"今日新增"条目滚入"往期内容"（去 NEW 标记、按同类目合并）
- 按 30 天窗口（滚动保留最近30天）剔除往期条目，月度全量在 data/news_*.json
- 换入 09-08 抓取的最新条目（is-new + NEW），更新各计数与 AI 区条数
- 国内 SHFE/上金所 09-07 收盘已出，价格卡刷新；LME 09-08 电子盘刷新
- 矿权条目按规范仅入 rightsSection 数据层（data/news_2026-09.json），不进主页列表
- 保留：specialSection / rightsSection / 会展预告 IIFE / 搜索 / CSV / PDF / 防横跳
境外条目（MINING.COM / SMM 国际站）保留英文原题（data-orig-title + 摘要末尾「原题：…」）
"""
import re, datetime, json, glob
from source_whitelist import is_allowed


def ni(url, src, date, title, summary, embed='ok', orig_title=''):
    """构造今日新增条目，并强制校验 URL 在白名单内。境外条目保留英文原题。"""
    if not is_allowed(url):
        raise ValueError(f"URL 不在允许信源白名单内: {url}")
    ot = ' data-orig-title="%s"' % orig_title if orig_title else ''
    if orig_title:
        summary = '%s（原题：%s）' % (summary, orig_title)
    return ('<div class="news-item is-new"%s data-url="%s" data-embed="%s"><div class="news-head"><span class="dot"></span>'
            '<span class="badge-new">NEW</span><a class="news-title" href="%s" target="_blank">%s</a></div>'
            '<div class="news-meta"><span class="src">%s</span> · %s</div><div class="news-summary">%s</div>'
            '</div>'
            % (ot, url, embed, url, title, src, date, summary))


SRC = 'index.html'
with open(SRC, encoding='utf-8') as f:
    html = f.read()

REPORT = '2026-09-08'
GRAB = '2026-09-08'
ARCHIVE_DAYS = 30
REPORT_DT = datetime.date.fromisoformat(REPORT)
CUTOFF_DT = REPORT_DT - datetime.timedelta(days=ARCHIVE_DAYS - 1)   # 往期最早日期（含）= 08-10
DATA_ASOF = '09-07'

# ============ 1. 标题 / 日期 / 更新时间 ============
html = re.sub(r'<title>\d{4}-\d{2}-\d{2}</title>', '<title>%s</title>' % REPORT, html)
html = html.replace('2026年09月07日 星期一', '2026年09月08日 星期二')
now = datetime.datetime.now().strftime('%H:%M')
html = re.sub(r'更新时间：2026-09-\d{2} \d{2}:\d{2}', '更新时间：%s %s' % (REPORT, now), html)
html = re.sub(r'今日新增（2026-09-\d{2} 抓取）', '今日新增（%s 抓取）' % GRAB, html)
html = re.sub(r'id="priceStripNote"[^>]*>2026-09-\d{2} 更新', 'id="priceStripNote">%s 更新' % REPORT, html)
html = re.sub(r'name="build-version" content="\d{8}-\d{4}"',
              'name="build-version" content="%s-%s"' % (REPORT.replace('-', ''), now.replace(':', '')), html)

# ============ 2. 价格卡刷新（国内 SHFE/上金所 09-07 收盘 + LME 09-08） ============
UP, DOWN, FLAT = '&#9650;', '&#9660;', '■'


def card(slug, name, tag, value, unit, chg_text, cls):
    return ('<div data-slug="%s" class="price-card %s"><div class="pc-name">%s <span class="pc-tag">%s</span></div>'
            '<div class="pc-value">%s</div><div class="pc-unit">%s</div><div class="pc-chg">%s</div></div>'
            % (slug, cls, name, tag, value, unit, chg_text))


SHFE = [
    ('cum', '沪铜', 'SHFE', '109,410', '元/吨', UP + ' +630 (+0.58%)', 'up'),
    ('alm', '沪铝', 'SHFE', '24,420', '元/吨', UP + ' +130 (+0.54%)', 'up'),
    ('pbm', '沪铅', 'SHFE', '16,210', '元/吨', UP + ' +80 (+0.50%)', 'up'),
    ('znm', '沪锌', 'SHFE', '27,095', '元/吨', UP + ' +350 (+1.31%)', 'up'),
    ('nim', '沪镍', 'SHFE', '127,820', '元/吨', UP + ' +40 (+0.03%)', 'up'),
    ('snm', '沪锡', 'SHFE', '418,870', '元/吨', UP + ' +2,410 (+0.58%)', 'up'),
    ('au9999', '上海金', 'Au99.99', '950.78', '元/克', DOWN + ' -15.18 (-1.57%)', 'down'),
    ('agtd', '白银', 'Ag(T+D)', '15,990', '元/千克', DOWN + ' -260 (-1.60%)', 'down'),
    ('lcm', '碳酸锂', '主力连续', '142,200', '元/吨', UP + ' +260 (+0.18%)', 'up'),
]
shfe_html = ''.join(card(*c) for c in SHFE)
# 电解钴：无当日源，保留上日 SMM 值并标注
shfe_html += ('<div class="price-card "><div class="pc-name">电解钴 <span class="pc-tag">SMM %s</span></div>'
              '<div class="pc-value">304,940</div><div class="pc-unit">元/吨</div>'
              '<div class="pc-chg">上日 304,940（SMM 未更新）</div></div>' % DATA_ASOF)

LME = [
    ('lcpt', 'LME 铜', 'LME', '14,521.00', '美元/吨', UP + ' +27.00 (+0.19%)', 'up'),
    ('lalt', 'LME 铝', 'LME', '3,313.50', '美元/吨', UP + ' +1.00 (+0.03%)', 'up'),
    ('lldt', 'LME 铅', 'LME', '1,897.50', '美元/吨', DOWN + ' -2.00 (-0.11%)', 'down'),
    ('lznt', 'LME 锌', 'LME', '3,994.50', '美元/吨', UP + ' +5.00 (+0.13%)', 'up'),
    ('lnkt', 'LME 镍', 'LME', '16,695.00', '美元/吨', UP + ' +5.00 (+0.03%)', 'up'),
    ('ltnt', 'LME 锡', 'LME', '55,085.00', '美元/吨', UP + ' +105.00 (+0.19%)', 'up'),
]
lme_html = ''.join(card(*c) for c in LME)


def _replace_block(h, tag, inner_html):
    """按 div 深度匹配替换整个块，避免非贪婪正则在第一张卡片处提前截断。"""
    i = h.find(tag)
    assert i != -1, 'block not found: %s' % tag
    j = h.find('>', i) + 1
    depth = 1
    n = len(h)
    while j < n and depth > 0:
        if h.startswith('<div', j):
            depth += 1
            k = h.find('>', j)
            j = (k + 1) if k != -1 else n
        elif h.startswith('</div>', j):
            depth -= 1
            j += 6
        else:
            j += 1
    return h[:i] + tag + inner_html + '</div>' + h[j:]


html = _replace_block(html, '<div class="price-cards" id="priceCardsShfe">', shfe_html)
html = _replace_block(html, '<div class="price-cards price-cards-lme" id="priceCardsLme">', lme_html)

# ============ 3. 解析今日/往期两个区（容错 data-page-node-id） ============
TAG_TODAY = '<div class="section" id="todaySection"'
TAG_ARCH = '<div class="section" id="archiveSection"'
TAG_RIGHTS = '<div class="section" id="rightsSection"'
i_t = html.find(TAG_TODAY)
i_a = html.find(TAG_ARCH)
i_r = html.find(TAG_RIGHTS)
assert 0 <= i_t < i_a < i_r, 'markers not found'

m_today = html.find('<!-- ==================== 今日新增')
assert m_today != -1, '今日新增 marker missing'

sp_start = html.find('<div class="section" id="specialSection"')
arch_marker_pos = html.find('<!-- ==================== 往期内容')
if sp_start != -1 and arch_marker_pos != -1 and arch_marker_pos > sp_start:
    special_block = html[sp_start:arch_marker_pos]
elif sp_start != -1:
    special_block = html[sp_start:i_a]
else:
    special_block = ''

today_raw = html[i_t:i_a]
arch_raw = html[i_a:i_r]


def split_items(block):
    out = []
    cat = None
    for mm in re.finditer(r'<div class="sub-cat"[^>]*>([^<]*)<span class="sub-count"[^>]*>([^<]*)</span></div>'
                          r'|<div class="sp-cat"[^>]*>([^<]*)</div>'
                          r'|<div class="news-item[^>]*>.*?</div>\s*</div>',
                          block, re.S):
        if mm.group(1) is not None:
            cat = mm.group(1).strip()
        elif mm.group(3) is not None:
            cat = mm.group(3).strip()
        else:
            if cat:
                out.append((cat, mm.group(0)))
    return out


today_items = split_items(today_raw)
arch_items = split_items(arch_raw)


def item_after_cutoff(it):
    m = re.search(r'</span>\s*·\s*([0-9]{2})-([0-9]{2})', it)
    if not m:
        return True
    im, id_ = int(m.group(1)), int(m.group(2))
    iy = REPORT_DT.year if im <= REPORT_DT.month else REPORT_DT.year - 1
    return (iy, im, id_) >= (CUTOFF_DT.year, CUTOFF_DT.month, CUTOFF_DT.day)


def item_url(it):
    m = re.search(r'data-url="([^"]+)"', it)
    return m.group(1) if m else it


def strip_new(it):
    it = it.replace(' is-new', '')
    it = re.sub(r'<span class="badge-new"[^>]*>NEW</span>', '', it)
    it = re.sub(r'<a class="btn-read"[^>]*>查看原文 →</a>', '', it)
    return it


CAT_KQ = '💼 矿权交易'

prev_today = [(cat, strip_new(it)) for cat, it in today_items if '<div class="news-item' in it and cat != CAT_KQ]
arch_keep = [(cat, strip_new(it)) for cat, it in arch_items
             if '<div class="news-item' in it and cat != CAT_KQ and item_after_cutoff(it)]

merge_seq = []
seen_url = set()
for cat, it in prev_today + arch_keep:
    url = item_url(it)
    if url in seen_url:
        continue
    seen_url.add(url)
    merge_seq.append((cat, it))

# ============ 4. 今日新增条目（09-08 抓取，均逐页核实标题/日期/正文） ============
CAT_ZK = '🔍 找矿成果与勘查技术'
CAT_HY = '🏭 行业动态'
CAT_GJ = '🌐 国际矿业动态'

# ============ 3.5 从累计库回补 30 天窗口（防止历史条目因窗口滚动丢失） ============
CAT_MAP = {
    '行业动态': CAT_HY,
    '国际矿业动态': CAT_GJ,
    '找矿成果与勘查技术': CAT_ZK,
    '培训与学术': CAT_HY,
    '政策法规': CAT_HY,
}
LIB_SKIP = {'矿权交易', '并购与投资'}


def _esc(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _lib_item(e):
    url = e.get('url', '')
    if not url:
        return None
    cat = CAT_MAP.get(e.get('category', ''))
    if not cat:
        return None
    title = _esc(e.get('title', ''))
    src = _esc(e.get('source', ''))
    od = e.get('orig_date', '') or (e.get('orig_date_full', '') or '')[5:]
    summary = _esc(e.get('summary', ''))
    embed = e.get('embed', 'ok') or 'ok'
    return (cat,
            '<div class="news-item" data-url="%s" data-embed="%s"><div class="news-head"><span class="dot"></span>'
            '<a class="news-title" href="%s" target="_blank">%s</a></div>'
            '<div class="news-meta"><span class="src">%s</span> · %s</div><div class="news-summary">%s</div></div>'
            % (url, embed, url, title, src, od, summary))


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
    # ---------- 🔍 找矿成果与勘查技术 ----------
    (CAT_ZK, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260902_2937434.html', '自然资源部', '09-02',
                '新一轮找矿突破战略行动再获标志性成果 安徽茶亭铜金矿勘查取得重大突破',
                '安徽省宣城市茶亭地区铜金矿勘查取得重大突破，矿床位于长江中下游成矿带南陵—宣城铜金矿集区，为火山岩覆盖区新发现的隐伏斑岩型铜金矿床，主矿体长约1.2千米、宽约1.1千米，单孔矿体最大视厚度1371米；初步估算铜潜在资源超数个大型铜矿规模、金达十余个大型金矿规模，深部尚未揭穿。西藏玉龙铜业2025年10月以86亿元竞得探矿权，4个月完成钻探近十万米，唐菊兴院士任勘查项目负责人。')),
    (CAT_ZK, ni('https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202609/t20260907_10307771.htm', '全球矿产资源信息系统', '09-07',
                '智利坎加洛铜矿等项目进展',
                '奥斯奎斯特（AUSQUEST）公司宣布其智利坎加洛（Cangallo）斑岩铜矿两孔将矿体自地表向下延伸800米，证实存在高品位给矿构造：北部孔自34米深处见矿355.8米，铜品位0.31%、金0.05克/吨，含10米厚铜0.71%、金0.08克/吨矿体；南部首孔自178米见矿348米，铜0.23%、金0.08克/吨。另太阳石金属在厄瓜多尔布拉马德罗斯项目梅罗纳尔、波罗蒂洛两矿床钻探与探槽均见矿。')),
    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473763', '中国有色金属报', '09-07',
                '具身智能、矿山大模型、数字孪生同台亮相 2026AI+矿山安全大会召开',
                '8月29日，2026AI+矿山安全大会在山东招远举行，主题「数智驱控 安全共生」，300余位院士专家与企业代表参会，现场分享具身智能、矿山大模型、智能凿岩、数字孪生等成果。中国工程院院士王国法作《数智技术赋能安全高效采矿》主题报告，指出智慧矿山建设存在智能装备环境适应性不足、系统常态化运行率偏低、系统间数据壁垒突出等痛点，强调数智矿山首要价值在于筑牢安全防线。')),

    # ---------- 🏭 行业动态 ----------
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473762', '中国有色金属报', '09-07',
                '金钛股份在北交所上市',
                '9月3日，朝阳金达钛业股份有限公司（证券简称：金钛股份，证券代码：920071）在北京证券交易所挂牌上市，成为我国首家主营业务为高品质海绵钛产品的上市企业。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473785', '中国有色金属报', '09-07',
                '易控智驾携手紫金矿业斩获"数据要素×"大赛双赛区一等奖',
                '2026年"数据要素×"大赛西藏分赛与福建分赛结果揭晓，易控智驾科技股份有限公司携手紫金矿业集团，凭借在巨龙铜矿、紫金山金铜矿的无人矿卡应用成果连续荣获一等奖。巨龙铜矿地处西藏5400米高寒地区，已规模化投运60台纯电动无人矿卡，通过多源感知融合、分布式制动与自适应控制、动态轨迹预测与协同调度，解决冻融湿滑路面与多车型混行难题。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473767', '中国有色金属报', '09-07',
                '双桅杆擎起高原新地标——中国十五冶卢安夏新矿永久井架吊装纪实',
                '当地时间8月14日，赞比亚卢安夏新矿穆南混合井永久井架一对直径4米、净重26吨天轮精准吊装就位，下天轮标高46米、上天轮52米。自7月30日304吨斜架双桅杆整体吊装、8月1日立架分节对接至本次双天轮就位，中国十五冶半个月内完成3场关键节点施工，首次在海外应用双桅杆旋转吊装工艺。卢安夏铜矿2009年被中国有色集团收购后重启，新矿由穆南浅部与玛希巴联合开采、28#井深部硫化矿3座矿山组成。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473775', '中国有色金属报', '09-07',
                '五矿铍业核心产品入选央企机器人十大高价值应用场景',
                '8月19日至23日2026世界机器人大会在北京举办，五矿铍业有限责任公司携核心产品高性能铍铜合金参展，该产品成功入选中央企业机器人十大高价值应用场景展示序列，落地特种涉爆高危作业场景与人形机器人核心零部件两大赛道。高性能铍铜合金是人形机器人、高端工业机械臂所需的核心精密材料。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473765', '中国有色金属报', '09-07',
                '西矿信息荣获第十五届中国创新创业大赛青海赛区企业组一等奖',
                '2026年第十五届中国创新创业大赛落幕，西部矿业集团西矿信息参赛项目「未来信息领域—矿山生产运营一体化数智管控平台」斩获青海赛区企业组一等奖。该项目紧扣矿山数字化转型需求，针对高海拔复杂作业环境开展技术攻坚，在平台架构设计、多源数据融合、现场场景适配等方面实现创新突破。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473771', '中国有色金属报', '09-07',
                '云铝股份召开深化"一本部多基地"集中管控改革推进会',
                '8月17日，云铝股份召开深化「一本部多基地」集中管控改革推进会，紧扣「强本部、强管控」核心思路，从制度、流程、数据三方面明确改革要求，提出实现「重构定位、重塑体系、重理边界」，强化「五个量化管理」，建立职责清单与风险清单，推动业务工作从「事务统计型」向「统筹管控型」转型。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473774', '中国有色金属报', '09-07',
                '陕西黄金集团西安秦金打出市场开拓"组合拳"',
                '今年以来，陕西黄金集团西安秦金围绕渠道拓展、客户深耕、人才筑基三条主线发力：线上运营官方微信公众号、筹建抖音官方账号，线下参加行业展会与区域博览会对接潜在客户；依托高端化、差异化产品优势为客户量身定制合作方案，已与行业头部企业达成初步合作意向；拟启动营销人才专项培养计划，覆盖一线销售与中层骨干。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473737', '中国有色金属报', '09-03',
                '西北有色地矿集团712总队公司实现"时间过半、任务过半"目标',
                '截至6月底，西北有色地矿集团七一二总队公司经营收入完成年度目标的50.22%、利润总额完成52.12%。上半年地质勘查、民生地质、工程施工、装备制造四大板块累计落地实体项目93项，新签合同总额完成年度目标80%，在新疆、内蒙古等省外市场实现「零的突破」，塞拉利昂海外项目成功落地，非金属地质勘查短板同步补齐。')),
    (CAT_HY, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260904_2937656.html', '自然资源部', '09-04',
                '2026中国国际矿业大会将于9月10日开幕',
                '以「合作共赢，绿色智能」为主题的2026（第二十八届）中国国际矿业大会将于9月10日至12日在天津梅江会展中心举办，在往届论坛、展览两大板块基础上新增矿业权交易板块。论坛设28场（主题1场、高层6场、专题21场），展览面积6.5万平方米创历届新高，并设置矿业权转让大市场、专场推介、项目签约等功能；已吸引全球25个国家658家企业参展。')),
    (CAT_HY, ni('http://gi.mnr.gov.cn/202609/t20260904_2937623.html', '自然资源部', '09-04',
                '2026年矿区生态修复典型案例评选结果公示',
                '自然资源部国土空间生态修复司公示2026年矿区生态修复典型案例评选结果，分废弃矿山生态修复、生产矿山、矿业遗迹三类共21个案例入选，覆盖北京、浙江、安徽、江西、湖北、湖南、重庆、河北、内蒙古、陕西等省份，涉及铁矿、金矿、钼矿、铝土矿、磷矿、石灰岩、煤矿等矿种，公示期由省级推荐并接受社会监督。')),
    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-09-08/1225551090.PDF', '巨潮资讯网', '09-08',
                '中信金属：关于参加中信股份2026年中期业绩联合发布会情况的公告',
                '中信金属股份有限公司公告参加中信股份2026年中期业绩联合发布会相关情况。中信金属主营铌、铜、铝等有色金属及铁矿石贸易与矿业投资，中期业绩发布内容涉及海外矿山项目运营与大宗商品贸易板块表现。', embed='pdf')),
    (CAT_HY, ni('http://disc.szse.cn/download/disc/disk03/finalpage/2026-09-08/ba888bf4-8062-4f9b-b17c-d430d4ca975a.PDF',
                '深圳证券交易所', '09-08',
                '电投能源：关于铝业期货套期保值年度计划方案调整暨关联交易公告',
                '内蒙古电投能源股份有限公司公告调整铝业期货套期保值年度计划方案，涉及关联交易事项，中信证券同步出具核查意见。电投能源主营煤炭与电解铝，套保方案调整反映铝价波动加剧背景下的风险管理需求。', embed='pdf')),
    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-09-07/1225549272.PDF', '巨潮资讯网', '09-07',
                '盛达资源：关于子公司德运矿业完成探矿权延续登记的公告',
                '盛达资源公告其子公司德运矿业已完成探矿权延续登记，相关矿权有效期得以延续，为公司后续地质勘查与资源增储工作奠定权属基础。盛达资源主营白银等贵金属矿产资源开发。', embed='pdf')),
    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-09-07/1225550300.PDF', '巨潮资讯网', '09-07',
                '中色股份：关于控股子公司中色印尼达瑞矿业有限公司收到法院通知的公告',
                '中国有色金属建设股份有限公司公告，其控股子公司中色印尼达瑞矿业有限公司收到法院通知。达瑞矿业为公司在印度尼西亚的铅锌矿项目平台，相关诉讼进展可能对公司海外项目推进产生影响。', embed='pdf')),
    (CAT_HY, ni('http://static.cninfo.com.cn/finalpage/2026-09-07/1225552242.PDF', '巨潮资讯网', '09-07',
                '蓝晓科技：关于签订盐湖提锂日常经营合同的公告',
                '西安蓝晓科技新材料股份有限公司公告签订盐湖提锂日常经营合同。公司主营吸附分离树脂与盐湖提锂成套装置，合同签署反映盐湖提锂产能建设与锂资源开发需求延续。', embed='pdf')),
    (CAT_HY, ni('https://www.ccmn.cn/news/ZX018/202609/be746e71851d49e1baca731d7084d796.html', '长江有色网', '09-07',
                '再生铅占精铅近50%！废电瓶高成本卡住冶炼利润，铅酸电池旺季备货能否接力',
                '国内再生铅占精铅供应比重已升至近50%，废电瓶作为核心原料采购价格持续高企，将冶炼厂利润卡在狭窄区间，成本刚性成为铅价难以深跌的底层逻辑。沪铅2610合约报16235元/吨、涨120元，长江现货1#铅均价16300元/吨、涨75元。再生铅冶炼厂在成本线附近维持开工，部分边际产能逼近停减产临界点；需求端铅酸电池旺季尾声排产边际走弱。')),

    # ---------- 🌐 国际矿业动态 ----------
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202609/t20260908_10308871.htm', '全球矿产资源信息系统', '09-08',
                '南非希望重回超级矿业大国行列',
                '据Miningnews.net报道，南非正寻求重回全球矿业大国行列，政府与行业组织目标是在2028年2月前使新投资回升到500亿兰特（约44亿澳元）。南非矿产委员会代表查巴纳在珀斯非澳会议（Africa Down Under）上表示，下一步重点是吸引外部投资。1980年矿业曾占南非GDP的21%，2025年该比例仅5.8%，矿山老化、勘探投资不足与审批缓慢是主因。')),
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202609/t20260908_10308872.htm', '全球矿产资源信息系统', '09-08',
                '哥伦比亚取消10项限制矿业政策',
                '据Mining.com报道，为落实阿韦拉多·德拉埃斯普列亚总统重振矿业投资、挖掘铜矿资源潜力的指示，哥伦比亚新政府废除10项限制自然资源勘查开采的政策。矿业部部长阿尔博莱达在卡塔赫纳矿业会议上宣布，前左翼政府时期以环境与土地利用名义出台的措施「设计得很差」，实际阻碍了投资与勘探。该国铜、金、煤、镍潜力大，但冗长许可、监管混乱与安全风险长期限制投资。')),
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kydt/hyyxdt/202609/t20260907_10307769.htm', '全球矿产资源信息系统', '09-07',
                '7月份美国铜进口量创历史新高',
                '据矿业周刊援引路透社报道，美国7月精炼铜和铜合金进口量达225094吨，为1990年以来最高月度水平，环比增长78%、同比增长8%，贸易商在美方可能加征关税前大量进口。美国商务部原定6月30日前宣布铜市场最新政策但迟迟未出，不确定性推动美国商品交易所铜库存升至创纪录的764597短吨（693630公吨），连续53天上升。美国铜进口46%来自智利，其次刚果（金）占1/4。')),
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202609/t20260907_10307772.htm', '全球矿产资源信息系统', '09-07',
                '淡水河谷搁置贱金属业务分拆上市',
                '据Mining.com报道，因巴西国内担心失去对战略矿业资产的控制，淡水河谷（Vale）已搁置其关键矿产业务单独IPO计划。总部位于伦敦的淡水河谷贱金属有限公司（VBM）2023年从母公司拆分成立并筹备上市，承接淡水河谷在加拿大、巴西、日本、英国、印尼的铜、镍、钴资产。2月VBM曾同意出售其加拿大合资企业多数股份，以支撑淡水河谷未来10年铜产量翻番目标——过去一年铜价上涨45%，涨幅近镍的4倍。')),
    (CAT_GJ, ni('https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202609/t20260907_10307773.htm', '全球矿产资源信息系统', '09-07',
                '国际锌价逼近4年来新高',
                '上周五（9月4日）国际矿产品价格多数下跌，锌价逼近四年来新高：LME锌收于3940.00美元/吨、上涨1.09%；铝3294.50美元/吨、跌0.69%；铅1905.00美元/吨、跌0.08%；镍16810.00美元/吨、跌0.50%；锡54850.00美元/吨、涨0.18%。62%品位铁矿粉收于99.65美元/吨、涨0.30%；铀（U3O8）89.50美元/磅持平。COMEX黄金收于4432.6美元/盎司（约142.5美元/克，按1金衡盎司≈31.1035克换算）、跌0.92%；白银65.99美元/盎司、跌1.45%。')),
    (CAT_GJ, ni('https://www.ccmn.cn/news/ZX018/202609/f1e611359ea74c178587444cfd8b6b24.html', '长江有色网', '09-07',
                '再度延期！澳洲 Aurukun 铝土矿审批推迟至明年2月，1500万吨项目命运未定',
                '国家环境保护机构发布通知，将嘉能可与三菱商事联合开发的澳大利亚约克角半岛Aurukun铝土矿项目审批决议时间延长至明年2月12日，延期时长超过100个工作日。这是该项目继6月之后第二次审批延期，这座规划年产1500万吨的铝土矿项目落地节奏再度延后。')),
    (CAT_GJ, ni('https://www.ccmn.cn/news/ZX018/202609/d8fa9b0e0d9940a99228c8415209a260.html', '长江有色网', '09-07',
                '从90%跌至67%！MHP钴计价大幅回落，电池企业压价，印尼HPAL厂商利润承压',
                '据三位知情人士透露，国内电动汽车电池制造企业正对MHP（氢氧化镍钴）原料中的钴提出更大幅度降价诉求，钴计价系数从此前约90%回落至67%。印尼HPAL高压酸浸企业本身已面临镍矿、硫磺原料成本上行压力，钴计价下调将进一步挤压其利润空间。')),
    (CAT_GJ, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473780', '中国有色金属报', '09-07',
                '亚行新融资机制旨在重塑亚太关键矿产供应链格局',
                '亚洲开发银行在乌兹别克斯坦举行的第五十九届年会上推出「关键矿产到制造端」融资伙伴关系机制，推动亚太经济体从单纯矿产开采向本土加工、制造、回收等高附加值环节延伸。文章指出亚太普遍存在「富资源、穷链条」格局：印尼镍储量占全球约四成，菲律宾镍矿出口占矿业总产值60%以上但高度依赖原矿出口，蒙古国依赖奥尤陶勒盖铜精矿，哈萨克斯坦铬、铀资源富集但深加工链条薄弱，澳大利亚锂辉石精矿多需境外冶炼。')),
    (CAT_GJ, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473779', '中国有色金属报', '09-07',
                'ITA发布更新版锡行业生命周期评价基准',
                '国际锡业协会（ITA）发布第二项全行业生命周期评价（LCA）结果，量化精锡生产的环境影响。该研究以2024年为基准年，更新2018/2019年基准，ITA成员企业100%参与、合计产量约占全球精锡产量51%，由Sphera Solutions依ISO 14040/14044标准开展，覆盖采矿、再生物料利用、选矿、冶炼和精炼环节，指标含全球变暖潜势、一次能源需求、蓝水消耗、富营养化、酸化与光化学臭氧生成潜势。')),
    # ---- 境外（英文原题保留）----
    (CAT_GJ, ni('https://www.mining.com/critical-minerals-security-collides-with-decades-long-mine-timelines',
                'MINING.COM', '09-08',
                '关键矿产安全撞上数十年矿山周期：北美自主化目标与现实脱节',
                '北美降低对华关键矿产依赖的努力正遭遇许可改革无法解决的瓶颈——判断项目技术与经济可行性仍需多年。在美国，一个矿床从发现到商业化生产往往超过30年，而国家安全与采购目标的时间尺度只有数年。修订后的《国防联邦采购条例补充规定》（DFARS）将于2027年1月生效，要求特定国防用途材料来自非对手国家，并自2026年1月1日起禁用中国原产稀土磁体及相关材料；受访企业界人士认为以当前产能无法按期达标。',
                orig_title='Critical minerals security collides with decades-long mine timelines')),
    (CAT_GJ, ni('https://www.mining.com/acg-metals-to-acquire-keskek-gold-project',
                'MINING.COM', '09-08',
                'ACG Metals 逾700万美元收购土耳其 Keşkek 金矿项目',
                'ACG Metals（LON: ACG）与 Meta Nikel Kobalt Madencilik 签署约束性协议，以逾700万美元收购含土耳其 Keşkek 金矿项目的采矿许可证100%权益：先期支付400万美元，2027年中实现首次黄金生产后再付385万美元。项目距公司 Gediktepe 矿约70公里（43英里），许可证面积666公顷，所产氧化矿将供现有堆浸设施处理，回收率已提升至约85%；公司称新增黄金产能有望使铜当量年产量从2万吨翻倍至4万吨，并延长 Gediktepe 金矿服务年限数年。',
                orig_title='ACG Metals to acquire Keşkek gold project')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104101668-mmg-dugald-river-signs-2027',
                'SMM 国际站', '09-07',
                '五矿资源 Dugald River 签署2027—2028年锌精矿销售协议',
                '五矿资源（MMG）9月7日公告，其子公司 Dugald River 与五矿北欧（Minmetals North-Europe）签署锌精矿销售协议，2027年和2028年每年销售约2万干吨，年度交易上限5000万美元。定价以LME特高级锌与LBMA白银价格扣减加工费（TC）确定，以CIF条件交付。Dugald River 位于澳大利亚昆士兰州，是MMG主力锌矿之一。',
                orig_title='MMG Dugald River Signs 2027–2028 Zinc Concentrate Sales Agreement')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104101639-eu-industry-chief-proposes-ban-on-waste-exports-to-non-oecd-nations',
                'SMM 国际站', '09-07',
                '欧盟拟全面禁止向非OECD国家出口废弃物，铝废料在列',
                '路透布鲁塞尔9月4日电，欧盟产业主管斯特凡纳·塞茹尔内（Stephane Sejourne）提议全面禁止向非OECD国家出口废弃物，铝废料亦在禁止之列，其内阁于周五作出上述表示。塞茹尔内原定于9月23日提出仅限制废料出口的贸易措施，但内部磋商显示该工具覆盖范围有限，最终改为提出全面禁令。若落地将显著影响全球再生铝原料流向。',
                orig_title='EU Industry Chief Proposes Ban on Waste Exports to Non-OECD Nations')),
]


def render_cat_groups(seq, mark_new=False):
    suffix = '条新增' if mark_new else '条'
    order, groups = [], {}
    for cat, it in seq:
        if cat not in groups:
            groups[cat] = []
            order.append(cat)
        groups[cat].append(it)
    out = []
    for cat in order:
        items = groups[cat]
        n = len(items)
        out.append('<div class="sub-cat" data-page-node-id="">%s<span class="sub-count" data-page-node-id="">%d%s</span></div>\n' % (cat, n, suffix))
        out.extend(items)
    return out


unique_new = []
new_seen_url = set()
for cat, it in new_items:
    url = item_url(it)
    if url in new_seen_url:
        continue
    new_seen_url.add(url)
    unique_new.append((cat, it))
new_items = unique_new

merge_seq = [x for x in merge_seq if item_url(x[1]) not in new_seen_url]

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

html = html[:m_today] + new_today_block + special_block + new_arch_block + html[i_r:]
html = html.replace('<!-- ==================== 今日新增 ==================== -->', '', 1)

# ============ 6. 更新计数与 AI 提示 ============
html = re.sub(r'id="tocAllCount"[^>]*>\d+<', 'id="tocAllCount">%d<' % all_n, html)
html = re.sub(r'id="tocTodayCount"[^>]*>\d+<', 'id="tocTodayCount">%d<' % n_today, html)
html = re.sub(r'id="tocArchiveCount"[^>]*>\d+<', 'id="tocArchiveCount">%d<' % arch_n, html)
html = re.sub(r'今日 \d+ 条新闻的智能解读', '今日 %d 条新闻的智能解读' % n_today, html)

with open(SRC, 'w', encoding='utf-8') as f:
    f.write(html)

print('OK index.html -> today=%d archive=%d all=%d size=%d' % (n_today, arch_n, all_n, len(html)))
