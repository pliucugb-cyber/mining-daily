#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_news.py — 有色金属行业新闻自动爬虫（P3 产能瓶颈根本解）

设计定位
--------
**爬虫负责"发现候选"，AI 负责"审核 + 翻译"。**
不是全自动发布——那样会牺牲"信息来源必须可靠"这条底线（用户 2026-09-07 明确要求）。
爬虫把「从零找新闻」变成「从几十条候选里挑」，产能提升但质量不降。

设计要点
--------
1. **零第三方依赖**：仅标准库（urllib/ssl/re/xml.etree/gzip），与 fetch_ma.py 一致。
   环境实测无 requests/bs4/lxml，禁止引入。
2. **源配置化**：新增源只需往 SOURCES 加一条配置，不改解析逻辑。
3. **三重过滤**：白名单域校验 → 有色相关性（须命中）→ 噪声排除（时政/广告/招聘）。
4. **去重**：URL 规范化去重 + 标题相似度去重（同一事件多源报道只留一条）。
5. **境外源单独标记**（foreign=True），提示 AI 需走英文翻译规范与可达性复检。

产出
----
默认写候选池 `data/news_candidates_YYYY-MM-DD.json`；
加 `--merge` 则同时并入 `data/news_YYYY-MM.json`（与 fetch_ma.py 同 schema）。

用法
----
    python fetch_news.py                          # 抓今日，写候选池
    python fetch_news.py --days 3                 # 抓最近 3 天
    python fetch_news.py --merge                  # 抓完并入月度库
    python fetch_news.py --source smm             # 只跑指定源
    python fetch_news.py --fetch-detail           # 逐条抓正文补摘要（慢）
    python fetch_news.py --dry-run                # 只打印不落盘
"""
import argparse
import datetime
import gzip
import hashlib
import html as htmllib
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
CTX = ssl.create_default_context()   # 2026-09-09 安全整改 P0：恢复 TLS 证书校验（此前全局关闭校验可被中间人篡改数据）

TIMEOUT = 20
# 2026-09-08 提升：原 40 会被主源打满（实测中国有色金属报当日正好 40 条触顶，
# 意味着还有内容被丢弃）。改为 120 全局默认，主源再靠源级 max_items 单独放大。
MAX_PER_SOURCE = 120         # 单源默认上限（源配置里的 max_items 可覆盖）
DETAIL_LIMIT = 12            # --fetch-detail 时最多抓多少条正文（防拖慢）

# ---------------------------------------------------------------------------
# 非金属（砂石土/建材类）排除：矿业权市场列表里 7 成是建筑石料、地热、灰岩，
# 而 INDUSTRY_KW 含单字「矿」，单靠相关性会把它们全部误判为有色相关。
# 只在 ky 源上生效（extra_exclude），避免误伤其他源。
# ---------------------------------------------------------------------------
NONMETALLIC_KW = [
    "建筑石料", "建筑用", "碎石", "砂石", "采砂", "取土", "地热", "矿泉水",
    "灰岩", "石灰岩", "花岗岩", "大理岩", "大理石", "砂岩", "石英砂", "石英岩",
    "白云岩", "页岩", "玄武岩", "凝灰岩", "片麻岩", "板岩", "硅石", "长石",
    "粘土", "黏土", "高岭土", "膨润土", "硅藻土", "珍珠岩", "沸石", "蛭石",
    "玉石", "饰面", "水泥用", "熔剂用", "玻璃用", "陶瓷用", "砖瓦用",
    "磷矿", "石膏", "滑石", "重晶石", "方解石", "萤石", "盐矿", "硫铁",
]

# ---------------------------------------------------------------------------
# 上市公司公告噪声：巨潮是全文检索，会捞出大量与行业无关的常规治理类公告
# （股东会通知、独董声明、章程修订等），这些每天都有但不构成「行业事件」。
# ---------------------------------------------------------------------------
ANNOUNCE_NOISE = [
    "独立董事", "独立非执行董事", "候选人声明", "提名人声明", "征集投票权",
    "股东大会", "股东会", "临时股东会", "会议通知", "法律意见书", "公司章程",
    "章程修订", "募集资金", "闲置募集资金", "理财产品", "定期报告", "季度报告",
    "半年度报告", "年度报告摘要", "业绩说明会", "投资者关系活动记录",
    "接待日", "网上集体接待", "内幕信息", "知情人登记", "监事会", "职工代表",
    "辞职", "聘任", "审计机构", "会计师事务所", "变更证券简称", "股票交易异常",
    "异动", "停牌", "复牌公告", "权益分派", "分红", "回购注销", "股权激励",
    "限售股", "解禁", "质押", "冻结", "裁定", "诉讼进展", "问询函回复",
    "更正公告", "补充公告", "延期回复", "风险提示公告",
    # 再融资/发行类：数量大但属常规融资流程，不构成行业事件
    "董事会决议", "监事会决议", "董事会会议", "会议决议", "董事离任", "补选董事",
    "募集说明书", "保荐书", "上市公告书", "发行公告", "发行结果", "配股",
    "可转债赎回", "债券赎回", "跟踪评级", "评级报告", "审计报告",
]

# ============================================================================
# 源配置（2026-09-08 实测标定：每个源的链接模式都经真实抓取验证）
# 字段：key/name/list_url/kind/link_re/category/source/foreign/enabled
#   kind     : 'rss' 走 XML 解析；'html' 走正则提取 <a>
#   link_re  : 从列表页 HTML 中筛出「新闻详情链接」的正则（必含一个分组用于拼 URL）
#   foreign  : True 表示境外/英文源，AI 采编时须走翻译规范 + 可达性复检
# ============================================================================
SOURCES = [
    {
        "key": "smm",
        "name": "上海有色网 SMM",
        "list_url": "https://news.smm.cn/",
        "kind": "html",
        "link_re": r"/news/(\d+)",
        "href_tpl": "https://news.smm.cn/news/{g1}",
        "category": "行业动态",
        "source": "上海有色网",
        "foreign": False,
        "enabled": True,
        "max_items": 150,     # 主源：日更量大，放宽上限避免截断
        "note": "有色行业最对口，实测链接模式 /news/数字，内容为镍钴锂锌金等品种动态",
    },
    {
        "key": "metal",
        "name": "SMM 国际站（英文）",
        "list_url": "https://news.metal.com/en",
        "kind": "html",
        "link_re": r"/en/newscontent/(\d+-[A-Za-z0-9\-]+)",
        "href_tpl": "https://news.metal.com/en/newscontent/{g1}",
        "category": "国际矿业动态",
        "source": "SMM 国际站",
        "foreign": True,
        "enabled": True,
        "note": "中国团队运营、境内直连无墙的英文源，补国际视角且无需翻墙",
    },
    {
        "key": "geoglobal",
        "name": "全球矿产资源信息系统",
        "list_url": "https://geoglobal.mnr.gov.cn/",
        "kind": "html",
        # 2026-09-08 修复：旧正则只取文件名、丢掉子栏目目录（kydt/zhyw、kczygl/zcdt 等），
        # 拼出的 /zx/t2026xxxx_xxxxx.htm 全部 404。必须把「子栏目/年月/」整段一起捕获。
        "link_re": r"\./zx/((?:[\w\-]+/)+t\d{8}_\d+\.htm)",
        "href_tpl": "https://geoglobal.mnr.gov.cn/zx/{g1}",
        "category": "国际矿业动态",
        "source": "全球矿产资源信息系统",
        "foreign": False,
        "enabled": True,
        "note": "自然资源部旗下，国际矿业动态为主",
    },
    {
        "key": "mining",
        "name": "MINING.COM",
        "list_url": "https://www.mining.com/feed/",
        "kind": "rss",
        "category": "国际矿业动态",
        "source": "MINING.COM",
        "foreign": True,
        "enabled": True,
        "note": "实测唯一的真 RSS 源；需排除 /sponsored-content/ 广告路径",
    },
    {
        "key": "chinania",
        "name": "中国有色金属工业协会",
        "list_url": "https://www.chinania.org.cn/",
        "kind": "html",
        # 实测详情页为 5 段路径且以 数字.html 结尾（如 /html/a/b/2022/1207/154.html），
        # 栏目页是目录无 .html —— 用「数字.html 结尾」可精确区分详情与栏目。
        "link_re": r"(/html/[\w\-/]+?/\d+\.html?)",
        "href_tpl": "https://www.chinania.org.cn{g1}",
        "category": "行业动态",
        "source": "中国有色金属工业协会",
        "foreign": False,
        "enabled": True,
        # 2026-09-08 修复：长期「115 raw -> 0 kept」不是正则问题（正则能解出 115 条，
        # 逐层过滤后仍有 76 条存活），而是**协会更新频率低**：沿用新闻源的 2 天窗口时，
        # 一周一批的协会动态几乎全被日期过滤掉。放宽到 7 天后稳定出 15~22 条。
        "lookback": 7,
        "max_items": 60,
        "note": "首页混入 news.cn 时政链接，靠 NOISE_KEYWORDS 过滤；回看窗口 7 天",
    },
    {
        "key": "cnmn",
        "name": "中国有色金属报",
        "list_url": "https://www.cnmn.com.cn/",
        "kind": "html",
        "link_re": r"(/ShowNews1\.aspx\?id=\d+)",
        "href_tpl": "https://www.cnmn.com.cn{g1}",
        "category": "行业动态",
        "source": "中国有色金属报",
        "foreign": False,
        "enabled": True,
        "max_items": 150,     # 主源：实测当日 40 条即触顶旧上限，必须放宽
        "note": "首页混入时政，需过滤",
    },
    {
        "key": "cgs",
        "name": "中国地质调查局",
        "list_url": "https://www.cgs.gov.cn/",
        "kind": "html",
        "link_re": r"\./(ywdt/[\w/]+/t\d{8}_\d+\.html)",
        "href_tpl": "https://www.cgs.gov.cn/{g1}",
        "category": "找矿成果与勘查技术",
        "source": "中国地质调查局",
        "foreign": False,
        "enabled": True,
        "note": "首页多为时政/旧闻，靠相关性+噪声双重过滤",
    },
    # 2026-09-08 实测 502 不可达，暂禁用；恢复后把 enabled 改 True 即可
    {
        "key": "chinamining",
        "name": "中国矿业网",
        "list_url": "https://www.chinamining.org.cn/",
        "kind": "html",
        "link_re": r"(https?://www\.chinamining\.org\.cn/[\w\-/]+\.html?)",
        "href_tpl": "{g1}",
        "category": "行业动态",
        "source": "中国矿业网",
        "foreign": False,
        "enabled": False,
        "note": "2026-09-08 实测 Tunnel 502，暂不可抓",
    },
    {
        "key": "zgkyb",
        "name": "中国矿业报",
        "list_url": "https://www.zgkyb.com/",
        "kind": "html",
        "link_re": r"([\w\-/]*\d{4}/\w+\.html?)",
        "href_tpl": "https://www.zgkyb.com/{g1}",
        "category": "行业动态",
        "source": "中国矿业报",
        "foreign": False,
        "enabled": False,
        "note": "2026-09-08 实测 Tunnel 502，暂不可抓",
    },
    # -------------------------------------------------------------------
    # 2026-09-08 新增：补齐覆盖度核查发现的三类结构性缺口
    #   cninfo     → 上市公司公告（并购/投产/增减持等硬事件，此前 0 覆盖）
    #   mnr_news   → 自然资源部要闻播报（找矿突破、矿业大会等行业要闻）
    #   mnr_policy → 自然资源部通知公告（矿业权管理、矿政政策，此前只靠 AI 搜索）
    #   miningrights → 矿业权市场（出让/转让/结果公示，此前全手工维护）
    # -------------------------------------------------------------------
    {
        "key": "cninfo",
        "name": "巨潮资讯网 上市公司公告",
        "list_url": "http://www.cninfo.com.cn/new/hisAnnouncement/query",
        "kind": "cninfo",
        # 全文检索轮查词：既有行业词也有品种词，避免只搜「矿业」漏掉白银有色这类公司
        "search_keys": ["矿业", "有色", "金属", "稀土", "锂", "钴", "黄金", "白银",
                        "铜", "铝", "锌", "镍", "锡", "钨", "钼", "锑"],
        "category": "上市公司公告",
        "source": "巨潮资讯网",
        "foreign": False,
        "enabled": True,
        "max_items": 80,
        "lookback": 3,        # 公告是硬性时点，超过 3 天不算「当日事件」
        "extra_exclude": ANNOUNCE_NOISE,
        "note": "POST 接口返回 UTF-8（非 GBK）；详情页 http://static.cninfo.com.cn/<adjunctUrl>；"
                "全文检索噪声大，靠 extra_exclude 剔除治理类公告",
    },
    {
        "key": "mnr_news",
        "name": "自然资源部 要闻播报",
        "list_url": "https://www.mnr.gov.cn/dt/ywbb/",
        "kind": "html",
        "link_re": r"\./(\d{6}/t\d{8}_\d+\.html)",
        "href_tpl": "https://www.mnr.gov.cn/dt/ywbb/{g1}",
        "category": "政策与监管",
        "source": "自然资源部",
        "foreign": False,
        "enabled": True,
        "max_items": 80,
        "lookback": 7,        # 部委要闻更新慢，2 天窗口常颗粒无收
        "note": "列表页大量党建/海洋内容，靠相关性+噪声双过滤；矿业类如找矿突破、矿业大会可命中",
    },
    {
        "key": "mnr_policy",
        "name": "自然资源部 通知公告",
        "list_url": "https://www.mnr.gov.cn/gk/tzgg/",
        "kind": "html",
        # 实测列表页混链：既有 gi.mnr.gov.cn 绝对地址，也有 ./ 相对地址。
        # 用 {g0} 原样保留 href，再由 parse_html 的 urljoin 补全相对路径。
        "link_re": r"((?:https?://gi\.mnr\.gov\.cn/|\./)\d{6}/t\d{8}_\d+\.html)",
        "href_tpl": "{g0}",
        "category": "政策与监管",
        "source": "自然资源部",
        "foreign": False,
        "enabled": True,
        "max_items": 80,
        "lookback": 7,        # 政策文件不定期发布
        "note": "矿业权管理、矿山生态修复等矿政文件出自此栏（已实测 gi.mnr.gov.cn 子域过白名单）",
    },
    {
        "key": "miningrights",
        "name": "矿业权市场（自然资源部）",
        "list_url": "https://ky.mnr.gov.cn/",
        "kind": "html",
        # 首页聚合 8 类栏目（招拍挂出让/结果公示/协议出让/转让公示 × 探矿权/采矿权）
        "link_re": r"\./((?:kyqcrgg|jggs|xycrgs|zrgs)/[\w/]+/t\d{8}_\d+\.htm)",
        "href_tpl": "https://ky.mnr.gov.cn/{g1}",
        "category": "矿权市场",
        "source": "矿业权市场",
        "foreign": False,
        "enabled": True,
        "max_items": 80,
        "lookback": 14,       # 出让/转让是分批公示，与站内矿权区 14 天窗口对齐
        "extra_exclude": NONMETALLIC_KW,
        "note": "产出归 rightsSection（gen_today.strip_rights_html 会从主列表剥离 ky 链接）；"
                "首页约 7 成是砂石土/地热，靠 NONMETALLIC_KW 剔除",
    },
    # -------------------------------------------------------------------
    # 2026-09-08 P1：长江有色（ccmn.cn）+ 深交所公告直连（szse.cn）
    #   ccmn    → 现货视角的品种资讯，与 SMM 互补（SMM 偏咨询定价，长江有色偏现货成交）
    #   szse    → 深交所官方公告接口，作为巨潮(cninfo)的备份链路
    #             （cninfo 实测会 504；两者内容重叠，跨源去重会自动只留一条）
    # -------------------------------------------------------------------
    {
        "key": "cjys",
        "name": "长江有色网",
        "list_url": "https://www.ccmn.cn/",
        "kind": "html",
        # 详情页形如 /news/ZX003/202609/<32位hex>.html；只认 www.ccmn.cn 且必须带 .html，
        # 天然排除 mall.ccmn.cn（商城产品页）与各类二级广告域。
        "link_re": r"(https://www\.ccmn\.cn/news/[A-Z]+\d*/\d{6}/[0-9a-f]{16,}\.html)",
        "href_tpl": "{g1}",
        "category": "行业动态",
        "source": "长江有色网",
        "foreign": False,
        "enabled": True,
        "max_items": 60,
        # URL 只精确到 /202609/（无日），且 hash 头两位会被误读成「日」，必须强制回查详情页
        "date_from_detail": True,
        "force_date_from_detail": True,
        # 「XX日报/周报/月评」是报价专栏，无事件价值；商城词防止链接模式变动后漏进来
        "extra_exclude": ["日报", "周报", "月评",
                          "网上协商价格", "现货供应", "厂家供货", "批发"],
        "note": "与 SMM 互补的现货视角；列表页不显示日期，靠 date_from_detail 逐条回查",
    },
    {
        "key": "szse",
        "name": "深圳证券交易所 上市公司公告",
        "list_url": "http://www.szse.cn/api/disc/announcement/annList",
        "kind": "szse",
        "search_keys": ["矿业", "有色", "锂", "稀土", "铜", "铝", "黄金", "镍", "钴", "锌"],
        "category": "上市公司公告",
        "source": "深圳证券交易所",
        "foreign": False,
        "enabled": True,
        "max_items": 60,
        "lookback": 3,        # 与 cninfo 对齐：公告是硬性时点
        "extra_exclude": ANNOUNCE_NOISE,
        "note": "JSON POST 接口；PDF 直链 http://disc.szse.cn/download<attachPath>；"
                "与 cninfo 内容高度重叠，作备份链路，跨源去重只留一条",
    },
]

# ---------------------------------------------------------------------------
# 相关性：命中任一即视为有色金属行业相关（用于从混杂列表页里捞出目标）
# ---------------------------------------------------------------------------
METALS = ["铜", "铝", "铅", "锌", "镍", "锡", "金", "银", "稀土", "钨", "钼",
          "锑", "锂", "钴", "钛", "镁", "锰", "硅", "铂", "钯", "锆", "铍",
          "铟", "锗", "镓", "铌", "钽", "钒", "石墨"]
INDUSTRY_KW = [
    "有色", "金属", "矿业", "矿山", "矿产", "矿床", "矿权", "采矿", "选矿", "冶炼",
    "精炼", "电解", "勘查", "勘探", "找矿", "钻探", "见矿", "储量", "资源量",
    "地质", "矿", "冶炼厂", "精矿", "矿石", "品位", "产能", "产量", "复产", "投产",
    "进出口", "关税", "库存", "供需", "现货", "期货", "升水", "加工费",
]
# 英文关键词（2026-09-08 补）：境外源标题为英文，只有中文词表会让英文源 100% 被误滤。
# 实测 SMM 国际站 64 条 raw 曾全军覆没，即此原因。
METALS_EN = [
    "copper", "aluminium", "aluminum", "lead", "zinc", "nickel", "tin", "gold",
    "silver", "lithium", "cobalt", "tungsten", "molybdenum", "antimony", "titanium",
    "magnesium", "manganese", "silicon", "platinum", "palladium", "zirconium",
    "indium", "germanium", "gallium", "niobium", "tantalum", "vanadium", "graphite",
    "rare earth", "rare-earth", "bauxite", "alumina", "cathode", "anode",
    # 注：刻意不收 "REE" 等超短缩写 —— 子串会误命中 agreement/free/three。
    # 所有英文词一律走词边界匹配（见 _RE_METALS_EN）。
]
INDUSTRY_KW_EN = [
    "mining", "mine", "miner", "mines", "ore", "mineral", "smelter", "smelting",
    "refinery", "refining", "exploration", "drilling", "deposit", "reserve",
    "resource", "output", "production", "supply", "demand", "inventory", "stock",
    "stockpile", "export", "import", "tariff", "concentrate", "grade", "assay",
    "metal", "metals", "nonferrous", "non-ferrous", "critical minerals",
    "shipment", "premium", "discount", "surplus", "deficit", "smelter",
]
# 英文金属名 → 中文标签（保证入库 tags 与站内中文体系一致）
METAL_EN2CN = {
    "copper": "铜", "aluminium": "铝", "aluminum": "铝", "lead": "铅", "zinc": "锌",
    "nickel": "镍", "tin": "锡", "gold": "金", "silver": "银", "lithium": "锂",
    "cobalt": "钴", "tungsten": "钨", "molybdenum": "钼", "antimony": "锑",
    "titanium": "钛", "magnesium": "镁", "manganese": "锰", "silicon": "硅",
    "platinum": "铂", "palladium": "钯", "zirconium": "锆", "indium": "铟",
    "germanium": "锗", "gallium": "镓", "niobium": "铌", "tantalum": "钽",
    "vanadium": "钒", "graphite": "石墨", "rare earth": "稀土", "rare-earth": "稀土",
    "bauxite": "铝", "alumina": "铝",
}


def _compile_words(words):
    """英文关键词一律转为「词边界」正则。
    2026-09-08 修复：子串匹配会把 agreement→ree(稀土)、listing→tin(锡)、
    leading→lead(铅)、before/core→ore(矿石) 全部误判。加 \\b 后可精确命中单词。"""
    return [re.compile(r"\b" + re.escape(w) + r"\b", re.I) for w in words]


_RE_METALS_EN = _compile_words(METALS_EN)
_RE_INDUSTRY_EN = _compile_words(INDUSTRY_KW_EN)
# ---------------------------------------------------------------------------
# 金融噪声：单看「银」会误判成「银行」，单看「期货」会误判成「纳指期货」。
# 故用组合判断——命中金融主体词 **且** 不含其他明确金属词时，才判为噪声。
# 这样「央行连续增持黄金」保留（无"银行"二字且含"金"），「财政部注资银行、险企」剔除。
# ---------------------------------------------------------------------------
FIN_NOISE = ["银行", "险企", "券商", "纳指", "道指", "美股", "港股", "A股",
             "股指", "理财", "信托", "债券", "银保", "银监", "证券", "IPO",
             "涨停", "跌停", "市值", "市盈率"]
# 这些金属词出现时，即使有金融词也倾向于是真行业新闻
_STRONG_METALS = [m for m in METALS if m not in ("银", "金")]


def is_fin_noise(title):
    if not any(k in title for k in FIN_NOISE):
        return False
    return not any(m in title for m in _STRONG_METALS)


# ---------------------------------------------------------------------------
# 噪声：命中任一即丢弃（列表页实测混入大量时政/服务类内容）
# ---------------------------------------------------------------------------
NOISE_KEYWORDS = [
    "习近平", "总书记", "主席", "总理", "委员长", "政协", "人大", "党中央", "国务院常务",
    "党建", "党史", "主题教育", "巡视", "纪检", "廉政", "任命", "免去", "同志",
    "招聘", "报名", "招生", "考试", "培训通知", "缴费", "公示（人事）",
    "天气预报", "彩票", "养生", "讣告", "悼", "开幕致辞", "贺信", "慰问",
    "登录", "注册", "订阅", "下载 APP", "隐私政策", "版权声明", "联系我们",
]
# 境外源广告/赞助路径（与 source_whitelist.FOREIGN_SPONSORED_PATTERNS 对应）
SPONSOR_PAT = re.compile(
    r"mining\.com/(sponsored-content|joint-venture)/|servedbyadbutler\.com", re.I)

# ---------------------------------------------------------------------------
# 黑色/能源排除：站内定位是「聚焦有色金属 … 排除：煤炭、石油、天然气、钢铁、铁矿」
# （见 index.html 底部）。境外源尤其容易混入 iron ore / coal，必须显式排除，
# 否则 INDUSTRY_KW_EN 里的 "ore"/"mine" 会把铁矿新闻当有色捞进来。
# ---------------------------------------------------------------------------
EXCLUDE_KW = ["铁矿", "煤炭", "钢铁", "石油", "天然气", "原油", "焦炭", "炼铁", "高炉"]
EXCLUDE_KW_EN = ["iron ore", "iron-ore", "iron", "coal", "steel", "crude oil",
                 "natural gas", "coking coal", "metallurgical coal", "pellet"]
_RE_EXCLUDE_EN = _compile_words(EXCLUDE_KW_EN)   # 须在 EXCLUDE_KW_EN 定义之后


# ============================================================================
# 网络层（与 fetch_ma.py 同风格：标准库 + 免验证 ssl + gzip + 多编码回退）
# ============================================================================
def http_get(url, timeout=TIMEOUT, retries=2):
    last = ""
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "gzip",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                for enc in ("utf-8", "gbk", "gb18030"):
                    try:
                        return raw.decode(enc)
                    except Exception:
                        continue
                return raw.decode("utf-8", "ignore")
        except Exception as e:
            last = str(e)
            if i < retries:
                continue
    return "__ERR__" + last


def http_post(url, data, timeout=TIMEOUT, retries=2, referer=""):
    """POST 表单（巨潮资讯网公告检索接口用）。返回文本；失败返回 '__ERR__...'"""
    last = ""
    for i in range(retries + 1):
        try:
            body = (urllib.parse.urlencode(data).encode("utf-8")
                    if isinstance(data, dict) else str(data).encode("utf-8"))
            headers = {
                "User-Agent": UA,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Encoding": "gzip",
                "X-Requested-With": "XMLHttpRequest",
            }
            if referer:
                headers["Referer"] = referer
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                for enc in ("utf-8", "gbk", "gb18030"):
                    try:
                        return raw.decode(enc)
                    except Exception:
                        continue
                return raw.decode("utf-8", "ignore")
        except Exception as e:
            last = str(e)
            if i < retries:
                continue
    return "__ERR__" + last


def clean_text(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    s = htmllib.unescape(s)
    s = s.replace("\u3000", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


# ============================================================================
# 解析层
# ============================================================================
def parse_rss(xml_text, cfg):
    """解析 RSS/Atom，返回 [{title,url,date,summary}]"""
    out = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    nodes = root.findall(".//item")
    if not nodes:
        nodes = root.findall(".//atom:entry", ns)
    for it in nodes:
        def sub(tag, ns_tag=None):
            # 2026-09-08 修复：原写法 `it.find(tag) if ns_tag is None else it.find(ns_tag, ns)`
            # 对 RSS 2.0 会直接跳去 Atom 分支导致全部取空（mining.com 曾解析出 0 条）。
            # 正确顺序：先普通 tag，取不到再退回 Atom 命名空间。
            el = it.find(tag)
            if el is None and ns_tag:
                el = it.find(ns_tag, ns)
            return (el.text or "").strip() if el is not None and el.text else ""
        title = clean_text(sub("title", "atom:title"))
        link = sub("link", "atom:link")
        if not link:
            el = it.find("link")
            if el is not None:
                link = (el.get("href") or "").strip()
            if not link:
                el = it.find("atom:link", ns)
                if el is not None:
                    link = (el.get("href") or "").strip()
        # Atom 的 summary 常带 HTML
        summary = clean_text(sub("description", "atom:summary"))[:300]
        date = sub("pubDate", "atom:updated") or sub("pubDate") or sub("atom:updated", "atom:updated")
        if title and link:
            out.append({"title": title, "url": link, "date": date, "summary": summary})
    return out


def parse_html(html_text, cfg):
    """从列表页正则提取 链接+标题，返回 [{title,url,date,summary}]"""
    out = []
    link_re = re.compile(cfg["link_re"])
    tpl = cfg.get("href_tpl", "{g1}")
    base = cfg["list_url"]
    # 逐个 <a> 匹配，避免跨标签误配
    for m in re.finditer(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
                         html_text, re.S | re.I):
        href, inner = m.group(1), m.group(2)
        title = clean_text(inner)
        if len(title) < 8:
            continue
        lm = link_re.search(href)
        if not lm:
            continue
        try:
            url = tpl.format(g1=lm.group(1), g0=lm.group(0))
        except Exception:
            url = urllib.parse.urljoin(base, href)
        if not url.startswith("http"):
            url = urllib.parse.urljoin(base, url)
        out.append({"title": title, "url": url, "date": "", "summary": ""})
    return out


def parse_cninfo(cfg, report_date, days):
    """巨潮资讯网公告检索（kind='cninfo'）。

    实测要点（2026-09-08）：
    - 是 POST 表单接口，非静态页；返回 **UTF-8**（按 GBK 解会整屏乱码）。
    - 详情页 URL = http://static.cninfo.com.cn/ + adjunctUrl（形如 finalpage/2026-09-08/1225552354.PDF）。
    - 公告日期取 announcementTime（毫秒时间戳），不能靠 URL 猜。
    - 标题里带 <em> 高亮标签，必须先剥标签再 clean_text。
    """
    start = (datetime.date.fromisoformat(report_date)
             - datetime.timedelta(days=max(0, days - 1))).isoformat()
    referer = "http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice"
    out, seen = [], set()
    for kw in cfg.get("search_keys", []):
        payload = {
            "pageNum": 1, "pageSize": 30, "column": "szse", "tabName": "fulltext",
            "searchkey": kw, "seDate": "%s~%s" % (start, report_date),
            "isHLtitle": "true",
        }
        txt = http_post(cfg["list_url"], payload, referer=referer)
        if txt.startswith("__ERR__"):
            continue
        try:
            j = json.loads(txt)
        except Exception:
            continue
        for a in (j.get("announcements") or []):
            aid = str(a.get("announcementId") or "")
            if not aid or aid in seen:
                continue
            seen.add(aid)
            title = clean_text(re.sub(r"<[^>]+>", "", a.get("announcementTitle") or ""))
            if not title:
                continue
            ts = a.get("announcementTime")
            try:
                d = datetime.datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d")
            except Exception:
                d = report_date
            adjunct = (a.get("adjunctUrl") or "").lstrip("/")
            if not adjunct:
                continue
            url = "http://static.cninfo.com.cn/" + adjunct
            secname = clean_text(re.sub(r"<[^>]+>", "", a.get("secName") or ""))
            code = a.get("secCode") or ""
            out.append({
                "title": ("%s：%s" % (secname, title)) if secname else title,
                "url": url,
                "date": d,
                "summary": "%s（%s）在上交所/深交所披露：%s" % (secname, code, title),
            })
    return out


def parse_szse(cfg, report_date, days):
    """深交所上市公司公告检索（kind='szse'）。

    实测要点（2026-09-08）：
    - 与巨潮不同：这是 **JSON body** 接口（Content-Type: application/json），
      不是 x-www-form-urlencoded，直接复用 http_post 会被拒。
    - 日期区间用 seDate: [起, 止] 数组，不是字符串区间。
    - publishTime 已是「YYYY-MM-DD HH:MM:SS」，直接取前 10 位即可。
    - 附件是 PDF：http://disc.szse.cn/download + attachPath。
    """
    start = (datetime.date.fromisoformat(report_date)
             - datetime.timedelta(days=max(0, days - 1))).isoformat()
    referer = "http://www.szse.cn/disclosure/listed/fixed/index.html"
    out, seen = [], set()
    for kw in cfg.get("search_keys", []):
        payload = json.dumps({
            "seDate": [start, report_date], "stock": [],
            "channelCode": ["listedNotice_disc"],
            "pageSize": 30, "pageNum": 1, "searchKey": [kw],
        }).encode("utf-8")
        txt = _post_json(cfg["list_url"], payload, referer=referer)
        if not txt:
            continue
        try:
            j = json.loads(txt)
        except Exception:
            continue
        for a in (j.get("data") or []):
            title = clean_text(a.get("title") or "")
            if not title or len(title) < 8:
                continue
            attach = (a.get("attachPath") or "").lstrip("/")
            if not attach:
                continue
            url = "http://disc.szse.cn/download/" + attach
            if url in seen:
                continue
            seen.add(url)
            d = (a.get("publishTime") or "")[:10]
            names = a.get("secName") or []
            codes = a.get("secCode") or []
            secname = clean_text(names[0]) if names else ""
            code = codes[0] if codes else ""
            out.append({
                "title": title,
                "url": url,
                "date": d,
                "summary": "%s（%s）在深交所披露：%s" % (secname, code, title)
                           if secname else title,
            })
    return out


def _post_json(url, payload, referer="", timeout=TIMEOUT, retries=1):
    """application/json POST（深交所接口专用）。失败返回 ''。"""
    for _ in range(retries + 1):
        try:
            headers = {
                "User-Agent": UA,
                "Content-Type": "application/json; charset=UTF-8",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip",
                "Referer": referer,
            }
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                return raw.decode("utf-8", "ignore")
        except Exception:
            continue
    return ""


# ============================================================================
# 过滤层
# ============================================================================
def is_allowed_domain(url):
    """复用 source_whitelist 的白名单，确保爬虫绝不会引入非授权源。"""
    try:
        sys.path.insert(0, BASE_DIR)
        import source_whitelist as sw
        return sw.is_allowed(url)
    except Exception:
        return False


# 金融语境词：标题里的「金」「银」常来自这些词而非贵金属，是典型的假阳性源。
# 实测案例：「住房城乡建设部 自然资源部 金融监管总局关于完善商品住房销售制度的通知」
# 因「金融」含「金」被判成黄金相关而混入政策源（与「银行/银」同源问题）。
FIN_CONTEXT = ["金融", "资金", "现金", "保证金", "融资", "基金", "银行", "证券",
               "理财", "公积金", "养老金", "存款", "信贷", "期货公司", "信托"]


def _strip_fin(t):
    for w in FIN_CONTEXT:
        t = t.replace(w, "")
    return t


def is_relevant(title):
    """中英文双语判定：中文子串匹配，英文词边界正则匹配。

    特例：「金」「银」是单字，在金融语境（金融/银行/资金…）里属假阳性，
    故单字命中要先把金融词剥掉再判，避免把住房销售制度当成黄金新闻。
    """
    if any(m in title for m in METALS if m not in ("金", "银")):
        return True
    if any(k in title for k in INDUSTRY_KW):
        return True
    if any(p.search(title) for p in _RE_METALS_EN):
        return True
    if any(p.search(title) for p in _RE_INDUSTRY_EN):
        return True
    if any(x in title for x in ("黄金", "白银", "金价", "银价", "金银")):
        return True
    t2 = _strip_fin(title or "")
    return ("金" in t2) or ("银" in t2)


def extract_tags(title):
    """标签提取：中文金属词 + 英文金属词映射为中文，保证与站内 tag 体系一致。"""
    tags = {m for m in METALS if m in title}
    for en, cn in METAL_EN2CN.items():
        if re.search(r"\b" + re.escape(en) + r"\b", title or "", re.I):
            tags.add(cn)
    return sorted(tags) or ["有色"]


def is_noise(title, url):
    if SPONSOR_PAT.search(url or ""):
        return True
    for k in NOISE_KEYWORDS:
        if k in title:
            return True
    if is_fin_noise(title):
        return True
    # 黑色/能源排除（中英文；英文走词边界，避免 iron 命中 ironic 之类）
    for k in EXCLUDE_KW:
        if k in title:
            return True
    if any(p.search(title) for p in _RE_EXCLUDE_EN):
        return True
    # 境外源的赞助内容标题特征
    if re.search(r"^\s*(Sponsored|AD|Advertisement)\b", title, re.I):
        return True
    return False


def extract_date(url, rss_date, fallback, text=""):
    """日期提取优先级：RSS pubDate > URL 里的 8 位日期 > 正文日期 > fallback"""
    if rss_date:
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
            try:
                dt = datetime.datetime.strptime(rss_date.strip()[:31], fmt)
                if dt.tzinfo:
                    dt = dt.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
                return dt.strftime("%Y-%m-%d")
            except Exception:
                continue
    m = re.search(r"(20\d{2})[-/]?(0[1-9]|1[0-2])[-/]?(0[1-9]|[12]\d|3[01])", url or "")
    if m:
        return "%s-%s-%s" % (m.group(1), m.group(2), m.group(3))
    m = re.search(r"/t(20\d{6})", url or "")
    if m:
        d = m.group(1)
        return "%s-%s-%s" % (d[:4], d[4:6], d[6:8])
    blob = text or ""
    m = re.search(r"(20\d{2})[-年/](\d{1,2})[-月/](\d{1,2})", blob)
    if m:
        return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
    return fallback


def _date_from_detail(url, limit=200):
    """URL 里无确切日期时，回详情页取发布日期（长江有色 URL 只到 /202609/）。

    只取正文前 4000 字符里的第一个 YYYY-MM-DD / YYYY年M月D日，
    避免把页脚版权年份等噪声当成发布日。
    """
    h = http_get(url, timeout=15, retries=1)
    if h.startswith("__ERR__"):
        return ""
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h)[:limit * 20]
    m = re.search(r"(20\d{2})[-年/](\d{1,2})[-月/](\d{1,2})", h)
    if not m:
        return ""
    try:
        return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
    except Exception:
        return ""


def norm_title(t):
    """标题归一：去标点空白，用于跨源去重（同一事件多源报道只留一条）"""
    return re.sub(r"[\s\W_]+", "", t or "").lower()


def fetch_detail_summary(url, limit=180):
    """抓正文页补摘要（慢，默认关闭）"""
    h = http_get(url, timeout=15, retries=1)
    if h.startswith("__ERR__"):
        return ""
    h = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", h)
    # 优先取 meta description
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', h, re.I)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']', h, re.I)
    if m and len(clean_text(m.group(1))) > 20:
        return clean_text(m.group(1))[:limit]
    body = clean_text(h)
    return body[:limit]


# ============================================================================
# 主流程
# ============================================================================
def run_source(cfg, report_date, days, use_detail):
    if not cfg.get("enabled"):
        return [], "disabled"
    # 源级回看天数覆盖：矿权/政策类更新频率低（几天一批），沿用新闻源的 2 天窗口会全被
    # 日期过滤掉——实测 miningrights 用 3 天窗口只剩 1 条，放宽到 14 天才有 18 条。
    days = int(cfg.get("lookback", days))
    if cfg["kind"] == "cninfo":
        raw = parse_cninfo(cfg, report_date, days)
    elif cfg["kind"] == "szse":
        raw = parse_szse(cfg, report_date, days)
    else:
        html_text = http_get(cfg["list_url"])
        if html_text.startswith("__ERR__"):
            return [], "fetch-fail: " + html_text[7:][:60]
        if cfg["kind"] == "rss":
            raw = parse_rss(html_text, cfg)
        else:
            raw = parse_html(html_text, cfg)

    cutoff = (datetime.date.fromisoformat(report_date)
              - datetime.timedelta(days=max(0, days - 1))).isoformat()
    limit = int(cfg.get("max_items", MAX_PER_SOURCE))
    extra_exclude = cfg.get("extra_exclude") or []
    items, seen_url, seen_title = [], set(), set()
    dropped_extra = 0
    for r in raw:
        if len(items) >= limit:
            break
        url = r["url"].split("#")[0].rstrip("/")
        title = clean_text(r["title"])
        if not title or len(title) < 8:
            continue
        if not is_allowed_domain(url):
            continue
        if is_noise(title, url):
            continue
        if not is_relevant(title):
            continue
        # 源级附加排除（如矿权源的砂石土类、巨潮源的治理类公告）
        if any(k in title for k in extra_exclude):
            dropped_extra += 1
            continue
        nt = norm_title(title)
        if url in seen_url or nt in seen_title:
            continue
        seen_url.add(url)
        seen_title.add(nt)

        # 日期：优先 URL/RSS 里的确切日期；URL 无日期、或源声明「URL 日期不可信」
        # 时回详情页取。长江有色的 URL 形如 /news/ZX003/202609/<hash>.html，hash
        # 以 09/16 开头时会被 extract_date 误读成 09-09 / 09-16 这类**未来日期**，
        # 所以该源必须强制回查详情页，不能信 URL。
        d = ""
        if not cfg.get("force_date_from_detail"):
            d = extract_date(url, r.get("date", ""), "", title)
        if (not d or cfg.get("force_date_from_detail")) and cfg.get("date_from_detail"):
            d = _date_from_detail(url) or d
        if not d:
            d = report_date
        if cfg.get("force_date_from_detail") and d > report_date:
            continue        # 未来日期必是 URL 误读，宁可丢也不收
        if d < cutoff:
            continue
        summary = r.get("summary") or ""
        if use_detail and not summary and len(items) < DETAIL_LIMIT:
            summary = fetch_detail_summary(url)
        items.append({
            "id": hashlib.md5(url.encode("utf-8")).hexdigest()[:12],
            "url": url,
            "title": title,
            "source": cfg["source"],
            "orig_date": d[5:],
            "orig_date_full": d,
            "report_date": report_date,
            "category": cfg["category"],
            "is_new": d == report_date,
            "summary": summary or title,
            "embed": "ok",
            "tags": extract_tags(title),
            "first_seen": report_date,
            "last_seen": report_date,
            "foreign": bool(cfg.get("foreign")),
            "fetch_src": cfg["key"],
        })
    note = "ok(%d raw -> %d kept" % (len(raw), len(items))
    if dropped_extra:
        note += ", 源级排除 %d" % dropped_extra
    if len(items) >= limit:
        note += ", 触顶 %d" % limit
    return items, note + ")"


def merge_into_month(items, report_date):
    """并入 data/news_YYYY-MM.json（与 fetch_ma.py 的入库方式一致，幂等）"""
    month = report_date[:7]
    path = os.path.join(DATA_DIR, "news_%s.json" % month)
    data = {"month": month, "updated_at": "", "count": 0, "news": []}
    if os.path.exists(path):
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            pass
    existing = {n.get("url"): n for n in data.get("news", [])}
    added = 0
    for it in items:
        if it["url"] in existing:
            existing[it["url"]]["last_seen"] = report_date
            continue
        data.setdefault("news", []).append(it)
        existing[it["url"]] = it
        added += 1
    data["count"] = len(data.get("news", []))
    data["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path, added, data["count"]


def main():
    ap = argparse.ArgumentParser(description="有色金属行业新闻自动爬虫（零依赖）")
    ap.add_argument("--report-date", default=datetime.date.today().isoformat(),
                    help="报告日期 YYYY-MM-DD，默认今天")
    ap.add_argument("--days", type=int, default=1, help="回看天数，默认 1（只要当天）")
    ap.add_argument("--source", default="", help="只跑指定源 key，逗号分隔")
    ap.add_argument("--merge", action="store_true", help="抓完并入 data/news_YYYY-MM.json")
    ap.add_argument("--fetch-detail", action="store_true",
                    help="逐条抓正文补摘要（慢，默认关）")
    ap.add_argument("--dry-run", action="store_true", help="只打印不落盘")
    ap.add_argument("--list-sources", action="store_true", help="列出源配置")
    args = ap.parse_args()

    if args.list_sources:
        print("%-12s %-22s %-8s %-8s %s" % ("KEY", "名称", "类型", "启用", "境外"))
        for c in SOURCES:
            print("%-12s %-22s %-8s %-8s %s" % (
                c["key"], c["name"], c["kind"],
                "✔" if c.get("enabled") else "✘",
                "是" if c.get("foreign") else "否"))
        return

    keys = {k.strip() for k in args.source.split(",") if k.strip()}
    targets = [c for c in SOURCES if not keys or c["key"] in keys]

    print("=" * 72)
    print("fetch_news.py | 报告日期 %s | 回看 %d 天 | 源 %d 个"
          % (args.report_date, args.days, len(targets)))
    print("=" * 72)

    all_items, report = [], []
    for cfg in targets:
        items, status = run_source(cfg, args.report_date, args.days, args.fetch_detail)
        report.append((cfg["key"], cfg["name"], len(items), status))
        all_items.extend(items)

    print()
    print("%-12s %-22s %-5s %s" % ("KEY", "名称", "条数", "状态"))
    for k, n, c, s in report:
        print("%-12s %-22s %-5d %s" % (k, n, c, s))
    print("-" * 72)
    print("候选合计：%d 条（境外 %d 条）"
          % (len(all_items), sum(1 for i in all_items if i.get("foreign"))))

    if args.dry_run or not all_items:
        for i in all_items[:25]:
            print("  [%s|%s] %s" % (i["fetch_src"], i["orig_date"], i["title"][:52]))
            print("      %s" % i["url"][:96])
        if not all_items:
            print("  （无候选：可能是当天确实无新内容，或源结构变化需调整 link_re）")
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    cand_path = os.path.join(DATA_DIR, "news_candidates_%s.json" % args.report_date)
    with open(cand_path, "w", encoding="utf-8") as f:
        json.dump({"report_date": args.report_date, "count": len(all_items),
                   "news": all_items}, f, ensure_ascii=False, indent=2)
    print()
    print("候选池已写入：%s" % cand_path)
    print("提示：AI 采编时读取该候选池挑选，境外条目（foreign=true）须走英文翻译规范。")

    if args.merge:
        path, added, total = merge_into_month(all_items, args.report_date)
        print("已并入月度库：%s（新增 %d，总计 %d）" % (path, added, total))

    print()
    print("候选条目预览（前 25 条）：")
    for i in all_items[:25]:
        flag = "🌍" if i.get("foreign") else "  "
        print("  %s[%s] %s | %s" % (flag, i["orig_date"], i["title"][:50], i["source"]))
        print("        %s" % i["url"][:92])


if __name__ == "__main__":
    main()
