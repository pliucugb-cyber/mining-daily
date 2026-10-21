/* conference-data.js —— 右栏「会议日程」数据源（2026-10-21 新增）
 *
 * 为什么单独建文件（不再靠新闻派生）：
 *   原「近期会展」卡靠 isExpo 关键词从新闻标题里"捡"会议条目，10 月库 407 条里
 *   只命中 3 条（其中 2 条是同一场会的不同源），过 14 天闸门只剩 1 条 → 卡片常年空。
 *   根因是方向错了：装的是"已召开会议的事后报道"，而会议预告有权威且稳定的出处
 *   （中国地质学会会议通知公告、各专委会二号通知、主办方官网、国际会议固定日程），
 *   不该等新闻来填。
 *
 * 维护方式：编辑本文件的 items 数组即可（每日生成脚本不碰本文件，regen-proof）。
 *   字段：s=开始日期  e=结束日期  t=标题  p=地点  o=主办方  tag=分类标签
 *         u=官方链接    note=补充信息（报名截止/亮点）  v=日期可信度(ok/tbd)
 *   日期一律 'YYYY-MM-DD'；未定日期填 ''（卡片归入「日期待定」区）。
 *   updated 填本次维护日期（卡片倒计时以它为基准）。
 *
 * 来源：中国地质学会会议通知公告(geosociety.org.cn)、广西自然资源厅、
 *       中国有色金属报(cnmn.com.cn)、Global Mining Review / Mining Journal 会议日历。
 */
window.CONFERENCE_DATA = {
  updated: '2026-10-21',
  source: '中国地质学会会议通知公告 · 中国有色金属报 · 主办方官网 · 国际会议官网',
  items: [
    /* ── 国内：日期已确认 ─────────────────────────────── */
    { s:'2026-11-05', e:'2026-11-06', t:'2026中国（广西）—东盟矿业合作大会', p:'南宁国际会展中心', o:'广西自治区政府 · 自治区自然资源厅', tag:'矿业大会', u:'https://dnr.gxzf.gov.cn/xwzx/zrzx/t28231172.shtml', note:'11/6-7 同场广西国际矿业展览会；特设 AI+找矿专题、老挝/东帝汶/加纳 3 场国家矿业专场', v:'ok' },
    { s:'2026-11-16', e:'2026-11-18', t:'2026年全国城市地质学术年会', p:'海南博鳌', o:'中国地质学会城市地质专业委员会', tag:'城市地质', u:'https://geosociety.org.cn/', note:'主题：筑牢城市地质安全基底 赋能地下空间开发利用', v:'ok' },
    { s:'2026-11-18', e:'2026-11-21', t:'第一届境外矿产勘查与矿业投资大会', p:'厦门悦华酒店', o:'中国地质学会 · 紫金矿业', tag:'矿业投资', u:'http://www.cnmn.com.cn/ShowNews1.aspx?id=474389', note:'18日报到、19-20 报告、21 紫金山—古田野外考察；★报名优惠截止 10-30（会员 1500／非会员 1900）', v:'ok' },
    { s:'2026-11-18', e:'2026-11-30', t:'矿冶工程论坛：科技创新引领 开创矿产资源新格局', p:'湖南·长沙', o:'山东黄金 · 中南大学 · 东北大学 · 中国地大(北京) · 中国矿大(北京) · 北科大', tag:'勘查技术', u:'http://www.kygczz.com/CN/news/news962.shtml', note:'11 月中下旬，具体日期待二号通知；四大专题：成矿理论／成矿带勘查进展／金属矿开采／资源综合利用与绿色智能', v:'tbd' },

    /* ── 国内：官方已发通知、日期待定 ──────────────────── */
    { s:'', e:'', t:'2026年全国工程地质学术年会', p:'待定', o:'中国地质学会工程地质专业委员会', tag:'工程地质', u:'https://geosociety.org.cn/', note:'二号通知已发（2026-08-31），具体日期待公告', v:'tbd' },
    { s:'', e:'', t:'2026年全国铀矿地质会议', p:'待定', o:'中国地质学会', tag:'铀矿', u:'https://geosociety.org.cn/', note:'一号通知已发（2026-07-29），日期待公告', v:'tbd' },
    { s:'', e:'', t:'全国生态地球化学交流研讨会', p:'待定', o:'中国地质学会', tag:'勘查技术', u:'https://geosociety.org.cn/', note:'已发通知且有地点变更公告（2026-09-30），日期待确认', v:'tbd' },
    { s:'', e:'', t:'第二十七届全国洞穴学术会议', p:'待定', o:'中国地质学会', tag:'学术会议', u:'https://geosociety.org.cn/', note:'二号通知已发（2026-09-20），日期待公告', v:'tbd' },
    { s:'', e:'', t:'第四届数据驱动与地学发展全国学术研讨会', p:'待定', o:'中国地质学会', tag:'数智勘查', u:'https://geosociety.org.cn/', note:'二号通知已发（2026-08-20），日期待公告', v:'tbd' },
    { s:'', e:'', t:'第二届全国生态地质学术研讨会', p:'待定', o:'中国地质学会', tag:'勘查技术', u:'https://geosociety.org.cn/', note:'二号通知已发（2026-08-21），日期待公告', v:'tbd' },
    { s:'', e:'', t:'非常规能源富集理论与勘查开采技术学术研讨会', p:'待定', o:'中国地质学会', tag:'勘查技术', u:'https://geosociety.org.cn/', note:'二号通知已发（2026-08-20），日期待公告', v:'tbd' },

    /* ── 国际：日期已确认 ─────────────────────────────── */
    { s:'2026-10-27', e:'2026-10-29', t:'IMARC 2026 国际矿业与资源大会', p:'悉尼 ICC', o:'IMARC', tag:'国际矿业', u:'https://globalminingreview.com/events', note:'澳方年度最大矿业展会', v:'ok' },
    { s:'2026-11-03', e:'2026-11-06', t:'MRMR 2026 矿产资源与储量会议', p:'地点待确认', o:'MRMR', tag:'资源储量', u:'https://globalminingreview.com/events', note:'聚焦 JORC/NI 43-101 等资源储量报告规范', v:'ok' },
    { s:'2026-11-16', e:'2026-11-17', t:'The Mining Show 2026', p:'地点待确认', o:'The Mining Show', tag:'国际矿业', u:'https://globalminingreview.com/events', note:'', v:'ok' },
    { s:'2026-11-17', e:'2026-11-17', t:'FT Metals & Mining Summit: India 2026', p:'印度', o:'Financial Times', tag:'国际矿业', u:'https://globalminingreview.com/events', note:'聚焦关键矿产与矿业政策改革', v:'ok' },
    { s:'2026-12-01', e:'2026-12-01', t:'Resourcing Tomorrow 2026', p:'地点待确认', o:'Resourcing Tomorrow', tag:'国际矿业', u:'https://globalminingreview.com/events', note:'2300+ 矿业与投资方参会', v:'ok' },
    { s:'2027-01-12', e:'2027-01-12', t:'Future Minerals Forum 2027', p:'利雅得', o:'Future Minerals Forum', tag:'国际矿业', u:'https://globalminingreview.com/events', note:'政府与投资方政策对接为主', v:'ok' },
    { s:'2027-01-24', e:'2027-01-25', t:'Vancouver Resource Investment Conference', p:'温哥华会展中心', o:'VRIC', tag:'矿业投资', u:'https://www.pdac.ca/members/member-resources/industry-events', note:'', v:'ok' },
    { s:'2027-01-25', e:'2027-01-28', t:'AME Roundup 2027', p:'温哥华会展中心', o:'AME', tag:'矿业投资', u:'https://www.pdac.ca/members/member-resources/industry-events', note:'矿业投资与并购路演', v:'ok' },
    { s:'2027-02-08', e:'2027-02-11', t:'Mining Indaba 2027', p:'开普敦 CTICC', o:'Mining Indaba', tag:'国际矿业', u:'https://www.pdac.ca/members/member-resources/industry-events', note:'非洲矿业投资年度第一会', v:'ok' },
    { s:'2027-02-28', e:'2027-03-03', t:'MINEXCHANGE 2027', p:'丹佛', o:'MINEXCHANGE', tag:'国际矿业', u:'https://globalminingreview.com/events', note:'', v:'ok' },
    { s:'2027-03-07', e:'2027-03-10', t:'PDAC 2027 矿业勘探与开采大会', p:'多伦多 MTCC', o:'PDAC', tag:'国际矿业', u:'https://www.pdac.ca/members/member-resources/industry-events', note:'★全球最大矿业会展，3.2 万人／140 国参与', v:'ok' },
    { s:'2027-04-20', e:'2027-04-23', t:'Expomin 2027', p:'智利', o:'Expomin', tag:'国际矿业', u:'https://globalminingreview.com/events', note:'拉美矿业展，日期以主办方为准', v:'tbd' },
    { s:'2027-04-22', e:'2027-05-01', t:'Geological Society of Nevada Symposium', p:'美国内华达·斯帕克斯', o:'Geological Society of Nevada', tag:'国际矿业', u:'https://www.pdac.ca/members/member-resources/industry-events', note:'', v:'ok' },
    { s:'2027-05-17', e:'2027-05-19', t:'Geoconvention 2027', p:'加拿大卡尔加里', o:'Canadian Society of Exploration Geophysicists', tag:'勘查技术', u:'https://www.pdac.ca/members/member-resources/industry-events', note:'物探技术年度会议', v:'ok' },
    { s:'2027-06-29', e:'2027-06-30', t:'Future of Mining Australia 2027', p:'珀斯 Crown', o:'Future of Mining', tag:'国际矿业', u:'https://www.mining-journal.com/events', note:'', v:'ok' },
    { s:'2027-10-12', e:'2027-10-14', t:'IMARC 2027 国际矿业与资源大会', p:'悉尼 ICC', o:'IMARC', tag:'国际矿业', u:'https://www.pdac.ca/members/member-resources/industry-events', note:'', v:'ok' },
    { s:'2027-10-23', e:'2027-10-28', t:'Exploration 27', p:'多伦多 MTCC', o:'Exploration 27', tag:'勘查技术', u:'https://www.pdac.ca/members/member-resources/industry-events', note:'勘探技术年度大会', v:'ok' }
  ]
};
