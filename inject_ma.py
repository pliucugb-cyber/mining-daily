# -*- coding: utf-8 -*-
"""
inject_ma.py —— 将 fetch_ma.py 抓取的并购/投资类公告注入 index.html

设计：
  - 读取 data/ma_YYYY-MM.json（追加式累积库），按日期窗口过滤：
    当日（== report_date）→ 注入「今日新增」区，标 is-new；
    窗口内更早（> report_date-ARCHIVE_DAYS）→ 注入「往期内容」区顶部。
  - 以独立子分类「💰 并购与投资」分组，便于读者识别。
  - 幂等：已存在于页面的 url 跳过；同一区已含该子分类则追加而非重复建头。
  - 仅插入合法 .news-item 标记，div 平衡由调用方 preflight_check 校验。
  - 计数交给前端 refresh() 实时重算，这里同步更新静态 span 作为 JS 加载前兜底。

用法：
  python inject_ma.py [--report-date 2026-09-07] [--days 14]
"""
import argparse
import datetime
import json
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(BASE_DIR, "index.html")
DATA_DIR = os.path.join(BASE_DIR, "data")
CAT_MA = "💰 并购与投资"
ARCHIVE_DAYS = 14


def load_ma(report_date, days):
    end = datetime.date.fromisoformat(report_date)
    start = end - datetime.timedelta(days=max(0, days - 1))
    items = []
    for fn in os.listdir(DATA_DIR):
        if not (fn.startswith("ma_") and fn.endswith(".json")):
            continue
        try:
            rows = json.load(open(os.path.join(DATA_DIR, fn), encoding="utf-8")).get("news", [])
        except Exception:
            continue
        for e in rows:
            od = e.get("orig_date_full", "")
            if not od:
                continue
            try:
                d = datetime.date.fromisoformat(od)
            except Exception:
                continue
            if start <= d <= end:
                items.append(e)
    # 去重（同 url 只保留一条）
    seen, uniq = set(), []
    for e in items:
        if e["url"] in seen:
            continue
        seen.add(e["url"])
        uniq.append(e)
    uniq.sort(key=lambda x: (x["orig_date_full"], x["title"]), reverse=True)
    return uniq


def item_html(e, is_new):
    cls = 'news-item is-new' if is_new else 'news-item'
    badge = '<span class="badge-new">NEW</span>' if is_new else ''
    return ('<div class="%s" data-url="%s" data-embed="ok"><div class="news-head"><span class="dot"></span>%s'
            '<a class="news-title" href="%s" target="_blank">%s</a></div>'
            '<div class="news-meta"><span class="src">%s</span> · %s</div>'
            '<div class="news-summary">%s</div></div>'
            % (cls, e["url"], badge, e["url"], e["title"], e["source"], e["orig_date"], e["summary"]))


def group_html(items, is_new):
    body = '<div class="sub-cat">%s<span class="sub-count">%d条%s</span></div>\n' % (
        CAT_MA, len(items), "新增" if is_new else "")
    for e in items:
        body += item_html(e, is_new) + "\n"
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-date", default=datetime.date.today().strftime("%Y-%m-%d"))
    ap.add_argument("--days", type=int, default=ARCHIVE_DAYS)
    args = ap.parse_args()
    report_date = args.report_date

    items = load_ma(report_date, args.days)
    if not items:
        print("[inject_ma] 无并购/投资类条目需注入（窗口 %d 天）" % args.days)
        return

    html = open(INDEX, encoding="utf-8").read()
    # 幂等：跳过已存在 url
    exist = set(re.findall(r'data-url="([^"]+)"', html))
    items = [e for e in items if e["url"] not in exist]
    if not items:
        print("[inject_ma] 全部条目已存在于页面，跳过")
        return

    today_items = [e for e in items if e["orig_date_full"] == report_date]
    old_items = [e for e in items if e["orig_date_full"] != report_date]

    def has_ma_block(section_html):
        return ('>%s<' % CAT_MA) in section_html or CAT_MA in section_html

    inserted = 0
    # —— 今日新增区（当日条目）——
    if today_items:
        i = html.find('<div class="section" id="todaySection"')
        j = html.find('<div class="section" id="archiveSection"', i)
        today_sec = html[i:j]
        if not has_ma_block(today_sec):
            block = group_html(today_items, True)
            # 插在今日区最后一个 </div>（区块闭合）之前
            close = today_sec.rfind('</div>')
            new_sec = today_sec[:close] + block + today_sec[close:]
            html = html[:i] + new_sec + html[j:]
            inserted += len(today_items)

    # —— 往期内容区（窗口内更早条目）——
    if old_items:
        i = html.find('<div class="section" id="archiveSection"')
        j = html.find('<div class="section" id="rightsSection"', i)
        arch_sec = html[i:j]
        if not has_ma_block(arch_sec):
            block = group_html(old_items, False)
            # 插在 fold-toggle 之后（无则插在 section-title 之后）
            m = re.search(r'<div class="fold-toggle"[^>]*>.*?</div>\s*', arch_sec, re.S)
            if m:
                pos = m.end()
            else:
                # section-title 行尾
                m2 = re.search(r'<div class="section-title[^>]*>.*?</div>\s*', arch_sec, re.S)
                pos = m2.end() if m2 else len(arch_sec)
            new_sec = arch_sec[:pos] + block + arch_sec[pos:]
            html = html[:i] + new_sec + html[j:]
            inserted += len(old_items)

    if inserted == 0:
        print("[inject_ma] 未注入（子分类已存在或窗口无新条目）")
        return

    # 同步静态计数兜底（前端 refresh() 会再实时重算）
    def count_in(sec):
        return len(re.findall(r'<div class="news-item', sec))
    ti = html.find('<div class="section" id="todaySection"')
    ai = html.find('<div class="section" id="archiveSection"', ti)
    ri = html.find('<div class="section" id="rightsSection"', ai)
    today_sec = html[ti:ai]
    arch_sec = html[ai:ri]
    n_today = count_in(today_sec)
    n_arch = count_in(arch_sec)
    n_all = n_today + n_arch
    html = re.sub(r'id="tocTodayCount"[^>]*>\d+<', 'id="tocTodayCount">%d<' % n_today, html)
    html = re.sub(r'id="tocArchiveCount"[^>]*>\d+<', 'id="tocArchiveCount">%d<' % n_arch, html)
    html = re.sub(r'id="tocAllCount"[^>]*>\d+<', 'id="tocAllCount">%d<' % n_all, html)
    html = re.sub(r'id="todayCount"[^>]*>\d+条<', 'id="todayCount">%d条<' % n_today, html)
    html = re.sub(r'id="archiveCount"[^>]*>\d+条<', 'id="archiveCount">%d条<' % n_arch, html)

    # bump build-version
    now = datetime.datetime.now().strftime("%H%M")
    html = re.sub(r'name="build-version" content="\d{8}-\d{4}"',
                  'name="build-version" content="%s-%s"' % (report_date.replace("-", ""), now), html)

    open(INDEX, "w", encoding="utf-8").write(html)
    print("[inject_ma] 注入 %d 条并购/投资（今日 %d + 往期 %d），build 已 bump"
          % (inserted, len(today_items), len(old_items)))


if __name__ == "__main__":
    main()
