# 腾讯云 SCF 轻后端部署说明（矿业新闻日报 /api/qa + /api/health）

> 为什么从 Cloudflare Workers 迁过来：Workers 的 `*.workers.dev` 在部分公司网络/地区被拦截，
> 浏览器发 POST 直接超时。腾讯云 SCF 是国内节点，同事访问基本不会被墙，DeepSeek 真 AI 可用。
>
> 腾讯云旧「API 网关触发器」已停止新建，本方案改用 **Web 函数 + 函数 URL**，更简单、更稳。
>
> 代码已进 git（`scf/index.py`），key 是云函数环境变量。换电脑不丢：只需 `git clone` + 控制台重新粘贴代码、设环境变量、开函数 URL。

---

## 前置准备

1. 注册腾讯云账号：https://cloud.tencent.com （需要实名认证，否则无法创建云函数）。
2. 准备 DeepSeek API Key：https://platform.deepseek.com （充值一点余额即可，按调用量计费）。

---

## 控制台手动创建（最直观，推荐首次用）

### 1) 创建云函数

1. 进入 **云函数 SCF** 控制台：https://console.cloud.tencent.com/scf
2. 左上角选地域（建议 **广州 / 上海 / 北京**，离同事近即可）。
3. 点 **新建** → 选择 **「从头开始」**：
   - **函数类型：Web 函数**（必须选这个，不要选事件函数）
   - 函数名称：`mining-daily-qa`
   - 运行环境：**Python 3.10**
   - 函数时长：默认 3s，建议改 **30s**（DeepSeek 有时要 10~25s）
   - 内存：默认 128MB 即可
   - 提交方法：**在线编辑**（把 `scf/index.py` 全文粘贴进 `index.py`）
   - 执行方法：`index.main_handler`（函数名默认就是 main_handler，确认入口是 `index.main_handler`）
4. 点 **完成**。

### 2) 粘贴函数代码

1. 在函数代码编辑区，删掉默认代码。
2. 把你电脑上 `scf/index.py` 的内容全文复制粘贴进去：
   - 路径：`C:\Users\中铝矿业投并部\mining-daily\scf\index.py`
3. 点 **保存** 或 **部署**。

### 3) 配置环境变量（key 不落代码）

1. 在函数详情页，左侧切到 **函数配置** → **环境变量**。
2. 新增：
   - Key：`DEEPSEEK_API_KEY`
   - Value：你的 DeepSeek key（如 `sk-xxxx`）
3. 保存。

> key 不要写在代码里，也不要发给别人，只填在腾讯云控制台的环境变量里。

### 4) 开启函数 URL（对外暴露 HTTP）

1. 函数详情页左侧，找到 **函数管理** → **函数 URL**（或「触发管理」→「函数 URL」）。
2. 点 **创建** 或 **开启**。
3. 配置建议：
   - 鉴权方式：**None（公网可访问）**
   - 跨域（CORS）：**由函数代码处理**（因为代码里已经按 `*.github.io` 做了白名单）
4. 保存后，腾讯云会生成一个固定网址，形如：
   ```
   https://mining-daily-qa-xxxxxxxx.gz.apigw.tencentcs.com
   ```
   复制这个 URL。

### 5) 填回前端并发布

1. 打开项目里的 `index.html`，找到：
   ```js
   var QA_API_BASE='https://REPLACE-ME.apigw.tencentcs.com/release';
   ```
2. 把单引号里的内容换成你复制的函数 URL，例如：
   ```js
   var QA_API_BASE='https://mining-daily-qa-xxxxxxxx.gz.apigw.tencentcs.com';
   ```
3. 保存 `index.html`。
4. 打开 Git Bash，进入项目目录并发布：
   ```bash
   cd "C:\Users\中铝矿业投并部\mining-daily"
   python deploy_pages.py
   ```

发布后等 1~2 分钟，打开网页点右下角「问 AI」，能正常回复就说明通了。

---

## 换电脑恢复步骤

代码在 git 里，key 在腾讯云环境变量里：

```bash
git clone <你的仓库>
cd mining-daily
```

然后登录腾讯云控制台：
1. 新建 Web 函数 `mining-daily-qa`
2. 粘贴 `scf/index.py`
3. 设环境变量 `DEEPSEEK_API_KEY`
4. 开函数 URL
5. 把 URL 填回 `index.html` 的 `QA_API_BASE`
6. `python deploy_pages.py`

无需迁移任何本地文件。

---

## 本地验证（不发起真实请求）

```bash
python scf/verify_scf.py
```

会 mock DeepSeek 调用，验证 OPTIONS 预检、/api/health、/api/qa、CORS 白名单、base64 body 解析等。
全部 PASS 说明函数逻辑正确，部署后浏览器就能真正调通 DeepSeek。

---

## 排错

| 现象 | 原因/处理 |
|---|---|
| 页面 AI 按钮显示「待配置」 | `QA_API_BASE` 还是 `REPLACE-ME` 占位符。按 F12 Console 看 `[qaAiProbe]` 日志。 |
| 点 AI 报 Failed to fetch | 浏览器到函数 URL 网络不通；确认 URL 复制完整，且函数 URL 已开启。 |
| /api/health 返回 `has_key:false` | 环境变量 `DEEPSEEK_API_KEY` 没配或配错，去函数配置补上并保存。 |
| 回答是关键词模板而非真 AI | 同上是无 key 兜底模式；配好 key 即变真 AI。 |
| 函数 URL 404 | 检查 `index.py` 是否已保存/部署；路径必须是 `/api/health` 或 `/api/qa`。 |
| CORS 报错 | 来源不是 `*.github.io` 或 localhost；检查前端部署域名，或临时把 `is_allowed_origin` 放宽。 |
