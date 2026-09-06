# -*- coding: utf-8 -*-
"""生成2026-08-27矿业新闻日报HTML"""
import re
import sys
import json
import os

# 命令行参数：--export-json-only 表示只导出结构化JSON，不覆盖index.html（安全验证模式）
EXPORT_JSON_ONLY = '--export-json-only' in sys.argv
INDEX_PATH = r'C:\Users\windows\WorkBuddy\2026-08-25-21-20-31\output\mining-daily\index.html'
JSON_PATH = r'C:\Users\windows\WorkBuddy\2026-08-25-21-20-31\output\mining-daily\mining_news.json'

with open(r'C:\Users\windows\WorkBuddy\2026-08-25-21-20-31\output\mining-daily\index.html','r',encoding='utf-8') as f:
    html=f.read()

# 提取style和script
style_block = re.search(r'<style>.*?</style>',html,re.S).group(0)
script_block = re.search(r'<script>.*?</script>',html,re.S).group(0)

# ============ 今日新增数据 ============
# 一、政策法规
today_news_policy = [
    {
        'url':'https://www.chinania.org.cn/html/zcfg/zhengcefagui/2026/0825/61821.html',
        'title':'下半年财政部将及时谋划出台务实管用的增量政策',
        'src':'中国有色金属工业协会','date':'08-25',
        'summary':'财政部表示下半年将及时谋划出台务实管用的增量政策，涉及宏观经济与产业政策协同方向。'
    },
    {
        'url':'https://www.chinania.org.cn/html/xiehuidongtai/xiehuitongzhi/2026/0824/61815.html',
        'title':'关于2026年度有色金属企业管理现代化创新成果审定结果的公示',
        'src':'中国有色金属工业协会','date':'08-24',
        'summary':'协会对2026年度有色金属企业管理现代化创新成果审定结果进行公示，覆盖有色行业管理创新成果。'
    },
]

# 二、找矿成果与勘查技术
today_news_explore = [
    {
        'url':'https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0825/61825.html',
        'title':'AI赋能铝产业关键在落地',
        'src':'中国有色金属工业协会','date':'08-25',
        'summary':'探讨AI技术在铝产业中落地的关键路径与应用前景，含找矿、智能制造等场景。'
    },
    {
        'url':'https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0825/61830.html',
        'title':'中铝科学院5款创新产品亮相2026世界机器人大会',
        'src':'中国有色金属工业协会','date':'08-25',
        'summary':'中铝科学院5款创新产品亮相世界机器人大会，布局高端材料与智能装备。'
    },
    {
        'url':'https://www.chinania.org.cn/html/xiehuidongtai/xiehuidongtai/2026/0822/61797.html',
        'title':'2026智能矿山高质量发展大会暨数智赋能本质安全论坛召开',
        'src':'中国有色金属工业协会','date':'08-22',
        'summary':'智能矿山高质量发展大会暨数智赋能本质安全论坛召开，推动矿山数字化、智能化转型与本质安全建设。'
    },
]

# 三、矿权交易
today_news_rights = [
    {
        'url':'https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260827_10299659.htm',
        'title':'吉林省舒兰市长发屯地区铜及多金属矿勘查探矿权挂牌出让公告',
        'src':'矿业权市场','date':'08-26',
        'summary':'东北地区铜及多金属矿勘查探矿权挂牌出让，区域有色金属勘查持续推进。'
    },
    {
        'url':'https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260826_10298772.htm',
        'title':'广西玉林市福绵区成均镇甘冲铜铅锌矿勘查探矿权网上挂牌出让公告',
        'src':'矿业权市场','date':'08-25',
        'summary':'广西玉林铜铅锌矿勘查探矿权网上挂牌出让。'
    },
    {
        'url':'https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260826_10298762.htm',
        'title':'新疆巴里坤哈萨克自治县木炭窑金矿勘查挂牌出让公告',
        'src':'矿业权市场','date':'08-25',
        'summary':'新疆巴里坤金矿勘查探矿权挂牌出让。'
    },
    {
        'url':'https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260826_10298763.htm',
        'title':'新疆托里县库札克曼特铜多金属矿勘查挂牌出让公告',
        'src':'矿业权市场','date':'08-25',
        'summary':'新疆托里县铜多金属矿勘查探矿权挂牌出让。'
    },
    {
        'url':'https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260826_10298764.htm',
        'title':'新疆新源县克泽拉夏铁铜多金属矿勘查挂牌出让公告',
        'src':'矿业权市场','date':'08-25',
        'summary':'新疆新源县铁铜多金属矿勘查探矿权挂牌出让。'
    },
    {
        'url':'https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260821_10295716.htm',
        'title':'四川省会理市汪家湾铜矿勘查探矿权挂牌出让公告',
        'src':'矿业权市场','date':'08-20',
        'summary':'四川会理市铜矿勘查探矿权挂牌出让，攀西铜矿资源基地持续布局。'
    },
    {
        'url':'https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260821_10295721.htm',
        'title':'内蒙古自治区多伦县西干沟乡夹皮山周围萤石矿勘查探矿权挂牌出让',
        'src':'矿业权市场','date':'08-20',
        'summary':'萤石为战略性矿产，内蒙古萤石矿勘查探矿权挂牌出让。'
    },
    {
        'url':'https://ky.mnr.gov.cn/zrgs/ckzrgs/202608/t20260825_10297603.htm',
        'title':'北京盛邦佳阳嵩县前河金矿北部采矿权转让公示',
        'src':'矿业权市场','date':'08-24',
        'summary':'嵩县前河金矿北部采矿权转让公示。'
    },
]

# 四、行业动态
today_news_industry = [
    {
        'url':'https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0825/61824.html',
        'title':'《有色钢铁融合发展蓝皮书》发布',
        'src':'中国有色金属工业协会','date':'08-25',
        'summary':'首届有色钢铁融合发展论坛发布《有色钢铁融合发展蓝皮书》。'
    },
    {
        'url':'https://www.chinania.org.cn/html/hangyetongji/tongji/2026/0825/61827.html',
        'title':'供应压力增加 铜价将震荡走强',
        'src':'中国有色金属工业协会','date':'08-25',
        'summary':'供应压力增加背景下，铜价预计将震荡走强。'
    },
    {
        'url':'https://www.chinania.org.cn/html/hangyetongji/tongji/2026/0825/61828.html',
        'title':'利好集聚 锡价有望小幅上涨',
        'src':'中国有色金属工业协会','date':'08-25',
        'summary':'多重利好集聚，锡价预计小幅上涨。'
    },
    {
        'url':'https://www.chinania.org.cn/html/hangyetongji/tongji/2026/0824/61809.html',
        'title':'沪铝能否进一步打开上涨空间',
        'src':'中国有色金属工业协会','date':'08-24',
        'summary':'分析沪铝期货后续走势及上涨空间。'
    },
    {
        'url':'https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0825/61826.html',
        'title':'银粉中试产线产能释放 多项贵金属替代技术取得关键突破',
        'src':'中国有色金属工业协会','date':'08-25',
        'summary':'陕西黄金集团汇创贵材银粉中试产线产能释放，贵金属替代技术取得关键突破。'
    },
    {
        'url':'https://www.cnmn.com.cn/ShowNews1.aspx?id=473442',
        'title':'紫金矿业主营金属产量稳中有进 价值创造能力持续提升',
        'src':'中国有色网','date':'08-25',
        'summary':'紫金矿业作为国内有色金属矿业龙头，主营金属产量稳中有进，价值创造能力持续提升。'
    },
    {
        'url':'https://www.cnmn.com.cn/ShowNews1.aspx?id=473447',
        'title':'五矿中亚南亚山达克铜矿举办"中巴同心绣友谊"文化交流活动',
        'src':'中国有色网','date':'08-24',
        'summary':'五矿集团旗下中亚南亚山达克铜矿（巴基斯坦项目）开展中巴文化交流活动，境外铜矿项目运营动态。'
    },
    {
        'url':'https://www.cngold.org.cn/news/show-9446.html',
        'title':'2026中国国际黄金大会在兰州开幕千余代表共赴金城之约',
        'src':'中国黄金协会','date':'08-25',
        'summary':'2026中国国际黄金大会在兰州开幕，行业年度重要会议聚焦黄金产业高质量发展。'
    },
]

# 五、国际矿业动态
today_news_global = [
    {
        'url':'https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202608/t20260821_10296568.htm',
        'title':'美能源部资助电池矿产和回收项目',
        'src':'全球矿产资源','date':'08-21',
        'summary':'美国能源部资助电池关键矿产与回收项目，聚焦锂钴镍等电池矿产供应链。'
    },
    {
        'url':'https://www.chinania.org.cn/html/hangyetongji/tongji/2026/0817/61755.html',
        'title':'两场联合国会议推动关键矿产全球治理进入新阶段',
        'src':'中国有色金属工业协会','date':'08-17',
        'summary':'联合国两场会议推动关键矿产全球治理进入新阶段，涉及国际矿产治理议题。'
    },
    {
        'url':'https://www.cnmn.com.cn/ShowNews1.aspx?id=473279',
        'title':'智利将采取多举措以实现将铜产量提升至600万吨/年的目标',
        'src':'中国有色网','date':'08-21',
        'summary':'智利作为全球最大产铜国，宣布将采取多项措施推动铜产量提升至600万吨/年目标，全球铜供给格局重大动态。'
    },
    {
        'url':'https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202608/t20260805_10287852.htm',
        'title':'印尼恢复出口可能含稀土产品',
        'src':'全球矿产资源','date':'08-05',
        'summary':'印尼恢复出口可能含稀土产品，东南亚稀土供应链动态。'
    },
    {
        'url':'https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202608/t20260803_10285662.htm',
        'title':'二季度智利铜产量创19年来新低',
        'src':'全球矿产资源','date':'08-03',
        'summary':'二季度智利铜产量创19年来新低，全球铜供给趋紧信号明确。'
    },
    {
        'url':'https://geoglobal.mnr.gov.cn/zx/kydt/zhyw/202608/t20260804_10286887.htm',
        'title':'上半年津巴布韦锂出口额增长2.3倍',
        'src':'全球矿产资源','date':'08-04',
        'summary':'上半年津巴布韦锂出口额同比增长2.3倍，非洲锂资源开发加速。'
    },
    {
        'url':'https://www.chinania.org.cn/html/hangyetongji/tongji/2026/0821/61796.html',
        'title':'供过于求格局延续 工业硅市场短期再度承压',
        'src':'中国有色金属工业协会','date':'08-21',
        'summary':'工业硅市场供过于求格局延续，短期价格再度承压。'
    },
    {
        'url':'https://www.chinania.org.cn/html/hangyetongji/tongji/2026/0821/61795.html',
        'title':'宏观因素托底 黄金维持偏强震荡格局',
        'src':'中国有色金属工业协会','date':'08-21',
        'summary':'宏观因素托底，黄金价格维持偏强震荡格局。'
    },
]

# 六、培训与学术
today_news_edu = [
    {
        'url':'https://www.cngold.org.cn/news/show-9511.html',
        'title':'贵金属周报669期',
        'src':'中国黄金协会','date':'08-25',
        'summary':'本周贵金属市场行情综述，含黄金、白银、铂钯价格走势及供需分析。'
    },
    {
        'url':'https://www.chinania.org.cn/html/hangyetongji/chanyeshuju/2026/0821/61792.html',
        'title':'1—7月份国民经济保持总体平稳、向新向优发展态势',
        'src':'中国有色金属工业协会','date':'08-21',
        'summary':'1—7月国民经济运行数据发布，总体平稳、向新向优发展，有色金属行业景气度持续。'
    },
]

# ============ 旧"今日新增"迁移到往期（仅日期>=08-20的保留，超7天丢弃）============
# 旧HTML里37条今日新增，按日期过滤，丢弃<08-20
archive_from_old_today = [
    {'url':'https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260826_10298776.htm',
     'title':'广西德保县登力-田阳古美矿区沉积型铝土矿勘查探矿权网上挂牌出让公告',
     'src':'矿业权市场','date':'08-25','summary':'沉积型铝土矿勘查探矿权网上挂牌出让，矿种类型与桂西铝土矿成矿带高度相关。'},
    {'url':'https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260826_10298758.htm',
     'title':'吉林省磐石市石咀铜矿勘查探矿权挂牌出让公告',
     'src':'矿业权市场','date':'08-25','summary':'东北地区铜矿勘查探矿权挂牌出让。'},
    {'url':'https://ky.mnr.gov.cn/kyqcrgg/tkq/202608/t20260826_10298777.htm',
     'title':'广西灌阳县新圩镇深浦源铅锌矿勘查探矿权网上挂牌出让公告',
     'src':'矿业权市场','date':'08-25','summary':'铅锌矿勘查探矿权网上挂牌出让。'},
    {'url':'https://ky.mnr.gov.cn/xycrgs/ckq/202608/t20260818_10293050.htm',
     'title':'江西省自然资源厅关于江西铜业德兴铜矿的协议出让（扩深）公示',
     'src':'矿业权市场','date':'08-14','summary':'德兴铜矿采矿权深部扩界协议出让公示，铜矿资源增储。'},
    {'url':'https://www.shumx.com/jiaoyi1_detail/id/2552.html',
     'title':'内蒙古自治区多伦县西干沟乡夹皮山萤石矿勘查探矿权挂牌出让',
     'src':'上海联合矿权交易所','date':'08-24','summary':'萤石为战略性矿产，内蒙古萤石矿勘查探矿权挂牌出让。'},
    {'url':'https://ky.mnr.gov.cn/jggs/jjgs/202608/t20260821_10295714.htm',
     'title':'甘肃省瓜州县花南沟萤石矿详查探矿权挂牌出让结果公示',
     'src':'矿业权市场','date':'08-20','summary':'萤石矿详查探矿权挂牌出让成交结果公示。'},
    {'url':'https://www.shumx.com/jiaoyi1_detail/id/2553.html',
     'title':'四川省丹巴县银槽子金矿勘查探矿权挂牌出让公告',
     'src':'上海联合矿权交易所','date':'08-24','summary':'四川丹巴金矿勘查探矿权挂牌出让。'},
    {'url':'https://ky.mnr.gov.cn/zrgs/ckzrgs/202608/t20260825_10297602.htm',
     'title':'灯塔市瑞河矿业有限公司采矿权转让变更公示',
     'src':'矿业权市场','date':'08-24','summary':'采矿权转让变更公示。'},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kcykf/resources_update/202608/t20260820_10295709.htm',
     'title':'西澳贝塔亨特金矿更新资源量',
     'src':'全球矿产资源','date':'08-20','summary':'澳大利亚贝塔亨特金矿更新资源量。'},
    {'url':'https://www.cnmn.com.cn/ShowNews1.aspx?id=473284',
     'title':'深耕物探科创一线 赋能地质找矿大局——西北有色地矿集团物化探总队陈靖物探创新团队',
     'src':'中国有色网','date':'08-22','summary':'物化探技术创新团队服务地质找矿的纪实报道。'},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kczygl/zcdt/202608/t20260825_10298748.htm',
     'title':'美国防部第三次军需关键矿产招标',
     'src':'全球矿产资源','date':'08-25','summary':'美国国防部第三次军需关键矿产招标，关键矿产地缘动态。'},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202608/t20260825_10298753.htm',
     'title':'维里迪斯融资开发科罗苏斯稀土矿',
     'src':'全球矿产资源','date':'08-25','summary':'维里迪斯公司融资开发科罗苏斯稀土矿。'},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202608/t20260825_10298754.htm',
     'title':'国际铀价逼近90美元/磅',
     'src':'全球矿产资源','date':'08-25','summary':'国际铀价逼近90美元/磅，核能矿产景气度持续。'},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kysc/kcpjg/202608/t20260824_10297600.htm',
     'title':'国际锌价创四年来新高',
     'src':'全球矿产资源','date':'08-24','summary':'国际锌价创四年来新高。'},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202608/t20260824_10297599.htm',
     'title':'铟泰公司签署布鲁克稀土矿承购协议',
     'src':'全球矿产资源','date':'08-24','summary':'铟泰公司签署布鲁克稀土矿承购协议。'},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kygs/kygsyj/202608/t20260821_10296571.htm',
     'title':'伦丁矿业下调2026年铜产量目标',
     'src':'全球矿产资源','date':'08-21','summary':'伦丁矿业下调2026年铜产量目标，全球铜供给趋紧。'},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kygs/kygsrtz/202608/t20260820_10295710.htm',
     'title':'美洲稀土公司推进豪莱克溪供应链',
     'src':'全球矿产资源','date':'08-20','summary':'美洲稀土公司推进豪莱克溪供应链建设。'},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kydt/hyyxdt/202608/t20260820_10295708.htm',
     'title':'BMI：全球矿产品市场存在诸多变数',
     'src':'全球矿产资源','date':'08-20','summary':'BMI分析全球矿产品市场变数。'},
    {'url':'https://www.cnmn.com.cn/ShowNews1.aspx?id=471474',
     'title':'中国恩菲与绿色动力签署战略合作协议',
     'src':'中国有色网','date':'08-22','summary':'中国恩菲工程技术有限公司与绿色动力签署战略合作协议。'},
    {'url':'https://www.cngold.org.cn/news/show-9500.html',
     'title':'2026年上半年我国黄金产量152.908吨，同比下降14.62%',
     'src':'中国黄金协会','date':'08-10','summary':'上半年黄金产量同比下降14.62%，消费量同比增长1.23%。'},
    {'url':'https://www.cngold.org.cn/news/show-9505.html',
     'title':'紫金矿业公布111亿元中期分红方案',
     'src':'中国黄金协会','date':'08-25','summary':'紫金矿业持续增厚股东回报，公布111亿元中期分红方案。'},
    {'url':'https://www.chinania.org.cn/html/hangyetongji/chanyeshuju/2026/0730/61611.html',
     'title':'上半年规模以上工业企业利润同比增长18.7% 有色行业利润增长99.4%',
     'src':'中国有色金属工业协会','date':'07-30','summary':'有色金属行业利润增长99.4%，在全部工业行业中表现突出。'},
    {'url':'https://www.chinania.org.cn/html/hangyetongji/jqzs/2026/0810/61686.html',
     'title':'中国有色金属产业月度景气指数报告（2026年7月）',
     'src':'中国有色金属工业协会','date':'08-10','summary':'2026年7月有色金属产业景气指数报告。'},
    {'url':'https://www.cnmn.com.cn/ShowNews1.aspx?id=473392',
     'title':'黄沙坪矿业铅锌尾矿伴生锡资源分选科研攻关取得重大突破',
     'src':'中国有色网','date':'08-24','summary':'铅锌尾矿伴生锡资源分选技术攻关取得重大突破。'},
    {'url':'https://www.chinania.org.cn/html/xiehuidongtai/xiehuidongtai/2026/0823/61800.html',
     'title':'有色金属行业智能制造暨数字化转型大会在沈阳召开',
     'src':'中国有色金属工业协会','date':'08-23','summary':'有色金属行业智能制造暨数字化转型大会在沈阳召开。'},
]

# 旧"往期"内容（15条）大部分>=08-20，仅2条<08-20被丢弃
archive_from_old_archive = [
    {'url':'https://www.cgs.gov.cn/ywdt/dwdt/202608/t20260818_866863.html',
     'title':'桂北九万大山-元宝山深部及外围找矿空间进一步拓展',
     'src':'中国地质调查局','date':'08-18',
     'summary':'桂北地区深部及外围找矿新进展，找矿空间进一步拓展。','date_discard':True},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kcykf/resources_update/202608/t20260825_10298752.htm',
     'title':'爱达荷州伊玛钨矿公布初估资源量',
     'src':'全球矿产资源','date':'08-25','summary':'美国爱达荷州伊玛钨矿公布初次估算资源量。'},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kcykf/resources_update/202608/t20260821_10296570.htm',
     'title':'西澳州皮特菲尔德成为世界最大钛矿',
     'src':'全球矿产资源','date':'08-21','summary':'西澳皮特菲尔德钛矿成为世界最大钛矿。'},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kcykf/ztjz/202608/t20260824_10297598.htm',
     'title':'格陵兰萨法托克铌稀土矿获勘查许可',
     'src':'全球矿产资源','date':'08-24','summary':'格陵兰萨法托克铌稀土矿获勘查许可。'},
    {'url':'https://www.cnmn.com.cn/ShowNews1.aspx?id=473401',
     'title':'希尔威金属矿业公布吉尔吉斯金矿重大勘探成果',
     'src':'中国有色网','date':'08-24','summary':'希尔威金属矿业公布吉尔吉斯斯坦金矿项目重大勘探成果。'},
    {'url':'https://www.cnmn.com.cn/ShowNews1.aspx?id=473461',
     'title':'加拿大Auro Metals再获496米厚大矿段 金品位达1.12克/吨',
     'src':'中国有色网','date':'08-25','summary':'加拿大Auro Metals钻探再获496米厚大矿段。'},
    {'url':'https://ky.mnr.gov.cn/jggs/jjgs/202608/t20260825_10297609.htm',
     'title':'福建省连城县浦竹洋矿区锰多金属矿探矿权拍卖出让结果公示',
     'src':'矿业权市场','date':'08-24','summary':'锰多金属矿探矿权拍卖出让结果公示。'},
    {'url':'https://ky.mnr.gov.cn/zrgs/tkzrgs/202608/t20260825_10297607.htm',
     'title':'辽宁省建平县喀喇沁镇五家子金矿普查探矿权转让公示',
     'src':'矿业权市场','date':'08-24','summary':'金矿普查探矿权转让公示。'},
    {'url':'https://ky.mnr.gov.cn/zrgs/ckzrgs/202608/t20260825_10297604.htm',
     'title':'洛阳双海矿业嵩县草宝山(含前岭)金矿采矿权转让公示',
     'src':'矿业权市场','date':'08-24','summary':'嵩县金矿采矿权转让公示。'},
    {'url':'https://ky.mnr.gov.cn/zrgs/tkzrgs/202608/t20260822_10296575.htm',
     'title':'山东省烟台市蓬莱区时金河矿区金矿勘探探矿权转让公示',
     'src':'矿业权市场','date':'08-21','summary':'金矿勘探探矿权转让公示。'},
    {'url':'https://www.cgs.gov.cn/ywdt/dwdt/202608/t20260820_866999.html',
     'title':'沈阳地调中心赴蒙古开展地学科技合作交流访问',
     'src':'中国地质调查局','date':'08-20','summary':'沈阳地质调查中心赴蒙古开展地学科技合作交流。'},
    {'url':'https://www.cnmn.com.cn/ShowNews1.aspx?id=473459',
     'title':'云锡控股与国开行云南分行签署战略合作协议',
     'src':'中国有色网','date':'08-25','summary':'云锡控股与国家开发银行云南省分行签署战略合作协议。'},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kydt/kykj/202608/t20260824_10297596.htm',
     'title':'美国用量子技术赋能关键矿产填图',
     'src':'全球矿产资源','date':'08-24','summary':'美国应用量子技术开展关键矿产填图。'},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kczygl/jgbg/202608/t20260821_10296569.htm',
     'title':'秘鲁政府希望矿业项目尽快落地',
     'src':'全球矿产资源','date':'08-21','summary':'秘鲁政府推动矿业项目落地进程。'},
    {'url':'https://geoglobal.mnr.gov.cn/zx/kczygl/jgbg/202608/t20260819_10294923.htm',
     'title':'印尼推进成立矿产和战略商品交易所',
     'src':'全球矿产资源','date':'08-19','summary':'印尼推进矿产和战略商品交易所建设。','date_discard':True},
    {'url':'https://www.geosociety.org.cn/?v1=v14&v4=v15&v2=6a62d50844e67&v3=v41',
     'title':'全国勘查地球化学找矿与分析技术培训交流会在江苏连云港举办',
     'src':'中国地质学会','date':'08-22','summary':'勘查地球化学找矿与分析技术培训交流会。'},
    {'url':'https://www.scdzxh.org.cn?default=xhdt&id=e225005/',
     'title':'四川省地质学会产业科技专家团赴炉霍开展化探副样二次开发技术服务',
     'src':'四川省地质学会','date':'08-12',
     'summary':'四川省地质学会战略性矿产资源勘查领域产业科技专家团赴甘孜州炉霍县开展化探副样二次开发项目技术服务。'},
]

# 过滤掉丢弃项
def keep(d):
    return not d.get('date_discard',False)

archive = [d for d in archive_from_old_today + archive_from_old_archive if keep(d)]
print('Total archive items:',len(archive))

# ============ 构建HTML ============

def make_news_item(d, is_new=True):
    badge = '<span class="badge-new">NEW</span>' if is_new else ''
    return (
        f'<div class="news-item{" is-new" if is_new else ""}" data-url="{d["url"]}">'
        f'<div class="news-head"><span class="dot"></span>{badge}<a class="news-title" href="{d["url"]}" target="_blank">{d["title"]}</a></div>'
        f'<div class="news-meta"><span class="src">{d["src"]}</span> · {d["date"]}</div>'
        f'<div class="news-summary">{d["summary"]}</div>'
        f'<a class="btn-read" href="{d["url"]}" target="_blank">查看原文 →</a>'
        f'</div>'
    )

# 今日新增六分类
new_total = (
    len(today_news_policy) + len(today_news_explore) + len(today_news_rights)
    + len(today_news_industry) + len(today_news_global) + len(today_news_edu)
)
print('Today new total:', new_total)

# 往期内容子分类
archive_explore = [d for d in archive if '找矿' in d.get('title','') or '新发现' in d.get('title','') or '勘查' in d.get('title','') or '勘探' in d.get('title','') or '钛' in d.get('title','') or '钨' in d.get('title','') or '矿' in d.get('title','') and '权' not in d.get('title','')]
archive_rights = [d for d in archive if '权' in d.get('title','') and ('出让' in d.get('title','') or '转让' in d.get('title','') or '公示' in d.get('title','') or '出让' in d.get('title',''))]
archive_industry = [d for d in archive if any(k in d.get('title','') for k in ['产量','分红','利润','景气','战略合作','恩菲','紫金','黄金','金属'])]
archive_global = [d for d in archive if any(k in d.get('title','') for k in ['美','智利','秘鲁','印尼','金矿','铀','量子','BMI','稀土矿','稀土','锌','铜','黄沙坪'])]
archive_edu = [d for d in archive if '学会' in d.get('title','') or '培训' in d.get('title','')]

# 简单按原顺序保留，避免复杂分类错误，原始archive列表已经分好子类
# 重新生成按原结构分类的archive
# 原archive_from_old_today前8条：8条全是矿权交易
# 原archive_from_old_today 9-11: 找矿成果
# 原archive_from_old_today 12-18: 国际矿业
# 原archive_from_old_today 19-25: 行业动态
# 原archive_from_old_today 26: 培训(沈阳地调?)
# 原archive_from_old_archive: 1条找矿成果+4条找矿+4条矿权+1条行业+3条国际+2条培训

# 我直接简单按URL和来源站点分类
def classify_archive(d):
    src = d.get('src','')
    title = d.get('title','')
    if '矿业权市场' in src or '北京矿权' in src or '上海联合' in src:
        return 'rights'
    if '矿业权市场' in title or '探矿权' in title or '采矿权' in title or '挂牌出让' in title or '拍卖出让' in title or '协议出让' in title or '转让公示' in title or '出让公告' in title:
        return 'rights'
    if '全球矿产资源' in src or 'geoglobal' in d['url']:
        return 'global'
    if any(k in title for k in ['西澳','爱达荷','格陵兰','金矿','铀','BMI','稀土','量子','铜产量','锌价','秘鲁','印尼']):
        return 'global'
    if '中国地质调查局' in src or 'cgs.gov.cn' in d['url']:
        return 'explore'
    if any(k in title for k in ['找矿','勘查','勘探','矿床','九万大山','沈阳地调中心']):
        return 'explore'
    if '中国地质学会' in src or 'geosociety' in d['url']:
        return 'edu'
    return 'industry'

archive_by_cat = {'rights':[],'explore':[],'global':[],'industry':[],'edu':[]}
for d in archive:
    cat = classify_archive(d)
    archive_by_cat[cat].append(d)

# 输出每个分类数量
for k,v in archive_by_cat.items():
    print(f'Archive {k}: {len(v)}')

# 今日新增HTML
today_html = ''
# 一、政策法规
today_html += '<div class="sub-cat">📜 政策法规<span class="sub-count">' + str(len(today_news_policy)) + '条新增</span></div>'
for d in today_news_policy:
    today_html += make_news_item(d)
# 二、找矿成果与勘查技术
today_html += '<div class="sub-cat">🔍 找矿成果与勘查技术<span class="sub-count">' + str(len(today_news_explore)) + '条新增</span></div>'
for d in today_news_explore:
    today_html += make_news_item(d)
# 三、矿权交易
today_html += '<div class="sub-cat">💼 矿权交易<span class="sub-count">' + str(len(today_news_rights)) + '条新增</span></div>'
for d in today_news_rights:
    today_html += make_news_item(d)
# 四、行业动态
today_html += '<div class="sub-cat">📊 行业动态<span class="sub-count">' + str(len(today_news_industry)) + '条新增</span></div>'
for d in today_news_industry:
    today_html += make_news_item(d)
# 五、国际矿业动态
today_html += '<div class="sub-cat">🌍 国际矿业动态<span class="sub-count">' + str(len(today_news_global)) + '条新增</span></div>'
for d in today_news_global:
    today_html += make_news_item(d)
# 六、培训与学术
today_html += '<div class="sub-cat">🎓 培训与学术<span class="sub-count">' + str(len(today_news_edu)) + '条新增</span></div>'
for d in today_news_edu:
    today_html += make_news_item(d)

# 往期HTML
archive_html = ''
# 找矿成果
if archive_by_cat['explore']:
    archive_html += '<div class="sub-cat">🔍 找矿成果</div>'
    for d in archive_by_cat['explore']:
        archive_html += make_news_item(d, is_new=False)
# 矿权交易
if archive_by_cat['rights']:
    archive_html += '<div class="sub-cat">💼 矿权交易</div>'
    for d in archive_by_cat['rights']:
        archive_html += make_news_item(d, is_new=False)
# 行业动态
if archive_by_cat['industry']:
    archive_html += '<div class="sub-cat">📊 行业动态</div>'
    for d in archive_by_cat['industry']:
        archive_html += make_news_item(d, is_new=False)
# 国际矿业
if archive_by_cat['global']:
    archive_html += '<div class="sub-cat">🌍 国际矿业</div>'
    for d in archive_by_cat['global']:
        archive_html += make_news_item(d, is_new=False)
# 培训
if archive_by_cat['edu']:
    archive_html += '<div class="sub-cat">🎓 培训信息</div>'
    for d in archive_by_cat['edu']:
        archive_html += make_news_item(d, is_new=False)

archive_count = sum(len(v) for v in archive_by_cat.values())
print('Total archive:', archive_count)

# ============ 拼装新HTML ============
header_part = '''<!DOCTYPE html>
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
<title>矿业新闻日报 2026-08-27</title>
'''

body_start = '''</head>
<body>
<nav class="toc-sidebar" id="tocSidebar">
<div class="toc-title">📑 目录导航</div>
<div class="toc-main-item toc-all active" onclick="showAll();window.scrollTo({top:0,behavior:'smooth'})">📋 全部内容 <span class="toc-count" id="tocAllCount">''' + str(new_total+archive_count) + '''</span></div>
<div class="toc-main-item" data-target="specialSection" onclick="scrollToSection('specialSection',this)" style="color:#b45009">⛏️ 找矿专项 <span class="toc-count" id="tocSpecialCount" style="background:#fdf3d7;color:#b45009">0</span></div>
<div class="toc-main-item" data-target="todaySection" onclick="scrollToSection('todaySection',this)">🔥 今日新增 <span class="toc-count" id="tocTodayCount">''' + str(new_total) + '''</span></div>
<div class="toc-main-item" data-target="archiveSection" onclick="scrollToSection('archiveSection',this)">📰 往期内容 <span class="toc-count">''' + str(archive_count) + '''</span></div>
<div class="toc-main-item" onclick="toggleFavFilter();window.scrollTo({top:0,behavior:'smooth'})" style="color:#f39c12">★ 我的收藏 <span class="toc-count" id="tocFavCount" style="background:#fef5e7;color:#f39c12">0</span></div>
<div class="toc-main-item" onclick="toggleHistoryFilter();window.scrollTo({top:0,behavior:'smooth'})" style="color:#8e44ad">📋 浏览记录 <span class="toc-count" id="tocHistoryCount" style="background:#f5eef8;color:#8e44ad">0</span></div>
<div class="toc-main-item" data-target="installGuideSection" onclick="scrollToSection('installGuideSection',this)" style="color:#0e7490">📲 安装到桌面 <span class="toc-count" id="tocInstallGuideCount" style="background:#e0f2fe;color:#0e7490">📘</span></div>
<div class="toc-back-top" onclick="window.scrollTo({top:0,behavior:'smooth'})">↑ 返回顶部</div>
</nav>
<div class="container">

<div class="header">
<h1>⛏️ 矿业新闻日报 <span class="date-badge">2026年8月27日 星期四</span></h1>
<div class="sub">每日 9:00 起自动更新（约 9:30 前出今日版本） · 11个信息源 · 聚焦有色金属</div>
<div class="install-tip show" id="installTip"><span id="installTipText">📲 手机：浏览器菜单选「<b>添加到桌面 / 添加书签</b>」（微信内先点右上角「···」→ 浏览器中打开）<br>💻 电脑：点 Edge/Chrome 地址栏右侧「<b>安装</b>」图标 → 变成独立窗口软件 ｜ <a href="javascript:void(0)" onclick="scrollToSection('installGuideSection',null)" style="color:#7dd3fc;text-decoration:underline">查看详细说明 ↓</a></span><button class="tip-close" onclick="dismissInstallTip()" title="我知道了">✕</button></div>
</div>

<!-- ==================== 金属价格 ==================== -->
<div class="price-strip" id="priceStrip">
<div class="price-strip-head">
<span class="price-strip-title">📊 金属价格</span>
<span class="price-strip-note">2026-08-27 · 沪期主力/SMM·上金所 · 涨红跌绿</span>
</div>
<div class="price-cards">
<div class="price-card down"><div class="pc-name">沪铜 <span class="pc-tag">SHFE</span></div><div class="pc-value">108,480</div><div class="pc-unit">元/吨</div><div class="pc-chg">▼ -320 (-0.29%)</div></div>
<div class="price-card up"><div class="pc-name">沪铝 <span class="pc-tag">SHFE</span></div><div class="pc-value">23,920</div><div class="pc-unit">元/吨</div><div class="pc-chg">▲ +50 (+0.21%)</div></div>
<div class="price-card up"><div class="pc-name">沪铅 <span class="pc-tag">SHFE</span></div><div class="pc-value">16,125</div><div class="pc-unit">元/吨</div><div class="pc-chg">▲ +10 (+0.06%)</div></div>
<div class="price-card up"><div class="pc-name">沪锌 <span class="pc-tag">SHFE</span></div><div class="pc-value">26,500</div><div class="pc-unit">元/吨</div><div class="pc-chg">▲ +245 (+0.93%)</div></div>
<div class="price-card down"><div class="pc-name">沪锡 <span class="pc-tag">SHFE</span></div><div class="pc-value">420,200</div><div class="pc-unit">元/吨</div><div class="pc-chg">▼ -5,890 (-1.38%)</div></div>
<div class="price-card down"><div class="pc-name">沪镍 <span class="pc-tag">SHFE</span></div><div class="pc-value">128,910</div><div class="pc-unit">元/吨</div><div class="pc-chg">▼ -610 (-0.47%)</div></div>
<div class="price-card"><div class="pc-name">上海金 <span class="pc-tag">Au99.99</span></div><div class="pc-value">1005.43</div><div class="pc-unit">元/克</div><div class="pc-chg">早盘 1005.43</div></div>
<div class="price-card"><div class="pc-name">白银 <span class="pc-tag">Ag(T+D)</span></div><div class="pc-value">16,705</div><div class="pc-unit">元/千克</div><div class="pc-chg">今开 16,705</div></div>
<div class="price-card down"><div class="pc-name">碳酸锂 <span class="pc-tag">电池级</span></div><div class="pc-value">152,774</div><div class="pc-unit">元/吨（SMM折）</div><div class="pc-chg">▼ -2.68%</div></div>
<div class="price-card up"><div class="pc-name">电解钴 <span class="pc-tag">SMM</span></div><div class="pc-value">307,571</div><div class="pc-unit">元/吨（SMM折）</div><div class="pc-chg">▲ +0.03%</div></div>
</div>
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
<div class="sp-cat">📌 政策与部署<span class="sub-count" id="spCount-policy">0条</span></div>
<div class="sp-list" id="spList-policy"></div>
<div class="sp-cat">🏔️ 找矿成果与新发现<span class="sub-count" id="spCount-result">0条</span></div>
<div class="sp-list" id="spList-result"></div>
<div class="sp-cat">🔬 勘查技术与装备<span class="sub-count" id="spCount-tech">0条</span></div>
<div class="sp-list" id="spList-tech"></div>
<div class="sp-cat">🌏 战略矿产与资源安全<span class="sub-count" id="spCount-security">0条</span></div>
<div class="sp-list" id="spList-security"></div>
</div>

<!-- ==================== 今日新增 ==================== -->
<div class="section" id="todaySection">
<div class="section-title today"><span class="icon">🔥</span> 今日新增（2026-08-27 抓取）<span class="news-count" id="todayCount"></span></div>
'''

body_today_end = '</div>\n\n<!-- ==================== 往期内容 ==================== -->\n<div class="section" id="archiveSection">\n<div class="section-title"><span class="icon">📰</span> 往期内容（滚动保留最近14天）<span class="news-count">' + str(archive_count) + '条</span></div>\n<div class="fold-toggle" id="foldToggle" style="display:none" onclick="toggleOldFold()">▸ 展开更早内容</div>\n\n'

body_archive_end = '</div>\n\n<!-- ==================== 详细安装指引（双端展开,默认浏览器加入到桌面或书签） ==================== -->\n<div class="section" id="installGuideSection">\n'

# 安装指引区 - 完整保留
install_guide = '''<div class="section-title guide"><span class="icon">📲</span> 安装到桌面 · 详细说明 <span class="news-count" style="background:#cffafe;color:#0e7490">建议收藏本页</span></div>
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

<!-- 安装 PWA 的链接（大字蓝色方便复制） -->
<a class="guide-link" href="https://04bad6570ebc40da9fa12c25c30b6ad3.app.workbuddy.link" target="_blank">📋 复制链接到浏览器：https://04bad6570ebc40da9fa12c25c30b6ad3.app.workbuddy.link</a>

<div class="guide-tip">💡 <b>安装后怎么卸载？</b>手机：长按桌面图标选「删除」；电脑：Edge / Chrome「设置」→「应用」→「已安装的应用」→ 找"矿业新闻日报"→「卸载」。链接收藏在书签：书签栏 → 浏览器「收藏夹管理器」删。本页面随时能在浏览器输入链接打开，不会因为卸载而丢失。</div>
</div>

<!-- ==================== 已归档收藏 ==================== -->
<div class="section" id="archivedFavSection" style="display:none">
<div class="section-title">🗂️ 已归档收藏（原新闻已滚出页面，收藏记录永久保留）<span class="news-count" id="archFavCount">0条</span></div>
<div id="archFavList"></div>
</div>

'''

# Footer
footer = '''<div class="footer">
<p>数据来源：自然资源部 · 中国地质调查局 · 矿业权市场 · 中国有色网 · 北京国际矿业权交易所 · 上海联合矿权交易所 · 全球矿产资源信息系统 · 中国地质学会 · 中国黄金协会 · 中国稀土行业协会 · 中国有色金属工业协会</p>
<p>聚焦有色金属：铜镍铅锌铝金银稀土钨钼锡锑锂钴 | 排除：煤炭、石油、天然气、钢铁：铁矿</p>
<p>更新时间：2026-08-27 09:30 | 每日9:00起自动更新（约9:30前完成） | 11个信息源 | 本页新增：已读状态存储于访问者本机浏览器</p>
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
'''

# 拼装完整HTML
new_html = (
    header_part
    + style_block + '\n'
    + body_start
    + today_html
    + body_today_end
    + archive_html
    + body_archive_end
    + install_guide
    + footer
    + script_block + '\n'
    + '</body>\n</html>\n'
)

if not EXPORT_JSON_ONLY:
    with open(INDEX_PATH,'w',encoding='utf-8') as f:
        f.write(new_html)
    print('Generated HTML size:', len(new_html))

# ============================================================
# P0：结构化JSON导出（智能体数据底座）
# 每条新闻统一字段：title/url/source/orig_date/report_date/category/is_new/tags/summary/embed
# 输出 mining_news.json，供对话式矿业情报智能体查询
# ============================================================

# 本次日报日期：从footer"更新时间"自动提取，保证每天生成时日期正确
_m = re.search(r'更新时间：(\d{4}-\d{2}-\d{2})', footer)
REPORT_DATE = _m.group(1) if _m else 'unknown'

# 今日新增六分类 → (列表, 中文分类名)
today_groups = [
    (today_news_policy,   '政策法规'),
    (today_news_explore,  '找矿成果与勘查技术'),
    (today_news_rights,   '矿权交易'),
    (today_news_industry, '行业动态'),
    (today_news_global,   '国际矿业动态'),
    (today_news_edu,      '培训与学术'),
]

# 往期分类英文key → 中文名（与今日分类口径一致，便于检索）
CAT_NAMES = {
    'rights':    '矿权交易',
    'explore':   '找矿成果与勘查技术',
    'global':    '国际矿业动态',
    'industry':  '行业动态',
    'edu':       '培训与学术',
}

# 矿种关键词表（标签提取用）
MINERALS = ['铜','镍','铅','锌','铝','金','银','稀土','钨','钼','锡','锑','锂','钴',
            '钛','铀','锰','钒','铬','镁','铌','钽','镓','锗','铟','铼','镉','铋','硒','碲','铂','钯','铁']
# 主题关键词表（标签提取用）
TOPICS = {
    '政策': ['政策','规划','方案','条例','办法','通知','公告','公示','实施意见','管理规定','准入'],
    '找矿': ['找矿','勘查','勘探','新发现','矿床','突破','增储'],
    '矿权': ['探矿权','采矿权','出让','转让','挂牌','拍卖','矿权'],
    '市场': ['价格','产量','行情','上涨','下跌','供需','库存','利润','景气'],
    '技术': ['技术','数字化','智能','装备','研发','创新','材料'],
    '安全': ['安全','事故','本质安全'],
    '国际': ['国际','全球','海外','西澳','格陵兰','秘鲁','印尼','智利'],
}

def extract_tags(d):
    """从标题+摘要提取矿种与主题标签，供智能体精确检索"""
    text = (d.get('title','') + ' ' + d.get('summary',''))
    # 排除组合词，避免"有色金属/金属"误提取出"金"标签
    text = text.replace('有色金属','').replace('金属','')
    tags = []
    for m in MINERALS:
        if m in text and m not in tags:
            tags.append(m)
    for topic, kws in TOPICS.items():
        if any(k in text for k in kws) and topic not in tags:
            tags.append(topic)
    return tags

def build_entry(d, category, is_new):
    return {
        'title': d.get('title',''),
        'url': d.get('url',''),
        'source': d.get('src',''),
        'orig_date': d.get('date',''),
        'report_date': REPORT_DATE,
        'category': category,
        'is_new': is_new,
        'tags': extract_tags(d),
        'summary': d.get('summary',''),
        'embed': embed_map.get(d.get('url',''), 'unknown'),
    }

# 从现有index.html读回嵌入标记（batch_check_embed.py 回填的结果）
embed_map = {}
try:
    with open(INDEX_PATH,'r',encoding='utf-8') as f:
        _cur = f.read()
    for _mm in re.finditer(r'data-url="([^"]+)"[^>]*data-embed="([^"]+)"', _cur):
        embed_map[_mm.group(1)] = _mm.group(2)
except Exception:
    pass

news_list = []
# 今日新增
for lst, cat in today_groups:
    for d in lst:
        news_list.append(build_entry(d, cat, True))
# 往期（按已分类好的 archive_by_cat）
for key, lst in archive_by_cat.items():
    cat = CAT_NAMES.get(key, key)
    for d in lst:
        news_list.append(build_entry(d, cat, False))

# 按url去重（同一url今日+往期都出现时保留今日）
seen = set()
dedup = []
for e in news_list:
    if e['url'] not in seen:
        seen.add(e['url'])
        dedup.append(e)
news_list = dedup

# 统计信息源
sources = sorted({e['source'] for e in news_list if e['source']})

mining_news = {
    'meta': {
        'report_date': REPORT_DATE,
        'generated_at': __import__('datetime').datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00'),
        'total': len(news_list),
        'new_today': sum(1 for e in news_list if e['is_new']),
        'archive': sum(1 for e in news_list if not e['is_new']),
        'sources': sources,
        'schema_version': '1.0',
        'note': 'P0 数据底座：每日生成时同步导出，供矿业情报智能体查询',
    },
    'news': news_list,
}

with open(JSON_PATH,'w',encoding='utf-8') as f:
    json.dump(mining_news, f, ensure_ascii=False, indent=2)
print('JSON exported:', JSON_PATH)
print('  total:', mining_news['meta']['total'], '| new:', mining_news['meta']['new_today'], '| archive:', mining_news['meta']['archive'])
print('OK')