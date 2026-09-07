# 阿里云函数计算 FC 部署指南（后端共享 DeepSeek key）

腾讯云 API 网关触发器已下线、函数 URL 域名 `tencentscf.com` 解析不到，所以迁移到 **阿里云函数计算 FC**。这是国内最稳的 serverless 后端，同事打开网页即可用 AI，不用每人输入 key。

---

## 先快速确认：你公司网络能通阿里云

阿里云 FC 真正的公网域名后缀是 **`fcapp.run`**。部署后你的函数 URL 会长这样：

```
https://mining-daily-qa-xxxxxxxx.cn-shanghai.fcapp.run
```

在 **电脑 + 手机** 浏览器打开根域测试：

| 测试地址 | 电脑 | 手机 |
|---------|------|------|
| `https://fcapp.run` | ? | ? |

- 如果能解析（出现 404/403/错误页都算通）→ 继续部署
- 如果显示 NXDOMAIN / 无法访问 → 告诉我，换华为云方案

---

## 第一步：登录阿里云控制台

1. 浏览器打开：https://www.aliyun.com
2. 用支付宝/钉钉/淘宝账号扫码或短信登录
3. 顶部搜索框输入：**函数计算 FC** → 点「函数计算 FC3.0」（新版）

> 首次使用可能需要实名认证 + 开通函数计算服务（有免费额度）。

---

## 第二步：创建函数

进入 FC 控制台 → 左侧「函数」→ 右上角蓝色按钮 **「创建函数」**：

| 配置项 | 怎么选 |
|--------|--------|
| 创建方式 | **内置运行时创建** / **使用自定义运行时创建** |
| 函数名称 | `mining-daily-qa` |
| 运行环境 | **Python 3.10** |
| 函数入口 | `index.handler`（默认就是，不用改）|
| 请求处理程序 | 默认 |
| 高级配置 → 超时时间 | **30 秒**（DeepSeek 有时要 10~25 秒）|

点 **创建**。

---

## 第三步：粘贴代码

创建完成后进入函数详情页，会看到一个代码编辑器：

1. 把左侧默认文件（一般是 `index.py` 或 `code.py`）里的内容**全部删掉**
2. 把本目录下 `index.py` 的内容**完整复制粘贴**进去
3. 点上方 **「部署代码」** 或 **「保存并部署」**

> 注意：代码里入口函数是 `handler(event, context)`，对应函数入口 `index.handler`。

---

## 第四步：设置环境变量（放 DeepSeek key）

1. 函数详情页 → 左侧「配置」→「环境变量」
2. 点「编辑」或「新增环境变量」
3. 添加：

| 变量名 | 变量值 |
|--------|--------|
| `DEEPSEEK_API_KEY` | 你的 DeepSeek API key（`sk-` 开头） |

4. 点 **保存**

> 你的 key 不要发给别人，也不要写进代码。只放在阿里云后台环境变量里。

---

## 第五步：创建 HTTP 触发器（让网页能访问）

1. 函数详情页 → 左侧「触发器」
2. 点「创建触发器」
3. 选择触发器类型：**HTTP 触发器**
4. 配置：

| 配置项 | 怎么选 |
|--------|--------|
| 触发器名称 | `mining-daily-http` |
| 请求方法 | 全选：`GET`、`POST`、`PUT`、`DELETE`、`HEAD`、`OPTIONS` |
| 认证方式 | **不开启 JWT 认证** / **无需认证**（公开访问）|

5. 点 **确定**

阿里云会生成一个默认 URL，形如：

```
https://mining-daily-qa-xxxxxxxx.cn-shanghai.fcapp.run
```

或者：

```
https://xxxxxxxx.cn-shanghai.fc.aliyuncs.com
```

**复制这个完整 URL**。

---

## 第六步：测试后端是否可用

在浏览器新标签页打开：

```
<你复制的 URL>/api/health
```

例如：

```
https://mining-daily-qa-xxxxxxxx.cn-shanghai.fcapp.run/api/health
```

如果看到类似下面的文字，说明后端通了：

```json
{"ok": true, "has_key": true, "model": "deepseek-chat", ...}
```

- `has_key: true` 表示 key 已配置上
- 如果显示 `has_key: false`，说明环境变量没填对

如果这一步打不开（超时/NXDOMAIN），告诉我，换其他方案。

---

## 第七步：把 URL 填回网页

1. 复制你的阿里云函数 URL（不带 `/api/health`，只到 `.run` 或 `.com`）
2. 打开项目里的 `index.html`
3. 搜索 `QA_API_BASE`
4. 把占位地址换成你的真实 URL：

```javascript
var QA_API_BASE = 'https://mining-daily-qa-xxxxxxxx.cn-shanghai.fcapp.run';
```

5. 保存文件

---

## 第八步：重新发布网页

打开 Git Bash，进入项目目录后运行：

```bash
cd "C:\Users\中铝矿业投并部\WorkBuddy\2026-09-04-15-18-07"
python deploy_pages.py
```

等它跑完，刷新网页（`Ctrl + Shift + R`），点右下角「问 AI」即可测试。

---

## 后续维护

- **换电脑恢复**：代码在 git 里，重新 clone 后，重复第三~五步即可（key 重新填一次环境变量）。
- **费用**：函数计算有免费额度，一般日调用几十次不要钱。具体看阿里云账单。
- **key 安全**：key 只存在阿里云环境变量，网页源码里没有，同事也看不到。
- **多人共用**：同事直接打开网页就能用 AI，不需要各自输入 key。

---

## 如果这一步卡住了

卡在哪一步，把以下信息截图发给我：
1. 控制台当前页面
2. 浏览器里 `/api/health` 访问结果
3. 函数日志（FC 控制台 → 函数详情 → 调用日志）
