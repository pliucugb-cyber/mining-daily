# 腾讯云 SCF 轻后端部署说明（矿业新闻日报 /api/qa + /api/health）

> 为什么从 Cloudflare Workers 迁过来：Workers 的 `*.workers.dev` 在部分公司网络/地区被拦截，
> 浏览器发 POST 直接超时。腾讯云 SCF 是国内节点，同事访问基本不会被墙，DeepSeek 真 AI 可用。
>
> 代码已进 git（`scf/index.py`），key 是云函数环境变量。换电脑不丢：只需 `git clone` + 重新部署。

---

## 前置准备

1. 注册腾讯云账号：https://cloud.tencent.com （需要实名认证，否则无法创建云函数/API 网关）。
2. 准备 DeepSeek API Key：https://platform.deepseek.com （充值一点余额即可，按调用量计费）。

---

## 方式一：控制台手动创建（最直观，推荐首次用）

### 1) 创建云函数

1. 进入 **云函数 SCF** 控制台：https://console.cloud.tencent.com/scf
2. 左上角选地域（建议 **广州 / 上海 / 北京**，离同事近即可）。
3. 点 **新建** → 选择 **「函数」**：
   - 创建方式：**自定义创建**
   - 函数名称：`mining-daily-qa`
   - 运行环境：**Python 3.10**
   - 函数时长：默认 3s，建议改 **30s**（DeepSeek 有时要 10~25s）
   - 内存：默认 128MB 即可
   - 提交方法：**在线编辑**（把 `scf/index.py` 全文粘贴进 `index.py`）
   - 执行方法：`index.main_handler`（函数名默认就是 main_handler，确认入口是 `index.main_handler`）
4. 点 **完成**。

### 2) 配置环境变量（key 不落代码）

1. 在刚创建的函数里，左侧切到 **函数配置** → **环境变量**。
2. 新增：
   - Key：`DEEPSEEK_API_KEY`
   - Value：你的 DeepSeek key（如 `sk-xxxx`）
3. 保存。

### 3) 创建 API 网关触发（对外暴露 HTTP）

1. 函数左侧 **触发管理** → **创建触发器**：
   - 触发类型：**API 网关触发**
   - 勾选 **「新建 API 服务」**（或复用已有）
   - 请求方法：**ANY**（一次覆盖 GET/POST/OPTIONS，函数内自己路由）
   - 发布环境：**release**
   - 鉴权方式：**免鉴权**
   - 路径：`/`（或 `/api`，函数在内部按 `/api/health`、`/api/qa` 路由）
2. 创建后，触发器会显示一个 **访问路径**，形如：
   ```
   https://service-xxxxx-1234567890.apigw.tencentcs.com/release/
   ```
   复制这个 URL（**不带末尾文件名，保留 `/release` 路径**）。

### 4) 发布 API

1. 进入 **API 网关** 控制台：https://console.cloud.tencent.com/apigw
2. 找到刚建的服务 → **服务** → **API 管理**，确认 API 已存在。
3. 点 **发布**，环境选 `release`，备注随便写。
4. 最终可访问地址：
   - 健康检查：`https://<上面那个域名>/release/api/health`
   - 问答：`https://<上面那个域名>/release/api/qa`

> 注意路径：前端 `QA_API_BASE` 填的是 **`https://<域名>/release`**（不带具体 api 路径），
> 函数内部会拼 `/api/health`、`/api/qa`。所以网关里 API 路径必须包含 `/api/...`，
> 即在网关创建 API 时路径填 `/api/{path+}`（或分别建 `/api/health`、`/api/qa` 两个，都指向本函数）。

### 5) 填回前端并发布

1. 打开 `index.html`，把顶部：
   ```js
   var QA_API_BASE='https://REPLACE-ME.apigw.tencentcs.com/release';
   ```
   改成你拿到的真实地址，例如：
   ```js
   var QA_API_BASE='https://service-xxxxx-1234567890.apigw.tencentcs.com/release';
   ```
2. 提交并发布 GitHub Pages：
   ```bash
   git add index.html
   git commit -m "chore: set QA_API_BASE to Tencent SCF API gateway URL"
   git push origin main
   python deploy_pages.py
   ```

---

## 方式二：Serverless Framework 一键部署（可进 git，换电脑最省心）

> 适合以后要反复部署/换电脑的场景。代码和配置都在仓库里，换机 `sls deploy` 即可。

1. 安装 Serverless Framework（用 WorkBuddy 自带 Node）：
   ```bash
   export PATH="$PATH:/c/Users/中铝矿业投并部/.workbuddy/binaries/node/versions/22.22.2-2"
   npm i -g serverless
   ```
2. 在 `scf/` 下创建 `serverless.yml`（已提供模板 `scf/serverless.yml`）：
   ```yaml
   service: mining-daily-qa
   provider:
     name: tencent
     runtime: Python3.10
   plugins:
     - serverless-tencent-scf
   functions:
     qa:
       handler: index.main_handler
       runtime: Python3.10
       timeout: 30
       environment:
         DEEPSEEK_API_KEY: ${env:DEEPSEEK_API_KEY}
       events:
         - apigw:
             name: miningDailyQaApigw
             parameters:
               protocols:
                 - https
               serviceName: mining-daily-qa
               description: 矿业新闻日报 AI 后端
               environment: release
               endpoints:
                 - path: /api/{path+}
                   method: ANY
   ```
3. 登录腾讯云并部署：
   ```bash
   export PATH="$PATH:/c/Users/中铝矿业投并部/.workbuddy/binaries/node/versions/22.22.2-2"
   export DEEPSEEK_API_KEY='sk-你的key'
   serverless deploy   # 或 sls deploy
   ```
   部署成功会输出 API 网关 URL，填回 `index.html` 的 `QA_API_BASE` 即可。

---

## 换电脑恢复步骤

代码、配置全在 git，key 在云函数环境变量（控制台或 serverless.yml 用 `${env:DEEPSEEK_API_KEY}` 注入）：

```bash
git clone <你的仓库>
cd mining-daily
# 方式二：装好 serverless 后
export DEEPSEEK_API_KEY='sk-你的key'
export PATH="$PATH:/c/Users/中铝矿业投并部/.workbuddy/binaries/node/versions/22.22.2-2"
serverless deploy
# 方式一：登录腾讯云控制台，按上面步骤重新粘贴 index.py + 设环境变量 + 发布 API
```

无需迁移任何本地文件、无需重设 key（key 已绑定在腾讯云账号下）。

---

## 本地验证（不发起真实请求）

```bash
python scf/verify_scf.py
```

会 mock DeepSeek 调用，验证 OPTIONS 预检、/api/health、/api/qa、CORS 白名单、base64 body 解析共 16 项。
全部 PASS 说明函数逻辑正确，部署后浏览器就能真正调通 DeepSeek。

---

## 排错

| 现象 | 原因/处理 |
|---|---|
| 页面 AI 按钮显示「待配置」 | `QA_API_BASE` 还是 `REPLACE-ME` 占位符，或探测被代理拦截。按 F12 Console 看 `[qaAiProbe]` 日志。 |
| 点 AI 报 Failed to fetch | 浏览器到 API 网关网络不通；确认 URL 路径含 `/release`，且网关已发布。 |
| /api/health 返回 `has_key:false` | 环境变量 `DEEPSEEK_API_KEY` 没配或配错，去函数配置补上并保存。 |
| 回答是关键词模板而非真 AI | 同上是无 key 兜底模式；配好 key 即变真 AI。 |
| 网关 404 | API 路径没映射到 `/api/...`，在网关里确认 `/api/{path+}` 或分别建 `/api/health`、`/api/qa`。 |
| CORS 报错 | 来源不是 `*.github.io` 或 localhost；检查前端部署域名，或临时把 `is_allowed_origin` 放宽。 |
