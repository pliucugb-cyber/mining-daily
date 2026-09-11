# REFERENCE.md — 矿业日报自动化 查阅类规则外置

> 用途：三套自动化 prompt 已瘦身为「只保留红线 + 指向本文件」。agent 在涉及**白名单核验 / 7 桶分类 / 低价值公告剔除 / 境外信源硬门槛**时，用 Grep 查本文件对应节，不靠记忆。
> 红线（互斥锁协议、LME 口径、矿权单视图、前端自愈引信）**不在此文件**，仍在各自动化 prompt 内，须逐字遵守。
> 本文件只供 agent 查阅，不参与日报构建，勿 git add 到业务提交（属参考文档，可提交但非必需）。

---

## §1 信源白名单（23 域，严禁引入白名单外域）

白名单由 `source_whitelist.py` 强制校验；自动化只需运行 `PY source_whitelist.py --check-file index.html --fail-on-error`，**勿手工维护域列表**。下列供分类/排障时核对。

**国内（14）**
- ky.mnr.gov.cn（矿业权市场，只进 rightsSection）
- mnr.gov.cn / geoglobal.mnr.gov.cn（自然资源部及全球矿产系统）
- cgs.gov.cn（中国地质调查局）
- chinania.org.cn（中国有色金属工业协会）
- cnmn.com.cn（中国有色金属报）
- cngold.org.cn
- chinamining.org.cn
- zgkyb.com（中国矿业报）
- cninfo.com.cn（巨潮，上市公司公告）
- smm.cn（上海有色网）
- antaike.com
- ccmn.cn（长江有色；**mall./ad. 子域已拉黑，勿收**）
- szse.cn（深交所公告，巨潮备份链路）

**境外（9）**
- metal.com（含 news.metal.com，SMM 国际站）
- icsg.org / ilzsg.org / insg.org（铜/铅锌/镍 研究组）
- world-aluminium.org
- lme.com（伦敦金属交易所）
- mining.com（排除 /sponsored-content/、/joint-venture/、servedbyadbutler）
- kitco.com
- gold.org

**已禁（被墙/反爬/付费墙/不可达，勿收）**
reuters、bloomberg、usgs、mining-journal、fastmarkets、cochilco

---

## §2 新闻 7 桶分类（按内容，严禁按信源硬编码）

桶序（与 generate_YYYYMMDD.py 的 THEME_BUCKET 一致）：
💼矿权交易｜🔍找矿成果与勘查技术｜📜政策与监管｜📊市场与价格｜🏭行业动态｜🌐国际矿业动态｜💰并购与投资

**判定原则：按内容不按信源。** 易错边界：
- 海关总署进出口数据 → 📊市场与价格（不是 📜政策与监管）
- 法规宣贯/培训班类 → 📜政策与监管（不是「会议」）
- 国有无对价股权划转 → 🏭行业动态（不是 💰并购与投资）
- 无实质事件的宣传稿 → 🏭行业动态
- 找矿类突破/成果 → 🔍找矿成果与勘查技术（重要条目由前端打⭐战略徽章，不单独建「找矿」分类）
- 并购重组/资产收购转让/对外投资/重大合同中标 → 💰并购与投资
- 投产扩产/停产检修/产量业绩 → 归 💰或 🏭，按事件性质
- 覆盖要求：7 桶都要覆盖，不偏科；🏭占比 >45% 视为偏科需复查

**红线**：category/region 只由 fetch_news.py + classify_llm.py 写；export_news_json.py 已禁止展示层反向覆盖月库。

---

## §3 低价值公告剔除（采编阶段不收，勿进主列表/简报）

**不收（公司治理/信披类，无行业事件价值）**
业绩说明会、投资者关系活动、机构调研、持续督导意见/总结/现场核查、券商核查意见、法律意见书、三会决议、独董换届/声明、异常波动、停复牌、权益变动、减持/增持计划、问询函/关注函/监管函回复、更正/补充公告、召开会议通知、募集说明书/保荐书/评级报告等常规融资流程文件。

**可收（有实质行业事件）**
并购重组、资产收购转让、对外投资、重大合同中标、投产/扩产/停产检修、产量业绩（归 💰并购与投资 或 🏭行业动态）。

> 简报「政策与产业」节须 `drop_notice=True` 走 LOW_VALUE_NOTICE，自动剥离上述治理类。

---

## §4 境外信源硬门槛（收录前必过）

1. **可达性**：收录前 `curl -sL -m15 -A "Mozilla/5.0" <url>`，HTTP 非 000 且正文非空且能取 `<title>` 才收；curl 报 size=0 以 http_code 为准，必要时 python 复测。
2. **已禁域**（见 §1）：reuters/bloomberg/usgs/mining-journal/fastmarkets/cochilco 一律不收。
3. **处理规范**：中文意译术语 + 2–3 句摘要 + 保留英文原题；美元/吨附 ≈元/吨，1oz≈31.1035g；排除 mining.com 的 /sponsored-content/、/joint-venture/、servedbyadbutler；涉华内容只陈述事实；同事件境内外只留 1 条；统一北京时间。
4. **广告清除**：纯广告招商不收，有实质内容可收。
