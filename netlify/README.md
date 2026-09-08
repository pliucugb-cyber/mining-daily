# AI 问答代理 · Netlify 边缘函数

## 它解决什么问题

站点是 **GitHub Pages 公开静态页**，任何写进 `index.html` 的 API Key 都等于公开——
混淆不是加密，访客 F12 或直接 `curl` 页面就能还原并盗用额度。

本代理把 Key 存在 **Netlify 环境变量**里：

```
浏览器 → index.html（无 Key） → POST /api/qa → Netlify 边缘函数（读 Key） → DeepSeek
```

- 页面里**没有任何 Key**，代码仓库里也没有
- 同事打开页面直接用，**不需要自己填 Key**
- 额外好处：CORS 白名单限制了只有本站 + localhost 能调用，防止被第三方站点盗刷

## 文件

| 文件 | 作用 |
|---|---|
| `edge-functions/qa.js` | 代理主体：`/api/health`、`/api/qa`，无 Key 时自动降级关键词兜底 |
| `../netlify.toml` | **仓库根目录**（不是本目录）：路由 `/api/*` + 安全响应头 |
| `public/index.html` | 占位首页（本站点实际只提供 API） |

⚠️ `netlify.toml` 必须放在**仓库根目录**。Netlify 约定 Edge Function 目录是
`<部署根目录>/netlify/edge-functions`；若把 `netlify/` 自身当部署根目录，
它会去找 `netlify/netlify/edge-functions`，结果是**打包 0 个函数、接口 404**。

## 部署（已验证可用的方式）

```bash
# 一次安装 CLI
npm --prefix ~/.workbuddy/binaries/node/workspace install netlify-cli

# 建站 + 部署（首次）；之后改了 qa.js 或环境变量用 --redeploy
python netlify_deploy.py
python netlify_deploy.py --redeploy
```

凭据读环境变量 `NETLIFY_TOKEN`，或本地 `netlify_token.txt`（已 gitignore）。

### ⚠️ 两个必须知道的坑

1. **必须用 CLI 部署，不能用 API 直传。** 直传 API（POST deploys + PUT 文件）
   不会打包 Edge Function（实测 `required_edge_functions` 为空），只有 CLI 会 esbuild 打包。
2. **新站点默认是「私有」，访客会被 401 踢到登录页。** Netlify 自 2026-07-28 起
   新项目默认私有，且**只能在网页端改**，API 改不动：
   `Project configuration → General → Visitor access → Project visibility`
   → Production deploys 选 **Public** → Save。

## 环境变量

`Project configuration → Environment variables` 新增 `DEEPSEEK_API_KEY`。
改完**必须重新部署一次**（`python netlify_deploy.py --redeploy`），Edge Function 才读得到新值。

## 部署后验证

```bash
curl https://<你的站点>.netlify.app/api/health
# 期望：{"ok":true,"has_key":true,"model":"deepseek-chat",...}

curl -X POST https://<你的站点>.netlify.app/api/qa \
  -H 'Content-Type: application/json' \
  -d '{"question":"铜价最近怎么样"}'
# 期望：返回 {"answer":"...","source":"deepseek",...}
```

`has_key:false` 说明环境变量没配好，此时问答会降级为关键词兜底（功能仍在，只是不是 AI 生成）。

## 更换 / 作废 Key

在 Netlify 站点环境变量里改 `DEEPSEEK_API_KEY`，改完跑一次 `python netlify_deploy.py --redeploy`；
页面代码不用动。

## 为什么不用 Cloudflare Workers

`workers.dev` 域名在本项目所在网络实测 `http_code=000`（不可达），
而 `*.netlify.app` 实测可达。故改用 Netlify。`worker/` 目录的 CF 版本保留作备选。
