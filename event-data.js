/* event-data.js —— 【自动生成，勿直接改】
 * 数据源：data/events.json（manual 人工 + review 待审核）
 * 生成器：fetch_events.py（python fetch_events.py --export-only 可重新生成）
 * 维护：人工事件请改 data/events.json 的 manual 区，脚本永不覆盖该区。
 * 字段：id 事件标识 · title 标题 · summary 摘要 · category 类别 · status 状态
 *       priority 优先级 · started 起始日 · timeline 时间线（含 news 关联新闻 URL）
 * 关联新闻 URL 由 window.NEWS_DATA 现查；news 字段仅存稳定 URL，不嵌内容。
 * （不用 id 的原因：news-data.js 为 slim schema，无 id 字段。）
 */
window.EVENT_DATA = {
  updated: '2026-10-25',
  source: '人工维护（data/events.json 的 manual 区）',
  items: [
    { id:'evt_anyuan_pt', title:'江西安远甲水铂矿探矿权转让', summary:'江西省自然资源厅公示（赣自然探转公示〔2026〕60号）：安远县甲水铂矿详查探矿权由江西省地质局第七地质大队转让给安远濂江矿业有限公司。矿种铂矿，面积 1.176 km²，勘查许可证有效期至 2031-06-01。', category:'矿权交易', status:'进行中', priority:'normal', started:'2026-10-24', timeline:[{"date": "2026-10-24", "title": "探矿权转让公示（赣自然探转公示〔2026〕60号）", "detail": "转让方江西省地质局第七地质大队 → 受让方安远濂江矿业有限公司；面积 1.176 km²，勘查许可证有效期至 2031-06-01。", "news": ["https://ky.mnr.gov.cn/zrgs/tkzrgs/202610/t20261024_10343563.htm"], "source": "矿业权市场", "milestone": true}] },
    { id:'evt_us_copper_tariff', title:'美国铜关税博弈：立场未决搅动全球铜市', summary:'白宫对进口精炼铜是否加征 232 条款关税立场未决，铜关税计划陷入停滞；关税预期落空与风险未消交织，成为四季度全球铜价的重要变量。', category:'政策与法规', status:'观察中', priority:'high', started:'2026-09-10', timeline:[{"date": "2026-09-10", "title": "白宫铜关税立场未决，伦铜单日重挫 4.25%", "detail": "当日伦铜收报 14,182.50 美元/吨（-629.50 美元），COMEX 12 月期铜盘中最大跌幅 5.4%；此前交易商因关税预期囤铜，曾推动铜价连续四个交易日创历史新高。", "news": ["https://news.metal.com/en/newscontent/104108744-white-house-undecided-on-copper-tariffs-lme-copper-drops-over-2-amid-market-uncertainty"], "source": "SMM 国际站", "milestone": true}, {"date": "2026-10-01", "title": "铜关税交易降温但风险未消", "detail": "SMM 分析：9 月 29 日午前美国未公布精炼铜关税，COMEX-LME 价差收窄使套利窗口关闭；COMEX 库存已由 32 万短吨升至近 77 万短吨。", "news": ["https://news.metal.com/en/newscontent/104139507-smm-analysis-the-us-copper-tariff-trade-is-fading-but-it-isnt-over-yet"], "source": "SMM 国际站", "milestone": false}, {"date": "2026-10-06", "title": "期货日报：四季度最大变数是美国 232 铜关税", "detail": "前三季度铜价中枢持续上移，9 月 10 日 LME 三个月期铜盘中触及 14,875 美元/吨创历史新高；四季度美国 232 铜关税最终走向及美国铜库存能否回流成为影响铜价的重要变量。", "news": ["https://news.smm.cn/news/104144078"], "source": "上海有色网", "milestone": false}, {"date": "2026-10-24", "title": "花旗：美国铜关税预期落空", "detail": "花旗称今年 LME 周与会者普遍看淡工业金属，理由包括经济增长疲弱、AI 相关风险、能源价格高企、供应增加与美国铜关税预期落空；在能源与关税明朗前对铜维持中性。", "news": ["https://news.smm.cn/news/104176868"], "source": "上海有色网", "milestone": true}] },
    { id:'evt_xinlv_honglian', title:'新铝时代收购东莞宏联电子 100% 股权', summary:'新铝时代以发行股份及支付现金方式向陈旺等 19 名交易对方购买东莞市宏联电子有限公司 100% 股权。', category:'并购与投资', status:'已达成', priority:'normal', started:'2026-08-28', timeline:[{"date": "2026-08-28", "title": "标的资产过户至公司名下", "detail": "东莞市宏联电子有限公司 100% 股权过户至新铝时代名下。", "news": [], "source": "巨潮资讯网", "milestone": true}, {"date": "2026-09-23", "title": "新增股份上市（23,561,616 股）", "detail": "发行股份购买资产对应的新增股份上市。", "news": [], "source": "巨潮资讯网", "milestone": false}, {"date": "2026-10-23", "title": "完成过户公告：过渡期未亏损，交易对方无需补偿", "detail": "审计显示过渡期（2025-04-01 至 2026-08-31）标的资产未发生亏损，收益由公司享有，交易对方无需承担补偿责任。", "news": ["http://static.cninfo.com.cn/finalpage/2026-10-23/1225616022.PDF"], "source": "巨潮资讯网", "milestone": true}] }
  ]
};
