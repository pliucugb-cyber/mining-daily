# -*- coding: utf-8 -*-
"""
_fetch_ma.py —— 并购/投资类信息抓取器（巨潮资讯网官方披露平台）

为什么用 cninfo：
  有色金属行业的并购、股权转让、资产重组、对外投资、矿业权（探/采矿权）交易，
  绝大多数由 A 股上市公司以《公告》形式在巨潮资讯网（cninfo.com.cn）官方披露。
  原日报 9 个白名单信源偏政策/行业通稿，缺资本市场公告这一环，故新增本抓取器。

实现要点：
  - 巨潮 `hisAnnouncement/query` 接口对 text 关键词过滤不生效，但按 seDate 区间可
    取当日全部公告；故改用「翻页取区间全部 + 客户端按矿企名单/标题关键词过滤」。
  - 矿企名单从巨潮官方 `szse_stock.json`（含沪深港全部 6247 只，带 orgId）动态提取：
    公司名含 铜/铝/铅/锌/镍/金/银/稀土/钨/钼/锡/锂/钴/矿/有色/资源 等即视为有色/矿业标的。
  - M&A 标题关键词：收购/股权/资产重组/资产购买/资产出售/重大资产/对外投/矿业权/
    探矿权/采矿权/并购/增资/认购/受让。
  - 详情页 URL：https://www.cninfo.com.cn/new/disclosure/detail?plate=<plate>&orgId=<orgId>&announcementId=<id>
    （plate 由 pageColumn 映射：SZZB→szse / SHZB→shse / HKB→hkex）

输出：
  - 追加式写入 data/ma_YYYY-MM.json（同 id 合并，历史累积）
  - 打印候选条目供人工/自动化确认
  - 默认只抓取 report_date 当天；--days N 可向前扩窗口（日常 09:00 建议 --days 1）

依赖：仅标准库（urllib/ssl/json），无第三方包，可在每日自动化环境直接跑。
"""
import argparse
import datetime
import hashlib
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STOCK_JSON = "https://www.cninfo.com.cn/new/data/szse_stock.json"
QUERY_API = "https://www.cninfo.com.cn/new/hisAnnouncement/query"

# 有色金属/矿业相关公司名关键词（用于从全市场股票里筛出矿企）。
# 注意：用「黄金/白银」而非单字「金/银」，避免误匹配银行/金融/金富科技等。
MINING_NAME_KW = ["铜业", "铜", "铝业", "铝", "铅", "锌", "镍", "稀土", "钨业", "钨",
                  "钼业", "钼", "锡业", "锡", "锂", "钴", "矿业", "有色", "资源", "矿",
                  "黄金", "白银"]
# 金融机构排除词（银行/券商/保险/信托等，非矿业标的）
FIN_EXCLUDE_KW = ["银行", "证券", "保险", "信托", "基金", "资本", "租赁", "金融"]
# 核心并购/投资类标题关键词（股权、资产、重组、对外投资等真交易）
MA_CORE_KW = ["收购", "资产重组", "资产购买", "资产出售", "重大资产", "并购",
              "受让", "对外投资", "增资", "拟收购", "拟转让", "股权转让",
              "资产置换", "向特定对象发行", "定增", "合资", "认购股份", "认购股权"]
# 矿权类：仅当为「转让/出让/收购/竞得」等交易形态才计入，排除延续/登记/变更等行政事项
MA_RIGHTS_KW = ["探矿权", "采矿权", "矿业权"]
RIGHTS_DEAL_KW = ["转让", "出让", "收购", "竞得"]
RIGHTS_ADMIN_KW = ["延续", "登记", "变更", "公示"]
# 理财/基金/资管认购：属财务投资而非矿业并购，剔除
FIN_PRODUCT_KW = ["基金", "理财", "资管"]
PLATE_MAP = {"SZZB": "szse", "SHZB": "shse", "HKB": "hkex",
             "BJB": "bse", "NQ": "nq", "": "szse"}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def http_post(url, params):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(), method="POST")
    req.add_header("User-Agent", "Mozilla/5.0")
    req.add_header("Referer", "https://www.cninfo.com.cn/")
    req.add_header("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
    with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def http_get_json(url):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


# 内置精选矿企名单（兜底用，避免依赖易抖动的巨潮股票列表接口）。
# 覆盖 A 股/北交所/港股主要有色与矿业标的；匹配时按子串双向包含，容错「股份/有限公司」后缀。
CURATED_MINERS = [
    "紫金矿业", "江西铜业", "铜陵有色", "云南铜业", "白银有色", "鹏欣资源",
    "中国铝业", "云铝股份", "神火股份", "中孚实业", "南山铝业", "天山铝业",
    "焦作万方", "怡球资源", "闽发铝业", "利源精制", "豪美新材",
    "洛阳钼业", "金钼股份", "厦门钨业", "章源钨业", "中钨高新", "翔鹭钨业",
    "广晟有色", "北方稀土", "盛和资源", "五矿稀土", "中国稀土",
    "山东黄金", "中金黄金", "赤峰黄金", "湖南黄金", "银泰黄金", "西部黄金",
    "四川黄金", "中金黄金", "万国黄金集团", "招金矿业", "中国黄金国际", "灵宝黄金",
    "盛达资源", "兴业银锡", "锡业股份", "驰宏锌锗", "中金岭南", "锌业股份",
    "罗平锌电", "株冶集团", "豫光金铅", "金徽股份", "华钰矿业", "西藏矿业",
    "金岭矿业", "金诚信", "海南矿业", "河钢资源", "大中矿业", "安宁股份",
    "钒钛股份", "西部矿业", "盛屯矿业", "藏格矿业", "盐湖股份",
    "赣锋锂业", "天齐锂业", "天华新能", "永兴材料", "融捷股份", "中矿资源",
    "盛新锂能", "雅化集团", "西藏城投", "科达制造", "蓝晓科技",
    "华友钴业", "寒锐钴业", "道氏技术", "洛阳钼业", "金川集团", "铜冠金源",
]
CACHE_PATH = os.path.join(DATA_DIR, ".mining_companies.json")


def _match_miner(sec, names):
    if not sec:
        return False
    if sec in names:
        return True
    for n in names:
        if n in sec or sec in n:   # 双向子串包含，容错后缀
            return True
    return False


def load_mining_companies(use_remote=True):
    """矿企名单：优先本地缓存；缺失/过期且允许远程时，从巨潮官方股票列表富化；
    任何失败回退到内置 CURATED_MINERS，保证每日运行不依赖易抖动接口。"""
    cached = None
    try:
        if os.path.exists(CACHE_PATH):
            cached = json.load(open(CACHE_PATH, encoding="utf-8"))
    except Exception:
        cached = None
    names = set(CURATED_MINERS)
    if cached and isinstance(cached, dict) and cached.get("names"):
        names |= set(cached["names"])
    if not use_remote:
        return names
    # 缓存 7 天内直接复用，跳过易抖动远程接口
    try:
        if cached and cached.get("updated_at"):
            cd = datetime.date.fromisoformat(cached["updated_at"])
            if (datetime.date.today() - cd).days < 7:
                return names
    except Exception:
        pass
    # 远程富化（带异常兜底）
    try:
        d = http_get_json(STOCK_JSON)
        lst = d.get("stockList", []) if isinstance(d, dict) else d
        added = 0
        for x in lst:
            nm = (x.get("zwjc") or x.get("name") or "").strip()
            if not nm:
                continue
            if any(k in nm for k in FIN_EXCLUDE_KW):
                continue
            if any(k in nm for k in MINING_NAME_KW):
                names.add(nm)
                added += 1
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            json.dump({"updated_at": datetime.datetime.now().strftime("%Y-%m-%d"),
                       "names": sorted(names)}, open(CACHE_PATH, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
        except Exception:
            pass
        print("[fetch_ma] 远程富化矿企 +%d（含内置共 %d）" % (added, len(names)))
    except Exception as e:
        print("[fetch_ma] 远程矿企名单获取失败，使用内置兜底名单（%d 家）：%s" % (len(names), e))
    return names


def bj_date(epoch_ms):
    """巨潮公告时间为毫秒时间戳（北京时间），转 YYYY-MM-DD。"""
    dt = datetime.datetime.fromtimestamp(epoch_ms / 1000, datetime.timezone.utc)
    dt = dt.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
    return dt.strftime("%Y-%m-%d"), dt.strftime("%m-%d")


def ma_type(title):
    for kw in ["探矿权", "采矿权", "矿业权"]:
        if kw in title:
            return "矿业权交易"
    if "重大资产重组" in title or "资产重组" in title:
        return "资产重组"
    if "资产购买" in title or "资产收购" in title or "收购" in title:
        return "股权/资产收购"
    if "股权转让" in title or "受让" in title:
        return "股权转让"
    if "增资" in title or "认购" in title:
        return "增资/认购"
    if "对外投资" in title:
        return "对外投资"
    if "并购" in title:
        return "并购"
    return "投资/资本运作"


def fetch_range(report_date, days):
    """翻页抓取 [report_date-days+1, report_date] 区间全部公告，返回原始公告列表。"""
    end = datetime.date.fromisoformat(report_date)
    start = end - datetime.timedelta(days=max(0, days - 1))
    se_date = "%s~%s" % (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    all_an = []
    page = 1
    while True:
        r = http_post(QUERY_API, {
            "pageNum": str(page), "pageSize": "30", "column": "", "tabName": "fulltext",
            "plate": "", "seDate": se_date, "isHL": "", "stock": "", "text": "",
        })
        anns = r.get("announcements") or []
        if not anns:
            break
        all_an.extend(anns)
        total = r.get("totalAnnouncement") or 0
        if len(all_an) >= total or len(anns) < 30:
            break
        page += 1
        if page > 200:
            break
    return all_an


def build_items(report_date, days, mining_names):
    raw = fetch_range(report_date, days)
    out = []
    seen_ids = set()
    for a in raw:
        aid = a.get("announcementId") or ""
        if not aid or aid in seen_ids:
            continue
        sec = (a.get("secName") or "").strip()
        title = (a.get("announcementTitle") or a.get("shortTitle") or "").strip()
        if not title:
            continue
        # 理财/基金/资管认购：财务投资噪声，剔除
        if "认购" in title and any(k in title for k in FIN_PRODUCT_KW):
            continue
        is_mining_co = _match_miner(sec, mining_names)
        has_core = any(k in title for k in MA_CORE_KW)
        rights_deal = (any(k in title for k in MA_RIGHTS_KW)
                       and any(k in title for k in RIGHTS_DEAL_KW)
                       and not any(k in title for k in RIGHTS_ADMIN_KW))
        # 矿企自身的并购公告，或跨行业但标的明确为矿业权转让/出让
        if not (has_core and (is_mining_co or rights_deal)):
            continue
        seen_ids.add(aid)
        full, mmdd = bj_date(a.get("announcementTime") or 0)
        # 巨潮 SPA 详情页在部分环境/浏览器下打不开，改用官方 PDF 直链更稳。
        adjunct = (a.get("adjunctUrl") or "").strip()
        if adjunct and not adjunct.startswith("http"):
            url = "https://static.cninfo.com.cn/" + adjunct.lstrip("/")
        else:
            org = a.get("orgId") or ""
            plate = PLATE_MAP.get(a.get("pageColumn"), "szse")
            url = "https://www.cninfo.com.cn/new/disclosure/detail?plate=%s&orgId=%s&announcementId=%s" % (plate, org, aid)
        mtype = ma_type(title)
        summary = "%s（%s）披露《%s》，涉及%s。" % (sec, a.get("secCode") or "", title, mtype)
        out.append({
            "id": hashlib.md5(aid.encode("utf-8")).hexdigest()[:12],
            "url": url,
            "title": title,
            "source": "巨潮资讯网·" + sec,
            "orig_date": mmdd,
            "orig_date_full": full,
            "report_date": report_date,
            "category": "并购与投资",
            "company": sec,
            "sec_code": a.get("secCode") or "",
            "ma_type": mtype,
            "summary": summary,
            "tags": sorted({k for k in ("铜", "铝", "铅", "锌", "镍", "金", "银", "稀土",
                                       "钨", "钼", "锡", "锂", "钴", "铁") if k in title} | {"并购"}),
        })
    # 按日期倒序
    out.sort(key=lambda x: (x["orig_date_full"], x["title"]), reverse=True)
    return out


def merge_into_month(items, report_date):
    os.makedirs(DATA_DIR, exist_ok=True)
    month = report_date[:7]
    path = os.path.join(DATA_DIR, "ma_%s.json" % month)
    store = {}
    if os.path.exists(path):
        try:
            store = {e["id"]: e for e in json.load(open(path, encoding="utf-8")).get("news", [])}
        except Exception:
            store = {}
    added = updated = 0
    for e in items:
        if e["id"] in store:
            store[e["id"]].update(e)
            updated += 1
        else:
            store[e["id"]] = e
            added += 1
    rows = sorted(store.values(), key=lambda x: (x["orig_date_full"], x["id"]), reverse=True)
    json.dump({"month": month, "updated_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
               "count": len(rows), "news": rows}, open(path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return added, updated, len(rows), path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-date", default=datetime.date.today().strftime("%Y-%m-%d"))
    ap.add_argument("--days", type=int, default=1, help="向前扩展窗口天数（含当天）")
    ap.add_argument("--no-write", action="store_true", help="只打印不写文件")
    args = ap.parse_args()

    print("[fetch_ma] 加载矿企名单…")
    mining_names = load_mining_companies()
    print("[fetch_ma] 矿企候选 %d 家（名称含有色/矿业关键词）" % len(mining_names))

    items = build_items(args.report_date, args.days, mining_names)
    print("[fetch_ma] 命中并购/投资类公告 %d 条（区间 %s，窗口 %d 天）"
          % (len(items), args.report_date, args.days))
    for it in items:
        print("  - [%s] %s | %s | %s" % (it["orig_date"], it["company"], it["ma_type"], it["title"][:50]))

    if not args.no_write and items:
        added, updated, total, path = merge_into_month(items, args.report_date)
        print("[fetch_ma] 写入 %s：新增 %d / 更新 %d / 累计 %d" % (path, added, updated, total))
    return items


if __name__ == "__main__":
    main()
