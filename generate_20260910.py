# -*- coding: utf-8 -*-
"""
生成 2026-09-10 矿业新闻日报 index.html
- 09-09 的「今日新增」滚入「往期内容」（去 NEW 标记、按同类目合并）
- 30 天窗口（ARCHIVE_DAYS=30，cutoff=2026-08-12）回补历史条目
- 换入 09-10 抓取的最新条目（is-new + NEW），更新计数
- 价格卡：国内 SHFE/上金所 09-09 收盘（按 price_history_detail.json 计算涨跌），
  LME 09-10（直接读 lme_data.json，零手抄），电解钴无当日源保留上值并标注
- 矿权条目仅入 rightsSection 数据层（data/news_2026-09.json），不进主页列表
- 保留：会展预告 IIFE / 搜索 / CSV / PDF / 防横跳
- 境外条目保留英文原题（data-orig-title + 摘要末尾「原题：…」）
"""
import re, datetime, json, glob
from source_whitelist import is_allowed


def ni(url, src, date, title, summary, embed='ok', orig_title=''):
    """构造今日新增条目，并强制校验 URL 在白名单内。境外条目保留英文原题。"""
    if not is_allowed(url):
        raise ValueError("URL 不在允许信源白名单内: %s" % url)
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

REPORT = '2026-09-10'
GRAB = '2026-09-10'
ARCHIVE_DAYS = 30
REPORT_DT = datetime.date.fromisoformat(REPORT)
CUTOFF_DT = REPORT_DT - datetime.timedelta(days=ARCHIVE_DAYS - 1)   # 2026-08-12
DATA_ASOF = '09-09'

# ============ 1. 标题 / 日期 / 更新时间 / build-version ============
html = re.sub(r'<title>\d{4}-\d{2}-\d{2}</title>', '<title>%s</title>' % REPORT, html)
html = html.replace('2026年09月09日 星期三', '2026年09月10日 星期四')
now = datetime.datetime.now().strftime('%H:%M')
html = re.sub(r'更新时间：2026-09-\d{2} \d{2}:\d{2}', '更新时间：%s %s' % (REPORT, now), html)
html = re.sub(r'今日新增（2026-09-\d{2} 抓取）', '今日新增（%s 抓取）' % GRAB, html)
html = re.sub(r'id="priceStripNote"[^>]*>2026-09-\d{2} 更新', 'id="priceStripNote">%s 更新' % REPORT, html)
html = re.sub(r'name="build-version" content="\d{8}-\d{4}"',
              'name="build-version" content="%s-%s"' % (REPORT.replace('-', ''), now.replace(':', '')), html)

# ============ 2. 价格卡刷新（国内 SHFE/上金所 09-09 收盘 + LME 09-10 电子盘） ============
UP, DOWN, FLAT = '&#9650;', '&#9660;', '■'


def card(slug, name, tag, value, unit, chg_text, cls):
    return ('<div data-slug="%s" class="price-card %s"><div class="pc-name">%s <span class="pc-tag">%s</span></div>'
            '<div class="pc-value">%s</div><div class="pc-unit">%s</div><div class="pc-chg">%s</div></div>'
            % (slug, cls, name, tag, value, unit, chg_text))


# 国内 10 卡：值来自 fetch_price_history / price_history_detail.json（09-09 收盘，涨跌与 09-08 比）
SHFE = [
    ('cum', '沪铜', 'SHFE', '111,080', '元/吨', UP + ' +460 (+0.42%)', 'up'),
    ('alm', '沪铝', 'SHFE', '24,560', '元/吨', UP + ' +100 (+0.41%)', 'up'),
    ('pbm', '沪铅', 'SHFE', '16,185', '元/吨', UP + ' +50 (+0.31%)', 'up'),
    ('znm', '沪锌', 'SHFE', '27,735', '元/吨', UP + ' +230 (+0.84%)', 'up'),
    ('nim', '沪镍', 'SHFE', '127,360', '元/吨', DOWN + ' -40 (-0.03%)', 'down'),
    ('snm', '沪锡', 'SHFE', '418,440', '元/吨', DOWN + ' -510 (-0.12%)', 'down'),
    ('au9999', '上海金', 'Au99.99', '952.22', '元/克', DOWN + ' -0.90 (-0.09%)', 'down'),
    ('agtd', '白银', 'Ag(T+D)', '16,224', '元/千克', UP + ' +99 (+0.61%)', 'up'),
    ('lcm', '碳酸锂', '主力连续', '142,000', '元/吨', DOWN + ' -1,480 (-1.03%)', 'down'),
]
shfe_html = ''.join(card(*c) for c in SHFE)
# 电解钴：无当日源，保留上日 SMM 值并标注
shfe_html += ('<div class="price-card "><div class="pc-name">电解钴 <span class="pc-tag">SMM %s</span></div>'
              '<div class="pc-value">304,940</div><div class="pc-unit">元/吨</div>'
              '<div class="pc-chg">上日 304,940（SMM 未更新）</div></div>' % DATA_ASOF)

# LME 6 卡：直接读 lme_data.json（2026-09-10 电子盘，零手抄）
_lme = json.load(open('lme_data.json', encoding='utf-8'))['metals']
_lme_map = {m['slug']: m for m in _lme}
LME_DEFS = [
    ('lcpt', 'LME 铜', 'LME', 'lcpt', '&#9650;' if _lme_map['lcpt']['chg'] >= 0 else '&#9660;'),
    ('lalt', 'LME 铝', 'LME', 'lalt', '&#9650;' if _lme_map['lalt']['chg'] >= 0 else '&#9660;'),
    ('lznt', 'LME 锌', 'LME', 'lznt', '&#9650;' if _lme_map['lznt']['chg'] >= 0 else '&#9660;'),
    ('lldt', 'LME 铅', 'LME', 'lldt', '&#9650;' if _lme_map['lldt']['chg'] >= 0 else '&#9660;'),
    ('lnkt', 'LME 镍', 'LME', 'lnkt', '&#9650;' if _lme_map['lnkt']['chg'] >= 0 else '&#9660;'),
    ('ltnt', 'LME 锡', 'LME', 'ltnt', '&#9650;' if _lme_map['ltnt']['chg'] >= 0 else '&#9660;'),
]
lme_list = []
for slug, name, tag, key, arrow in LME_DEFS:
    m = _lme_map[key]
    val = ('%s' % format(m['price'], ',.2f')) if m['price'] is not None else '--'
    if m['price'] is None:
        chg = '暂无数据'; cls = 'flat'
    else:
        sign = '+' if m['chg'] >= 0 else ''
        chg = '%s %s (%s%.2f%%)' % (arrow, sign + format(m['chg'], ',.2f'), sign, m['chg_pct'])
        cls = 'up' if m['chg'] >= 0 else 'down'
    lme_list.append((slug, name, tag, val, '美元/吨', chg, cls))
lme_html = ''.join(card(*c) for c in lme_list)


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

# ============ 3. 解析今日/往期两个区 ============
TAG_TODAY = '<div class="section" id="todaySection"'
TAG_ARCH = '<div class="section" id="archiveSection"'
TAG_RIGHTS = '<div class="section" id="rightsSection"'
i_t = html.find(TAG_TODAY)
i_a = html.find(TAG_ARCH)
i_r = html.find(TAG_RIGHTS)
assert 0 <= i_t < i_a < i_r, 'markers not found'

m_today = html.find('<!-- ==================== 今日新增')
assert m_today != -1, '今日新增 marker missing'

today_raw = html[i_t:i_a]
arch_raw = html[i_a:i_r]


def split_items(block):
    out = []
    cat = None
    for mm in re.finditer(r'<div class="sub-cat"[^>]*>([^<]*)<span class="sub-count"[^>]*>([^<]*)</span></div>'
                          r'|<div class="news-item[^>]*>.*?</div>\s*</div>', block, re.S):
        if mm.group(1) is not None:
            cat = mm.group(1).strip()
        elif mm.group(0).startswith('<div class="news-item'):
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

# ============ 4. 今日新增条目（09-10 抓取，均逐源核实） ============
CAT_ZK = '🔍 找矿成果与勘查技术'
CAT_HY = '🏭 行业动态'
CAT_GJ = '🌐 国际矿业动态'
CAT_MA = '💰 并购与投资'

# ============ 3.5 从累计库回补 30 天窗口 ============
CAT_MAP = {
    '行业动态': CAT_HY,
    '国际矿业动态': CAT_GJ,
    '找矿成果与勘查技术': CAT_ZK,
    '培训与学术': CAT_HY,
    '政策法规': CAT_HY,
    '市场行情与价格异动': CAT_HY,
    '贸易进出口与库存': CAT_HY,
    '环保安全': CAT_HY,
    '上市公司经营动态': CAT_HY,
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
    (CAT_ZK, ni('https://news.smm.cn/news/104106346', '上海有色网', '09-10',
                '马里萨南柯罗金矿钻探见富矿',
                '马里萨南柯罗（Sanankoro）金矿最新一轮钻探在多个孔段见厚大金矿体，矿化连续性较好、品位较高，进一步印证该西非金矿项目资源前景，为后续资源量更新与开发方案优化提供支撑。')),
    (CAT_ZK, ni('https://news.smm.cn/news/104106345', '上海有色网', '09-10',
                '巴西稀土公司生产首批稀土精矿',
                '巴西一家稀土企业产出首批稀土精矿，标志其矿山进入试生产阶段，南美稀土供应链多元化再添一员，也反映全球关键矿产"去单一来源"布局加速。')),
    (CAT_ZK, ni('https://news.smm.cn/news/104106209', '上海有色网', '09-10',
                '华锡有色箭猪坡矿区锑多金属矿资源储量核实报告通过评审备案 锑资源储量规模达大型',
                '华锡有色托管企业河池五吉箭猪坡矿业提交的矿产资源储量评审备案申请近日通过自然资源部评审备案。核实区保有矿石资源量增幅显著，其中锑保有金属量规模达大型，锡、铟、铅、锌、银、金、镓等共生伴生，为后续项目建设与延长矿山服务年限提供资源保障。')),

    # ---------- 🏭 行业动态 ----------
    (CAT_HY, ni('https://news.smm.cn/news/104103410', '上海有色网', '09-09',
                '海关总署：1~8月铜材进口降6.7%稀土进口降2.6%铝材出口增16.7%',
                '海关总署9月8日数据显示，前8个月我国货物贸易进出口总值34.78万亿元、同比增长17.6%；8月进出口4.65万亿元、增长19.8%。金属品种方面：8月未锻轧铜及铜材进口38.2万吨、累计329.7万吨同比降6.7%；8月铜矿砂及精矿进口250.8万吨、累计1949.2万吨同比降2.8%；8月未锻轧铝及铝材出口62.6万吨、累计466.5万吨同比增长16.7%；8月稀土进口6861.7吨同比增36.7%、累计7.02万吨同比降2.6%。')),
    (CAT_HY, ni('https://news.smm.cn/news/104106348', '上海有色网', '09-10',
                '巴西寻平衡关键矿产管控和外资',
                '巴西在推动稀土、铌、镍等关键矿产开发利用的同时，试图在资源管控与吸引外资之间寻求平衡。其政策取向将影响全球关键矿产供应格局与跨国矿企的投资决策。')),
    (CAT_HY, ni('https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0908/61959.htm', '中国有色金属工业协会', '09-08',
                '2项镁行业新标准获批 2027年3月1日起实施',
                '两项镁行业新标准获批，将于2027年3月1日起正式实施，有利于规范镁冶炼与加工产品质量、统一检测方法，推动镁产业高质量发展。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473653', '中国有色金属报', '09-08',
                '英国加码投资关键矿产本土供应链建设',
                '英国进一步加大关键矿产本土供应链投资，通过资金与政策扶持提升战略性矿产自给与加工能力，以应对全球供应链重塑与地缘扰动带来的供应风险。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473782', '中国有色金属报', '09-09',
                '2026中国国际矿业大会将于9月10日开幕',
                '2026中国国际矿业大会于9月10日开幕，汇聚国内外矿业主管部门、企业与机构，围绕资源安全、绿色勘查、智能矿山与国际合作等议题展开交流，是年内最重要的矿业盛会之一。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473660', '中国有色金属报', '09-08',
                '洛阳铜加工产出首根镁合金铸锭',
                '洛阳铜加工产出首根镁合金铸锭，标志其在镁合金材料制备工艺上取得突破，进一步拓展有色金属加工产品矩阵，服务轻量化与高端制造需求。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473833', '中国有色金属报', '09-08',
                '铜基新材料山西省重点实验室突破技术瓶颈 用"手撕铜"标注山西铜产业新高度',
                '铜基新材料山西省重点实验室突破关键技术瓶颈，研发出可"手撕"的超薄铜箔产品，标注山西铜产业技术新高度，服务集成电路、新能源等高端制造对高性能铜材的需求。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473843', '中国有色金属报', '09-08',
                '把海外资源转化为关键金属绿色产能——贵阳院攻克三水铝石矿利用关键技术',
                '贵阳院攻克三水铝石矿利用关键技术，为海外铝土矿资源就地转化为关键金属绿色产能提供"中国方案"，支撑铝产业链安全与低碳转型，输出工程技术与装备能力。')),
    (CAT_HY, ni('https://news.smm.cn/news/104106247', '上海有色网', '09-10',
                '金力永磁：预计2027年底磁材产能将达6万吨/年 上半年净利同比增51.58%',
                '金力永磁预计2027年底磁材产能将达6万吨/年；上半年净利润同比增长51.58%。在新能源汽车、风电与机器人需求拉动下，稀土永磁产能扩张与业绩增长形成共振。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473821', '中国有色金属报', '09-08',
                '中铝股份贵州分公司猫场铝矿全自主开采书写"十五五"开局新答卷',
                '中铝股份贵州分公司猫场铝矿实现全自主开采，提升铝土矿原料自主保障能力，为"十五五"开局期间氧化铝产业链安全稳定奠定基础。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473834', '中国有色金属报', '09-08',
                '中国一冶矿冶固废绿色利用技术成果荣获冶金科学技术奖一等奖',
                '中国一冶矿冶固废绿色利用技术成果荣获冶金科学技术奖一等奖，推动矿山固废资源化、减量化与绿色矿山建设，助力冶金行业低碳循环发展。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473780', '中国有色金属报', '09-08',
                '亚行新融资机制旨在重塑亚太关键矿产供应链格局',
                '亚洲开发银行推出新融资机制，旨在重塑亚太地区关键矿产供应链格局，引导资金投向勘探、加工与回收环节，降低区域对单一来源的依赖。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473779', '中国有色金属报', '09-08',
                'ITA发布更新版锡行业生命周期评价基准',
                '国际锡协会（ITA）发布更新版锡行业生命周期评价基准，为锡产业链碳排放核算、绿色贸易与可持续采购提供统一参考，呼应全球ESG监管趋严。')),
    (CAT_HY, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260904_2937623.html', '自然资源部', '09-04',
                '2026年矿区生态修复典型案例评选结果公示',
                '2026年矿区生态修复典型案例评选结果公示，集中展示一批矿山生态修复示范工程，推广可复制、可推广的治理模式与技术路径。')),
    (CAT_HY, ni('https://www.mnr.gov.cn/dt/ywbb/202609/t20260909_2937992.html', '自然资源部', '09-09',
                '全国省级地勘基金矿产勘查投入去年增长近三成',
                '全国省级地质勘查基金矿产勘查投入去年增长近三成，财政资金引导社会资本加大找矿投入，支撑新一轮找矿突破战略行动与资源保障能力建设。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473842', '中国有色金属报', '09-08',
                '八达镁业再获SCS翠鸟认证',
                '八达镁业再获SCS翠鸟再生认证，再生镁绿色产品竞争力与国际化认可度进一步提升，契合全球对低碳材料的采购偏好。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473841', '中国有色金属报', '09-08',
                '宝武镁业控股股东变更为中国宝武',
                '宝武镁业控股股东变更为中国宝武，镁产业内部资源整合与协同有望增强，巩固在镁合金领域的布局与一体化优势。')),

    # ---------- 💰 并购与投资 ----------
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-10/1225555563.PDF', '巨潮资讯网', '09-10',
                '湖南黄金：重大资产重组获得湖南省国资委批复',
                '湖南黄金重大资产重组事项获得湖南省国资委批复，交易涉及发行股份购买资产并募集配套资金，旨在进一步整合省内黄金矿产资源、提升资产证券化与主业集中度。')),
    (CAT_MA, ni('http://static.cninfo.com.cn/finalpage/2026-09-10/1225555557.PDF', '巨潮资讯网', '09-10',
                '*ST威领：西藏山南锑金资源有限公司要约收购公司股份第二次提示性公告',
                '*ST威领发布西藏山南锑金资源有限公司要约收购公司股份的第二次提示性公告，涉及锑金资源控股权变更，要约收购进入关键窗口期，相关方须关注要约条件与期限。')),
    (CAT_MA, ni('https://www.mining.com/galantas-exits-omagh-gold-project-in-5m-deal', 'MINING.COM', '09-10',
                'Galantas 以 500 万美元交易退出爱尔兰 Omagh 金矿项目',
                'Galantas 以 500 万美元交易退出爱尔兰 Omagh 金矿项目，项目控股权易手，反映中小矿企在融资环境与开发节奏压力下的资产组合调整策略。',
                orig_title='Galantas exits Omagh gold project in $5M deal')),

    # ---------- 🌐 国际矿业动态（境外，保留英文原题） ----------
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104103752-zimbabwe-bans-antimony-tungsten-exports-to-boost-domestic-processing', 'SMM 国际站', '09-09',
                '津巴布韦禁止锑、钨出口以推动本土加工',
                '津巴布韦即时禁止锑和钨出口，要求相关矿产在本土开展精炼加工，以推动矿业价值链升级。这是继锂之后非洲"锁矿潮"向传统小金属延伸的最新举措，或阶段性影响全球锑、钨供应格局。',
                orig_title='Zimbabwe Bans Antimony, Tungsten Exports to Boost Domestic Processing')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104103881-smm-analysis-lme-stocks-climb-while-backwardation-widens-whats-behind-zincs-apparent-paradox', 'SMM 国际站', '09-08',
                'LME 锌库存攀升而现货升水走阔 显性累库难缓现货紧张',
                '8月中旬以来 LME 锌注册+注销仓单库存自8.65万吨增至9月4日11.31万吨（累计增2.66万吨），但现货对三月升水不降反扩至约168.62美元/吨，显示显性库存回升未能缓解现货端紧张，呈现"库存与升水同增"的 paradox。',
                orig_title='LME Stocks Climb While Backwardation Widens — What’s Behind Zinc’s Apparent Paradox?')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104106350-indonesias-low-water-levels-disrupt-bauxite-shipments-threatening-alumina-production', 'SMM 国际站', '09-10',
                '印尼水位偏低扰动铝土矿发运 氧化铝生产或受威胁',
                '印尼水位偏低已影响部分铝土矿的内运转运，若情况延续可能扰动氧化铝生产；当前态势预计持续，需关注对全球铝土矿—氧化铝供应链的潜在冲击。',
                orig_title='Indonesia’s Low Water Levels Disrupt Bauxite Shipments, Threatening Alumina Production')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104101447-south-american-lithium-supply-disrupted-sigma-suspension-and-argentina-weather-impact-deliverability', 'SMM 国际站', '09-07',
                '南美锂供应受扰：Sigma 停产与阿根廷极端天气拖累可交付性',
                '巴西 Sigma 锂业因法律纠纷暂停采矿活动，叠加阿根廷普纳高原冬季暴雪扰动盐湖提锂发运与项目建设。短期构成供应中断，中长期则暴露南美新建盐湖项目的执行与基础设施风险。',
                orig_title='South American Lithium Supply Disrupted: Sigma Suspension and Argentina Weather Impact Deliverability')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104106368-indias-kabil-eyes-colombian-critical-minerals-opportunities-as-supply-diversification-expands', 'SMM 国际站', '09-10',
                '印度 KABIL 瞄准哥伦比亚关键矿产机会 供应链多元化再扩围',
                '印度国有关键矿产机构 KABIL 将目光投向哥伦比亚关键矿产机会，作为其供应链多元化布局的一环，意在保障锂、镍等战略资源的海外权益与长期供应。',
                orig_title='India’s KABIL Eyes Colombian Critical-Minerals Opportunities as Supply Diversification Expands')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104106349-india-russia-eye-expanded-mining-and-critical-minerals-partnership', 'SMM 国际站', '09-10',
                '印度与俄罗斯谋求扩展矿业与关键矿产伙伴关系',
                '印度与俄罗斯寻求将合作从矿产勘探拓展至先进材料，扩大矿业与关键矿产伙伴关系，反映主要经济体围绕战略资源的结盟与供应链重构趋势。',
                orig_title='India, Russia Eye Expanded Mining and Critical Minerals Partnership')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104106369-platinum-seen-outperforming-palladium-as-supply-deficits-and-industrial-demand-support-outlook', 'SMM 国际站', '09-10',
                '供应缺口与工业需求支撑 铂金表现料优于钯金',
                '分析认为铂金表现将优于钯金，受供应缺口与工业需求（尤其绿氢电解槽、汽车催化剂）支撑；铂钯比价与基本面分化预计延续。',
                orig_title='Platinum Seen Outperforming Palladium as Supply Deficits and Industrial Demand Support Outlook')),
    (CAT_GJ, ni('https://www.mining.com/copper-price-pauses-below-record-as-chinas-imports-slump-mine-supply-heads-for-first-drop-since-2017', 'MINING.COM', '09-10',
                '铜价于纪录高位下方暂歇 中国进口走弱、矿端供应迎2017年来首降',
                '铜价在纪录高位下方暂缓涨势，因中国进口走弱且矿端供应面临2017年来首次年度下降。短期多空因素交织，市场关注供需再平衡与冶炼端扰动节奏。',
                orig_title='Copper price pauses below record as China’s imports slump, mine supply heads for first drop since 2017')),
    (CAT_GJ, ni('https://www.mining.com/chile-bill-targets-foreign-cash-for-next-mining-boom', 'MINING.COM', '09-09',
                '智利法案瞄准外资 支撑下一轮矿业繁荣',
                '智利推进法案以吸引外资支撑下一轮矿业繁荣，拟通过税收与融资安排引导海外资本投入铜、锂等项目，缓解本土投资不足并加速产能建设。',
                orig_title='Chile bill targets foreign cash for next mining boom')),
    (CAT_GJ, ni('https://www.mining.com/eldorados-skouries-turns-years-of-setbacks-into-copper', 'MINING.COM', '09-09',
                'Eldorado 的 Skouries 铜金项目多年波折终见产出',
                'Eldorado Gold 的 Skouries 铜金项目历经多年波折步入产出阶段，这一希腊大型铜金资产有望逐步贡献产量，改善公司铜板块布局与现金流。',
                orig_title='Eldorado’s Skouries turns years of setbacks into copper')),
    (CAT_GJ, ni('https://www.mining.com/chile-mines-a-quarter-of-worlds-copper-but-smelts-just-4', 'MINING.COM', '09-09',
                '智利采出全球约四分之一铜 但冶炼量仅占约4%',
                '智利采出全球约四分之一的铜，但冶炼量仅占约4%，凸显其"原矿出口—海外冶炼"的结构性失衡，推动本土冶炼产能建设的议题再度升温。',
                orig_title='Chile mines a quarter of world’s copper, but smelts just 4%')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104106287-smm-news-core-lithiums-finniss-restart-reaches-a-key-milestone', 'SMM 国际站', '09-10',
                'Core Lithium 的 Finniss 锂项目重启达成关键里程碑',
                'Core Lithium 的 Finniss 锂项目重启达成关键里程碑，澳大利亚这一锂辉石项目复产进度推进，为全球锂原料供应边际增量再添变量。',
                orig_title='[SMM News] Core Lithium’s Finniss Restart Reaches a Key Milestone')),
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


# ============ 并购关键词重归类 ============
CAT_MA2 = CAT_MA
MA_REQUIRE = ['收购', '并购', '受让', '股权转让', '资产重组', '资产购买', '资产出售',
              '增资', '认购', '合资', '定增', '资产置换', '向特定对象发行', '拟收购', '拟转让', '要约收购']


def _reclassify_ma(cat, it):
    if cat in ('💼 矿权交易', CAT_MA2):
        return cat
    title = (re.search(r'class="news-title"[^>]*>([^<]+)</a>', it) or [None, ''])[1]
    sum_m = re.search(r'class="news-summary">([^<]+)</div>', it)
    summary = sum_m.group(1) if sum_m else ''
    text = title + ' ' + summary
    if any(k in text for k in MA_REQUIRE):
        return CAT_MA2
    return cat


unique_new = []
new_seen_url = set()
for cat, it in new_items:
    url = item_url(it)
    if url in new_seen_url:
        continue
    new_seen_url.add(url)
    unique_new.append((_reclassify_ma(cat, it), it))
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

html = html[:m_today] + new_today_block + new_arch_block + html[i_r:]
html = html.replace('<!-- ==================== 今日新增 ==================== -->', '', 1)

# ============ 6. 更新计数与 AI 提示 ============
html = re.sub(r'id="tocAllCount"[^>]*>\d+<', 'id="tocAllCount">%d<' % all_n, html)
html = re.sub(r'id="tocTodayCount"[^>]*>\d+<', 'id="tocTodayCount">%d<' % n_today, html)
html = re.sub(r'id="tocArchiveCount"[^>]*>\d+<', 'id="tocArchiveCount">%d<' % arch_n, html)
html = re.sub(r'今日 \d+ 条新闻的智能解读', '今日 %d 条新闻的智能解读' % n_today, html)

with open(SRC, 'w', encoding='utf-8') as f:
    f.write(html)

print('OK index.html -> today=%d archive=%d all=%d size=%d' % (n_today, arch_n, all_n, len(html)))
