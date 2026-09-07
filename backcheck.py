#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""次日回溯漏稿检测（2026-09-08 新增）

思路
----
当天采集难免有遗漏，而**次日**的行业综述（SMM 日评、有色报要闻、协会简讯等）
会把前一天的重要事件重述一遍。用次日综述「反查」已入库条目，就能把漏掉的事件找回来。

做法
----
1. 汇总已入库：data/news_YYYY-MM.json + mining_news.json 的**全量**条目
   ⚠ 不要用「目标日」过滤：mining_news.json 的 report_date 是**报告生成日**，
   事件真实日期在 orig_date_full，两者相差数天。按目标日过滤会得到 0~1 条基准，
   导致全部句子误判为漏稿（2026-09-08 踩坑）。
2. 抓次日综述：抓次日候选，挑出「日评/早报/收评/每日」类；
   **排除月评/周评/年报/回顾展望**——它们讲的是上月行情，不是昨日事件。
3. 抓正文拆事件句：按句切分，只保留有色金属相关**且含具体实体**的句子
   （企业名/矿山名/带单位数字），滤掉「下游需求萎靡」这类泛泛而谈的分析句。
4. 相似度比对：字符 2-gram Jaccard，与已入库标题/摘要的最大相似度低于阈值即疑似漏稿
5. 输出 reports：data/backcheck_YYYY-MM-DD.md（供人工补录，不自动入库）

用法
----
    python backcheck.py                      # 回溯昨天
    python backcheck.py --date 2026-09-07    # 回溯指定日
    python backcheck.py --top 30             # 最多列多少条疑似漏稿
    python backcheck.py --threshold 0.35     # 放宽/收紧判定阈值
    python backcheck.py --loose              # 放宽：不要求含具体实体（含纯行情句）

注意
----
- 只做「提示」，绝不自动写库——漏稿清单要人工核实后才补录（信源真实性底线）。
- 综述源正文抓取较慢，默认最多抓 8 篇（可用 --max-docs 调整）。
"""
import argparse
import datetime
import json
import os
import re

import fetch_news as fn

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# 综述/盘点类标题特征：只有这类文章才会回述前一天事件
REVIEW_KW = ["日评", "日报", "早报", "早餐", "晨报", "盘点", "综述",
             "周报", "要闻", "简讯", "午评", "收评", "快讯汇总",
             "每日", "今日", "一周", "隔夜", "外盘", "收盘"]
# ⚠ 周期性综述排除词：月评/周评/年报讲的是上月行情，不是昨日事件。
#   2026-09-08 踩坑：「【钛月评】8月钛市场回顾及后市展望」被当成日评，
#   里面全是上月价格描述句，导致 190 句全部误判为漏稿。
PERIODIC_KW = ["月评", "月报", "月度", "周评", "周报", "季报", "季度", "年报",
               "年度", "上半年", "下半年", "一季度", "二季度", "三季度", "四季度",
               "回顾", "展望", "十四五", "半年报"]
# 综述源：优先信息密度高的
REVIEW_SOURCES = ["smm", "cnmn", "chinania", "metal"]

THRESHOLD = 0.35      # 低于该相似度即疑似漏稿（0.22 实测误报率 100%）
MAX_DOCS = 8          # 最多抓几篇综述正文
MIN_REVIEW_DOCS = 4   # 日评类少于此数就从候选池补足，避免样本太小
BODY_LIMIT = 12000    # 正文截取长度

# 「具体实体」判定：没有实体的一律是分析/行情感慨，不是可补录的事件
RE_ENTITY_ORG = re.compile(
    # 完整公司名（最稳）
    r"[一-龥]{2,12}(?:股份有限公司|集团有限公司|有限责任公司)|"
    # 矿业企业常见字号后缀。⚠ 刻意不含泛词「金属|有色|资源|股份|集团」：
    # 「基本金属」「有色金属」「矿产资源」会把行情描述句误判成企业名
    # （2026-09-08 踩坑：「内盘基本金属普涨」被当成企业动态）。
    r"[一-龥A-Za-z]{2,10}(?:矿业|铜业|铝业|锌业|铅业|镍业|锡业|锂业|钴业|"
    r"钛业|镁业|锑业|钨业|钼业|金属集团|有色集团|Group|Mining|Metals)")
# ⚠ 刻意不含「黄金|稀土|矿山|资源」等泛词：「这一轮黄金市场」「高需求稀土产品」
# 「该矿山」「矿产资源」都会把它们误判成企业名（2026-09-08 踩坑）。
RE_ENTITY_NUM = re.compile(
    r"\d+(?:\.\d+)?\s*(?:万吨|吨|亿元|万元|亿美元|万美元|元/吨|美元/吨|%|"
    r"百分点|千吨|盎司|兆瓦)")
RE_ENTITY_PLACE = re.compile(
    r"[一-龥]{2,8}(?:省|市|自治区|矿区|县|州|盟)|"
    r"(?:青海|西藏|新疆|内蒙|云南|江西|甘肃|四川|湖南|广西|河南|山东|"
    r"陕西|安徽|福建|贵州|黑龙江|辽宁|吉林)")

# 事件动词：含这些词的句子才可能是「可补录的事件」。
# 纯行情句（「沪锌以1.31%的涨幅领涨」）既无企业名也无事件动词 → 丢弃，
# 否则 SMM 日评里 90% 的报价句都会变成「疑似漏稿」，清单毫无价值。
EVENT_VERB = ["投产", "复产", "复工", "停产", "减产", "检修", "开工", "竣工",
              "获批", "核准", "批复", "通过", "签署", "签约", "签订", "收购",
              "并购", "转让", "中标", "挂牌", "出让", "拍卖", "环评", "公示",
              "公告", "达产", "扩产", "新建", "投资", "增资", "上市", "IPO",
              "探获", "发现", "增储", "资源整合", "合作协议", "战略合作",
              "投产仪式", "点火", "试车", "出矿", "见矿", "封存", "关停",
              "启动", "发布", "召开", "落地", "交割", "重组", "破产", "拍卖成交",
              "增持", "减持", "回购", "定增", "募资", "竞得", "摘牌", "注销",
              "设立", "成立", "回运", "稳产", "达产"]
# 纯行情特征
QUOTE_NOISE = ["主力", "主连", "收盘", "涨幅", "跌幅", "涨逾", "跌逾", "上涨",
               "下跌", "报价", "结算价", "持仓", "仓单", "成交", "库存", "升水",
               "贴水", "比价", "盘面", "期货", "现货升水"]

# 非新闻文本：投资者互动问答、推广引导、编号列表
RE_QNA = re.compile(r"(?:^\d+\s*[、.．]|\?|？|贵司|请问|您好|感谢您|如何|"
                    r"点击查看|订购查看|扫码|关注我们|免责声明|风险提示)")


# ---------------------------------------------------------------------------
def load_existing(date):
    """汇总已入库条目。

    ⚠ 刻意**不按 date 过滤**：mining_news.json 的 report_date 是报告生成日
    （全库同一个值），事件真实日期在 orig_date_full，两者可差数天。若按目标日
    过滤只会有 0~1 条基准，导致次日综述里所有句子都被判成漏稿。
    这里取「当月月度库 + mining_news.json」全量做比对基准。
    """
    items = []
    path_month = os.path.join(DATA_DIR, "news_%s.json" % date[:7])
    if os.path.exists(path_month):
        try:
            d = json.load(open(path_month, encoding="utf-8"))
            items += list(d.get("news", []))
        except Exception:
            pass
    p = os.path.join(BASE_DIR, "mining_news.json")
    if os.path.exists(p):
        try:
            d = json.load(open(p, encoding="utf-8"))
            src = d.get("news") if isinstance(d, dict) else d
            items += list(src or [])
        except Exception:
            pass
    # 去重（同 URL 只留一条）
    seen, out = set(), []
    for n in items:
        u = n.get("url") or ""
        if u in seen:
            continue
        seen.add(u)
        out.append(n)
    return out


# 正文容器候选（按优先级）。⚠ 非贪婪 (.*?)</div> 很容易只吃到 89 字节的
# 外层装饰 div（2026-09-08 在 news.smm.cn 踩坑：命中 <div class="left">）。
# 因此每条候选都要过「清洗后长度达标」这一关，全部不达标才退回整页。
BODY_PATTERNS = [
    r'(?is)<div[^>]*class="[^"]*sjys-content[^"]*"[^>]*>(.*?)</div>\s*</div>',
    r'(?is)<div[^>]*id="[^"]*(?:zoom|Zoom|content|Content|article|articleCon)[^"]*"[^>]*>(.*?)</div>\s*</div>',
    r'(?is)<div[^>]*class="[^"]*(?:article-content|articleContent|conTxt|TRS_Editor|'
    r'detail-content|news-content|post-content|rich-text)[^"]*"[^>]*>(.*?)</div>\s*</div>',
    r'(?is)<article[^>]*>(.*?)</article>',
]
MIN_BODY_LEN = 300     # 容器提取低于该字数视为失败


def fetch_body(url, limit=BODY_LIMIT):
    """抓正文纯文本（综述类文章需要全文，fetch_detail_summary 的 180 字不够）"""
    h = fn.http_get(url, timeout=20, retries=1)
    if h.startswith("__ERR__"):
        return ""
    h = re.sub(r"(?is)<(script|style|nav|footer|header|form)[^>]*>.*?</\1>", " ", h)
    for pat in BODY_PATTERNS:
        for m in re.finditer(pat, h):
            txt = fn.clean_text(m.group(1))
            if len(txt) >= MIN_BODY_LEN:
                return txt[:limit]
    # 容器提取失败 → 退回整页（导航噪声由后续 is_relevant / has_entity 过滤）
    return fn.clean_text(h)[:limit]


SENT_SPLIT = re.compile(r"[。！？；\n]+")


def has_entity(s):
    """句内是否含「具体实体」——企业/机构名、带单位数字、地名。

    没有实体的句子（如「由于下游需求端萎靡，国内矿商销售压力逐步增大」）
    是分析感慨，无法补录成一条新闻，直接滤掉。
    """
    return bool(RE_ENTITY_ORG.search(s)
                or RE_ENTITY_NUM.search(s)
                or RE_ENTITY_PLACE.search(s))


RE_BODY_DATE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def body_date_ok(text, allowed_mmdd):
    """正文日期校验。

    综述类文章开头会写「SMM 9月7日讯」。若正文里出现的日期全部不在
    允许集合内，说明这篇是旧文（如 8月29日的隔夜行情被候选池收进来），
    用它回溯会串日期，必须剔除。
    """
    if not allowed_mmdd:
        return True
    found = {"%02d-%02d" % (int(a), int(b))
             for a, b in RE_BODY_DATE.findall(text[:400])}
    if not found:
        return True          # 抓不到日期不冤枉它
    return bool(found & allowed_mmdd)


def is_event_sentence(s, strict=True):
    """是否「可补录的事件句」。

    strict 模式下必须满足其一：
      a) 含企业/矿山/机构名（公司动态、项目投产、矿业权成交）
      b) 含事件动词且不是纯行情句（政策获批、矿权出让等）
    纯报价句一律不要——它们不是漏稿，是行情。
    """
    # 0) 投资者互动问答 / 推广引导 / 编号列表一律不是新闻
    if RE_QNA.search(s):
        return False
    # a) 含企业/矿山/机构名 → 一定是可补录的动态
    if RE_ENTITY_ORG.search(s):
        return True
    # b) 含事件动词且不是纯行情句 → 政策/矿权/项目类事件
    if any(v in s for v in EVENT_VERB) and not any(q in s for q in QUOTE_NOISE):
        return True
    # c) --loose 才收「只有数字/地名」的泛行情句
    if not strict and has_entity(s):
        return True
    return False


def extract_events(text, min_len=12, max_len=140, strict=True):
    """从综述正文里切出「与有色金属相关的事件句」"""
    out, seen = [], set()
    for s in SENT_SPLIT.split(text or ""):
        s = s.strip()
        if len(s) < min_len or len(s) > max_len:
            continue
        if not fn.is_relevant(s):
            continue
        if fn.is_noise(s, ""):
            continue
        if strict and not is_event_sentence(s, strict):
            continue
        k = s[:24]
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def grams(s):
    return {(s[i:i + 2] or "") for i in range(max(0, len(s) - 1))}


def similarity(a, b):
    A, B = grams(a), grams(b)
    if not A or not B:
        return 0.0
    return len(A & B) / float(len(A | B))


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="次日回溯漏稿检测")
    ap.add_argument("--date", default="", help="回溯哪一天（默认昨天）")
    ap.add_argument("--top", type=int, default=25, help="最多列多少条疑似漏稿")
    ap.add_argument("--threshold", type=float, default=THRESHOLD,
                    help="相似度阈值，低于该值判为疑似漏稿")
    ap.add_argument("--max-docs", type=int, default=MAX_DOCS, help="最多抓几篇综述")
    ap.add_argument("--loose", action="store_true",
                    help="放宽：不要求句内含具体实体（会混入纯行情描述句）")
    args = ap.parse_args()

    date = args.date or (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    next_day = (datetime.date.fromisoformat(date) + datetime.timedelta(days=1)).isoformat()
    # 综述正文日期只允许是目标日或次日（形如 "09-07" / "09-08"）
    allowed_mmdd = {date[5:], next_day[5:]}

    print("=" * 72)
    print("backcheck.py | 回溯 %s（对照 %s 次日综述）" % (date, next_day))
    print("=" * 72)

    existing = load_existing(date)
    pool = []
    for n in existing:
        if n.get("title"):
            pool.append(n["title"])
        if n.get("summary"):
            pool.append(n["summary"][:200])
    target_hit = sum(1 for n in existing
                     if (n.get("orig_date_full") or n.get("report_date")) == date)
    print("已入库基准：%d 条（参与比对文本 %d 段；其中目标日 %d 条）"
          % (len(existing), len(pool), target_hit))
    if not pool:
        print("\n比对基准为空：data/news_*.json 与 mining_news.json 都没读到条目，终止。")
        return

    # 1) 抓次日候选
    cfgs = [c for c in fn.SOURCES if c["key"] in REVIEW_SOURCES and c.get("enabled")]
    cands = []
    for c in cfgs:
        items, st = fn.run_source(c, next_day, 1, False)
        print("  %-10s %s" % (c["key"], st))
        cands += items
    # 2) 只保留「日」级综述，排除月评/周评/年报/回顾展望
    def is_periodic(t):
        return any(k in t for k in PERIODIC_KW)

    reviews = [x for x in cands
               if any(k in (x.get("title") or "") for k in REVIEW_KW)
               and not is_periodic(x.get("title") or "")]
    dropped = sum(1 for x in cands
                  if any(k in (x.get("title") or "") for k in REVIEW_KW)
                  and is_periodic(x.get("title") or ""))
    # 日评类不足 3 篇时，从次日候选池补足（仍排除周期性旧文）。
    # 否则样本太小——实测只命中 1 篇 SMM 日评时，结论没有说服力。
    if len(reviews) < MIN_REVIEW_DOCS:
        seen_t = {x.get("title") for x in reviews}
        for x in cands:
            if len(reviews) >= args.max_docs:
                break
            t = x.get("title") or ""
            if t in seen_t or is_periodic(t):
                continue
            seen_t.add(t)
            reviews.append(x)
    reviews = reviews[:args.max_docs]
    print("综述候选：%d 篇（候选池 %d 条，剔除周期性 %d 篇）"
          % (len(reviews), len(cands), dropped))

    # 3) 抓正文拆事件句
    strict = not args.loose
    events, stale = [], 0
    for r in reviews:
        body = fetch_body(r["url"])
        if not body:
            continue
        if not body_date_ok(body, allowed_mmdd):
            stale += 1
            print("    [跳过·日期不符] %s" % r["title"][:40])
            continue
        evs = extract_events(body, strict=strict)
        print("    %s → %d 句" % (r["title"][:34], len(evs)))
        for s in evs:
            events.append({"text": s, "src": r})
    if stale:
        print("（剔除日期不符的旧文 %d 篇）" % stale)
    if not events:
        print("\n未提取到事件句：可能综述源当天无盘点类内容，或源结构变化。")
        return

    # 次日候选池里已有的内容不算漏稿——AI 采编时本就看得见它们。
    # 只有「库里没有 + 候选池也没有」的事件才真正值得提示。
    for x in cands:
        if x.get("title"):
            pool.append(x["title"])

    # 4) 相似度比对（预计算基准 grams，避免 O(n*m) 重复切分）
    pool_g = [(p, grams(p)) for p in pool]
    miss = []
    for e in events:
        best, best_txt = 0.0, ""
        G, A = grams(e["text"]), None
        A = G
        for p, B in pool_g:
            if not A or not B:
                v = 0.0
            else:
                v = len(A & B) / float(len(A | B))
            if v > best:
                best, best_txt = v, p
        if best < args.threshold:
            miss.append({"text": e["text"], "sim": round(best, 3),
                         "nearest": best_txt[:60],
                         "src_title": e["src"].get("title", ""),
                         "src_url": e["src"].get("url", "")})
    miss.sort(key=lambda x: x["sim"])

    print("\n疑似漏稿：%d 条（阈值 %.2f，共比对 %d 句）"
          % (len(miss), args.threshold, len(events)))

    # 5) 落盘报告
    os.makedirs(DATA_DIR, exist_ok=True)
    out_md = os.path.join(DATA_DIR, "backcheck_%s.md" % date)
    lines = [
        "# 漏稿回溯 %s" % date,
        "",
        "- 回溯日期：%s（对照次日 %s 综述）" % (date, next_day),
        "- 已入库条目：%d 条" % len(existing),
        "- 综述来源：%d 篇，事件句 %d 句" % (len(reviews), len(events)),
        "- 疑似漏稿：**%d 条**（相似度阈值 %.2f）" % (len(miss), args.threshold),
        "",
        "> 本清单仅供参考，**不自动入库**。人工核实信源后按站内格式补录。",
        "",
    ]
    for i, m in enumerate(miss[:args.top], 1):
        lines += [
            "## %d.（相似度 %.3f）" % (i, m["sim"]),
            "",
            "- 事件句：%s" % m["text"],
            "- 出处：%s" % m["src_title"],
            "- 链接：%s" % m["src_url"],
            "- 库内最接近：%s" % (m["nearest"] or "（无）"),
            "",
        ]
    if not miss:
        lines += ["未发现疑似漏稿：次日综述提及的事件在库内均有对应条目。", ""]
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("报告已写入：%s" % out_md)

    print("\n疑似漏稿预览（最可能是漏稿的排前面）：")
    for m in miss[:10]:
        print("  [%.3f] %s" % (m["sim"], m["text"][:60]))
        print("         出处：%s" % m["src_title"][:52])


if __name__ == "__main__":
    main()
