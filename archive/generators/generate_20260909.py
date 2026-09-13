# -*- coding: utf-8 -*-
"""
生成 2026-09-09 矿业新闻日报 index.html（补跑：06:00 自动化生成任务未跑成）
- 09-08 的"今日新增"条目滚入"往期内容"（去 NEW 标记、按同类目合并）
- 按 30 天窗口（滚动保留最近30天）剔除往期条目，月度全量在 data/news_*.json
- 换入 09-09 抓取的最新条目（is-new + NEW），更新各计数与 AI 区条数
- 国内 SHFE/上金所 09-08 收盘已出，价格卡刷新；LME 09-09 电子盘刷新
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

REPORT = '2026-09-09'
GRAB = '2026-09-09'
ARCHIVE_DAYS = 30
REPORT_DT = datetime.date.fromisoformat(REPORT)
CUTOFF_DT = REPORT_DT - datetime.timedelta(days=ARCHIVE_DAYS - 1)   # 往期最早日期（含）= 08-11
DATA_ASOF = '09-08'

# ============ 1. 标题 / 日期 / 更新时间 ============
html = re.sub(r'<title>\d{4}-\d{2}-\d{2}</title>', '<title>%s</title>' % REPORT, html)
html = html.replace('2026年09月08日 星期二', '2026年09月09日 星期三')
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
    ('cum', '沪铜', 'SHFE', '110,620', '元/吨', UP + ' +1,210 (+1.11%)', 'up'),
    ('alm', '沪铝', 'SHFE', '24,460', '元/吨', UP + ' +40 (+0.16%)', 'up'),
    ('pbm', '沪铅', 'SHFE', '16,135', '元/吨', DOWN + ' -75 (-0.46%)', 'down'),
    ('znm', '沪锌', 'SHFE', '27,505', '元/吨', UP + ' +410 (+1.51%)', 'up'),
    ('nim', '沪镍', 'SHFE', '127,400', '元/吨', DOWN + ' -420 (-0.33%)', 'down'),
    ('snm', '沪锡', 'SHFE', '418,950', '元/吨', UP + ' +80 (+0.02%)', 'up'),
    ('au9999', '上海金', 'Au99.99', '953.12', '元/克', UP + ' +2.34 (+0.25%)', 'up'),
    ('agtd', '白银', 'Ag(T+D)', '16,125', '元/千克', UP + ' +135 (+0.84%)', 'up'),
    ('lcm', '碳酸锂', '主力连续', '143,480', '元/吨', UP + ' +1,280 (+0.90%)', 'up'),
]
shfe_html = ''.join(card(*c) for c in SHFE)
# 电解钴：无当日源，保留上日 SMM 值并标注
shfe_html += ('<div class="price-card "><div class="pc-name">电解钴 <span class="pc-tag">SMM %s</span></div>'
              '<div class="pc-value">304,940</div><div class="pc-unit">元/吨</div>'
              '<div class="pc-chg">上日 304,940（SMM 未更新）</div></div>' % DATA_ASOF)

LME = [
    ('lcpt', 'LME 铜', 'LME', '14,686.00', '美元/吨', DOWN + ' -42.00 (-0.29%)', 'down'),
    ('lalt', 'LME 铝', 'LME', '3,339.00', '美元/吨', UP + ' +5.00 (+0.15%)', 'up'),
    ('lldt', 'LME 铅', 'LME', '1,916.50', '美元/吨', UP + ' +1.50 (+0.08%)', 'up'),
    ('lznt', 'LME 锌', 'LME', '4,010.50', '美元/吨', DOWN + ' -10.50 (-0.26%)', 'down'),
    ('lnkt', 'LME 镍', 'LME', '16,765.00', '美元/吨', UP + ' +10.00 (+0.06%)', 'up'),
    # 2026-09-10 数据对齐：lme_data.json 中锡 price=null，静态值必须写 --/暂无数据
    # （与前端 renderLmePrices() 的 null 兜底口径一致），严禁手抄任何夜盘/昨日数字。
    ('ltnt', 'LME 锡', 'LME', '--', '美元/吨', '暂无数据', 'flat'),
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
    # ---------- 🔍 找矿成果与勘查技术（09-09 抓取） ----------
    (CAT_ZK, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473846', '中国有色金属报', '09-08',
                '箭猪坡锑多金属矿储量核实报告通过自然资源部评审备案',
                '华锡有色托管企业河池五吉箭猪坡矿业有限公司提交的矿产资源储量评审备案申请近日通过自然资源部评审备案。截至2024年12月31日，核实区（+500米至-300米标高）保有矿石资源量797.2万吨、增幅268.02%，其中锑保有金属量超13万吨、增幅169.90%，锡、铟、铅、锌、银、金、镓等多种金属共生伴生。本次储量大幅增长得益于深部找矿和"探边摸底"，锑资源储量规模达到大型，为后续项目建设与延长矿山服务年限提供资源保障。')),
    (CAT_ZK, ni('https://news.smm.cn/news/104104007', '上海有色网', '09-09',
                '巴西铁山稀土矿等项目进展：澳/乌/科多国矿端见矿',
                '动力矿产公司（Power Minerals）巴西铁山（Morro do Ferro）稀土项目钻孔从地表起88米、总稀土氧化物（TREO）品位6.33%，其中磁体稀土氧化物（MREO）品位1.2%；另见50米厚TREO品位9%、MREO 1.56%矿体；该孔验证矿床中心北东方向新区。布莱兹矿产公司达成购买乌干达巴哈蒂、布亚加两个钨矿项目协议，巴哈蒂矿床生产钨270吨。奥伦资源公司在科特迪瓦邦迪亚利金矿32米深处见矿5.63米、金品位31.79克/吨，包括2.63米厚、品位67.6克/吨的富矿。')),

    # ---------- 🏭 行业动态（09-09 抓取） ----------
    (CAT_HY, ni('https://news.smm.cn/news/104103410', '上海有色网', '09-09',
                '海关总署：1~8月铜材进口降6.7%稀土进口降2.6%铝材出口增16.7%',
                '海关总署9月8日数据显示，前8个月我国货物贸易进出口总值34.78万亿元、同比增长17.6%；8月份进出口4.65万亿元、增长19.8%。金属品种方面：8月未锻轧铜及铜材进口38.2万吨、累计329.7万吨同比降6.7%；8月铜矿砂及精矿进口250.8万吨、累计1949.2万吨同比降2.8%；8月未锻轧铝及铝材出口62.6万吨、累计466.5万吨同比增长16.7%；8月稀土进口6861.7吨同比增长36.7%、累计7.02万吨同比降2.6%。')),
    (CAT_HY, ni('https://news.smm.cn/news/104099041', '上海有色网', '09-09',
                '报道：津巴布韦暂停锑和钨出口以推动本土加工',
                '据彭博获得的津巴布韦矿业部7月21日信函，该国即时禁止锑和钨出口、进一步收紧对关键矿产资源出口管控，以强制矿业公司在本国境内开展更多精炼加工业务。信函要求所有锑精矿、锑金属及钨精矿、钨铁等暂停出口，已签发但未执行的出口许可证一律暂停。津巴布韦是非洲主要锂、铂、铬矿生产国，本次禁令是继锂出口管控之后再度扩面至锑钨，被视为非洲"锁矿潮"向传统小金属延伸的最新例证。')),
    (CAT_HY, ni('https://news.smm.cn/news/104070712', '上海有色网', '09-09',
                'SMM：预计全球锡市场将维持紧平衡状态 新矿产能将在2028年集中释放',
                'SMM亚洲电池材料合作论坛评论：随缅甸佤邦复产推进，中国锡矿供应逐步从过度依赖单一来源转向多元化，2025年缅甸进口占比降至24%~30%、刚果金升至28%、尼日利亚升至11%、澳洲同比增长101%。但缅甸佤邦高品位矿坑淹水、4月7日爆炸事故后爆炸物管控、5-10月季风期排水难度加大等多重因素，使该地区产量恢复速度不及预期。SMM预计全球锡市场紧平衡格局延续，新矿产能将在2028年集中释放。')),
    (CAT_HY, ni('https://news.smm.cn/news/103825840', '上海有色网', '09-09',
                '江苏连云港破获涉案稀土达220吨、价值超46亿的重大走私案？官方辟谣',
                '针对网传"江苏连云港破获涉案稀土达220吨、价值超46亿元的稀土走私案"传言，连云港公安等部门核查后发布通报予以辟谣：该案系2024年侦办的"9.18"特大走私案涉案企业、人员诉讼及执行进展报道，并非新近案件；涉案稀土数量、案值与网传数据存在差异，公安机关将依法追究恶意造谣、传谣者责任。')),
    (CAT_HY, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473816', '中国有色金属报', '09-08',
                '多引擎协同发力 金川镍钴粉体材料厂聚力打造全国一流球镍产业高地',
                '金川镍钴粉体材料厂2026年上半年聚焦球形氢氧化镍高端化、系列化主线，统筹产线数字化改造、关键工艺迭代攻关、产品矩阵多元扩展，产品从单一镍氢专用产品延伸至覆盖镍铁、镍锌三大技术路线8个规格系列产品，跻身国内头部新能源厂商核心供应链。今年以来球镍系列产品产量同比增长48.14%、营业收入同比增长47.72%，后续2000吨扩能项目稳步推进；覆钴球镍综合性能跻身行业一流水平。')),

    # ---------- 🌐 国际矿业动态（09-09 抓取） ----------
    (CAT_GJ, ni('https://www.cnmn.com.cn/ShowNews1.aspx?id=473831', '中国有色金属报', '09-08',
                '智利和阿根廷推进跨边界铜矿开发',
                '近日，阿根廷与智利官员重新履行1997年《矿业融合互补条约》，推进维库尼亚、尼索安迪诺与费洛南矿业项目，批准矿床位于两国交界安第斯山区，可共享基础设施与资源。智利矿业部表示该框架有望释放207亿美元矿业项目投资、年增铜产量54万吨。三大潜在受益项目包括麦克尤恩铜业的洛斯阿苏莱斯、嘉能可的埃尔帕琼、伦丁矿业与必和必拓合资的维库尼亚；分析师预计阿根廷2030年将跻身全球前十大产铜国。')),
    # ---- 境外（英文原题保留）----
    (CAT_GJ, ni('https://www.mining.com/marimaca-hits-thick-copper-silver-zone-at-pampa-medina-in-chile',
                'MINING.COM', '09-09',
                'Marimaca 智利 Pampa Medina 铜银矿见厚大矿体，铜品位近1%',
                'Marimaca Copper（TSX: MARI; ASX: MC2）宣布智利安托法加斯塔大区 Pampa Medina 项目钻探见厚大铜银矿体：SPRD-15 孔自466米起216米段铜品位0.96%、银7.2克/吨，其中602米起62米段铜2.2%、银21.5克/吨；SPD-13 孔自194米起222米段铜0.5%；SPRD-12 孔自748米起56米段铜0.95%、银4.2克/吨。公司今年计划在 Pampa Medina 完成3万米钻探，PampaMedina 距 Marimaca 主氧化矿床28千米，依赖已有基础设施；公司股价当日涨13%。',
                orig_title='Marimaca hits thick copper-silver zone at Pampa Medina in Chile')),
    (CAT_GJ, ni('https://www.mining.com/rio-tinto-acquires-aurukun-bauxite-project-from-glencore-mitsubishi',
                'MINING.COM', '09-09',
                '力拓收购嘉能可/三菱 Aurukun 铝土矿项目',
                '力拓（ASX: RIO）同意从嘉能可（LON: GLEN）与三菱开发公司手中收购澳大利亚昆士兰州 Aurukun 铝土矿项目。嘉能可此前持有多数股权，三菱持有约30%。该项目仍处于"矿产开发许可证"阶段，尚未取得"采矿租约"。交易财务条款未披露，仍待昆士兰州政府及澳大利亚其他监管机构批准。Aurukun 项目位于力拓现有 Weipa 业务以北约200公里，Weipa 矿区年产量超过3000万吨铝土矿，可为 Aurukun 提供现有基础设施支撑。',
                orig_title='Rio Tinto acquires Aurukun bauxite project from Glencore, Mitsubishi')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104104009-ivanhoe-expands-drc-western-forelands-copper-resource-by-30-makoko-scoping-study-planned-for-2027',
                'SMM 国际站', '09-08',
                '艾芬豪将刚果（金）西部前沿铜资源量扩大30% Makoko 概略研究计划2027年启动',
                '艾芬豪矿业将其在刚果民主共和国"西部前沿"勘探项目的铜资源量增加约30%，进一步扩大 Makoko 区铜矿规模。更新后的2026年矿产资源量包括指示资源量4200万吨（铜品位2.66%）、推断资源量6.12亿吨（铜品位1.80%）；2025年5月以来约6.4万米岩芯钻探使含铜量增至约1200万吨。Makoko 概略研究计划2027年一季度启动；公司称这是过去十年全球规模最大、品位最高的铜矿发现之一。',
                orig_title='Ivanhoe Expands DRC Western Forelands Copper Resource by 30%, Makoko Scoping Study Planned for 2027')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104103985-gacc-chinas-january-august-copper-ore-and-concentrate-imports-totaled-1949-million-mt-down-28-yoy',
                'SMM 国际站', '09-08',
                '海关总署：1~8月中国铜矿砂及精矿进口累计1949万吨，同比降2.8%',
                '海关总署9月8日数据显示，8月中国铜矿砂及精矿进口250.8万吨，前8月累计进口1949.15万吨、同比降2.8%；8月未锻轧铜及铜材进口38.19万吨，前8月累计329.71万吨、同比降6.7%。出口侧，8月未锻轧铝及铝材出口62.56万吨，前8月累计466.5万吨、同比增长16.7%。1~8月我国货物贸易进出口总值34.78万亿元、同比增长17.6%；8月进出口4.65万亿元、增长19.8%。',
                orig_title="GACC: China's January-August copper ore and concentrate imports totaled 19.49 million mt, down 2.8% YoY")),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104103970-global-copper-concentrate-market-tightens-as-smelting-capacity-expands-cochilco',
                'SMM 国际站', '09-08',
                '智利铜业委员会：全球铜精矿市场结构性趋紧 冶炼产能加速扩张',
                '智利铜业委员会 Cochilco 最新报告指出，全球铜精矿市场面临结构性趋紧：矿端品位下降、项目延期与运营扰动限制精矿供应，而新增冶炼产能持续扩张（中国与印尼尤为明显），现货 TC/RC 在2025-2026年间已接近零或为负。Cochilco 预计已识别项目到2041年将新增约820万吨/年精炼当量冶炼产能，主要集中在亚洲，智利精矿处理产能544万吨/年仍居拉美第一，但当前开工率仅约70%。',
                orig_title='Global Copper Concentrate Market Tightens as Smelting Capacity Expands — Cochilco')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104103575-general-administration-of-customs-copper-semis-imports-down-67-rare-earth-imports-down-26-aluminum-semis-exports-up-167-january-august',
                'SMM 国际站', '09-09',
                '海关总署：1~8月铜材进口降6.7% 稀土进口降2.6% 铝材出口增16.7%',
                '海关总署9月8日发布数据，前8月中国货物贸易进出口34.78万亿元、同比增长17.6%；8月进出口4.65万亿元、增长19.8%。金属品种方面：8月未锻轧铜及铜材进口38.2万吨、前8月累计329.7万吨同比降6.7%；8月铜矿砂及精矿进口250.8万吨同比降9.1%、累计1949.2万吨同比降2.8%；8月未锻轧铝及铝材出口62.6万吨同比增17.2%、累计466.5万吨同比增16.7%；8月稀土进口6861.7吨同比增36.7%、累计7.02万吨同比降2.6%。',
                orig_title='General Administration of Customs: Copper Semis Imports Down 6.7%, Rare Earth Imports Down 2.6%, Aluminum Semis Exports Up 16.7% January-August')),
    (CAT_GJ, ni('https://news.metal.com/en/newscontent/104103965-approximately-14-billion-india-plans-130-billion-rupee-battery-component-incentive-program',
                'SMM 国际站', '09-08',
                '印度拟推约14亿美元电池组件激励计划',
                '据印度《商业标准报》报道，印度政府正制定总额约1300亿卢比（约14亿美元）的高级电池组件激励计划，覆盖正负极活性材料、电解液、隔膜与铜箔等关键电池单元组件。消息人士称该计划已完成跨部委磋商，即将提交财政部支出财务委员会审批。',
                orig_title='Approximately $1.4 billion! India plans 130 billion rupee battery component incentive program')),
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


# ============ 3.6 并购关键词重归类（方案B：让境外/行业源里的并购新闻也进「并购与投资」） ============
CAT_MA = '💰 并购与投资'
MA_KW = ['收购', '并购', '资产重组', '资产购买', '资产出售', '股权转让', '受让',
         '增资', '拟收购', '拟转让', '认购', '合资', '重大资产', '定增',
         '资产置换', '向特定对象发行']
# 叙述性误判排除：仅当标题/摘要同时出现「标的/交易/股权/项目」等实质交易语境才归并购
MA_REQUIRE = ['收购', '并购', '受让', '股权转让', '资产重组', '资产购买', '资产出售',
              '增资', '认购', '合资', '定增', '资产置换', '向特定对象发行', '拟收购', '拟转让']

def _reclassify_ma(cat, it):
    """命中并购实质关键词且当前非矿权/并购类时，归到「并购与投资」。"""
    if cat in ('💼 矿权交易', CAT_MA):
        return cat
    title = (re.search(r'class="news-title"[^>]*>([^<]+)</a>', it) or [None, ''])[1]
    sum_m = re.search(r'class="news-summary">([^<]+)</div>', it)
    summary = sum_m.group(1) if sum_m else ''
    text = title + ' ' + summary
    if any(k in text for k in MA_REQUIRE):
        return CAT_MA
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
