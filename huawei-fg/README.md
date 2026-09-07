# 华为云 FunctionGraph 部署指南（后端共享 DeepSeek key）

腾讯云 API 网关触发器已下线、函数 URL 域名 `tencentscf.com` 解析不到，阿里云 FC 域名测试又被我给错格式。这个方案用 **华为云函数工作流 FunctionGraph + API 网关触发器**，域名 `functiongraph.cn-north-4.myhuaweicloud.com` 已确认可解析，更踏实。

---

## 先快速确认：你公司网络能通华为云

在 **电脑 + 手机** 浏览器打开：

```
https://functiongraph.cn-north-4.myhuaweicloud.com
```

| 电脑 | 手机 |
|------|------|
| ? | ? |

- 如果能解析（出现 404/403/502/错误页都算通）→ 继续部署
- 如果显示 NXDOMAIN / 无法访问 → 告诉我

---

## 第一步：登录华为云控制台

1. 浏览器打开：https://www.huaweicloud.com
2. 用手机号/华为账号登录
3. 顶部搜索框输入：**函数工作流 FunctionGraph** → 进入

> 首次使用可能需要实名认证 + 开通服务。

---

## 第二步：创建函数

进入 FunctionGraph 控制台 → 左侧「函数」→ 右上角 **「创建函数」**：

| 配置项 | 怎么选 |
|--------|--------|
| 创建方式 | 空白函数 |
| 函数类型 | 事件函数 |
| 函数名称 | `mining-daily-qa` |
| 运行时 | **Python 3.10** |
| 企业项目 | 默认 |

点 **创建函数**。

---

## 第三步：粘贴代码

进入函数详情页 → 「代码」标签：

1. 左侧默认文件（`index.py`）里的内容**全部删掉**
2. 把本目录下 `index.py` 的内容**完整复制粘贴**进去
3. 点上方 **「保存并部署」**

> 代码入口函数是 `handler(event, context)`，对应执行方法 `index.handler`（华为云默认就是这个）。

---

## 第四步：设置环境变量（放 DeepSeek key）

1. 函数详情页 → 「配置」标签 → 「环境变量」
2. 点「添加环境变量」
3. 填写：

| 变量名 | 变量值 |
|--------|--------|
| `DEEPSEEK_API_KEY` | 你的 DeepSeek API key（`sk-` 开头） |

4. 点 **保存**

> 你的 key 不要发给别人，也不要写进代码。只放在华为云后台环境变量里。

---

## 第五步：创建 API 网关触发器

1. 函数详情页 → 「设置」标签 → 「触发器」
2. 点「创建触发器」
3. 触发器类型选择：**API 网关服务 APIG**
4. 配置：

| 配置项 | 怎么选 |
|--------|--------|
| API 名称 | `mining-daily-api` |
| 分组 | 默认（或新建一个） |
| 请求方法 | 全选：`GET`、`POST`、`PUT`、`DELETE`、`HEAD`、`OPTIONS` |
| 鉴权方式 | **无认证** |
| 后端超时 | **30000 ms**（30 秒） |
| 集成响应 | 保持默认 |

5. 点 **确定**

华为云会生成一个调用 URL，形如：

```
https://xxxxxxxx.apigw.cn-north-4.myhuaweicloud.com
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
https://xxxxxxxx.apigw.cn-north-4.myhuaweicloud.com/api/health
```

如果看到类似下面的文字，说明后端通了：

```json
{"ok": true, "has_key": true, "model": "deepseek-chat", ...}
```

- `has_key: true` 表示 key 已配置上
- 如果显示 `has_key: false`，说明环境变量没填对

---

## 第七步：把 URL 填回网页

1. 复制你的华为云 API 网关 URL（不带 `/api/health`，只到 `.com`）
2. 打开项目里的 `index.html`
3. 搜索 `QA_API_BASE`
4. 把占位地址换成你的真实 URL：

```javascript
var QA_API_BASE = 'https://xxxxxxxx.apigw.cn-north-4.myhuaweicloud.com';
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
- **费用**：FunctionGraph 有免费额度，一般日调用几十次不要钱。具体看华为云账单。
- **key 安全**：key 只存在华为云环境变量，网页源码里没有，同事也看不到。
- **多人共用**：同事直接打开网页就能用 AI，不需要各自输入 key。

---

## 如果这一步卡住了

卡在哪一步，把以下信息截图发给我：
1. 控制台当前页面
2. 浏览器里 `/api/health` 访问结果
3. 函数日志（FunctionGraph 控制台 → 函数详情 → 监控 → 日志）
