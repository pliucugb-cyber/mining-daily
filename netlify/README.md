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
| `netlify.toml` | 路由 `/api/*` + 安全响应头 |
| `public/.gitkeep` | 占位（本站点不托管页面） |

## 部署（三种方式，任选其一）

### 方式 A：Netlify 网页拖拽（Key 不经手任何人，最安全）

1. 打开 <https://app.netlify.com/drop>，把 `netlify` 目录整个拖进去
2. 站点设置 → Environment variables → 新增 `DEEPSEEK_API_KEY` = 你的 Key
3. Deploys → Trigger deploy
4. 把站点域名（形如 `https://xxxx-xxxx.netlify.app`）填回 `index.html` 的 `QA_API_BASE`

### 方式 B：Netlify CLI（可脚本化）

```bash
cd netlify
npm i -g netlify-cli          # 或 npx netlify
netlify login                 # 绑定账号（换电脑重做这步即可）
netlify sites:create --name mining-daily-qa
netlify env:set DEEPSEEK_API_KEY "<你的Key>"
netlify deploy --prod
```

### 方式 C：连 GitHub 仓库自动部署

Netlify 新建站点 → Import from Git → 选本仓库 → Base directory 填 `netlify` →
环境变量填 `DEEPSEEK_API_KEY` → 之后推送即自动部署。

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

只需在 Netlify 站点环境变量里改 `DEEPSEEK_API_KEY`，**无需改代码、无需重新部署页面**。

## 为什么不用 Cloudflare Workers

`workers.dev` 域名在本项目所在网络实测 `http_code=000`（不可达），
而 `*.netlify.app` 实测可达。故改用 Netlify。`worker/` 目录的 CF 版本保留作备选。
