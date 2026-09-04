#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
矿业新闻日报生成脚本 - 2026-09-01
"""
import os
import re
from datetime import datetime

TODAY = datetime(2026, 9, 1)
TODAY_STR = TODAY.strftime("%Y-%m-%d")
TODAY_CN = TODAY.strftime("%Y年%m月%d日")
WEEKDAY = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][TODAY.weekday()]

# ============ 今日新增新闻数据 ============
today_news = {
    "找矿成果与勘查技术": [
        {
            "title": "希尔威金属矿业公布吉尔吉斯金矿重大勘探成果",
            "url": "https://www.cnmn.com.cn/ShowNews1.aspx?id=473401",
            "src": "中国有色网",
            "date": "08-26",
            "summary": "希尔威金属矿业公布吉尔吉斯斯坦金矿项目重大勘探成果，海外金矿资源勘查取得关键进展。",
            "embed": "ok"
        },
        {
            "title": "全国勘查地球化学找矿与分析技术培训交流会在江苏连云港举办",
            "url": "https://www.geosociety.org.cn/?v1=v14&v4=v15&v2=6a62d50844e67&v3=v41",
            "src": "中国地质学会",
            "date": "08-24",
            "summary": "全国勘查地球化学找矿与分析技术培训交流会在江苏连云港举办，聚焦地球化学找矿方法、分析技术及应用实践。",
            "embed": "ok"
        },
    ],
    "矿权交易": [
    ],
    "行业动态": [
        {
            "title": "加拿大矿业公司Auro Metals再获496米厚大矿段 高品位矿段金品位达1.12克/吨",
            "url": "https://www.cnmn.com.cn/ShowNews1.aspx?id=473461",
            "src": "中国有色网",
            "date": "08-31",
            "summary": "加拿大Auro Metals公司勘探取得重大突破，新发现496米厚大矿段，其中高品位矿段金品位达1.12克/吨，海外金矿勘查成果亮眼。",
            "embed": "ok"
        },
        {
            "title": "西北有色地矿集团七一一总队深耕地勘主业聚力实现新突破",
            "url": "https://www.cnmn.com.cn/ShowNews1.aspx?id=473589",
            "src": "中国有色网",
            "date": "08-31",
            "summary": "西北有色地矿集团七一一总队持续深耕地质勘查主业，在矿产勘查与资源发现领域实现新突破，聚焦有色金属找矿。",
            "embed": "ok"
        },
        {
            "title": "金川镍钴承压奋进攀高逐新",
            "url": "https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0831/61862.html",
            "src": "中国有色金属工业协会",
            "date": "08-31",
            "summary": "金川集团镍钴产业在压力中持续奋进，围绕镍、钴等关键矿产提升资源保障与产业竞争力，奋力攀登高质量发展新高度。",
            "embed": "ok"
        },
        {
            "title": "【谱写\"十五五\"有色新篇章】利润总额同比大增98% 中国铝业中期增速再创历史新高",
            "url": "https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0831/61856.html",
            "src": "中国有色金属工业协会",
            "date": "08-31",
            "summary": "中国铝业发布中期业绩，利润总额同比大增98%，增速再创历史新高，铝产业高质量发展动能强劲。",
            "embed": "ok"
        },
        {
            "title": "2026年08月24日稀土价格指数",
            "url": "http://www.ac-rei.org.cn/article/0a0d05a6-7f7c-4ee7-a5d6-06af20c68123",
            "src": "中国稀土行业协会",
            "date": "08-24",
            "summary": "中国稀土行业协会发布2026年8月24日稀土价格指数，反映国内稀土市场行情变动。",
            "embed": "ok"
        },
    ],
    "国际矿业动态": [
        {
            "title": "智阿秘玻四国成立关键矿产联盟",
            "url": "https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202608/t20260831_10302802.htm",
            "src": "全球矿产资源",
            "date": "08-31",
            "summary": "智利、阿根廷、秘鲁、玻利维亚四国宣布成立关键矿产联盟，加强锂、铜等战略性矿产供应链合作与资源安全协调。",
            "embed": "ok"
        },
        {
            "title": "西澳州纳纳迪铜金矿钻探见厚富矿体",
            "url": "https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202608/t20260831_10302803.htm",
            "src": "全球矿产资源",
            "date": "08-31",
            "summary": "西澳大利亚州纳纳迪铜金矿项目最新钻探见厚富矿体，铜金勘查取得重要进展，为海外铜金资源开发提供新靶区。",
            "embed": "ok"
        },
        {
            "title": "智利和阿根廷推进跨边界铜矿开发",
            "url": "https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202608/t20260831_10302801.htm",
            "src": "全球矿产资源",
            "date": "08-31",
            "summary": "智利与阿根廷两国就跨边界铜矿开发达成共识，推进安第斯山脉铜矿带资源整合与基础设施互联互通。",
            "embed": "ok"
        },
    ],
    "培训与学术": [
        {
            "title": "中国稀土集团2026年安全环保绿色低碳专题研修班开班",
            "url": "https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0831/61861.html",
            "src": "中国有色金属工业协会",
            "date": "08-31",
            "summary": "中国稀土集团举办2026年安全环保绿色低碳专题研修班，推动稀土产业绿色低碳转型与可持续发展。",
            "embed": "ok"
        },
    ],
}

# ============ 往期内容（昨日"今日新增"移入） ============
archive_news = {
    "政策法规": [
        {
            "title": "下半年财政部将及时谋划出台务实管用的增量政策",
            "url": "https://www.chinania.org.cn/html/zcfg/zhengcefagui/2026/0825/61821.html",
            "src": "中国有色金属工业协会",
            "date": "08-25",
            "summary": "财政部表示下半年将及时谋划出台务实管用的增量政策，支撑有色金属产业绿色低碳、智能制造、关键矿产供给。",
            "embed": "block"
        },
    ],
    "找矿成果与勘查技术": [
        {
            "title": "中国恩菲设计的太平矿业金矿石建设项目TBM始发",
            "url": "https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0828/61850.html",
            "src": "中国有色金属工业协会",
            "date": "08-28",
            "summary": "8月22日，中国恩菲设计的内蒙古太平矿业浩尧尔忽洞金矿年开采825万吨金矿石建设项目（二标段）TBM始发，标志着项目建设进入关键攻坚阶段。",
            "embed": "block"
        },
        {
            "title": "探矿工程所\"一种超短半径水平井造斜段轨迹控制系统\"获国家发明专利授权",
            "url": "https://www.cgs.gov.cn/ywdt/dwdt/202608/t20260821_867102.html",
            "src": "中国地质调查局",
            "date": "08-24",
            "summary": "中国地质调查局探矿工程所研发的超短半径水平井造斜段轨迹控制系统获国家发明专利授权，为深部找矿与关键矿产勘查提供装备支撑。",
            "embed": "ok"
        },
    ],
    "矿权交易": [
        {
            "title": "湖南省株洲市芦淞区长垅矿区金矿普查探矿权网上挂牌出让公告",
            "url": "https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260828_10300653.htm",
            "src": "矿业权市场",
            "date": "08-28",
            "summary": "湖南省株洲市芦淞区长垅矿区金矿普查探矿权以网上挂牌方式公开出让，主矿种为金矿，助力区域金矿勘查开发。",
            "embed": "ok"
        },
        {
            "title": "广西灌阳县新圩镇深浦源铅锌矿勘查探矿权网上挂牌出让公告",
            "url": "https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260826_10298777.htm",
            "src": "矿业权市场",
            "date": "08-25",
            "summary": "广西灌阳县新圩镇深浦源铅锌矿勘查探矿权以网上挂牌方式出让，主矿种为铅、锌，区域有色金属勘查再添新项目。",
            "embed": "ok"
        },
        {
            "title": "吉林省磐石市石咀铜矿勘查探矿权挂牌出让公告",
            "url": "https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260826_10298758.htm",
            "src": "矿业权市场",
            "date": "08-25",
            "summary": "吉林省磐石市石咀铜矿勘查探矿权挂牌出让，主矿种为铜，推动东北地区铜矿勘查工作。",
            "embed": "ok"
        },
        {
            "title": "吉林省舒兰市长发屯地区铜及多金属矿勘查探矿权挂牌出让公告",
            "url": "https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260827_10299659.htm",
            "src": "矿业权市场",
            "date": "08-27",
            "summary": "吉林省舒兰市长发屯地区铜及多金属矿勘查探矿权挂牌出让，起始价446万元，区域有色金属勘查持续推进。",
            "embed": "ok"
        },
        {
            "title": "福建省自然资源厅矿业权出让合同管理两份文件公开征求意见",
            "url": "https://www.shumx.com/kyzixun_detail/id/11194.html",
            "src": "上海联合矿权交易所",
            "date": "08-24",
            "summary": "福建省自然资源厅就矿业权出让合同管理相关文件公开征求意见，规范矿业权出让合同管理。",
            "embed": "block"
        },
        {
            "title": "关于公开征求《自然资源部关于规范矿业权管理有关事项的通知（征求意见稿）》意见的公告",
            "url": "https://www.mnr.gov.cn/gk/tzgg/202608/t20260824_2936891.html",
            "src": "自然资源部",
            "date": "08-24",
            "summary": "为贯彻落实《矿产资源法》《矿产资源法实施条例》，规范矿业权管理，推动矿产资源合理开发利用和增储上产，提高矿产资源保障能力，自然资源部起草通知征求意见稿。",
            "embed": "block"
        },
        {
            "title": "广西德保县登力-田阳古美矿区沉积型铝土矿勘查探矿权网上挂牌出让公告",
            "url": "https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260826_10298776.htm",
            "src": "矿业权市场",
            "date": "08-26",
            "summary": "广西沉积型铝土矿勘查探矿权挂牌出让公告发布。",
            "embed": "ok"
        },
        {
            "title": "安徽省自然资源厅关于采矿权\"南陵县冲口铜矿\"转让信息的公示",
            "url": "https://ky.mnr.gov.cn/zrgs/ckzrgs/202608/t20260828_10300645.htm",
            "src": "矿业权市场",
            "date": "08-27",
            "summary": "安徽省自然资源厅对南陵县冲口铜矿采矿权转让信息进行公示，转让方与受让方信息已披露。",
            "embed": "ok"
        },
        {
            "title": "湖南省溆浦县后溪垄矿区金矿普查探矿权网上挂牌出让公告",
            "url": "https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260828_10300654.htm",
            "src": "矿业权市场",
            "date": "08-26",
            "summary": "湖南溆浦县后溪垄金矿普查探矿权以网上挂牌方式公开出让，矿种为金矿，挂牌出让公示期已发布。",
            "embed": "ok"
        },
        {
            "title": "湖南省平江县杨树洞矿区金矿普查探矿权网上挂牌出让公告",
            "url": "https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260828_10300657.htm",
            "src": "矿业权市场",
            "date": "08-26",
            "summary": "湖南省平江县杨树洞金矿普查探矿权以网上挂牌方式出让，矿区位于平江县境内。",
            "embed": "ok"
        },
        {
            "title": "湖南省平江县八里矿区铅锌铌钽矿普查探矿权网上挂牌出让公告",
            "url": "https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260828_10300656.htm",
            "src": "矿业权市场",
            "date": "08-26",
            "summary": "湖南省平江县八里矿区铅锌铌钽矿普查探矿权以网上挂牌方式公开出让，主矿种涵盖铅、锌、铌、钽等多金属。",
            "embed": "ok"
        },
        {
            "title": "辽宁省凤城市青城子镇杨树村金矿普查探矿权协议出让公示",
            "url": "https://ky.mnr.gov.cn/xycrgs/tkq/202608/t20260827_10299679.htm",
            "src": "矿业权市场",
            "date": "08-26",
            "summary": "辽宁凤城市青城子镇杨树村金矿普查探矿权以协议方式出让，公示期已发布。",
            "embed": "ok"
        },
        {
            "title": "四川省丹巴县银槽子金矿勘查探矿权挂牌出让公告",
            "url": "https://www.shumx.com/jiaoyi1_detail/id/2553.html",
            "src": "上海联合矿权交易所",
            "date": "08-24",
            "summary": "四川丹巴县银槽子金矿勘查探矿权以挂牌方式公开出让，主矿种为金矿。",
            "embed": "block"
        },
        {
            "title": "湖南省宁远县老人咀矿区方解石矿普查探矿权网上挂牌出让公告",
            "url": "https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260828_10300655.htm",
            "src": "矿业权市场",
            "date": "08-26",
            "summary": "湖南方解石矿普查探矿权挂牌出让。",
            "embed": "ok"
        },
        {
            "title": "河南省内乡县靳家湾杜槽钒矿详查探矿权转让公示",
            "url": "https://ky.mnr.gov.cn/zrgs/tkzrgs/202608/t20260825_10297606.htm",
            "src": "矿业权市场",
            "date": "08-24",
            "summary": "河南钒矿详查探矿权转让公示发布。",
            "embed": "ok"
        },
        {
            "title": "洛阳双海矿业有限公司嵩县草宝山(含前岭)金矿采矿权转让公示",
            "url": "https://ky.mnr.gov.cn/zrgs/ckzrgs/202608/t20260825_10297604.htm",
            "src": "矿业权市场",
            "date": "08-24",
            "summary": "洛阳嵩县草宝山金矿采矿权转让公示。",
            "embed": "ok"
        },
        {
            "title": "内蒙古自治区多伦县西干沟乡夹皮山周围萤石矿勘查探矿权挂牌出让公告",
            "url": "https://www.shumx.com/jiaoyi1_detail/id/2552.html",
            "src": "上海联合矿权交易所",
            "date": "08-24",
            "summary": "内蒙古多伦县萤石矿勘查探矿权挂牌出让。",
            "embed": "block"
        },
    ],
    "行业动态": [
        {
            "title": "自然资源部持续推进绿色矿山建设",
            "url": "https://www.shumx.com/kyzixun_detail/id/11195.html",
            "src": "上海联合矿权交易所",
            "date": "08-24",
            "summary": "自然资源部介绍绿色矿山建设工作进展，推动矿业绿色低碳转型发展。",
            "embed": "block"
        },
        {
            "title": "2026年有色金属行业经济运行报告会暨有色企业统计信息发布会在济南召开",
            "url": "https://www.cnmn.com.cn/ShowNews1.aspx?id=473538",
            "src": "中国有色网",
            "date": "08-27",
            "summary": "8月26日，中国有色金属工业协会主办的2026年有色金属行业经济运行报告会在济南召开，研判行业形势与高质量发展路径。",
            "embed": "ok"
        },
        {
            "title": "数智赋能护航矿业高质量发展新征程 2026智能矿山高质量发展大会暨数智赋能本质安全论坛召开",
            "url": "https://www.cnmn.com.cn/ShowNews1.aspx?id=473443",
            "src": "中国有色网",
            "date": "08-25",
            "summary": "8月20日，2026智能矿山高质量发展大会在辽宁丹东召开，聚焦数智赋能与矿山本质安全，铜铝锂等金属需求持续增长。",
            "embed": "ok"
        },
        {
            "title": "深化产融协同 共促黄金市场高质量发展——中国黄金协会赴上海黄金交易所拜访交流",
            "url": "https://www.cngold.org.cn/news/show-9515.html",
            "src": "中国黄金协会",
            "date": "08-24",
            "summary": "8月21日，中国黄金协会赴上海黄金交易所拜访交流，双方将在产业调研、风险防控、政策研究等领域协同发力。",
            "embed": "block"
        },
        {
            "title": "新疆有色集团持续推进关键金属增储上产（续）",
            "url": "https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0828/61849.html",
            "src": "中国有色金属工业协会",
            "date": "08-28",
            "summary": "新疆有色集团聚焦铜、镍、锂等关键金属，持续推进增储上产国家级研发项目后续成果转化，攻关硬岩矿产与共伴生资源综合利用。",
            "embed": "block"
        },
        {
            "title": "东方测控与中铁资源签署战略合作协议 携手推进矿山智能化高质量发展",
            "url": "https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0828/61851.html",
            "src": "中国有色金属工业协会",
            "date": "08-28",
            "summary": "东方测控与中铁资源签署战略合作协议，双方将围绕矿山智能化建设开展深度合作，携手推进矿山智能化高质量发展。",
            "embed": "block"
        },
        {
            "title": "改革\"必答题\"的标杆解法——西南铝获评国务院国资委\"双百行动\"标杆企业",
            "url": "https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0827/61842.html",
            "src": "中国有色金属工业协会",
            "date": "08-27",
            "summary": "西南铝坚持\"两端发力\"加快产业迭代，布局高性能宽幅铝合金板带、大规格挤压等重点项目，2025年服务国家战略产品产量较2022年增长32%，获评国务院国资委\"双百行动\"标杆企业。",
            "embed": "block"
        },
        {
            "title": "\"破\"\"立\"之间见成效——华中铜业的扭亏密码",
            "url": "https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0827/61841.html",
            "src": "中国有色金属工业协会",
            "date": "08-27",
            "summary": "面对铜价高位震荡、加工费空间收窄压力，华中铜业1—7月实现盈利131万元，加工费总收入同比增长21.63%，冷轧成品月产量连续两个月突破8000吨。",
            "embed": "block"
        },
        {
            "title": "中国黄金协会发布严正声明 谴责非法黄金交易行为",
            "url": "https://www.cngold.org.cn/news/show-9510.html",
            "src": "中国黄金协会",
            "date": "08-28",
            "summary": "中国黄金协会发布严正声明，强烈谴责非法黄金交易、违规黄金衍生品炒作等行为，提示行业及消费者注意风险。",
            "embed": "block"
        },
        {
            "title": "黄金行业深化产融协同 共建高质量产业生态",
            "url": "https://www.cngold.org.cn/news/show-9511.html",
            "src": "中国黄金协会",
            "date": "08-28",
            "summary": "中国黄金协会组织行业骨干企业深化产融协同，推动黄金产业与金融、贸易及下游应用深度协同，构建高质量产业生态。",
            "embed": "block"
        },
        {
            "title": "紫金矿业主营金属产量稳中有进 价值创造能力持续提升",
            "url": "https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0825/61822.html",
            "src": "中国有色金属工业协会",
            "date": "08-25",
            "summary": "紫金矿业发布2026年半年报：矿产金47吨（同比+13%）、矿产铜53.4万吨、当量碳酸锂4.4万吨（同比+496%）；巨龙铜矿改扩建建成投产，马诺诺锂矿提前投产，\"第三增长极\"形成规模贡献。",
            "embed": "block"
        },
        {
            "title": "关于2026年度有色金属企业管理现代化创新成果审定结果的公示",
            "url": "https://www.chinania.org.cn/html/xiehuidongtai/xiehuitongzhi/2026/0824/61815.html",
            "src": "中国有色金属工业协会",
            "date": "08-24",
            "summary": "中国有色金属工业协会对2026年度有色金属企业管理现代化创新成果审定结果进行公示，覆盖有色行业管理创新成果。",
            "embed": "block"
        },
        {
            "title": "数字孪生贯通采选全链路 中铁资源鹿鸣矿业两项成果入选国家级新质生产力优秀创新成果名录",
            "url": "https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0827/61845.html",
            "src": "中国有色金属工业协会",
            "date": "08-27",
            "summary": "中铁资源鹿鸣矿业的数字孪生贯通采选全链路两项创新成果入选国家级新质生产力名录，标志矿山数字化、智能化升级。",
            "embed": "block"
        },
        {
            "title": "聚集硬核力量 历时五年攻关 新疆有色国家级研发项目通过验收的背后",
            "url": "https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0827/61843.html",
            "src": "中国有色金属工业协会",
            "date": "08-27",
            "summary": "新疆有色集团历时五年攻关的国家级研发项目通过验收，聚焦硬岩矿产、有色金属资源综合利用。",
            "embed": "block"
        },
        {
            "title": "中铝集团攻克高寒矿区生态修复难题",
            "url": "https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0827/61839.html",
            "src": "中国有色金属工业协会",
            "date": "08-27",
            "summary": "中铝集团在高寒矿区生态修复领域取得技术突破，为高海拔有色金属矿山绿色开发提供可推广方案。",
            "embed": "block"
        },
        {
            "title": "利好集聚 锡价有望小幅上涨",
            "url": "https://www.chinania.org.cn/html/hangyetongji/tongji/2026/0825/61828.html",
            "src": "中国有色金属工业协会",
            "date": "08-25",
            "summary": "锡价受供给收紧与电子需求回升支撑，短期有望小幅上涨。",
            "embed": "block"
        },
        {
            "title": "中国五矿推进南部非洲片区工作",
            "url": "https://www.cnmn.com.cn/ShowNews1.aspx?id=473507",
            "src": "中国有色网",
            "date": "08-27",
            "summary": "中国五矿集团积极推进南部非洲片区业务，包括铜、钴、铬、铂族等关键矿产资源开发与社区协作。",
            "embed": "ok"
        },
    ],
    "国际矿业动态": [
        {
            "title": "国际铀价突破90美元/磅关口",
            "url": "https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202608/t20260827_10300644.htm",
            "src": "全球矿产资源",
            "date": "08-27",
            "summary": "周三国际矿产品价格多数上涨，铀价收于90.60美元/磅突破90美元关口；LME铜价持平，镍价下跌，黄金收于4593.7美元/盎司。",
            "embed": "ok"
        },
        {
            "title": "巴西罗查稀土矿发现更多高品位矿段",
            "url": "https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202608/t20260828_10301647.htm",
            "src": "全球矿产资源",
            "date": "08-28",
            "summary": "巴西罗查稀土矿阿尔托山矿床在北、南、东侧证实高品位延伸带，共伴生铌钪钽铀品位高，计划钻探5000米进一步圈定矿床范围，新结果尚未纳入资源量估算。",
            "embed": "ok"
        },
        {
            "title": "周四国际矿产品价格多数上涨",
            "url": "https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202608/t20260828_10301649.htm",
            "src": "全球矿产资源",
            "date": "08-28",
            "summary": "周四国际矿产品价格多数上涨：纽约商品交易所黄金收于4600.5美元/盎司（+0.15%），白银69.26美元/盎司（+1.71%），铂、钯亦有上涨。",
            "embed": "ok"
        },
        {
            "title": "美能源部资助关键矿产研发项目",
            "url": "https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202608/t20260828_10301646.htm",
            "src": "全球矿产资源",
            "date": "08-28",
            "summary": "美国能源部宣布资助7个关键矿产研发项目，涉及重稀土、镓、铜等关键材料，依托CMIH专业技术力量攻关重大技术难题，强化关键矿产产业链。",
            "embed": "ok"
        },
        {
            "title": "博利登并购尼克萨资源公司股份",
            "url": "https://geoglobal.mnr.gov.cn/zx/kygs/kygsbg/202608/t20260828_10301648.htm",
            "src": "全球矿产资源",
            "date": "08-28",
            "summary": "博利登（Boliden）并购尼克萨资源公司股份，交易完成后将发起自愿现金要约收购剩余全部股份，国际矿业并购重组提速。",
            "embed": "ok"
        },
        {
            "title": "第二季度澳大利亚勘查投资创新高",
            "url": "https://geoglobal.mnr.gov.cn/zx/kydt/hyyxdt/202608/t20260828_10301645.htm",
            "src": "全球矿产资源",
            "date": "08-28",
            "summary": "澳大利亚第二季度矿产勘查投资创近年新高，关键矿产（金、铜、镍、锂、稀土）项目增速明显，全球勘查市场延续回暖。",
            "embed": "ok"
        },
        {
            "title": "智利谢拉戈达铜矿更新资源量",
            "url": "https://geoglobal.mnr.gov.cn/zx/kcykf/resources_update/202608/t20260827_10300640.htm",
            "src": "全球矿产资源",
            "date": "08-27",
            "summary": "智利谢拉戈达铜矿公布最新资源量更新成果，铜资源量较此前估算有所提升，反映南美关键铜矿勘查持续推进。",
            "embed": "ok"
        },
        {
            "title": "安大略省威胁切断对美关键矿产供应",
            "url": "https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202608/t20260827_10300641.htm",
            "src": "全球矿产资源",
            "date": "08-27",
            "summary": "加拿大安大略省威胁切断对美关键矿产供应，凸显北美关键矿产供应链地缘风险，相关矿产含镍、锂、铜、钴、稀土等。",
            "embed": "ok"
        },
        {
            "title": "美国防部第三次军需关键矿产招标",
            "url": "https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202608/t20260825_10298748.htm",
            "src": "全球矿产资源",
            "date": "08-25",
            "summary": "美国国防部启动第三次军需关键矿产招标，目标保障军工供应链对稀土、锂、钴、镓、锗等关键矿产的稳定获取。",
            "embed": "ok"
        },
        {
            "title": "格陵兰萨法托克铌稀土矿获勘查许可",
            "url": "https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202608/t20260824_10297598.htm",
            "src": "全球矿产资源",
            "date": "08-24",
            "summary": "格陵兰萨法托克铌稀土矿获颁勘查许可，该项目为大型稀土-铌多金属矿，是新一轮关键矿产勘查的重点项目之一。",
            "embed": "ok"
        },
        {
            "title": "维里迪斯融资开发科罗苏斯稀土矿",
            "url": "https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202608/t20260825_10298753.htm",
            "src": "全球矿产资源",
            "date": "08-25",
            "summary": "澳大利亚维里迪斯公司完成新一轮融资，推进科罗苏斯稀土矿项目开发，海外稀土资源端整合加速。",
            "embed": "ok"
        },
        {
            "title": "美国用量子技术赋能关键矿产填图",
            "url": "https://geoglobal.mnr.gov.cn/zx/kydt/kykj/202608/t20260824_10297596.htm",
            "src": "全球矿产资源",
            "date": "08-24",
            "summary": "美国采用量子技术开展关键矿产地质填图工作，提升识别精度。",
            "embed": "ok"
        },
        {
            "title": "铟泰公司签署布鲁克稀土矿承购协议",
            "url": "https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202608/t20260824_10297599.htm",
            "src": "全球矿产资源",
            "date": "08-24",
            "summary": "铟泰公司签署加拿大布鲁克稀土矿承购协议，海外稀土供应链布局推进。",
            "embed": "ok"
        },
    ],
    "培训与学术": [
        {
            "title": "第六届\"非传统稳定同位素地球化学\"暑期学校在中国地质科学院京区基地举办",
            "url": "https://www.geosociety.org.cn/?v1=v14&v4=v15&v2=6a8bdad842942&v3=v41&v6=1",
            "src": "中国地质学会",
            "date": "08-24",
            "summary": "第六届非传统稳定同位素地球化学暑期学校举办，系统讲解理论、分析技术及其在矿床学等领域应用。",
            "embed": "block"
        },
        {
            "title": "自然资源部举办矿产资源法实施条例贯彻实施培训班",
            "url": "https://www.mnr.gov.cn/dt/ywbb/202608/t20260828_2937200.html",
            "src": "自然资源部",
            "date": "08-28",
            "summary": "8月25日至26日，自然资源部在武汉举办矿产资源法实施条例贯彻实施培训班，部相关司局围绕地质勘查、矿业权管理、矿产资源勘查开采、矿区生态修复等作系统讲解，160人参加培训。",
            "embed": "block"
        },
    ],
}

# ============ 金属价格数据 ============
# 2026-09-01 数据
metal_prices = [
    {"name": "沪铜", "tag": "SHFE", "value": "109,790", "unit": "元/吨", "chg": "▲ +1,110 (+1.02%)", "direction": "up"},
    {"name": "沪铝", "tag": "SHFE", "value": "24,115", "unit": "元/吨", "chg": "▲ +155 (+0.65%)", "direction": "up"},
    {"name": "沪铅", "tag": "SHFE", "value": "16,125", "unit": "元/吨", "chg": "▼ -140 (-0.86%)", "direction": "down"},
    {"name": "沪锌", "tag": "SHFE", "value": "27,070", "unit": "元/吨", "chg": "▲ +715 (+2.71%)", "direction": "up"},
    {"name": "沪锡", "tag": "SHFE", "value": "425,640", "unit": "元/吨", "chg": "▲ +6,060 (+1.44%)", "direction": "up"},
    {"name": "沪镍", "tag": "SHFE", "value": "127,530", "unit": "元/吨", "chg": "▲ +30 (+0.02%)", "direction": "up"},
    {"name": "上海金", "tag": "早盘价", "value": "956.84", "unit": "元/克", "chg": "早盘 956.84 / 午盘 959.97", "direction": ""},
    {"name": "白银", "tag": "Ag(T+D)", "value": "16,375", "unit": "元/千克", "chg": "今开 16,375", "direction": ""},
    {"name": "碳酸锂", "tag": "电池级", "value": "153,785", "unit": "元/吨（SMM折）", "chg": "▲ +550 (+0.36%)", "direction": "up"},
    {"name": "电解钴", "tag": "SMM", "value": "303,025", "unit": "元/吨（SMM折）", "chg": "▼ -403 (-0.13%)", "direction": "down"},
]

# ============ HTML生成 ============

def render_news_item(item, is_new=False):
    new_cls = ' is-new' if is_new else ''
    badge = '<span class="badge-new">NEW</span>' if is_new else ''
    return f'''<div class="news-item{new_cls}" data-url="{item['url']}" data-embed="{item.get('embed', 'ok')}"><div class="news-head"><span class="dot"></span>{badge}<a class="news-title" href="{item['url']}" target="_blank">{item['title']}</a></div><div class="news-meta"><span class="src">{item['src']}</span> · {item['date']}</div><div class="news-summary">{item['summary']}</div><a class="btn-read" href="{item['url']}" target="_blank">查看原文 →</a></div>'''

def render_price_card(p):
    direction_cls = p.get('direction', '')
    return f'''<div class="price-card {direction_cls}"><div class="pc-name">{p['name']} <span class="pc-tag">{p['tag']}</span></div><div class="pc-value">{p['value']}</div><div class="pc-unit">{p['unit']}</div><div class="pc-chg">{p['chg']}</div></div>'''

def render_section(title, icon, items, section_id, extra_cls=''):
    if not items:
        return ''
    count = len(items)
    items_html = '\n'.join(render_news_item(item) for item in items)
    return f'''<div class="section" id="{section_id}">
<div class="section-title{extra_cls}"><span class="icon">{icon}</span> {title}<span class="news-count" id="{section_id.replace('Section', 'Count')}">{count}条</span></div>
{items_html}
</div>'''

def render_subsection(title, icon, items, is_new=False):
    if not items:
        return ''
    count = len(items)
    count_label = f'{count}条新增' if is_new else f'{count}条'
    items_html = '\n'.join(render_news_item(item, is_new) for item in items)
    return f'''<div class="sub-cat">{icon} {title}<span class="sub-count">{count_label}</span></div>
{items_html}'''

# 统计
today_total = sum(len(v) for v in today_news.values())
archive_total = sum(len(v) for v in archive_news.values())
all_total = today_total + archive_total

# 找矿突破专项：从今日新增中筛选命中SPECIAL_KEYWORDS的
SPECIAL_KEYWORDS = ['新一轮找矿','找矿突破','找矿攻坚','找矿行动','战略性矿产','紧缺矿产','大宗矿产','增储上产','增储','新发现矿产地','找矿空间','找矿大局','找矿方向','找矿布局','深地探测','深地工程','深部找矿','深部探测','绿色勘查','攻深找盲','资源安全保障','成矿区带','重点成矿','AI找矿','关键矿产']

def is_special(item):
    text = item['title'] + item['summary']
    # 矿权出让/转让/挂牌/拍卖类公告不进专项
    import re
    if re.search(r'(出让|转让|挂牌|拍卖|成交公示|招拍挂)', item['title']):
        return False
    return any(k in text for k in SPECIAL_KEYWORDS)

def special_cat(item):
    text = item['title'] + item['summary']
    if re.search(r'(通知|意见|规划|方案|部署|政策|条例|办法|战略行动)', text):
        return 'policy'
    if re.search(r'(新发现|矿产地|找矿空间|找矿成果|勘查成果|资源量|重大进展|找矿突破)', text):
        return 'result'
    if re.search(r'(关键矿产|供应链|地缘|资源安全|储备)', text):
        return 'security'
    return 'tech'

special_items = {'policy': [], 'result': [], 'tech': [], 'security': []}
for cat, items in today_news.items():
    for item in items:
        if is_special(item):
            sp_cat = special_cat(item)
            special_items[sp_cat].append(item)

special_total = sum(len(v) for v in special_items.values())

# 生成HTML
html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#1a3a5c">
<link rel="manifest" href="manifest.json">
<link rel="apple-touch-icon" href="icon-192.png">
<link rel="icon" type="image/png" sizes="192x192" href="icon-192.png">
<link rel="icon" type="image/png" sizes="512x512" href="icon-512.png">
<link rel="icon" type="image/png" sizes="192x192" href="icon-192-maskable.png" purpose="maskable">
<link rel="icon" type="image/png" sizes="512x512" href="icon-512-maskable.png" purpose="maskable">
<title>矿业新闻日报 {TODAY_STR}</title>
<style>
'''

# 读取旧文件的style
with open('C:/Users/windows/WorkBuddy/2026-08-25-21-20-31/output/mining-daily/index.html', 'r', encoding='utf-8') as f:
    old_html = f.read()

# 提取style
style_start = old_html.find('<style>') + len('<style>')
style_end = old_html.find('</style>')
style = old_html[style_start:style_end]

html += style
html += f'''</style>
</head>
<body>
<nav class="toc-sidebar" id="tocSidebar">
<div class="toc-title">📑 目录导航</div>
<div class="toc-main-item toc-all active" onclick="showAll();window.scrollTo({{top:0,behavior:'smooth'}})">📋 全部内容 <span class="toc-count" id="tocAllCount">{all_total}</span></div>
<div class="toc-main-item" data-target="specialSection" onclick="scrollToSection('specialSection',this)" style="color:#b45009">⛏️ 找矿专项 <span class="toc-count" id="tocSpecialCount" style="background:#fdf3d7;color:#b45009">{special_total}</span></div>
<div class="toc-main-item" data-target="todaySection" onclick="scrollToSection('todaySection',this)">🔥 今日新增 <span class="toc-count" id="tocTodayCount">{today_total}</span></div>
<div class="toc-main-item" data-target="archiveSection" onclick="scrollToSection('archiveSection',this)">📰 往期内容 <span class="toc-count" id="tocArchiveCount">{archive_total}</span></div>
<div class="toc-main-item" onclick="toggleFavFilter();window.scrollTo({{top:0,behavior:'smooth'}})" style="color:#f39c12">★ 我的收藏 <span class="toc-count" id="tocFavCount" style="background:#fef5e7;color:#f39c12">0</span></div>
<div class="toc-main-item" onclick="toggleHistoryFilter();window.scrollTo({{top:0,behavior:'smooth'}})" style="color:#8e44ad">📋 浏览记录 <span class="toc-count" id="tocHistoryCount" style="background:#f5eef8;color:#8e44ad">0</span></div>
<div class="toc-main-item" data-target="installGuideSection" onclick="scrollToSection('installGuideSection',this)" style="color:#0e7490">📲 安装到桌面 <span class="toc-count" id="tocInstallGuideCount" style="background:#e0f2fe;color:#0e7490">📘</span></div>
<div class="toc-back-top" onclick="window.scrollTo({{top:0,behavior:'smooth'}})">↑ 返回顶部</div>
</nav>
<div class="container">

<div class="header">
<h1>⛏️ 矿业新闻日报 <span class="date-badge">{TODAY_CN} {WEEKDAY}</span></h1>
<div class="sub">每日 9:00 起自动更新（约 9:30 前出今日版本） · 11个信息源 · 聚焦有色金属 · 部门内部参考 · 点击标题查看原文</div>
<div class="install-tip show" id="installTip"><span id="installTipText">📲 手机：浏览器菜单选「<b>添加到桌面 / 添加书签</b>」（微信内先点右上角「···」→ 浏览器中打开）<br>💻 电脑：点 Edge/Chrome 地址栏右侧「<b>安装</b>」图标 → 变成独立窗口软件 ｜ <a href="javascript:void(0)" onclick="scrollToSection('installGuideSection',null)" style="color:#7dd3fc;text-decoration:underline">查看详细说明 ↓</a></span><button class="tip-close" onclick="dismissInstallTip()" title="我知道了">✕</button></div>
</div>
<div class="price-strip" id="priceStrip">
<div class="price-strip-head">
<span class="price-strip-title">📊 金属价格</span>
<span class="price-strip-note">{TODAY_STR} 晨间更新 · 沪期主力/SMM·上金所 · 涨红跌绿</span>
</div>
<div class="price-cards">
'''

for p in metal_prices:
    html += render_price_card(p)

html += f'''</div>
</div>
<div class="stats-bar">
<div class="stat-item"><span class="stat-num new" id="newCount">0</span> 今日新增</div>
<div class="stat-item"><span class="stat-num unread" id="unreadCount">0</span> 条未读</div>
<button class="btn btn-filter" id="filterBtn" onclick="toggleFilter()">只看新增</button>
<button class="btn btn-special" id="specialBtn" onclick="toggleSpecialFilter()" title="只看与新一轮找矿突破战略行动相关的新闻" style="margin-left:8px">⛏️ 专项 <span id="specialCountNum">0</span></button>
<button class="btn btn-restore" onclick="clearAllRead()" title="一键清除所有已读记录，全部恢复为未读状态" style="margin-left:8px">↻ 全部恢复未读</button>
<button class="btn btn-fav" id="favBtn" onclick="toggleFavFilter()" style="margin-left:8px">★ 收藏 <span id="favCount">0</span></button>
<button class="btn btn-history" id="historyBtn" onclick="toggleHistoryFilter()">📋 历史 <span id="historyCount">0</span></button>
<button class="btn btn-allread" onclick="markAllRead()">✓ 全部标为已读</button>
</div>
<!-- ==================== 新一轮找矿突破战略行动·专项 ==================== -->
<div class="section" id="specialSection">
<div class="section-title special"><span class="icon">⛏️</span> 新一轮找矿突破战略行动 · 专项<span class="news-count" id="specialCount"></span></div>
<div class="sp-cat">📌 政策与部署<span class="sub-count" id="spCount-policy">{len(special_items['policy'])}条</span></div>
<div class="sp-list" id="spList-policy">
'''
for item in special_items['policy']:
    html += render_news_item(item, True)

html += f'''</div>
<div class="sp-cat">🏔️ 找矿成果与新发现<span class="sub-count" id="spCount-result">{len(special_items['result'])}条</span></div>
<div class="sp-list" id="spList-result">
'''
for item in special_items['result']:
    html += render_news_item(item, True)

html += f'''</div>
<div class="sp-cat">🔬 勘查技术与装备<span class="sub-count" id="spCount-tech">{len(special_items['tech'])}条</span></div>
<div class="sp-list" id="spList-tech">
'''
for item in special_items['tech']:
    html += render_news_item(item, True)

html += f'''</div>
<div class="sp-cat">🌏 战略矿产与资源安全<span class="sub-count" id="spCount-security">{len(special_items['security'])}条</span></div>
<div class="sp-list" id="spList-security">
'''
for item in special_items['security']:
    html += render_news_item(item, True)

html += '''</div>
</div>
<!-- ==================== 今日新增 ==================== -->
<div class="section" id="todaySection">
<div class="section-title today"><span class="icon">🔥</span> 今日新增（''' + TODAY_STR + ''' 抓取）<span class="news-count" id="todayCount"></span></div>
'''

# 今日新增各子类
for cat_name, items in today_news.items():
    if items:
        icon_map = {
            "找矿成果与勘查技术": "🔍",
            "矿权交易": "💼",
            "行业动态": "🏭",
            "国际矿业动态": "🌐",
            "培训与学术": "🎓",
        }
        icon = icon_map.get(cat_name, "•")
        html += render_subsection(cat_name, icon, items, is_new=True)

html += '''</div>

<!-- ==================== 往期内容 ==================== -->
<div class="section" id="archiveSection">
<div class="section-title"><span class="icon">📰</span> 往期内容（滚动保留最近7天）<span class="news-count" id="archiveCount">''' + str(archive_total) + '''条</span></div>
<div class="fold-toggle" id="foldToggle" style="display:none" onclick="toggleOldFold()">▸ 展开更早内容</div>
'''

# 往期内容各子类
for cat_name, items in archive_news.items():
    if items:
        icon_map = {
            "政策法规": "📜",
            "找矿成果与勘查技术": "🔍",
            "矿权交易": "💼",
            "行业动态": "🏭",
            "国际矿业动态": "🌐",
            "培训与学术": "🎓",
        }
        icon = icon_map.get(cat_name, "•")
        html += render_subsection(cat_name, icon, items, is_new=False)

html += '''</div>

<!-- ==================== 详细安装指引 ==================== -->
<div class="section" id="installGuideSection">
<div class="section-title guide"><span class="icon">📲</span> 安装到桌面 · 详细说明 <span class="news-count" style="background:#cffafe;color:#0e7490">建议收藏本页</span></div>
<div class="guide-intro">本页面是网页，<b>不需要"装软件"</b>。推荐做法：把链接<br><b>① 收藏到浏览器书签</b>（任意浏览器都行——每天打开一次即可）<br>② 或通过浏览器菜单"<b>添加到主屏幕 / 添加到桌面</b>"，桌面会出现一个图标、点图标直达、像App一样。本页面在介绍两种方式的详细操作、适用浏览器和常见坑。</div>

<div class="guide-cols">
<!-- ============== 手机端 ============== -->
<div class="guide-col mobile">
<div class="guide-col-head">📱 手机端 · 把日报添加到桌面</div>
<div class="guide-col-body">
<div class="guide-step gs-mobile"><strong>① 安卓 Chrome（最常见）</strong>右上角「⋮」（三点）→「<b>添加到主屏幕</b>」→ 可改名称（默认"矿业新闻日报"）→「<b>添加</b>」。桌面出图标，点图标直达、全屏显示。</div>
<div class="guide-step gs-mobile"><strong>①' 安卓 Edge / QQ 浏览器 / 360 极速</strong>这几种支持 <b>PWA</b>：菜单选「<b>安装应用 / 添加到主屏幕</b>」→「<b>添加</b>」。比普通"添加到主屏幕"更强——可全屏、有启动动画、离线也能开。</div>
<div class="guide-step gs-mobile"><strong>①'' 安卓三星 / 华为 / 小米 自带浏览器</strong>右上角菜单 → 找「<b>添加到主屏幕</b>」「添加书签到桌面」之类选项，名称略有差异。</div>
<div class="guide-step gs-mobile"><strong>② iPhone Safari / iPad</strong>底部工具栏「<b>分享 □↑</b>」图标 → 滚到下方找「<b>添加到主屏幕</b>」→「<b>添加</b>」。iPhone 没有 PWA 全屏，但桌面图标直达已经很方便。</div>
<div class="guide-step gs-warn"><strong>⚠️ 微信里看不到这些按钮！</strong>必须先点微信右上角「<b>···</b>」 →「<b>在浏览器中打开</b>」（若没这个选项，选「<b>复制链接</b>」→ 打开手机自带的浏览器 → 把链接粘贴进去）。</div>
<div class="guide-step"><small>💡 "添加到桌面"的桌面图标其实是<b>网页书签</b>，不是真正安装App。优点是几乎所有浏览器都支持、不占内存、即加即用；缺点是不像 PWA 那样能离线运行。</small></div>
</div>
</div>

<!-- ============== 电脑端 ============== -->
<div class="guide-col pc">
<div class="guide-col-head">💻 电脑端 · 装成独立窗口软件</div>
<div class="guide-col-body">
<div class="guide-step gs-pc"><strong>方式一：地址栏「安装」图标（推荐，最像 App）</strong>用 <b>Microsoft Edge</b> 或 <b>Google Chrome</b> 打开日报链接 → 看地址栏最右侧有没有一个<b>小方块+下载箭头</b>图标（有的浏览器显示 ⊞ 或 ⬇）→ 鼠标悬停显示「<b>安装 矿业新闻日报</b>」→ 点一下 → 弹窗确认「<b>安装</b>」。会自动：① 桌面生成图标 ②「开始菜单」里出现「矿业新闻日报」 ③ 以后双击图标就打开日报，<b>无地址栏、无标签页、全屏独立窗口</b>。</div>
<div class="guide-step gs-pc"><strong>方式二：菜单「安装」</strong>如果地址栏右侧没图标，可点浏览器右上角「···」菜单 → 找「<b>安装 矿业新闻日报</b>」或「<b>将此网站作为应用安装</b>」选项。</div>
<div class="guide-step gs-pc"><strong>方式三：Ctrl+D 收藏（兜底，所有浏览器都行）</strong>任意浏览器按 <b>Ctrl+D</b>（Mac 是 ⌘+D）→ 可改名称 → 选保存到「<b>书签栏</b>」（或收藏夹）→「完成」。每天打开浏览器点书签直达，无需安装。</div>
<div class="guide-step gs-pc"><small>✅ 支持安装 PWA 的浏览器：<b>Microsoft Edge</b>（Windows 自带，强烈推荐）、<b>Google Chrome</b>、<b>QQ 浏览器（极速模式）</b>、<b>360 极速浏览器</b>、<b>Brave</b>。<br>❌ 不支持 PWA 安装、只能用 Ctrl+D 收藏：Firefox（火狐）、Safari（Mac）、IE、360 安全浏览器。<br>💡 推荐用电脑自带的 <b>Microsoft Edge</b> 即可，零下载，Win10/11 系统自带。</small></div>
</div>
</div>
</div>

<!-- 安装 PWA 的链接 -->
<a class="guide-link" href="https://04bad6570ebc40da9fa12c25c30b6ad3.app.workbuddy.link" target="_blank">📋 复制链接到浏览器：https://04bad6570ebc40da9fa12c25c30b6ad3.app.workbuddy.link</a>

<div class="guide-tip">💡 <b>安装后怎么卸载？</b>手机：长按桌面图标选「删除」；电脑：Edge / Chrome「设置」→「应用」→「已安装的应用」→ 找"矿业新闻日报"→「卸载」。链接收藏在书签：书签栏 → 浏览器「收藏夹管理器」删。本页面随时能在浏览器输入链接打开，不会因为卸载而丢失。</div>
</div>
<!-- ==================== 已归档收藏 ==================== -->
<div class="section" id="archivedFavSection" style="display:none">
<div class="section-title">🗂️ 已归档收藏（原新闻已滚出页面，收藏记录永久保留）<span class="news-count" id="archFavCount">0条</span></div>
<div id="archFavList"></div>
</div>
<div class="footer">
<p>数据来源：自然资源部 · 中国地质调查局 · 矿业权市场 · 中国有色网 · 北京国际矿业权交易所 · 上海联合矿权交易所 · 全球矿产资源信息系统 · 中国地质学会 · 中国黄金协会 · 中国稀土行业协会 · 中国有色金属工业协会</p>
<p>聚焦有色金属：铜镍铅锌铝金银稀土钨钼锡锑锂钴 | 排除：煤炭、石油、天然气、钢铁、铁矿</p>
<p>更新时间：{TODAY_STR} 10:30 | 每日9:00起自动更新（约9:30前完成） | 11个信息源 | 本页新增：已读状态存储于访问者本机浏览器</p>
<p>📱 手机：在浏览器菜单选「<b>添加到主屏幕</b>」｜ 💻 电脑：用 Edge 或 Chrome 点击地址栏右侧「安装」图标 → 独立窗口运行 ｜ <a href="javascript:void(0)" onclick="scrollToSection('installGuideSection',null)" style="color:#1a3a5c;text-decoration:underline">详细说明 ↓</a></p>
<div style="border-top:1px solid #d5dde5;margin:14px 0 10px;padding-top:12px;text-align:left">
<p style="font-size:12px;color:#5b6b7a;line-height:1.8"><b style="color:#3a4a5a">版权与免责声明</b><br>
本页面信息均来源于互联网公开渠道，包括但不限于中国政府机构、行业协会、权威媒体的官方网站及公开新闻报道。所有著作权及其他权利归原机构 / 原媒体所有。<br>
本站仅作<b>信息聚合展示</b>，不存储完整原文，不作任何商业用途；通过「查看原文」链接引导读者返回原网站阅读，以尊重原网站访问流量与运营收益。<br>
如原权利人认为本站所展示的内容存在侵权，请通过邮箱 <a href="mailto:1642988981@qq.com" style="color:#1a3a5c;text-decoration:underline">1642988981@qq.com</a> 联系我们，并提供：① 权利人身份证明；② 涉嫌侵权内容的页面链接；③ 要求删除的具体说明。我们将在收到通知后 <b>3 个工作日内</b>核实并处理。<br>
本站不对所聚合信息的及时性、准确性、完整性作担保；如因信息源变更导致链接失效，概与本站无关。</p>
</div>
</div>
</div>
<script>
'''

# 提取旧文件的script
script_start = old_html.find('<script>') + len('<script>')
script_end = old_html.find('</script>')
script = old_html[script_start:script_end]

html += script
html += '''
</script>
</body>
</html>'''

# 写入文件
output_path = 'C:/Users/windows/WorkBuddy/2026-08-25-21-20-31/output/mining-daily/index.html'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Generated: {output_path}")
print(f"Today news: {today_total}")
print(f"Archive news: {archive_total}")
print(f"Special items: {special_total}")
print(f"Total: {all_total}")
