#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 GitHub Pages 所需的静态数据文件（无需 Python 后端即可运行日报）：

  - data/hot_news.json                 热榜 Top N（纯本地计算，无需联网）
  - data/ai_analysis_YYYY-MM-DD.json  AI 深度解析快照（可选，需设置 DEEPSEEK_API_KEY）

用法（在本仓库根目录执行）：
  python build_static.py                       # 仅生成热榜
  DEEPSEEK_API_KEY=sk-xxx python build_static.py   # 同时生成 AI 解析快照

生成后正常 git add / commit / push 即可，GitHub Pages 会自动采用新文件。
"""
import os
import re
import json
import datetime
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
NEWS_JS = os.path.join(HERE, "news-data.js")

TOP_N = 3     # 热榜展示条数（与页面 "TOP 3" 一致）
AI_N = 7      # AI 解析取前 N 条头条

# ===== 热榜加权参数（与 server.py 保持一致）=====
SOURCE_WEIGHTS = {
    "自然资源部": 12, "中国地质调查局": 10, "中国地质学会": 8,
    "中国有色金属工业协会": 8, "中国黄金协会": 8, "中国稀土行业协会": 7,
    "中国有色网": 7, "矿业权市场": 6, "全球矿产资源": 5,
    "上海联合矿权交易所": 5, "上海期货交易所": 6, "中国矿业报": 7,
    "中国矿业网": 6, "中国黄金集团": 6, "紫金矿业": 5,
    "中国黄金网": 6, "矿冶集团": 6, "中国稀土集团": 7,
}
HOT_KW = ["突破", "重大", "战略", "世界第一", "首次", "关键矿产", "新一轮",
          "标志性", "历史最好", "历史新高", "刷新", "龙头", "全球第一",
          "亚洲第一", "国内首台", "首套", "首发", "首发阵容"]
NORMAL_KW = ["找矿", "勘查", "探矿", "重要", "规划", "增量", "分红",
             "成果", "进展", "签约", "投产", "扩建", "增资", "中标", "出让",
             "成交", "创", "新高", "领先"]

# ===== DeepSeek（仅生成 AI 快照时需要）=====
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"


def load_news_data():
    """从 news-data.js 解析 window.NEWS_DATA（前端同源静态数据）。"""
    with open(NEWS_JS, encoding="utf-8") as f:
        txt = f.read()
    m = re.search(r"window\.NEWS_DATA\s*=\s*(\{.*\})\s*;?\s*$", txt, re.DOTALL)
    if not m:
        raise RuntimeError("无法解析 news-data.js 中的 window.NEWS_DATA")
    return json.loads(m.group(1))


def compute_hot_news(rows, today, n=TOP_N):
    """移植 server.py 的热榜加权算法（来源权重 + 时效衰减 + 关键词加权）。"""
    try:
        today_dt = datetime.datetime.strptime(today, "%Y-%m-%d")
    except Exception:
        today_dt = datetime.datetime.now()
    scored = []
    for r in rows:
        t = str(r.get("t", "")).strip()
        s = str(r.get("s", "")).strip()
        d = str(r.get("d", "")).strip()
        u = str(r.get("u", "")).strip()
        if not t or not u or not d:
            continue
        try:
            days_diff = (today_dt - datetime.datetime.strptime(d, "%Y-%m-%d")).days
        except Exception:
            days_diff = 0
        if days_diff < 0:
            days_diff = 0
        recency = max(0, 30 - days_diff * 4)
        src_w = SOURCE_WEIGHTS.get(s, 3)
        hot_bonus = 20 if any(kw in t for kw in HOT_KW) else 0
        normal_bonus = 5 if (hot_bonus == 0 and any(kw in t for kw in NORMAL_KW)) else 0
        score = src_w * 10 + recency + hot_bonus + normal_bonus
        scored.append({"d": d, "t": t, "s": s, "u": u, "score": score, "hot": hot_bonus > 0})
    scored.sort(key=lambda x: (x["score"], x["d"]), reverse=True)
    seen, out = set(), []
    for it in scored:
        if it["u"] in seen:
            continue
        seen.add(it["u"])
        out.append(it)
        if len(out) >= n:
            break
    for i, it in enumerate(out):
        it["rank"] = i + 1
    return out


def deepseek_chat(messages, max_tokens=320, temperature=0.3):
    if not DEEPSEEK_API_KEY:
        return None
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    try:
        req = urllib.request.Request(
            DEEPSEEK_ENDPOINT,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + DEEPSEEK_API_KEY,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        print("[deepseek] HTTP", e.code, e.reason)
        return None
    except Exception as e:
        print("[deepseek] error:", type(e).__name__, str(e)[:200])
        return None


def ai_analyze_one(news):
    """对单条新闻生成 AI 深度解析：要点/启示/风险。"""
    title = str(news.get("t", "")).strip()
    src = str(news.get("s", "")).strip()
    url = str(news.get("u", "")).strip()
    summary = str(news.get("m", news.get("summary", ""))).strip()
    if not title or not url:
        return None
    user_prompt = (
        "你是资深矿业行业分析师。基于以下新闻给出 3 点结构化解析（简洁专业、不啰嗦）：\n\n"
        f"标题：{title}\n来源：{src}\n摘要：{summary}\n\n"
        "请严格按 JSON 格式输出（不要任何额外说明文字、不要 markdown 代码块标记）：\n"
        '{"summary":"一句话核心要点（≤30字）",'
        '"insight":"对矿业行业/从业者的启示（≤60字）",'
        '"risk":"潜在风险或注意事项（≤40字，无则填\'无\'）"}'
    )
    content = deepseek_chat([
        {"role": "system", "content": "你是矿业行业资深分析师，输出简洁、结构化、不啰嗦。"},
        {"role": "user", "content": user_prompt},
    ], max_tokens=320, temperature=0.3)
    if not content:
        return None
    m = re.search(r"\{[^{}]+\}", content, re.DOTALL)
    if not m:
        return None
    try:
        j = json.loads(m.group(0))
        return {
            "url": url,
            "title": title,
            "src": src,
            "summary": str(j.get("summary", "")).strip(),
            "insight": str(j.get("insight", "")).strip(),
            "risk": str(j.get("risk", "无")).strip() or "无",
        }
    except Exception:
        return None


def main():
    obj = load_news_data()
    rows = obj.get("news", [])
    updated = str(obj.get("updated", ""))[:10] or datetime.datetime.now().strftime("%Y-%m-%d")
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    os.makedirs(DATA_DIR, exist_ok=True)

    # 1) 热榜（Top AI_N 用于 AI 候选，对外展示 Top TOP_N）
    top = compute_hot_news(rows, today, AI_N)
    hot = top[:TOP_N]
    with open(os.path.join(DATA_DIR, "hot_news.json"), "w", encoding="utf-8") as f:
        json.dump({"date": today, "updated": updated, "hot": hot}, f, ensure_ascii=False, indent=2)
    print(f"[hot] 生成 {len(hot)} 条热榜 -> data/hot_news.json")

    # 2) AI 解析快照（可选）
    if not DEEPSEEK_API_KEY:
        print("[ai] 未设置 DEEPSEEK_API_KEY，跳过 AI 解析生成。")
        print("     如需 GitHub Pages 上也显示 AI 解析，请配置密钥后重跑：")
        print("     DEEPSEEK_API_KEY=sk-xxx python build_static.py")
        return
    items = []
    for r in top:
        a = ai_analyze_one(r)
        if a:
            items.append(a)
        else:
            print(f"[ai] 跳过（无结果）：{r.get('t', '')[:24]}")
    out = {"v": 1, "date": today, "items": items}
    path = os.path.join(DATA_DIR, f"ai_analysis_{today}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[ai] 生成 {len(items)} 条 AI 解析 -> {os.path.basename(path)}")


if __name__ == "__main__":
    main()
