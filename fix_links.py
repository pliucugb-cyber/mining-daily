# -*- coding: utf-8 -*-
"""修复 2026-08-29 日报中的 11 条坏链（10 条内容级错配 + cgs 403 实为反爬无需修复）
原因：生成时文章 ID / 栏目路径 / 日期目录被错配或编号不存在。
原则：只替换 URL/标题/摘要，绝不动 <style> 和 <script>。"""

import io, sys

PATH = r"C:\Users\windows\WorkBuddy\2026-08-25-21-20-31\output\mining-daily\index.html"

# (旧串, 新串, 说明) —— URL 替换均为全量替换（每条新闻 3 处）
REPLACEMENTS = [
    # 1. mnr 培训班：/zt/dlfg/2937216 → /dt/ywbb/2937200
    ("https://www.mnr.gov.cn/zt/dlfg/202608/t20260828_2937216.html",
     "https://www.mnr.gov.cn/dt/ywbb/202608/t20260828_2937200.html", "mnr培训班URL"),
    ("自然资源部召开《矿产资源法实施条例》贯彻实施培训班</a>",
     "自然资源部举办矿产资源法实施条例贯彻实施培训班</a>", "mnr标题"),
    ("自然资源部召开《矿产资源法实施条例》贯彻实施培训班，对全国矿业权管理、矿区生态修复、关键矿产资源安全保障等议题进行宣贯部署。",
     "8月25日至26日，自然资源部在武汉举办矿产资源法实施条例贯彻实施培训班，部相关司局围绕地质勘查、矿业权管理、矿产资源勘查开采、矿区生态修复等作系统讲解，160人参加培训。", "mnr摘要"),
    ('data-url="https://www.mnr.gov.cn/dt/ywbb/202608/t20260828_2937200.html" data-embed="block"',
     'data-url="https://www.mnr.gov.cn/dt/ywbb/202608/t20260828_2937200.html" data-embed="ok"', "mnr embed"),

    # 2. 巴西罗查稀土矿：ztjz/10301646 → ztjz/10301647
    ("https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202608/t20260828_10301646.htm",
     "https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202608/t20260828_10301647.htm", "巴西罗查URL"),
    ("巴西罗查稀土矿项目取得重要进展</a>",
     "巴西罗查稀土矿发现更多高品位矿段</a>", "巴西罗查标题"),
    ("南美巴西罗查稀土矿项目公布最新勘查进展，资源量与选冶指标进一步优化，南美关键稀土资源开发提速。",
     "巴西罗查稀土矿阿尔托山矿床在北、南、东侧证实高品位延伸带，共伴生铌钪钽铀品位高，计划钻探5000米进一步圈定矿床范围，新结果尚未纳入资源量估算。", "巴西罗查摘要"),

    # 3. 美能源部：zcdt/10301648 → zcdt/10301646
    ("https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202608/t20260828_10301648.htm",
     "https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202608/t20260828_10301646.htm", "美能源部URL"),
    ("美国能源部资助关键矿产研发项目</a>",
     "美能源部资助关键矿产研发项目</a>", "美能源部标题"),
    ("美国能源部新增资助一批关键矿产（含稀土、锂、钴、镓、锗、镍等）研发项目，强化新能源与军工领域关键矿产产业链。",
     "美国能源部宣布资助7个关键矿产研发项目，涉及重稀土、镓、铜等关键材料，依托CMIH专业技术力量攻关重大技术难题，强化关键矿产产业链。", "美能源部摘要"),

    # 4. 周四矿产品价格：hyyxdt/10301647 → kysc/kcpjg/10301649
    ("https://geoglobal.mnr.gov.cn/zx/kydt/hyyxdt/202608/t20260828_10301647.htm",
     "https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202608/t20260828_10301649.htm", "周四价格URL"),
    ("周四国际矿产品价格行情综述</a>",
     "周四国际矿产品价格多数上涨</a>", "周四价格标题"),
    ("全球矿产资源系统发布周四国际矿产品价格综述：铜、铝、铅、锌、镍、钴、锂、稀土等品种价格走势分化，详情可查询金属价格栏。",
     "周四国际矿产品价格多数上涨：纽约商品交易所黄金收于4600.5美元/盎司（+0.15%），白银69.26美元/盎司（+1.71%），铂、钯亦有上涨。", "周四价格摘要"),

    # 5. 博利登：kygsrtz/10301649 → kygsbg/10301648
    ("https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202608/t20260828_10301649.htm",
     "https://geoglobal.mnr.gov.cn/zx/kygs/kygsbg/202608/t20260828_10301648.htm", "博利登URL"),
    ("博利登完成对北欧矿企的战略并购</a>",
     "博利登并购尼克萨资源公司股份</a>", "博利登标题"),
    ("加拿大博利登（Boliden）完成对一家北欧矿企的战略并购，整合铜、锌、镍等多金属资源，国际矿业并购重组提速。",
     "博利登（Boliden）并购尼克萨资源公司股份，交易完成后将发起自愿现金要约收购剩余全部股份，国际矿业并购重组提速。", "博利登摘要"),

    # 6. 东方测控：61853 → 61851（0828）
    ("https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0828/61853.html",
     "https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0828/61851.html", "东方测控URL"),
    ("东方测控以智能矿山解决方案赋能有色行业数字化转型</a>",
     "东方测控与中铁资源签署战略合作协议 携手推进矿山智能化高质量发展</a>", "东方测控标题"),
    ("东方测控持续输出智能矿山整体解决方案，赋能有色金属采选智能化、少人化、绿色化升级。",
     "东方测控与中铁资源签署战略合作协议，双方将围绕矿山智能化建设开展深度合作，携手推进矿山智能化高质量发展。", "东方测控摘要"),

    # 7. 中国恩菲：61854 → 61850（0828）
    ("https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0828/61854.html",
     "https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0828/61850.html", "恩菲URL"),
    ("中国恩菲承担大型铜冶炼项目主体设计</a>",
     "中国恩菲设计的太平矿业金矿石建设项目TBM始发</a>", "恩菲标题"),
    ("中国恩菲工程技术有限公司承担某大型铜冶炼项目主体设计任务，项目聚焦低碳冶炼、智能控制与多金属综合回收。",
     "8月22日，中国恩菲设计的内蒙古太平矿业浩尧尔忽洞金矿年开采825万吨金矿石建设项目（二标段）TBM始发，标志着项目建设进入关键攻坚阶段。", "恩菲摘要"),

    # 8. 西南铝业：0827/61851（不存在，61851 实为东方测控）→ 0827/61842 西南铝双百标杆
    ("https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0827/61851.html",
     "https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0827/61842.html", "西南铝URL"),
    ("西南铝业高端铝合金板带产能再上新台阶</a>",
     "改革“必答题”的标杆解法——西南铝获评国务院国资委“双百行动”标杆企业</a>", "西南铝标题"),
    ("西南铝业高端铝合金板带产能扩产项目顺利达产，重点服务航空航天、轨道交通、新能源汽车等高端制造领域。",
     "西南铝坚持“两端发力”加快产业迭代，布局高性能宽幅铝合金板带、大规格挤压等重点项目，2025年服务国家战略产品产量较2022年增长32%，获评国务院国资委“双百行动”标杆企业。", "西南铝摘要"),

    # 9. 华中铜业：0827/61852（不存在）→ 0827/61841 华中铜业扭亏密码
    ("https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0827/61852.html",
     "https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0827/61841.html", "华中铜业URL"),
    ("华中铜业高端铜箔技改项目投产</a>",
     "“破”“立”之间见成效——华中铜业的扭亏密码</a>", "华中铜业标题"),
    ("华中铜业高端电解铜箔技改项目正式投产，瞄准新能源汽车、储能及 5G/AI 服务器用铜箔需求。",
     "面对铜价高位震荡、加工费空间收窄压力，华中铜业1—7月实现盈利131万元，加工费总收入同比增长21.63%，冷轧成品月产量连续两个月突破8000吨。", "华中铜业摘要"),

    # 10. 协会报告会：61855（不存在）→ 0825/61822 紫金矿业半年报（同为协会网真实文章，量级相当）
    ("https://www.chinania.org.cn/html/xiehuidongtai/xiehuitongzhi/2026/0827/61855.html",
     "https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0825/61822.html", "紫金URL"),
    ("中国有色金属工业协会举办2026年行业经济运行报告会</a>",
     "紫金矿业主营金属产量稳中有进 价值创造能力持续提升</a>", "紫金标题"),
    ("中国有色金属工业协会举办行业经济运行报告会，邀请权威专家解读2026年有色金属行业经济运行形势、产业政策与下游需求变化。",
     "紫金矿业发布2026年半年报：矿产金47吨（同比+13%）、矿产铜53.4万吨、当量碳酸锂4.4万吨（同比+496%）；巨龙铜矿改扩建建成投产，马诺诺锂矿提前投产，“第三增长极”形成规模贡献。", "紫金摘要"),
    ('<span class="src">中国有色金属工业协会</span> · 08-27</div><div class="news-summary">紫金矿业发布2026年半年报',
     '<span class="src">中国有色金属工业协会</span> · 08-25</div><div class="news-summary">紫金矿业发布2026年半年报', "紫金日期"),
]

def main():
    html = io.open(PATH, encoding="utf-8").read()
    n_ok = 0
    for old, new, label in REPLACEMENTS:
        cnt = html.count(old)
        if cnt == 0:
            print("[MISS] %s —— 未找到旧串，请人工检查：%s" % (label, old[:80]))
            continue
        if old != new:
            html = html.replace(old, new)
        n_ok += 1
        print("[OK]   %s（替换 %d 处）" % (label, cnt))
    io.open(PATH, "w", encoding="utf-8").write(html)
    print("完成：%d/%d 组替换成功" % (n_ok, len(REPLACEMENTS)))
    if n_ok < len(REPLACEMENTS):
        sys.exit(1)

if __name__ == "__main__":
    main()
