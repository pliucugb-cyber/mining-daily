#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把矿业日报的 AI 问答代理部署到 Netlify。

为什么必须用 CLI 而不是 API 直传:
    直传 API（POST /sites/{id}/deploys + PUT 文件）**不会打包 Edge Function**
    （实测 deploy.required_edge_functions 为空 → 接口 404）。
    只有 netlify-cli 会做 esbuild 打包，所以部署环节走 CLI。

为什么 netlify.toml 必须在仓库根目录:
    Netlify 约定 Edge Function 目录为 <部署根目录>/netlify/edge-functions。
    若把 netlify/ 当部署根目录，会去找 netlify/netlify/edge-functions → 0 个函数。

用法:
    python netlify_deploy.py                 # 建站（首次）+ 部署
    python netlify_deploy.py --redeploy      # 复用已缓存站点重新部署（改了 qa.js / 环境变量后用它）

前置: 已在托管 node workspace 安装 netlify-cli
      npm --prefix <workspace> install netlify-cli

凭据: 读环境变量 NETLIFY_TOKEN，或本地 netlify_token.txt（已 gitignore）。
站点信息缓存在 netlify/.site.json（已 gitignore）。

注意:
  1. 修改/新增环境变量后必须重新部署一次，Edge Function 才会读到新值。
  2. 新站点默认是「私有」（Netlify 2026-07-28 起），访客会被 401 踢到登录页。
     须在网页端改：Project configuration → General → Visitor access →
     Project visibility → Production deploys 设为 Public。API 改不动。
"""
import os
import re
import ssl
import json
import hashlib
import argparse
import subprocess
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "netlify")
STATE = os.path.join(SRC, ".site.json")
SITE_NAME = "mining-daily-qa"
API = "https://api.netlify.com/api/v1"


def load_token():
    tok = os.environ.get("NETLIFY_TOKEN", "").strip()
    if tok:
        return tok
    p = os.path.join(ROOT, "netlify_token.txt")
    if os.path.exists(p):
        tok = open(p, encoding="utf-8").read().strip()
        if tok:
            return tok
    raise SystemExit(
        "未找到 Netlify token。设置环境变量 NETLIFY_TOKEN，或写入 netlify_token.txt（已 gitignore）。"
    )


CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
TOKEN = load_token()


def api(path, method="GET", body=None, raw=False):
    req = urllib.request.Request(API + path, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("User-Agent", "Mozilla/5.0 (mining-daily deployer)")
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        r = urllib.request.urlopen(req, data=data, timeout=60, context=CTX)
        raw_bytes = r.read()
        return r.status, (raw_bytes if raw else json.loads(raw_bytes.decode("utf-8", "ignore")))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        try:
            detail = json.dumps(json.loads(detail), ensure_ascii=False)[:800]
        except Exception:
            detail = detail[:500]
        print("  HTTP %s: %s" % (e.code, detail))
        raise


def upload_file(deploy_id, path, content_bytes):
    req = urllib.request.Request(
        API + "/deploys/%s/files%s" % (deploy_id, path),
        data=content_bytes,
        method="PUT",
    )
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("User-Agent", "Mozilla/5.0 (mining-daily deployer)")
    req.add_header("Content-Type", "application/octet-stream")
    urllib.request.urlopen(req, timeout=60, context=CTX).read()


def collect_files():
    """返回 {'/相对路径': bytes}，跳过状态文件与说明文档。"""
    skip = {".site.json", ".DS_Store"}
    out = {}
    for dirpath, dirnames, filenames in os.walk(SRC):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules")]
        for fn in filenames:
            if fn in skip or fn.endswith(".pyc"):
                continue
            full = os.path.join(dirpath, fn)
            rel = "/" + os.path.relpath(full, SRC).replace("\\", "/")
            out[rel] = open(full, "rb").read()
    return out


def get_or_create_site(force_new=False):
    if os.path.exists(STATE) and not force_new:
        st = json.load(open(STATE, encoding="utf-8"))
        code, s = api("/sites/%s" % st["id"])
        if code == 200:
            print("复用已有站点: %s" % s.get("url"))
            return s
    code, s = api("/sites", "POST", {"name": SITE_NAME})
    print("新建站点: %s (id=%s)" % (s.get("url"), s.get("id")))
    return s


CLI = os.path.join(
    os.path.expanduser("~"),
    ".workbuddy", "binaries", "node", "workspace",
    "node_modules", "netlify-cli", "bin", "run.js",
)


def deploy(site):
    """走 netlify-cli：只有 CLI 会打包 Edge Function。"""
    if not os.path.exists(CLI):
        raise SystemExit(
            "找不到 netlify-cli，请先安装:\n"
            "  npm --prefix %s install netlify-cli"
            % os.path.join(os.path.expanduser("~"), ".workbuddy", "binaries", "node", "workspace")
        )
    env = dict(os.environ, NETLIFY_AUTH_TOKEN=TOKEN)
    cmd = ["node", CLI, "deploy", "--prod", "--build", "--site", site["id"]]
    print("执行:", " ".join(cmd))
    r = subprocess.run(cmd, cwd=ROOT, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    tail = (r.stdout or "") + ("\n[stderr]\n" + r.stderr if r.stderr else "")
    print(tail[-2500:])
    if r.returncode != 0:
        raise SystemExit("部署失败，退出码 %s" % r.returncode)
    # 校验：CLI 输出里若出现 "0 edge functions" 说明没打包成功
    if "0 edge functions" in (r.stdout or ""):
        print("\n[警告] 本次部署未打包任何 Edge Function，请检查 netlify.toml 位置与目录结构！")
    return {"id": None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--redeploy", action="store_true", help="复用已缓存的站点重新部署")
    ap.add_argument("--new", action="store_true", help="忽略缓存，强制新建站点")
    args = ap.parse_args()

    site = get_or_create_site(force_new=args.new)
    json.dump({"id": site["id"], "url": site.get("url"), "name": site.get("name")},
              open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    deploy(site)
    print("\n站点地址: %s" % site.get("url"))
    print("把上面的域名填进 index.html 的 QA_API_BASE，然后重新部署页面即可。")
    print("提示: 改了环境变量后需再跑一次本脚本，Edge Function 才会读到新值。")


if __name__ == "__main__":
    main()
