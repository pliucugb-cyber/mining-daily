# -*- coding: utf-8 -*-
"""update_analysis_common.py — update_analysis_YYYYMMDD.py 系列的公共骨架。

与 generate_common.py 同构：把 13 份 update_analysis 中跨日逐字重复的
9 个函数 + 一组配置常量抽出来，每日脚本 import 后只留当日数据 + 主流程。

约束（改这里前先看）
--------------------
1. 旧脚本不动：archive/analysis/ 下 0905–0913 是历史产物，保持原样；
   只有根目录 0914–0926 这 13 份才 import 本模块。
2. 不改调用方式：每日分析链依赖 update_analysis_YYYYMMDD.py 这一文件名
   与 `python update_analysis_YYYYMMDD.py` 的调用方式，不动。
3. 抽出的函数保持原签名与语义；依赖的当日量（news / ph）由每日脚本
   在加载 JSON 后调用 bind(news, ph) 注入本模块命名空间，函数体不改。
"""
import re

# ---- 配置常量（跨日逐字一致）----

POS = ['突破', '重大', '新增', '升级', '上涨', '增长', '创新高', '达标', '获批', '加速',
       '提速', '提升', '新高', '先进', '领先', '最大', '潜力', '投产', '开幕', '达成', '一等奖']

NEG = ['下跌', '下降', '回落', '下滑', '减产', '停产', '短缺', '风险', '约束', '收紧',
        '亏损', '事故', '灾害', '违规', '处罚', '暂停', '扰动', '瓶颈', '压力', '延期', '搁置', '跳水', '重挫']

COMM = {
    '铜': ['铜'], '铝': ['铝'], '铅': ['铅'], '锌': ['锌'], '镍': ['镍'],
    '锡': ['锡'], '金': ['金'], '银': ['银'], '锂': ['锂', '碳酸锂'],
    '钴': ['钴'], '稀土': ['稀土'], '钪': ['钪'], '锑': ['锑'],
    '钼': ['钼'], '钨': ['钨'], '锗': ['锗'], '磷': ['磷'],
    '铂族': ['铂', '钯'], '铀': ['铀'], '铁矿': ['铁矿', '铁矿石'],
    '钛': ['钛'], '铍': ['铍'], '钽铌': ['钽', '铌'],
}

THEMES = {
    '价格': ['价格', '美元', '元/吨', '上涨', '下跌', '涨幅', '跌幅', '收于', '报价'],
    '矿权': ['探矿权', '采矿权', '出让', '挂牌', '拍卖', '竞买', '起始价', '转让'],
    '找矿': ['找矿', '勘查', '勘探', '资源量', '见矿', '钻探', '钻孔', '新发现', '增储', '靶区'],
    '政策': ['政策', '规划', '监管', '通知', '办法', '大会', '年会', '论坛', '意见', '公示'],
    '国际': ['国际', '全球', '海外', '美元', '智利', '澳洲', '西澳', '非洲', '美国', '巴西',
             '南非', '哥伦比亚', '欧盟', '土耳其', '印尼', '淡水河谷'],
    '技术': ['技术', '工艺', '智能', '数字化', '回收率', '无人驾驶', '双碳', '低碳', '绿色', '数字孪生'],
}

LOW_VALUE_NOTICE = [
    '公告参加', '参加中信', '业绩说明会', '业绩发布会', '中期业绩联合发布会', '投资者关系',
    '互动易', '接待调研', '机构调研', '持续督导', '核查意见', '法律意见书',
    '股东大会', '董事会决议', '监事会', '独立董事', '换届', '薪酬',
    '股票交易异常波动', '停牌', '复牌', '权益变动', '减持', '增持',
    '问询函', '关注函', '监管函', '更正公告', '补充公告', '关于召开', '拟变更',
]

ROUTINE_NOTICE = [
    '装车发运', '出厂检验', '启运', '工商登记变更', '工商变更', '完成工商',
    '业绩说明会', '投资者关系', '机构调研', '持续督导', '核查意见', '法律意见书',
    '股东大会', '董事会决议', '监事会', '异常波动', '问询函', '关注函',
    '更正公告', '补充公告', '权益变动', '减持', '增持',
]

BRIEF_MAX = 80

DOM = [('cum', '沪铜', 'SHFE 主连'), ('alm', '沪铝', 'SHFE 主连'), ('pbm', '沪铅', 'SHFE 主连'),
       ('znm', '沪锌', 'SHFE 主连'), ('snm', '沪锡', 'SHFE 主连'), ('nim', '沪镍', 'SHFE 主连'),
       ('au9999', '上海金', '上金所 Au99.99'), ('agtd', '白银', '上金所 Ag(T+D)'),
       ('lcm', '碳酸锂', 'GFEX 主连')]

LME_MAP = [('lcpt', 'Cu', '铜'), ('lalt', 'Al', '铝'), ('lznt', 'Zn', '锌'),
           ('lldt', 'Pb', '铅'), ('lnkt', 'Ni', '镍'), ('ltnt', 'Sn', '锡')]

NOTE = {
    '偏强': '三日累计上行，短期偏强',
    '中性': '区间震荡，方向不明',
    '偏弱': '三日累计下行，短期偏弱',
}

SEC_NAMES = ['行情', '政策与产业', '勘查与技术', '并购与投资', '矿权市场']

# ---- 由每日脚本注入的当日量 ----
news = None
ph = None


def bind(news_val, ph_val):
    global news, ph
    news = news_val
    ph = ph_val


# ---- 9 个跨日同构函数（原样搬入，签名/语义不变）----

def text(n):
    return (n.get('title', '') + ' ' + n.get('summary', ''))

def score_item(n):
    t = text(n)
    s = 50
    for w in POS:
        if w in t:
            s += 6
    for w in NEG:
        if w in t:
            s -= 6
    if '涨' in t and '%' in t:
        s += 4
    if '跌' in t and '%' in t:
        s -= 4
    return max(5, min(95, s))

def label(s):
    return '偏多' if s >= 60 else ('偏空' if s < 40 else '中性')

def trend(key, days=3):
    p = ph[key]['points']
    if len(p) < days + 1:
        return None, None
    base = p[-1 - days][1]
    last = p[-1][1]
    prev = p[-2][1]
    prev_base = p[-2 - days][1]
    return (last - base) / base * 100, (prev - prev_base) / prev_base * 100

def fmt_bullet(n, max_len=0):
    """简报单条（2026-09-11 用户要求「总结全」）：默认使用完整摘要，不再按 80 字截断。

    历史上 max_len=80 会把 36 条里的 35 条切在句子中间（如「HVLP4 代铜箔实…」），
    读者看到的是半句话。改为整条呈现：max_len=0 不截断；若显式传 max_len>0，
    只按句末标点（。！？）截到该长度内，绝不在句中硬切。
    """
    body = (n.get('summary') or n.get('title') or '').strip()
    if not body:
        return ''
    # 简报是中文摘要，行尾「（原题：英文标题）」对读者是噪音；英文原题在新闻卡片上已保留。
    _i = body.find('（原题：')
    if _i > 0:
        body = body[:_i].rstrip()
    if max_len and len(body) > max_len:
        cut = body[:max_len]
        pos = max(cut.rfind('。'), cut.rfind('！'), cut.rfind('？'))
        if pos >= 40:
            body = cut[:pos + 1]
    s = n.get('source', '').strip()
    return '- %s%s' % (body, '（%s）' % s if s else '')

def is_low_value_notice(n):
    t = text(n)
    return any(w in t for w in LOW_VALUE_NOTICE)

def recent_items(category, limit=0, drop_notice=False):
    """取该类目当日新增条目（2026-09-12 起默认全量）。

    limit=0（默认）= 不截断条数。历史上 limit=4 会让「行业动态」9 条只出 4 条、
    「找矿」6 条只出 4 条，读者看到的简报是残缺的。前端 setupBriefClamp() 已有
    420px 折叠 +「展开全部（N 条）」兜底，放全不会把价格区顶到屏幕外，故不再限条数。
    需要限量时显式传 limit>0。
    category 可传单个类目名，也可传列表（多类目并按传入顺序拼接）。
    """
    cats = list(category) if isinstance(category, (list, tuple)) else [category]
    arr = [n for n in news if n.get('category') in cats and n.get('is_new')]
    if drop_notice:
        arr = [n for n in arr if not is_low_value_notice(n)]
    arr.sort(key=lambda x: x.get('orig_date_full', ''), reverse=True)
    return arr[:limit] if limit else arr

def to_items(arr):
    """news 条目 → 结构化 bullet [{t,u,s}]；正文为空则丢弃。

    t = 完整摘要（不截断，剥掉行尾「（原题：…）」英文题），u = 原文链接（= 页面卡片 data-url）。
    """
    out = []
    for n in arr:
        body = (n.get('summary') or n.get('title') or '').strip()
        _i = body.find('（原题：')
        if _i > 0:
            body = body[:_i].rstrip()
        if body:
            out.append({'t': body, 'u': n.get('url', ''), 's': (n.get('source') or '').strip()})
    return out

def digest_summary(body, max_len=BRIEF_MAX):
    """长摘要 → ≤max_len 的关键句：整句优先，单句超长退到逗号/分号，绝不在句中硬切。"""
    body = (body or '').strip()
    _i = body.find('（原题：')
    if _i > 0:
        body = body[:_i].rstrip()
    if len(body) <= max_len:
        return body
    out = ''
    for seg in re.split(r'(?<=[。！？])', body):
        if len(out) + len(seg) > max_len:
            break
        out += seg
    if out:
        return out
    cut = body[:max_len]
    pos = max(cut.rfind('，'), cut.rfind('；'), cut.rfind('、'))
    return cut[:pos + 1] if pos >= 20 else cut
