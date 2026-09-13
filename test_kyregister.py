#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""矿权登记结果源（kyreg_tk / kyreg_ck）解析契约测试（无网络）。

验证 parse_table 对真实 fixtures 的解析正确性：
  ① 正确定位数据表（区别于顶部搜索表单 table，其表头带冒号）；
  ② 列映射正确（探矿权 12 列 / 采矿权 11 列）；
  ③ 标题 = 【探/采矿权·项目类型】名称（矿种），摘要含许可证号+矿业权人/采矿权人+面积；
  ④ 公告日期列提取为 YYYY-MM-DD；
  ⑤ NONMETALLIC_KW 排除谓词：金属矿种保留、砂石土/地热剔除。
不依赖网络，仅靠 fixtures/ky_dj_tk_p0.html 与 ky_dj_ck_p0.html。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch_news as F  # noqa: E402

DATE_RE = re.compile(r"20\d{2}-\d{2}-\d{2}")

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        print("  FAIL  %s  %s" % (name, detail))


def load(key):
    suffix = "tk" if key == "kyreg_tk" else "ck"
    fn = os.path.join(HERE, "fixtures", "ky_dj_%s_p0.html" % suffix)
    return open(fn, encoding="utf-8").read()


def test_parse(key, label, type_label, name_field, mineral_field):
    cfg = next(c for c in F.SOURCES if c["key"] == key)
    html = load(key)
    rows = F.parse_table(html, cfg)
    check("%s: 解析出 15 行数据" % label, len(rows) == 15, "got %d" % len(rows))
    if not rows:
        return
    r0 = rows[0]
    check("%s: 首行许可证号非空" % label, bool(r0["url"].split("lic=")[1]), r0["url"])
    check("%s: 首行日期为 YYYY-MM-DD" % label, bool(DATE_RE.match(r0["date"])),
          r0["date"])
    check("%s: 标题以【%s·" % (label, type_label), r0["title"].startswith("【%s·" % type_label),
          r0["title"])
    check("%s: 标题含矿种（%s）" % (label, mineral_field), mineral_field in r0["title"],
          r0["title"])
    check("%s: 摘要含 许可证号" % label, "许可证号" in r0["summary"], r0["summary"][:40])
    check("%s: 摘要含 %s 字段" % (label, name_field),
          name_field in r0["summary"], r0["summary"][:60])
    check("%s: 摘要含 面积" % label, "面积" in r0["summary"], r0["summary"][:60])
    # 全部行日期合法、许可证号唯一
    dates_ok = all(DATE_RE.match(r["date"]) for r in rows)
    lics = [r["url"].split("lic=")[1] for r in rows]
    check("%s: 所有行日期合法" % label, dates_ok)
    check("%s: 许可证号互不重复" % label, len(set(lics)) == len(lics),
          "dup=%d" % (len(lics) - len(set(lics))))
    # 搜索表单 table 未被误选：若误选表头带冒号的那张，会得 0 或 1 行
    check("%s: 未误选搜索表单表" % label, len(rows) > 1)


def test_exclusion():
    # 金属矿种标题应保留，非金属应剔除（与 run_source 的 extra_exclude 同谓词）
    metal = "【探矿权·变更登记】某某铅锌多金属矿勘探（铅矿）"
    stone = "【采矿权·首次登记】某某建筑用砂矿（建筑用砂）"
    geo = "【采矿权·首次登记】某某地热（地热）"
    check("排除谓词：金属矿种不被 NONMETALLIC_KW 命中",
          not any(k in metal for k in F.NONMETALLIC_KW))
    check("排除谓词：建筑用砂被剔除",
          any(k in stone for k in F.NONMETALLIC_KW))
    check("排除谓词：地热被剔除",
          any(k in geo for k in F.NONMETALLIC_KW))
    # run_source 对 table 源启用 use_raw_date，日期直接采用公告日期列
    tk = next(c for c in F.SOURCES if c["key"] == "kyreg_tk")
    ck = next(c for c in F.SOURCES if c["key"] == "kyreg_ck")
    check("kyreg_tk 启用 use_raw_date", bool(tk.get("use_raw_date")))
    check("kyreg_ck 启用 use_raw_date", bool(ck.get("use_raw_date")))
    check("kyreg_tk 归类 矿权市场", tk["category"] == "矿权市场")
    check("kyreg_ck 归类 矿权市场", ck["category"] == "矿权市场")
    check("kyreg_tk 已启用", bool(tk.get("enabled")))
    check("kyreg_ck 已启用", bool(ck.get("enabled")))


def main():
    print("==== test_kyregister ====")
    test_parse("kyreg_tk", "探矿权登记", "探矿权", "探矿权人", "铅矿")
    test_parse("kyreg_ck", "采矿权登记", "采矿权", "采矿权人", "闪长岩")
    test_exclusion()
    print("-" * 40)
    print("PASS=%d  FAIL=%d" % (PASS, FAIL))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
