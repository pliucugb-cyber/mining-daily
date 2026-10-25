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
| `edge-functions/qa.js` | 代理主体：`/api/health`、`/api/balance`（余额查询）、`/api/qa`，无 Key 时自动降级关键词兜底 |
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

## 余额查询（/api/balance，2026-10-25 新增）

DeepSeek 官方无月度预算功能（按量付费、余额扣完自动停、不会欠费），故只需
"快用完时提醒"。`GET /api/balance` 供每日定时任务查询：

- 与 `/api/qa` **同来源闸门**——脚本调用必须带合法 Origin 头
- 只回 `is_available / currency / total_balance` 等告警字段，Key 不回传
- HTTP 层恒 200，业务状态看 `ok` 字段（`ok:false` 时 `reason` 给原因）

```bash
curl -s https://mining-daily-qa.netlify.app/api/balance \
  -H 'Origin: https://pliucugb-cyber.github.io'
# 期望：{"ok":true,"is_available":true,"currency":"CNY","total_balance":"110.00",...}
```

## 更换 / 作废 Key

在 Netlify 站点环境变量里改 `DEEPSEEK_API_KEY`，改完跑一次 `python netlify_deploy.py --redeploy`；
页面代码不用动。

## 为什么不用 Cloudflare Workers

`workers.dev` 域名在本项目所在网络实测 `http_code=000`（不可达），
而 `*.netlify.app` 实测可达。故改用 Netlify。`worker/` 目录的 CF 版本保留作备选。


---

## 安全加固（2026-10-25 · 外部系统审查 A01/A02）

### 代码侧已修（`edge-functions/qa.js`，需重新部署后生效）

| 项 | 旧行为 | 新行为 |
|---|---|---|
| origin 白名单 | 两条正则放行**任意** `*.github.io` / `*.netlify.app` 子域 | 精确到 `ALLOWED_ORIGINS` 两个本站 origin + localhost |
| POST 鉴权 | `isAllowedOrigin` 只用于构造 CORS 头，请求本身不拒绝（curl 不受 CORS 约束） | `/api/qa` 的 POST 先过来源闸门：不合法/缺失 Origin → **403，不读 body、不触达上游** |
| 请求体 | 零校验：体积/条数/字符/角色均无限制 | 64KB 字节上限（413）、≤30 条消息、单条 ≤4000 字符、总 ≤24000 字符、角色白名单 system/user/assistant（400） |
| max_tokens / temperature | 客户端直传，可传负数/超大值 | 服务端钳制：tokens 1–4000，temperature 0–2 |
| 上游超时 | 无，可永久悬挂 | 非流式 30s、流式 90s（`AbortSignal.timeout`） |
| 兜底透明度 | 上游失败返回 200 + 同构 JSON，前端当 AI 成功渲染并写缓存 | 前端（app.js B06）显式标注「AI 暂不可用，以下为基础检索提示」+ 原因，不进答案缓存 |

守护测试：`node test_qa_proxy.js`（26 断言，vm 沙箱 + mock 上游，零真实额度消耗）。

### ⚠️ 平台侧待办（需 Netlify 账号操作者执行，代码改不动这些）

1. **重新部署**：以上代码修改要 `netlify deploy --prod`（或推送触发自动构建）后才生效。
   部署后自检：`curl -X POST https://mining-daily-qa.netlify.app/api/qa -H 'Content-Type: application/json' -d '{"question":"x"}'`
   应返回 **403 origin not allowed**（无 Origin 头）；带合法 Origin 才放行。
2. **确认 Key 只在环境变量里**：Netlify 后台 Site settings → Environment variables → `DEEPSEEK_API_KEY`。
   仓库与页面任何位置不得出现 Key（`/api/health` 只回 `has_key` 布尔）。
3. **预算/速率防护**（Netlify 免费版无内置限流，代码侧已挡异常来源与超限体，但挡不住
   分布式的合法外观请求）：
   - DeepSeek 开放平台设置**月度预算 + 用量告警**（最有效的一道）；
   - 如后续用量增长，考虑在 Netlify 前加 Cloudflare（Rate Limiting 规则）或迁移到带配额的后端。
4. **不要做的事**：不要把共享密钥写进前端（公开静态页等于公开）；不要把 CORS 当鉴权
   （非浏览器客户端不受其约束——这正是本次加固的根因）。

