# -*- coding: utf-8 -*-
"""
fetch_company.py — 矿业公司情报板块数据采集（v1：cninfo 国内 25 + SEC 北美 8）

数据来源（均落在信源白名单 §1 27 域内）：
  - 国内 25 家 A股矿业龙头：巨潮资讯网 cninfo（topSearch 取 code+orgId → hisAnnouncement 定向检索）
  - 北美 8 家上市矿企：美国 SEC EDGAR（company_tickers.json 按 ticker 精确取 CIK → submissions API）

输出：data/company_news.json
  {
    "updated_at": "YYYY-MM-DD",
    "companies": [
      {"name","code"/"ticker","sector","region":"CN"|"NA","exchange","total","kept","items":[
         {"t","d","c","lv","u","form?"}
      ]}, ...
    ]
  }

噪声过滤 + 事件分类分级复用自原型 md_company_collect3.py；SEC 标题由 filing 的
form + items + primaryDocDescription 合成可读中文，避免「FORM 8-K」这种无意义标题。

运行：python fetch_company.py
"""
import os
import re
import json
import time
import ssl
import urllib.request
import urllib.parse

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
# SEC 要求带 UA，否则 403；必须用「research <contact>」格式，纯产品型 UA 会被拒。
SEC_UA = 'research mining-daily contact@example.com'

HERE = os.path.dirname(os.path.abspath(__file__))
# 输出到仓库根目录（与 morning_report.json 等运行时 JSON 同位），由 deploy_pages 随站点发布。
OUT = os.path.join(HERE, 'company_news.json')

# ============================ 1. 公司花名册 ============================
# 国内 25 家 A股矿业龙头（按矿种归类）
DOMESTIC = [
    ('紫金矿业', '601899', '铜'), ('江西铜业', '600362', '铜'),
    ('铜陵有色', '000630', '铜'), ('云南铜业', '000878', '铜'),
    ('西部矿业', '601168', '铜'), ('洛阳钼业', '603993', '钼'),
    ('中国铝业', '601600', '铝'), ('南山铝业', '600219', '铝'),
    ('云铝股份', '000807', '铝'), ('神火股份', '000933', '铝'),
    ('天山铝业', '002532', '铝'),
    ('山东黄金', '600547', '黄金'), ('中金黄金', '600489', '黄金'),
    ('赤峰黄金', '600988', '黄金'), ('湖南黄金', '002155', '黄金'),
    ('天齐锂业', '002466', '锂'), ('赣锋锂业', '002460', '锂'),
    ('华友钴业', '603799', '钴'), ('藏格矿业', '000408', '锂'),
    ('北方稀土', '600111', '稀土'), ('中国稀土', '000831', '稀土'),
    ('驰宏锌锗', '600497', '铅锌'), ('中金岭南', '000060', '铅锌'),
    ('锡业股份', '000960', '锡'), ('厦门钨业', '600549', '钨'),
]

# 北美 7 家（SEC EDGAR 覆盖；含加拿大 Barrick 补齐）。
# 注：First Quantum（FM）无 SEC 注册（仅在 TSX 上市），SEC 无备案 → 已剔除，留待 Phase 2 加拿大 SEDAR 源。
# cik 为回退值；运行时优先用 company_tickers.json 按 ticker 精确解析（避免 Gold.com 误判 Barrick）。
SEC_COMPANIES = [
    ('Newmont',         'NEM', '黄金', 1164727),
    ('Albemarle',       'ALB', '锂',   915913),
    ('Southern Copper',  'SCCO','铜',   1001838),
    ('Agnico Eagle',    'AEM', '黄金', 2809),
    ('Freeport-McMoRan','FCX', '铜',   831259),
    ('Teck Resources',  'TECK','铅锌', 886986),
    ('Barrick',         'B',   '黄金', 756894),    # 2025 更名 Barrick Mining Corp
]

# ============================ 2. 噪声 + 分类（cninfo 国内） ============================
NOISE = [
    "独立董事", "独立非执行董事", "候选人声明", "提名人声明", "征集投票权",
    "股东大会", "股东会", "会议通知", "法律意见书", "公司章程", "章程修订",
    "募集资金", "闲置募集资金", "理财产品", "定期报告", "季度报告",
    "半年度报告", "年度报告摘要", "业绩说明会", "投资者关系活动记录",
    "接待日", "网上集体接待", "内幕信息", "知情人登记", "监事会", "职工代表",
    "辞职", "聘任", "审计机构", "会计师事务所", "变更证券简称", "股票交易异常",
    "异动", "停牌", "复牌公告", "权益分派", "限售股", "解禁",
    "问询函回复", "更正公告", "延期回复", "风险提示公告",
    "董事会决议", "监事会决议", "董事会会议", "会议决议", "董事离任", "补选董事",
    "募集说明书", "保荐书", "上市公告书", "发行公告", "发行结果", "配股",
    "可转债赎回", "跟踪评级", "评级报告", "审计报告",
    "持续督导意见", "持续督导总结报告", "持续督导现场核查", "持续督导年度报告",
    "券商核查意见", "保荐机构核查", "独立财务顾问",
    "翌日披露报表", "证券变动月报表", "月报表", "H股市场公告",
    "薪酬方案", "薪酬管理制度", "捐赠", "报废", "风险持续评估", "风险评估报告",
    "商品房", "尾盘", "商业用地", "地块", "置业", "物业服务",
    "续聘", "内部控制", "自查报告", "专项核查",
    "简式权益变动报告书", "详式权益变动报告书",
    "回购注销", "限制性股票", "股票期权",
]

FIN_INSTR = ['中期票据', '公司债', '超短融', '融资券', '可转债', '债券', '资产支持']
M_ACQ  = ['收购', '并购', '重组', '要约', '资产购买', '股权转让', '受让', '竞得',
          '摘牌', '资产置换', '吸收合并', '借壳']
M_CAP  = ['投产', '扩产', '达产', '试生产', '复产', '停产', '扩建', '新建项目',
          '生产线', '技改', '项目开工', '复工复产']
M_RES  = ['储量', '增储', '资源量', '探矿权', '采矿权', '矿业权', '探明', '勘查',
          '矿区', '品位', '竞拍取得']
M_ORD  = ['中标', '供货合同', '销售合同', '采购合同', '战略合作', '框架协议',
          '长期协议', '订单']
M_INV  = ['对外投资', '共同投资', '增资', '设立控股', '合资', '产业基金', '认购']
M_SHR  = ['增持', '减持', '控制权', '实际控制人', '举牌', '股份转让', '解除质押',
          '质押']
M_PERF = ['产量', '销量', '营业收入', '净利润', '业绩快报', '预增', '预盈',
          '扭亏', '经营数据', '生产经营', '生产情况']
M_BUY  = ['回购', '股权激励', '员工持股']
M_FIN  = ['担保', '财务资助', '融资', '借款', '保理', '信用证', '信托', '授信']

def classify(t):
    """国内公告分类：融资/担保优先判低优先级，再按经营维度分级。"""
    if any(k in t for k in FIN_INSTR):
        return '融资发行', 'low'
    if any(k in t for k in M_FIN):
        return '融资担保', 'low'
    if any(k in t for k in M_ACQ):
        return '并购重组', 'high'
    if any(k in t for k in M_CAP):
        return '产能项目', 'high'
    if any(k in t for k in M_RES):
        return '资源储量', 'high'
    if any(k in t for k in M_ORD):
        return '合同订单', 'high'
    if any(k in t for k in M_INV):
        return '对外投资', 'mid'
    if any(k in t for k in M_SHR):
        return '股东变动', 'mid'
    if any(k in t for k in M_PERF):
        return '经营业绩', 'mid'
    if any(k in t for k in M_BUY):
        return '股份回购', 'low'
    return '其他', 'low'

# ============================ 3. cninfo 采集 ============================
def post(url, data, referer='http://www.cninfo.com.cn/', timeout=25, retries=2):
    for i in range(retries + 1):
        try:
            body = urllib.parse.urlencode(data).encode('utf-8')
            req = urllib.request.Request(url, data=body, headers={
                'User-Agent': UA, 'Content-Type': 'application/x-www-form-urlencoded',
                'X-Requested-With': 'XMLHttpRequest', 'Referer': referer})
            return urllib.request.urlopen(req, timeout=timeout, context=ctx).read().decode('utf-8', 'replace')
        except Exception:
            if i == retries:
                return '__ERR__'
            time.sleep(1.2)
    return '__ERR__'

def clean(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', s or '')).strip()

def top_search(kw):
    t = post('http://www.cninfo.com.cn/new/information/topSearch/query',
             {'keyWord': kw, 'maxNum': 10})
    if t.startswith('__ERR__'):
        return None
    try:
        j = json.loads(t)
    except Exception:
        return None
    for it in (j if isinstance(j, list) else []):
        return it.get('code'), it.get('orgId')
    return None

def query_ann(code, org, days=45):
    col = 'sse' if code.startswith('6') else 'szse'
    plate = 'sh' if code.startswith('6') else 'sz'
    end = time.strftime('%Y-%m-%d')
    start = time.strftime('%Y-%m-%d', time.localtime(time.time() - days * 86400))
    t = post('http://www.cninfo.com.cn/new/hisAnnouncement/query', {
        'pageNum': 1, 'pageSize': 60, 'column': col, 'tabName': 'fulltext',
        'plate': plate, 'stock': code + ',' + org, 'searchkey': '', 'secid': '',
        'category': '', 'trade': '', 'seDate': start + '~' + end,
        'sortName': '', 'sortType': '', 'isHLtitle': 'true'})
    try:
        return (json.loads(t).get('announcements') or [])
    except Exception:
        return []

def run_domestic(days=45):
    out = []
    for name, code, sector in DOMESTIC:
        r = top_search(name)
        if not r:
            print('  [skip] %s 未检索到 code/orgId' % name)
            continue
        rcode, org = r
        anns = query_ann(rcode, org, days)
        kept, dropped = [], 0
        for a in anns:
            title = clean(a.get('announcementTitle'))
            if not title:
                continue
            if any(k in title for k in NOISE):
                dropped += 1
                continue
            try:
                dt = time.strftime('%Y-%m-%d', time.localtime(int(a.get('announcementTime')) / 1000))
            except Exception:
                dt = ''
            adj = (a.get('adjunctUrl') or '').lstrip('/')
            cat, lv = classify(title)
            kept.append({'t': title, 'd': dt, 'c': cat, 'lv': lv, 'co': name, 'code': rcode,
                         'sector': sector, 'u': ('http://static.cninfo.com.cn/' + adj) if adj else ''})
        kept.sort(key=lambda x: x['d'], reverse=True)
        out.append({'name': name, 'code': rcode, 'sector': sector, 'region': 'CN',
                    'exchange': 'A股', 'total': len(anns), 'kept': len(kept),
                    'dropped': dropped, 'items': kept[:12]})
        print('  %-8s %-7s 公告%-4d 留%-3d 剔%-3d %s'
              % (name, rcode, len(anns), len(kept), dropped,
                 (kept[0]['t'][:28] if kept else '—')))
        time.sleep(0.35)
    return out

# ============================ 4. SEC 采集 ============================
SEC_ITEM_ZH = {
    '1.01': '订立重大协议', '1.02': '终止重大协议', '1.03': '破产或接管',
    '1.04': '矿山安全通报', '2.01': '完成资产收购/处置', '2.02': '经营业绩与财务状况',
    '2.03': '重大财务债务', '2.05': '私下谈判交易', '2.06': '重大资产减值',
    '3.01': '上市状态变更', '4.01': '审计师变更', '5.01': '控制权变更',
    '5.02': '董事/高管变动', '5.03': '章程修订', '5.07': '股东投票结果',
    '7.01': 'FD规则披露', '8.01': '其他重大事项', '9.01': '财务报表及附件',
}
SEC_FORM_ZH = {
    '10-K': '年度报告', '10-Q': '季度报告', '10-K/A': '年度报告（修订）', '10-Q/A': '季度报告（修订）',
    '20-F': '年度报告（境外）', '40-F': '年度报告（加拿大）', '6-K': '当期报告', '8-K': '重大事件报告',
    'S-4': '并购/重组登记', 'F-4': '并购登记（境外）', '425': '招股/要约声明', 'SC TO': '收购要约声明',
    'DEF 14A': '委托投票书', 'DEFA14A': '附加委托投票书',
}
# 保留的经营相关 form（剔除纯证券/持股/基金类流程件）
SEC_KEEP_FORMS = {
    '10-K', '10-Q', '10-K/A', '10-Q/A', '20-F', '40-F', '6-K', '8-K',
    'S-4', 'F-4', '425', 'SC TO', 'DEF 14A', 'DEFA14A',
}

def sec_get(url, timeout=30):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': SEC_UA, 'Accept': 'application/json'})
        return urllib.request.urlopen(req, timeout=timeout, context=ctx).read().decode('utf-8', 'replace')
    except Exception as e:
        return ''

def load_ticker_map():
    raw = sec_get('https://www.sec.gov/files/company_tickers.json')
    m = {}
    if not raw:
        return m
    try:
        d = json.loads(raw)
        for v in d.values():
            m[str(v.get('ticker', '')).upper()] = int(v['cik_str'])
    except Exception:
        pass
    return m

def resolve_cik(ticker, fallback, tmap):
    if fallback:
        return int(fallback)
    return tmap.get(ticker.upper())

def sec_classify(form, items):
    """由 form + items 推导分类与级别。"""
    f = (form or '').upper()
    codes = [x.strip() for x in (items or '').replace(' ', '').split(',') if x.strip()]
    if f in ('S-4', 'F-4', '425', 'SC TO'):
        return '并购重组', 'high'
    if f in ('10-K', '10-Q', '10-K/A', '10-Q/A', '20-F', '40-F'):
        return '经营业绩', 'mid'
    # 8-K / 6-K 按 items
    for c in codes:
        if c in ('1.01', '1.02', '2.01', '2.05', '2.06'):
            return '并购重组/产能项目', 'high'
        if c == '2.02':
            return '经营业绩', 'mid'
        if c in ('5.01', '5.02', '5.03'):
            return '股东变动', 'mid'
        if c in ('7.01', '8.01', '9.01'):
            return '其他', 'low'
        if c == '3.01':
            return '其他', 'low'
    return '其他', 'low'

def sec_title(co, form, items, desc):
    f = (form or '').upper()
    codes = [x.strip() for x in (items or '').replace(' ', '').split(',') if x.strip()]
    labels = [SEC_ITEM_ZH.get(c, c) for c in codes if c in SEC_ITEM_ZH]
    if labels:
        return '%s %s：%s' % (co, f, '/'.join(labels[:2]))
    zh = SEC_FORM_ZH.get(f, f)
    return '%s 提交 %s（%s）' % (co, f, zh)

def run_sec(tmap, days=180):
    out = []
    cutoff = time.strftime('%Y-%m-%d', time.localtime(time.time() - days * 86400))
    for name, ticker, sector, fcik in SEC_COMPANIES:
        cik = resolve_cik(ticker, fcik, tmap)
        if not cik:
            print('  [skip] %s (%s) 未解析到 CIK' % (name, ticker))
            continue
        url = 'https://data.sec.gov/submissions/CIK%010d.json' % cik
        raw = sec_get(url)
        if not raw:
            print('  [skip] %s (%s) submissions 获取失败' % (name, ticker))
            continue
        try:
            j = json.loads(raw)
        except Exception:
            print('  [skip] %s (%s) JSON 解析失败' % (name, ticker))
            continue
        rec = (j.get('filings') or {}).get('recent') or {}
        forms = rec.get('form') or []
        dates = rec.get('filingDate') or []
        accs = rec.get('accessionNumber') or []
        docs = rec.get('primaryDocument') or []
        descs = rec.get('primaryDocDescription') or []
        itemss = rec.get('items') or []
        n = min(len(forms), len(dates))
        kept, total = [], 0
        for i in range(n):
            f = (forms[i] or '').upper().strip()
            if f not in SEC_KEEP_FORMS:
                continue
            total += 1
            d = dates[i] or ''
            if d < cutoff:
                continue
            acc = (accs[i] or '').replace('-', '')
            doc = docs[i] or ''
            desc = descs[i] or ''
            items = itemss[i] if i < len(itemss) else ''
            u = ('https://www.sec.gov/Archives/edgar/data/%d/%s/%s'
                 % (cik, acc, doc)) if acc and doc else ''
            cat, lv = sec_classify(f, items)
            kept.append({'t': sec_title(name, f, items, desc), 'd': d, 'c': cat, 'lv': lv,
                         'co': name, 'ticker': ticker, 'sector': sector,
                         'form': f, 'u': u})
        kept.sort(key=lambda x: x['d'], reverse=True)
        out.append({'name': name, 'ticker': ticker, 'sector': sector, 'region': 'NA',
                    'exchange': 'SEC', 'total': total, 'kept': len(kept),
                    'dropped': 0, 'items': kept[:12]})
        print('  %-16s %-5s 命中%-3d 留%-3d %s'
              % (name, ticker, total, len(kept),
                 (kept[0]['t'][:30] if kept else '—')))
        time.sleep(0.4)
    return out

# ============================ 5. 主流程 ============================
def main():
    print('===== 国内 25 家（cninfo） =====')
    domestic = run_domestic()
    print('\n===== 北美 8 家（SEC EDGAR） =====')
    tmap = load_ticker_map()
    print('  ticker→CIK 映射载入 %d 条' % len(tmap))
    foreign = run_sec(tmap)
    companies = domestic + foreign
    data = {
        'updated_at': time.strftime('%Y-%m-%d'),
        'companies': companies,
        'counts': {
            'domestic': len(domestic), 'foreign': len(foreign),
            'total': len(companies),
            'items': sum(len(c['items']) for c in companies),
        },
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print('\n国内 %d / 北美 %d / 合计 %d 家，条目 %d'
          % (len(domestic), len(foreign), len(companies),
             data['counts']['items']))
    print('saved', OUT)

if __name__ == '__main__':
    main()
