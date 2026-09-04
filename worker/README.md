# 矿业新闻日报 · 轻后端（Cloudflare Workers）

只干一件事：给 GitHub Pages 上的静态前端提供 `/api/qa`（AI 问答，调用 DeepSeek）
和 `/api/health`（健康检查）两个端点。代码与配置全在本目录、进 git，密钥存在
Cloudflare 平台（secret，不落代码）。

> 设计原则：**无状态**。前端把「问题 + 本地已检索到的相关新闻」一起 POST 过来，
> 本函数只负责调 DeepSeek 组织答案。不读任何数据文件、不依赖数据库、不追踪配额。

---

## 一、首次部署（约 5 分钟）

前置：一个 Cloudflare 账号（免费，邮箱注册即可，无需绑卡）。

```bash
cd worker                         # 进入本目录
npm i -g wrangler                # 或：npx wrangler（不全局装也行）
wrangler login                   # 浏览器跳转发授权，绑定你的 Cloudflare 账号

# 把 DeepSeek API key 存为平台 secret（绝不要写进任何文件！）
wrangler secret put DEEPSEEK_API_KEY
# 按提示粘贴 sk-xxxxxxxxxxxxxxxx

wrangler deploy                  # 输出形如：
#   https://mining-daily-qa.<你的子域>.workers.dev
```

拿到上面的 worker URL 后，把它填回前端：

- 打开仓库根目录 `index.html`
- 找到 `var QA_API_BASE='https://mining-daily-qa.YOUR-CF-SUBDOMAIN.workers.dev';`
- 把 `YOUR-CF-SUBDOMAIN` 换成真实子域（即上面 deploy 输出的地址）

然后照常 `python deploy_pages.py` 把前端推到 GitHub Pages 即可。

> 改 `name`（在 `wrangler.toml`）即可换 worker 地址；不改则每次 `wrangler deploy`
> 覆盖同一地址。地址变了记得同步改 `index.html` 的 `QA_API_BASE`。

---

## 二、换电脑后怎么办（重点）

代码、配置、`README`、密钥引用**全在 git 仓库里**，所以换机器只是「重新登录 + 重新部署」，
**不需要迁移任何文件**：

```bash
git clone <本仓库>                # 或在新机打开已有仓库
cd mining-daily/worker
npm i -g wrangler
wrangler login                   # 用同一个 Cloudflare 账号登录（密钥就绑在这个账号上）
wrangler deploy                  # 密钥(secret) 已随账号存在，无需重新 put
```

要点：
- **密钥不随电脑走、也不随 git 走**，它存在你的 Cloudflare 账号里。只要用同一个账号
  `wrangler login`，`wrangler deploy` 会自动复用之前 `secret put` 的 key，无需重设。
- 如果你**换了新的 Cloudflare 账号**，则需要重新 `wrangler secret put DEEPSEEK_API_KEY`。
- 前端 `QA_API_BASE` 指向的是固定 worker 地址；只要该地址不变（不改 `name`），
  前端无需任何改动即可继续工作。

---

## 三、本地调试

想在本机纯前端联调（不部署 worker）时，可用 `server.py` 临时顶替：

```bash
DEEPSEEK_API_KEY=sk-xxx PORT=3000 python server.py
# 然后把 index.html 的 QA_API_BASE 临时改成 'http://127.0.0.1:3000'
```

注意 `server.py` 的 `/api/qa` 目前是关键词兜底版（未接 AI），仅用于验证前端联调；
线上 AI 能力以本 worker 为准。

---

## 四、验证

```bash
node verify_worker.mjs     # 逻辑自测：health / qa(有key) / 兜底 / CORS / 404
```

（`verify_frontend.mjs` 用 jsdom 验证「前端把本地新闻作为 context 传给 /api/qa」，
需能解析到 `jsdom` 模块，依赖 node 实验环境，仅供本地回归。）

端点速查：
- `GET  /api/health` → `{ok, has_key, model, time}`
- `POST /api/qa`      → body `{question, context:[{d,t,s,u}]}`
                       → `{answer, question, source:'deepseek'|'keyword-fallback', cited, refs}`
- CORS：仅放行 `*.github.io` 与 `localhost/127.0.0.1`，防 key 被任意站点盗用。
