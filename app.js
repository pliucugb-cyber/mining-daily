
// 2026-09-11：启动信标 + 收起内联引信可能已弹出的「脚本未加载」横幅。
// 置于 app.js 最顶端——只要本文件开始执行即视为「脚本已加载」，index.html 里的看门狗随即失效。
// （09-10 事故正是 app.js 没跑起来却毫无提示，用户只能看到永久「加载中…」。）
window.__mdBooted=true;
try{var _bw=document.getElementById('mdBootWarn');if(_bw)_bw.style.display='none';}catch(e){}
// 2026-09-11 加固：QA_ROWS 在本文件中段（约 2838 行）才 `var` 初始化。
// 若顶层代码在其中途抛错（09-10/09-11 两轮事故的形态），QA_ROWS 会停留在 undefined，
// 而 computeHotNewsLocal() 等在它之前的函数读 QA_ROWS.length 就会 TypeError →
// 热榜直接显示「加载失败」，掩盖了真正的根因。此处先占位成空数组，让降级路径可控。
window.QA_ROWS=window.QA_ROWS||[];
// 2026-09-11 P0（第三轮事故的真正根因，见下方长注释）：先把「列表型全局」占位成空数组。
// 它们的真实赋值都在文件后段；一旦顶层提前中断，后面所有 var 都停在 undefined，
// 渲染函数连 `X.forEach` 都过不去（线上原样报错：qaInitData / renderDigest →
// "Cannot read properties of undefined (reading 'forEach')"）。
window.QA_MINERALS=window.QA_MINERALS||[];
window.QA_TOPICS=window.QA_TOPICS||[];
window.DIGEST_SRC=window.DIGEST_SRC||[];
window.DIGEST_KW=window.DIGEST_KW||[];
window.DIGEST_N=window.DIGEST_N||4;

// 2026-09-11 P0 —— 「Cannot access 'newsSearchText' before initialization」根因修复
// ---------------------------------------------------------------------------
// index.html 里 4 个脚本都是 defer：**真实浏览器执行 defer 脚本时 document.readyState
// 已经是 'interactive'**（不是 'loading'）。于是下面第 44 行的矿权 IIFE：
//     if(readyState==="loading") addEventListener(DOMContentLoaded, ...);
//     else { renderRightsSection(); injectRightsResultSummary(); bindRights(); }
// 走 else 分支，**在 app.js 求值期间当场调用** renderRightsSection()
//   → mdApplySearchToRights() → 读 newsSearchText → 命中 TDZ ReferenceError。
// 这 4 个模块状态原先声明在第 ~695 行，还没有执行到。
// 后果不是「少一个筛选功能」，而是 app.js 在此处**整体中断**：
// 其后所有顶层语句都不执行 —— 包括 2285 行的初始化链（fetchHotNews/loadBrief/refresh）
// 以及 2139/2793 行的 DIGEST_SRC / QA_MINERALS 等 var 赋值。
// 表现就是用户看到的：静态内容（生成器写死的价格卡/新闻条目）都在，
// 而要靠 JS 现算的今日要闻 / 热榜 / AI 检索全空、下拉框没有选项。
// 修法：① 声明提到文件最前，任何时点读到的都是合法初值（消除 TDZ）；
//       ② 那个 IIFE 的即时分支改为 setTimeout 0（见该处注释），不再在求值期跑业务逻辑。
let filterMode='none';
let tagFilter=null;
let newsSearchText='';
let oldExpanded=false;   // 往期内容中"超过14天旧闻"是否展开
// 问答筛选下拉的「干净快照」：qaInitData() 会往两个 select 里 append 带计数的新选项，
// 并非幂等（重复调用会出现「铜 (12)」成倍重复）。自愈重跑前先还原到快照。
window.__mdQaSelSnap=(function(){
  try{
    var out={};
    ['qaFloatMineral','qaFloatTopic'].forEach(function(id){
      var el=document.getElementById(id);
      if(el)out[id]=el.innerHTML;
    });
    return out;
  }catch(e){ return {}; }
})();
function qaReinit(){
  try{
    for(var id in window.__mdQaSelSnap){
      var el=document.getElementById(id);
      if(el)el.innerHTML=window.__mdQaSelSnap[id];
    }
  }catch(e){}
  if(typeof qaInitData==='function')qaInitData();
}
window.qaReinit=qaReinit;
// ===== 权威转义函数（第 3 批收敛：原 4 份局部 esc + 1 份 escapeHtml 合并为此一个）=====
// 语义取原先最严格的一份：null/undefined 安全，转义 & < > " '。
// 各局部作用域不再重复定义，统一用这个；escapeHtml 保留为兼容别名。
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
// 统一外链校验：黑名单制，只拦危险协议（javascript:/data:/vbscript:/file:）。
// 不用白名单——页面存在 #rightsSection 锚点与相对路径，白名单会把它们拦空、打断跳转。
// 顺带把 " 转成 %22，因此可直接放进 href="..." 属性。返回 '' 表示不可用（调用方应降级为纯文本）。
// 注：qaSafeUrl 是给 LLM 生成内容用的**白名单**版本，刻意更严，与本函数并存，勿合并。
function safeHref(u){if(u==null)return '';var s=String(u).trim();if(!s)return '';if(/[\x00-\x1F\x7F]/.test(s))return '';var t=s.replace(/[\s\u0000-\u0020]+/g,'').toLowerCase();if(/^(javascript|data|vbscript|file):/.test(t))return '';return s.replace(/"/g,'%22');}
/* ===================== 矿权交易独立专区渲染（9-06 新增）===================== */
(function(){
  function parseRights(it){
    var m=it.m||"", t=it.t||"", g=it.g||[];
    var full=t+" "+m;
    // 2026-09-07：先按标题区分业务类型，再决定展示字段
    var rightsType="other";
    if(/结果公示/.test(t)) rightsType="result";
    else if(/转让公示/.test(t)) rightsType="transfer";
    else if(/拍卖出让公告/.test(t)) rightsType="auction";
    else if(/挂牌出让公告/.test(t)) rightsType="listing";
    else if(/协议出让/.test(t)) rightsType="listing"; // 协议公示字段与挂牌公告相近
    var methodMap={result:"结果",transfer:"转让",auction:"拍卖",listing:"挂牌",other:"其他"};
    var method=methodMap[rightsType]||"其他";
    var mineral="";
    var mm=m.match(/勘查矿种([一-龥]{1,4})矿/);
    if(mm) mineral=mm[1];
    else {
      var order=["金","银","铜","铅","锌","镍","锡","锂","稀土","磷","铁","钨","钼","铌","钽","铝"];
      // 2026-09-08 晚：组合矿种规则表（标题优先匹配，避免"广西铝土矿""宁远方解石矿"落到「—」）。
      // 顺序即优先级；后续新矿种在此追加一行即可，勿再散落多处。
      var combo=[[/钽铌|铌钽/,"铌钽"],[/铝土/,"铝土"],[/方解石/,"方解石"],[/石灰岩|灰岩/,"石灰岩"],[/萤石/,"萤石"],[/石墨/,"石墨"],[/重晶石/,"重晶石"],[/高岭土/,"高岭土"],[/钾盐|岩盐|盐矿/,"盐矿"],[/石膏/,"石膏"],[/石英/,"石英"],[/长石/,"长石"],[/硅石/,"硅石"],[/芒硝/,"芒硝"],[/膨润土/,"膨润土"],[/耐火粘土|耐火黏土/,"耐火粘土"]];
      var mineral="";
      for(var ci=0;ci<combo.length;ci++){ if(combo[ci][0].test(t)){mineral=combo[ci][1];break;} }
      if(!mineral) mineral=g.filter(function(x){return order.indexOf(x)>=0;})[0]||"";
      if(!mineral && /铅锌/.test(t)) mineral="铅锌";
      if(!mineral && /钨钼/.test(t)) mineral="钨钼";
      if(!mineral && /多金属/.test(t)) mineral="多金属";
      if(!mineral && g.some(function(x){return /金属/.test(x);})) mineral="多金属";
    }
    // 价格：结果公示优先成交价；挂牌/拍卖用起始价
    var startPrice=null, dealPrice=null, price=null;
    var dealM=m.match(/成交价([\d.]+)万元/);
    if(dealM) dealPrice=parseFloat(dealM[1]);
    var pm=m.match(/起始价([\d.]+)万元/);
    if(pm) startPrice=parseFloat(pm[1]);
    if(rightsType==="result") price=dealPrice!=null?dealPrice:startPrice;
    else price=startPrice;
    var dm=m.match(/(?:竞买保证金|保证金)([\d.]+)万元/); var deposit=dm?parseFloat(dm[1]):null;
    var am=m.match(/面积([\d.]+)平方千米/); var area=am?parseFloat(am[1]):null;
    // 日期字段：挂牌/拍卖取截标/拍卖日；结果/转让取公示期
    var deadline=null, pubStart=null, pubEnd=null;
    // 1) 挂牌期/竞价期/报价期 "2026年X月X日至2026年X月X日"
    var dl=m.match(/(?:挂牌期|竞价期|报价期)\s*(\d{4})年(\d{1,2})月(\d{1,2})日\s*至\s*(\d{4})年(\d{1,2})月(\d{1,2})日/);
    if(dl){
      pubStart=dl[1]+"-"+("0"+dl[2]).slice(-2)+"-"+("0"+dl[3]).slice(-2);
      deadline=pubEnd=dl[4]+"-"+("0"+dl[5]).slice(-2)+"-"+("0"+dl[6]).slice(-2);
    }else{
      // 2) 拍卖定于 / 拍卖会定于
      var dl2=m.match(/(?:拍卖[会]?定于|拍卖时间|拍卖[日]?)[^0-9]*(\d{4})年(\d{1,2})月(\d{1,2})日/);
      if(dl2) deadline=dl2[1]+"-"+("0"+dl2[2]).slice(-2)+"-"+("0"+dl2[3]).slice(-2);
      else {
        // 3) 公示期（结果/转让）：可能只有开始日，也可能有起止；兼容"2026-09-07"和"2026年9月7日"
        var dl3=m.match(/公示期[^0-9]*(\d{4})[\-\/年](\d{1,2})[\-\/月](\d{1,2})(?:日)?(?:\s*至\s*(\d{4})[\-\/年](\d{1,2})[\-\/月](\d{1,2})(?:日)?)?/);
        if(dl3){
          pubStart=dl3[1]+"-"+("0"+dl3[2]).slice(-2)+"-"+("0"+dl3[3]).slice(-2);
          if(dl3[4]) pubEnd=dl3[4]+"-"+("0"+dl3[5]).slice(-2)+"-"+("0"+dl3[6]).slice(-2);
          deadline=pubEnd||pubStart; // 无截止日时展示开始日
        }else{
          // 4) 兜底：截/止/标/报名截止/交纳截止
          var dl4=m.match(/(?:截[止至标]|报名截止|交纳截止)[^0-9]*(\d{4})年(\d{1,2})月(\d{1,2})日/);
          if(dl4) deadline=dl4[1]+"-"+("0"+dl4[2]).slice(-2)+"-"+("0"+dl4[3]).slice(-2);
        }
      }
    }
    // 转让人/受让人/竞得人
    var transferor="", transferee="", bidder="";
    var tm=m.match(/转让人为?\s*([^，,。；;]+)/);
    if(tm) transferor=tm[1].trim();
    var tm2=m.match(/受让人为?\s*([^，,。；;]+)/);
    if(tm2) transferee=tm2[1].trim();
    var bm=m.match(/竞得人\s*([^，,。；;]+)/);
    if(bm) bidder=bm[1].trim();
    var rg=t.match(/([一-龥]{2,}(?:省|市|县|区|旗|自治州|盟|新区))/);
    var region=rg?rg[1]:"";
    return {
      rightsType: rightsType, method: method, mineral: mineral,
      price: price, startPrice: startPrice, dealPrice: dealPrice, deposit: deposit, area: area,
      deadline: deadline, pubStart: pubStart, pubEnd: pubEnd,
      transferor: transferor, transferee: transferee, bidder: bidder,
      region: region, it: it
    };
  }
  function refDate(){
    try{ if(window.NEWS_DATA&&window.NEWS_DATA.updated){ var d=new Date(window.NEWS_DATA.updated.replace(/-/g,"/")); if(!isNaN(d)) return d; } }catch(e){}
    return new Date();
  }
  function daysBetween(a,b){ return Math.round((a-b)/86400000); }
  function fmtMoney(v){ return v==null?"—":v.toLocaleString("zh-CN")+" 万元"; }
  function fmtArea(v){ return v==null?"—":v+" km²"; }
  function fmtDeadline(d){ return d?d.slice(5):"—"; }
  var rightsSort={key:null,dir:"asc"};
  // 矿权卡片/表格默认按数量折叠：超过 RIGHTS_COLLAPSE_AT 条时只显示前 N 条，其余收进「展开全部」
  var RIGHTS_COLLAPSE_AT=8;
  var rightsExpanded=false;
  function rightsSetExpanded(v){ rightsExpanded=!!v; renderRightsSection(); }
  // onclick 内联属性在全局作用域执行，须把 toggle 挂到 window（IIFE 内函数非全局）
  window.rightsSetExpanded=rightsSetExpanded;
  function rightsMoreBtn(listLen, shownLen){
    // 只要原始条数超过阈值，就始终显示按钮（展开后显示「收起」），保证可来回切换
    if(listLen<=RIGHTS_COLLAPSE_AT) return "";
    var btn=rightsExpanded
      ? '<button class="rights-more-btn" type="button" onclick="rightsSetExpanded(false)">▾ 收起（'+listLen+' 条）</button>'
      : '<button class="rights-more-btn" type="button" onclick="rightsSetExpanded(true)">▸ 展开全部 '+listLen+' 条</button>';
    return btn;
  }
  function getRightsData(){
    if(!window.NEWS_DATA||!window.NEWS_DATA.news) return [];
    // 矿权交易结构化专区只展示「矿业权市场」官方出让/转让公告（ky.mnr.gov.cn），
    // 避免把其它来源被归类为矿权交易的普通新闻混入卡片。
    var arr=window.NEWS_DATA.news.filter(function(it){
      return it.s==="矿业权市场" || /ky\.mnr\.gov\.cn/.test(it.u||"");
    }).map(parseRights);
    // 同一宗公告在数据里常存两个 URL（列表页 + 详情页 / PDF 直链），若按 URL 去重会渲染两遍。
    // 这里按归一化标题去重（与「并购公告去重不能按 URL」是同一类坑）。
    var seen={},out=[];
    arr.forEach(function(r){
      var k=String((r.it&&r.it.t)||"").replace(/[^一-龥A-Za-z0-9]/g,"");
      if(!k||seen[k])return;
      seen[k]=1;out.push(r);
    });
    return out;
  }
  function rightsTypeLabel(r){
    if(r.rightsType==="result") return "结果公示";
    if(r.rightsType==="transfer") return "转让公示";
    if(r.rightsType==="auction") return "拍卖出让";
    return r.method||"出让";
  }
  function renderRightsSection(){
    var data=getRightsData();
    var cardsEl=document.getElementById("rightsCards");
    var emptyEl=document.getElementById("rightsEmpty");
    var countEl=document.getElementById("rightsCount");
    var tocEl=document.getElementById("tocRightsCount");
    if(!cardsEl) return;
    if(!data.length){
      cardsEl.innerHTML="";
      if(emptyEl) emptyEl.hidden=false;
      if(countEl) countEl.textContent="0 条";
      if(tocEl) tocEl.textContent="0";
      return;
    }
    var ref=refDate();
    var fm=(document.getElementById("rightsFilterMethod")||{}).value||"";
    var fmin=(document.getElementById("rightsFilterMineral")||{}).value||"";
    var fwin=(document.getElementById("rightsFilterWindow")||{}).value||"all";
    var list=data.filter(function(r){
      if(fm && r.method!==fm) return false;
      if(fmin){
        if(fmin==="铅锌"){ if(r.it.g.indexOf("铅")<0 && r.it.g.indexOf("锌")<0) return false; }
        else if(fmin==="钨钼"){ if(r.it.g.indexOf("钨")<0 && r.it.g.indexOf("钼")<0) return false; }
        else if(fmin==="多金属"){ if(r.mineral!=="多金属") return false; }
        else { if(r.mineral!==fmin && r.it.g.indexOf(fmin)<0) return false; }
      }
      if(fwin!=="all"){
        var w=parseInt(fwin,10);
        var dd=daysBetween(ref, new Date(r.it.d.replace(/-/g,"/")));
        if(dd<0 || dd>w) return false;
      }
      return true;
    });
    // 暴露「筛选后全量」给 CSV 导出用：卡片/表格受 RIGHTS_COLLAPSE_AT 折叠限制
    // 只渲染前 N 条，若导出时读 DOM 会只拿到 8 条，让用户误以为是全量。
    window.__rightsFullList=list;
    function score(r){
      if(r.deadline){
        var d=daysBetween(new Date(r.deadline.replace(/-/g,"/")), ref);
        if(d<0) return 3;
        if(d<=7) return 0;
        return 1;
      }
      return 2;
    }
    list.sort(function(a,b){
      if(rightsSort.key){
        var va,vb;
        if(rightsSort.key==="mineral"){ va=a.mineral||""; vb=b.mineral||""; return rightsSort.dir==="asc"?va.localeCompare(vb,"zh"):vb.localeCompare(va,"zh"); }
        if(rightsSort.key==="price"){ va=a.price==null?-1:a.price; vb=b.price==null?-1:b.price; }
        else { va=a.deadline||"9999-12-31"; vb=b.deadline||"9999-12-31"; }
        return rightsSort.dir==="asc"?(va<vb?-1:va>vb?1:0):(va>vb?-1:va<vb?1:0);
      }
      var sa=score(a), sb=score(b);
      if(sa!==sb) return sa-sb;
      if(a.deadline && b.deadline) return a.deadline<b.deadline?-1:1;
      return a.it.d>b.it.d?-1:(a.it.d<b.it.d?1:0);
    });
    // 默认折叠：超过阈值只显示前 N 条，其余收进「展开全部」
    var shownList=list.slice(0, rightsExpanded?list.length:RIGHTS_COLLAPSE_AT);
    cardsEl.innerHTML=shownList.map(function(r){
      var badge="";
      if(r.deadline){
        var d=daysBetween(new Date(r.deadline.replace(/-/g,"/")), ref);
        var cls="rc-normal", txt="";
        if(r.rightsType==="result" || r.rightsType==="transfer"){
          txt="公示期 "+fmtDeadline(r.deadline);
          if(d<0){ cls="rc-expired"; txt="公示已结束 "+fmtDeadline(r.deadline); }
          else if(d<=7){ cls="rc-urgent"; txt="公示期 "+fmtDeadline(r.deadline)+" · 剩"+d+"天"; }
        }else{
          txt="截标 "+fmtDeadline(r.deadline);
          if(r.rightsType==="auction") txt="拍卖 "+fmtDeadline(r.deadline);
          if(d<0){ cls="rc-expired"; txt="已截标 "+fmtDeadline(r.deadline); }
          else if(d<=7){ cls="rc-urgent"; txt=(r.rightsType==="auction"?"拍卖 ":"截标 ")+fmtDeadline(r.deadline)+" · 剩"+d+"天"; }
          else if(d<=14){ cls="rc-soon"; txt=(r.rightsType==="auction"?"拍卖 ":"截标 ")+fmtDeadline(r.deadline)+" · 剩"+d+"天"; }
        }
        badge='<span class="rc-deadline '+cls+'">'+txt+'</span>';
      }
      var mineralHtml=r.mineral?'<span class="rc-mineral">'+r.mineral+'</span>':'';
      // 按业务类型决定展示字段
      var grid4='';
      if(r.rightsType==="result"){
        grid4='<div class="rr-field"><span>成交价</span><b class="'+(r.dealPrice==null?'na':'')+'">'+fmtMoney(r.dealPrice)+'</b></div>'
             +'<div class="rr-field"><span>起始价</span><b class="'+(r.startPrice==null?'na':'')+'">'+fmtMoney(r.startPrice)+'</b></div>'
             +'<div class="rr-field"><span>面积</span><b class="'+(r.area==null?'na':'')+'">'+fmtArea(r.area)+'</b></div>'
             +'<div class="rr-field"><span>公示期</span><b class="'+(r.deadline?'':'na')+'">'+fmtDeadline(r.deadline)+'</b></div>';
      }else if(r.rightsType==="transfer"){
        grid4='<div class="rr-field"><span>转让人</span><b class="'+(r.transferor?'':'na')+'">'+(r.transferor||'—')+'</b></div>'
             +'<div class="rr-field"><span>受让人</span><b class="'+(r.transferee?'':'na')+'">'+(r.transferee||'—')+'</b></div>'
             +'<div class="rr-field"><span>面积</span><b class="'+(r.area==null?'na':'')+'">'+fmtArea(r.area)+'</b></div>'
             +'<div class="rr-field"><span>公示期</span><b class="'+(r.deadline?'':'na')+'">'+fmtDeadline(r.deadline)+'</b></div>';
      }else{
        grid4='<div class="rr-field"><span>起始价</span><b class="'+(r.price==null?'na':'')+'">'+fmtMoney(r.price)+'</b></div>'
             +'<div class="rr-field"><span>保证金</span><b class="'+(r.deposit==null?'na':'')+'">'+fmtMoney(r.deposit)+'</b></div>'
             +'<div class="rr-field"><span>面积</span><b class="'+(r.area==null?'na':'')+'">'+fmtArea(r.area)+'</b></div>'
             +'<div class="rr-field"><span>'+(r.rightsType==="auction"?'拍卖日':'截标日')+'</span><b class="'+(r.deadline?'':'na')+'">'+fmtDeadline(r.deadline)+'</b></div>';
      }
      var extra='';
      if(r.rightsType==="result" && r.bidder) extra='<div class="rc-extra">竞得人：'+esc(r.bidder)+'</div>';
      else if(r.rightsType==="transfer" && (r.transferor || r.transferee)) extra='<div class="rc-extra">'+esc(r.transferor||'—')+' → '+esc(r.transferee||'—')+'</div>';
      // 金额摘要：按业务类型取最相关的那个数字（结果看成交价，转让看面积，出让看起始价）
      var numTxt="";
      if(r.rightsType==="result") numTxt=(r.dealPrice==null?"—":r.dealPrice.toLocaleString("zh-CN")+" 万元");
      else if(r.rightsType==="transfer") numTxt=(r.area==null?"—":fmtArea(r.area));
      else numTxt=(r.price==null?"—":r.price.toLocaleString("zh-CN")+" 万元");
      return '<div class="rights-row" data-method="'+r.method+'" data-mineral="'+r.mineral+'">'
        +'<div class="rr-head">'
        +'<span class="rr-type">'+rightsTypeLabel(r)+'</span>'
        +'<a class="rr-title" href="'+safeHref(r.it.u)+'" target="_blank" rel="noopener" title="'+esc(r.it.t)+'">'+esc(r.it.t)+'</a>'
        +(r.region?'<span class="rr-region">📍 '+esc(r.region)+'</span>':'')
        +'</div>'
        +'<div class="rr-grid">'+grid4+'</div>'
        +(badge?'<div class="rr-line">'+badge+'</div>':'')
        +(extra?'<div class="rr-line">'+extra+'</div>':'')
        +'</div>';
    }).join("")+'<div class="rights-more">'+rightsMoreBtn(list.length, shownList.length)+'</div>';
    mdApplySearchToRights();   // 2026-09-10 P1：重渲染后补跑搜索过滤
    if(emptyEl) emptyEl.hidden=list.length>0;
    if(countEl) countEl.textContent=data.length+" 条"+(list.length!==data.length?"（筛后 "+list.length+"）":"");
    if(tocEl) tocEl.textContent=String(list.length);
  }
  // 若今日有矿权出让/转让结果，在 #todaySection 顶部注入一条摘要卡片，锚点至矿权专区
  function injectRightsResultSummary(){
    if(!window.NEWS_DATA || !window.NEWS_DATA.news) return;
    var today=qaReportDate();
    var minerals=['铜','镍','铅','锌','铝','金','银','稀土','钨','钼','锡','锑','锂','钴','铌','钽'];
    var results=[];
    window.NEWS_DATA.news.forEach(function(r){
      var u=r.u||r.url||'';
      var t=r.t||r.title||'';
      var c=r.c||r.category||'';
      var s=r.s||r.source||'';
      var d=r.d||r.orig_date_full||'';
      var n=r.n||r.first_seen||'';
      if(u.indexOf('ky.mnr.gov.cn')===-1) return;
      if(c!=='矿权交易' && s!=='矿业权市场') return;
      var isResult=/结果|成交|竞得|中标/.test(t) && !/挂牌|拍卖|公告/.test(t);
      var isTransfer=/转让/.test(t);
      if(!isResult && !isTransfer) return;
      if(n!==today && d!==today) return;
      results.push(r);
    });
    // 同一宗结果可能有「列表页 + 详情页」两个 URL → 按归一化标题去重，聚合条里只列一次
    var _seen={};
    results=results.filter(function(r){
      var k=String(r.t||r.title||"").replace(/[^一-龥A-Za-z0-9]/g,"");
      if(!k||_seen[k])return false;
      _seen[k]=1;return true;
    });
    if(results.length===0) return;
    if(document.querySelector('.news-item[data-rights-summary="1"]')) return;
    var foundMinerals=[];
    results.forEach(function(r){
      var t=r.t||r.title||'';
      minerals.forEach(function(m){ if(t.indexOf(m)>=0 && foundMinerals.indexOf(m)<0) foundMinerals.push(m); });
    });
    function escA(s){return (s||'').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
    function escT(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
    var html;
    if(results.length===1){
      var fr=results[0];
      var fUrl=escA(fr.u||fr.url||'#rightsSection');
      var fTitle=escT((fr.t||fr.title||'').trim()) || '今日矿权出让结果';
      // 矿权结果摘要不参与「今日新增」计数（2026-09-09）：它是对 rightsSection 的汇总提示，
      // 不是独立新闻条目；若加 is-new，顶部统计会把简报「今日收录 N 条」多算 1 条。
      html='<div class="news-item rights-summary-item" data-url="'+fUrl+'" data-rights-summary="1" data-embed="ok">'
         + '<div class="news-head"><span class="dot"></span><span class="badge-rights">矿权</span>'
         + '<a class="news-title" href="'+fUrl+'">'+fTitle+'</a></div>'
         + '<div class="news-meta"><span class="src">矿业权市场</span> · '+today.slice(5)+'</div>'
         + '<div class="news-summary">今日矿权交易专区更新 1 宗出让/转让结果，点击标题查看原公告。</div>'
         + '</div>';
    } else {
      // 多宗：列出全部原公告标题（各带链接），而非只取首条 +「等 X 宗」
      var links=results.map(function(r){
        var u=escA(r.u||r.url||'#rightsSection');
        var t=escT((r.t||r.title||'').trim());
        return '<a class="rr-link" href="'+safeHref(u)+'" target="_blank" rel="noopener">'+t+'</a>';
      }).join('');
      html='<div class="news-item rights-summary-item" data-url="#rightsSection" data-rights-summary="1" data-embed="ok">'
         + '<div class="news-head"><span class="dot"></span><span class="badge-rights">矿权</span>'
         + '<span class="news-title">今日矿权出让/转让结果共 '+results.length+' 宗</span></div>'
         + '<div class="news-meta"><span class="src">矿业权市场</span> · '+today.slice(5)+'</div>'
         + '<div class="news-summary">今日矿权交易专区更新 '+results.length+' 宗出让/转让结果：'+links+'</div>'
         + '</div>';
    }
    var todaySection=document.getElementById('todaySection');
    if(!todaySection) return;
    // 2026-09-08：读者反馈矿权只需"大致浏览"，不应占据今日新增的头条位置 → 改为追加到末尾
    var wrapper=document.createElement('div');
    todaySection.appendChild(wrapper);
    wrapper.outerHTML=html;
    if(typeof refresh==='function') refresh();
  }
  function bindRights(){
    ["rightsFilterMethod","rightsFilterMineral","rightsFilterWindow"].forEach(function(id){
      var el=document.getElementById(id); if(el) el.addEventListener("change", renderRightsSection);
    });
  }
  // 2026-09-11 P0：app.js 以 defer 加载 → 执行时 readyState 已是 'interactive'。
  // 原实现在 else 分支**当场**调用这三个函数，而它们依赖的模块状态与常量
  // （newsSearchText、STORE_KEY / FAV_KEY / ARCH_FAV_DEFAULT_TITLE 等）都在文件后段才初始化，
  // 于是抛 TDZ ReferenceError，把整个 app.js 打断在半路 —— 这就是 09-11 事故的机制。
  // 改为「本次求值结束后再初始化」：setTimeout 0，届时所有顶层声明都已就绪。
  function mdInitRights(){ renderRightsSection(); injectRightsResultSummary(); bindRights(); }
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded", mdInitRights);
  else setTimeout(mdInitRights, 0);
})();

;




// ===== 已读/未读 + 收藏 + 浏览记录（localStorage，按访问者本机存储）=====
const STORE_KEY='mining_daily_read_urls';
const FAV_KEY='mining_daily_favorites';
const HISTORY_KEY='mining_daily_history';

// 2026-09-06 晚：统一 localStorage 写入封装（隐私模式/配额满时静默失败，不中断交互）
// ⚠️ 2026-09-08 晚修复严重回归：原写法 window.lsSet(k,v) 是自调用（顶层函数声明即 window 属性），
// 无限递归被 try/catch 吞掉 → 09-06 23:20 起所有 lsSet 写入静默失效（已读/收藏/历史/主题/QA 历史等全没存上）。
function lsSet(k,v){try{localStorage.setItem(k,v);}catch(e){}}
// 2026-09-11 P1 修复：qaCacheGet/qaCachePut 读缓存时调用了未定义的 lsGet，导致缓存永远命中不了（ReferenceError 被 try/catch 吞掉）。补齐镜像读函数。
function lsGet(k){try{return localStorage.getItem(k);}catch(e){return null;}}
function getReadSet(){try{return new Set(JSON.parse(localStorage.getItem(STORE_KEY)||'[]'))}catch(e){return new Set()}}
function saveReadSet(s){lsSet(STORE_KEY,JSON.stringify([...s]))}
// 收藏存储：新格式为对象数组 {url,title,date,src}；旧格式（纯URL字符串数组）自动迁移
function getFavs(){
  let arr;try{arr=JSON.parse(localStorage.getItem(FAV_KEY)||'[]')}catch(e){arr=[]}
  if(!Array.isArray(arr))return[];
  return arr.map(v=>typeof v==='string'?{url:v}:v).filter(v=>v&&v.url)
}
function saveFavs(arr){lsSet(FAV_KEY,JSON.stringify(arr.slice(0,300)))}
function getFavUrls(){return new Set(getFavs().map(f=>f.url))}
function getHistory(){try{return JSON.parse(localStorage.getItem(HISTORY_KEY)||'[]')}catch(e){return[]}}
function saveHistory(arr){lsSet(HISTORY_KEY,JSON.stringify(arr.slice(0,100)))}

// 标记已读 + 记录浏览历史
function markRead(url){
  const s=getReadSet();
  if(!s.has(url)){s.add(url);saveReadSet(s);refresh()}
  recordHistory(url);
}
// 按 URL 定位新闻节点。
// 注意：不能写成 '.news-item[data-url="x" data-embed="ok"]' —— 单个方括号内只允许一个属性条件，
// 这种写法整个选择器非法、querySelector 直接抛错，曾导致浏览历史一条都记不下来。
function newsItemByUrl(url){
  var list=document.querySelectorAll('.news-item');
  for(var i=0;i<list.length;i++){ if(list[i].getAttribute('data-url')===url)return list[i]; }
  return null;
}
function recordHistory(url){
  const item=newsItemByUrl(url);
  if(!item)return;
  const title=item.querySelector('.news-title')?.textContent||'';
  const src=item.querySelector('.src')?.textContent||'';
  let arr=getHistory();
  arr=arr.filter(h=>h.url!==url);
  arr.unshift({url,title,src,time:new Date().toISOString()});
  saveHistory(arr);
  updateHistoryCount();
}
function markAllRead(){
  const prev=[...getReadSet()];
  const s=getReadSet();
  document.querySelectorAll('.news-item').forEach(el=>s.add(el.dataset.url));
  saveReadSet(s);refresh();
  if(typeof mdUndoToast==='function')mdUndoToast('已全部标为已读',function(){saveReadSet(new Set(prev));refresh();});
}
function clearAllRead(){
  if(!confirm('确定要清除所有已读记录吗？\n\n所有新闻将恢复为「未读」状态。'))return;
  localStorage.removeItem(STORE_KEY);
  refresh();
}
// 单条标记为未读（针对某一条）
function markUnread(url){
  const s=getReadSet();
  if(s.has(url)){
    s.delete(url);
    saveReadSet(s);
    refresh();
    // 短暂提示
    const item=newsItemByUrl(url);
    if(item){
      const old=item.style.boxShadow;
      item.style.boxShadow='0 0 0 2px #16a085';
      setTimeout(()=>{item.style.boxShadow=old},600);
    }
  }
}

// ===== 收藏功能（对象存储：收藏永久保留，即使新闻滚出页面）=====
function toggleFav(url){
  const favs=getFavs();
  const i=favs.findIndex(f=>f.url===url);
  if(i>=0){favs.splice(i,1)}
  else{
    let el=null;
    document.querySelectorAll('.news-item:not(.arch-fav)').forEach(n=>{if(n.dataset.url===url)el=n});
    const info={url};
    if(el){
      const t=el.querySelector('.news-title');if(t)info.title=t.textContent.trim();
      const m=el.querySelector('.news-meta');if(m)info.date=m.textContent.split('·').pop().trim();
      const sc=el.querySelector('.src');if(sc)info.src=sc.textContent.trim();
    }
    favs.unshift(info);
  }
  saveFavs(favs);
  applyFavStates();
  updateFavCount();
  renderArchivedFavs();
  if(filterMode==='fav')applyFilter();
}
function applyFavStates(){
  const favUrls=getFavUrls();
  document.querySelectorAll('.news-item').forEach(el=>{
    const isFav=favUrls.has(el.dataset.url);
    el.classList.toggle('favorited',isFav);
    const star=el.querySelector('.btn-star');
    if(star)star.innerHTML=isFav?'★':'☆';
  });
}
function updateFavCount(){
  const n=getFavs().length;
  const fc=document.getElementById('favCount'); if(fc)fc.textContent=n;
  // 收藏为 0 时按钮淡化置灰（2026-09-08 深夜），有收藏再点亮
  const fb=document.getElementById('favBtn');
  if(fb)fb.classList.toggle('is-zero',n===0);
  const t=document.getElementById('tocFavCount');
  if(t)t.textContent=n;
  // 2026-09-09：左侧目录「我的收藏」不再显示数字，也始终可见（0 条不隐藏）
}
// ===== 已归档收藏渲染：收藏但新闻已不在当前页面的条目 =====
// 兼容别名：历史调用点较多，统一转发到权威 esc（行为更严：null 安全 + 转义 '）
function escapeHtml(s){return esc(s);}
const ARCH_FAV_DEFAULT_TITLE='🗂️ 已归档收藏（原新闻已滚出页面，收藏记录永久保留）';
function buildArchFavItemHtml(f){
  if(!f)return '';   // 脏数据兜底：整条缺失时不抛错、不渲染
  const url=safeHref(f.url);   // null 安全 + 危险协议过滤 + " 转义
  const title=escapeHtml(f.title||f.url);
  const meta=[escapeHtml(f.src||''),escapeHtml(f.date||'')].filter(Boolean).join(' · ')||'收藏记录';
  const summary=escapeHtml(f.summary||'');
  return '<div class="news-item arch-fav" data-url="'+url+'" data-embed="no">'+
    '<div class="news-head"><span class="dot"></span>'+
    '<a class="news-title" href="'+url+'" target="_blank">'+title+'</a></div>'+
    '<div class="news-meta"><span class="src">'+meta+'</span></div>'+
    (summary?'<div class="news-summary">'+summary+'</div>':'')+
    '</div>';
}
function renderArchivedFavs(){
  const list=document.getElementById('archFavList');
  const sec=document.getElementById('archivedFavSection');
  if(!list||!sec)return;
  list.innerHTML='';
  const titleEl=sec.querySelector('.section-title');
  if(titleEl)titleEl.childNodes[0].textContent=ARCH_FAV_DEFAULT_TITLE;
  const pageUrls=new Set();
  document.querySelectorAll('.news-item').forEach(el=>pageUrls.add(el.dataset.url));
  const archived=getFavs().filter(f=>f.url&&!pageUrls.has(f.url));
  document.getElementById('archFavCount').textContent=archived.length+'条';
  list.innerHTML=archived.map(buildArchFavItemHtml).join('');
}

// ===== 收藏 / 浏览记录聚合视图（2026-09-09）=====
// 点击目录「我的收藏」或「浏览记录」时，不再区分今日/往期，
// 而是把命中条目（当前页面内 + 已滚出页面的归档）聚合到 #archivedFavSection 平铺展示。
function extractItemDate(el){
  const meta=el.querySelector('.news-meta');
  if(!meta)return '';
  const parts=meta.textContent.split('·');
  return (parts[parts.length-1]||'').trim();
}
function renderFavHistoryAggregate(mode){
  const list=document.getElementById('archFavList');
  const sec=document.getElementById('archivedFavSection');
  if(!list||!sec)return;
  list.innerHTML='';
  const titleEl=sec.querySelector('.section-title');
  const countEl=document.getElementById('archFavCount');
  const pageUrls=new Set();
  document.querySelectorAll('.news-item').forEach(el=>pageUrls.add(el.dataset.url));
  const items=[];
  if(mode==='fav'){
    if(titleEl)titleEl.childNodes[0].textContent='⭐ 我的收藏';
    const favs=getFavs();
    const favMap=new Map(favs.map(f=>[f.url,f]));
    // 当前页面内的收藏条目（克隆）
    document.querySelectorAll('.news-item').forEach(el=>{
      if(favMap.has(el.dataset.url)){
        items.push({type:'page', date:extractItemDate(el), time:'', el:el, url:el.dataset.url});
      }
    });
    // 已滚出页面的归档收藏
    favs.forEach(f=>{
      if(!pageUrls.has(f.url)){
        items.push({type:'arch', date:f.date||'', time:'', url:f.url, data:f});
      }
    });
  } else if(mode==='history'){
    if(titleEl)titleEl.childNodes[0].textContent='📋 浏览记录';
    const history=getHistory();
    const histMap=new Map(history.map(h=>[h.url,h]));
    document.querySelectorAll('.news-item').forEach(el=>{
      if(histMap.has(el.dataset.url)){
        const h=histMap.get(el.dataset.url);
        items.push({type:'page', date:extractItemDate(el), time:h.time||'', el:el, url:el.dataset.url});
      }
    });
    history.forEach(h=>{
      if(!pageUrls.has(h.url)){
        items.push({type:'arch', date:formatHistoryDate(h.time)||'', time:h.time||'', url:h.url, data:h});
      }
    });
  }
  // 排序：有精确 time 优先按 time 倒序（浏览记录），否则按 date 字符串倒序
  items.sort(function(a,b){
    if(a.time&&b.time) return new Date(b.time)-new Date(a.time);
    return String(b.date||'').localeCompare(String(a.date||''));
  });
  const frag=document.createDocumentFragment();
  items.forEach(function(it){
    if(it.type==='page'){
      const clone=it.el.cloneNode(true);
      clone.classList.remove('hidden');
      clone.classList.add('aggregate-clone');
      frag.appendChild(clone);
    } else {
      const wrapper=document.createElement('div');
      if(mode==='fav'){
        wrapper.innerHTML=buildArchFavItemHtml(it.data);
      } else {
        wrapper.innerHTML=buildHistoryItemHtml(it.data);
      }
      frag.appendChild(wrapper.firstElementChild);
    }
  });
  list.appendChild(frag);
  if(countEl)countEl.textContent=items.length+'条';
  if(items.length===0){
    const emptyMsg = mode==='fav'
      ? '<div class="aggregate-empty"><div class="empty-icon">⭐</div><div class="empty-title">暂无收藏</div><div class="empty-tip">打开任意条目后，点击右侧的 ★ 即可收藏到这里</div></div>'
      : '<div class="aggregate-empty"><div class="empty-icon">📋</div><div class="empty-title">暂无浏览记录</div><div class="empty-tip">打开任意条目后会自动记录到这里</div></div>';
    list.innerHTML=emptyMsg;
  }
  // 为聚合列表注入星标/未读按钮并同步收藏态
  injectStars();
  applyFavStates();
  const readUrls=getReadSet();
  list.querySelectorAll('.news-item').forEach(el=>el.classList.toggle('read',readUrls.has(el.dataset.url)));
}
function formatHistoryDate(iso){
  if(!iso)return '';
  try{
    const d=new Date(iso);
    const mm=('0'+(d.getMonth()+1)).slice(-2);
    const dd=('0'+d.getDate()).slice(-2);
    return mm+'-'+dd;
  }catch(e){return '';}
}
function buildHistoryItemHtml(h){
  const url=safeHref(h.url);   // null 安全 + 危险协议过滤 + " 转义
  const title=escapeHtml(h.title||h.url||'未知条目');
  const src=escapeHtml(h.src||'浏览记录');
  const date=escapeHtml(formatHistoryDate(h.time)||'');
  return '<div class="news-item arch-fav" data-url="'+url+'" data-embed="no">'+
    '<div class="news-head"><span class="dot"></span>'+
    '<a class="news-title" href="'+url+'" target="_blank">'+title+'</a></div>'+
    '<div class="news-meta"><span class="src">'+src+'</span>'+(date?' · '+date:'')+'</div>'+
    '</div>';
}

// ===== 整张卡片点击打开原文（2026-09-05 增强）=====
// 标题与「查看原文」本就是 <a> 链接直接可点；这里补全：点击卡片其余区域（摘要/来源等）
// 也能打开原文。点 <a>（链接本身）或 <button>（收藏/未读等）不拦截，走各自默认行为。
// 同时标记已读，与「浏览记录」统计口径一致。
function setupCardOpen(){
  document.addEventListener('click',function(e){
    var item=e.target.closest?e.target.closest('.news-item,.hot-item,.digest-list > li'):null;
    if(!item)return;
    if(e.target.closest('a')||e.target.closest('button'))return; // 链接/按钮各自处理
    var url=item.getAttribute('data-url');
    if(url&&url!=='#'&&/^https?:/i.test(url)){
      e.preventDefault();
      markRead(url);
      window.open(url,'_blank','noopener');
    }
  });
}
function updateHistoryCount(){
  const n=getHistory().length;
  const hc=document.getElementById('historyCount'); if(hc)hc.textContent=n;
  const t=document.getElementById('tocHistoryCount');
  if(t)t.textContent=n;
  // 2026-09-09：左侧目录「浏览记录」不再显示数字，也始终可见（0 条不隐藏）
}

// ===== 新一轮找矿突破战略行动专项：按关键词自动识别并归类 =====
// 命中关键词的新闻从"今日新增/往期内容"移动到专项区对应子类（不重复展示）
// 找矿专项归集：仅当标题/摘要明确含"找矿"或"新一轮找矿突破战略行动"才归专项。
// 2026-09-07 收紧：原 SPECIAL_KEYWORDS 含"关键矿产/绿色勘查/增储/战略性矿产"等过宽词，
// 会把"英国关键矿产供应链""绿色矿业六大场景科普"等国际动态/技术科普误拉进专项区（与往期区重复出现）。
function isSpecialNews(el){
  const title=((el.querySelector('.news-title')||{}).textContent||'');
  const t=title+((el.querySelector('.news-summary')||{}).textContent||'');
  // 矿权出让/转让/挂牌/拍卖类公告不进专项（属常规矿权交易分类，即使摘要提到"战略性矿产/增储"等词）
  if(/(出让|转让|挂牌|拍卖|成交公示|招拍挂)/.test(title))return false;
  // 收窄：必须明确围绕"找矿突破战略行动"才归专项，避免过宽词误归类
  return t.includes('找矿') || t.includes('新一轮找矿突破战略行动');
}
// 专项子类归类：政策/成果/技术/资源安全（未命中前者的默认归技术）
function initSpecial(){
  // 2026-09-08 改造：找矿专项区已取消。原实现会把命中"找矿"的条目 DOM 搬移到专项区，
  // 造成同一话题被拆到两处看（读者反馈"专项里的内容基本都是前面的"）。
  // 现在只补「战略」徽章做标记，条目留在今日新增 / 往期内容的原位（子分类：找矿成果与勘查技术）。
  document.querySelectorAll('#todaySection .news-item, #archiveSection .news-item').forEach(el=>{
    if(el.classList.contains('arch-fav'))return;
    if(!isSpecialNews(el))return;
    el.classList.add('is-special');
    const head=el.querySelector('.news-head');
    if(!head||head.querySelector('.badge-strategy'))return;
    const badge=document.createElement('span');
    badge.className='badge-strategy';
    badge.textContent='战略';
    badge.title='新一轮找矿突破战略行动相关';
    head.insertBefore(badge,head.querySelector('.news-title'));
  });
}

// ===== 筛选模式：none | new | fav | history | tag | special =====
// filterMode / tagFilter / newsSearchText / oldExpanded 的声明已于 2026-09-11
// 提到文件最前端（见文件头注释）：留在原位置会被矿权 IIFE 的即时调用命中 TDZ。
function setFilter(mode,noScroll){
  filterMode=mode;
  if(mode==='none'){document.body.removeAttribute('data-filter-mode');}
  else{document.body.dataset.filterMode=mode;}
  if(mode!=='tag'){tagFilter=null;setChipActive(null)}
  // 2026-09-09：顶栏「未读」「筛选」按钮已移除，以下控件可能不存在，统一做空值保护。
  const filterBtn=document.getElementById('filterBtn');
  if(filterBtn){filterBtn.classList.toggle('active',mode==='new');filterBtn.textContent=mode==='new'?'显示全部':'只看新增';}
  const spBtn=document.getElementById('specialBtn');
  if(spBtn)spBtn.classList.toggle('active',mode==='special');
  const unBtn=document.getElementById('unreadBtn');
  if(unBtn)unBtn.classList.toggle('active',mode==='unread');
  const favBtn=document.getElementById('favBtn'); if(favBtn)favBtn.classList.toggle('active',mode==='fav');
  const historyBtn=document.getElementById('historyBtn'); if(historyBtn)historyBtn.classList.toggle('active',mode==='history');
  // 下拉触发按钮在「只看新增 / 战略」任一激活时高亮（按钮已移除，保留兼容）
  const ft=document.querySelector('.nf-filter-toggle'); if(ft)ft.classList.toggle('active',mode==='new'||mode==='special');
  // 2026-09-09 凌晨重写：筛选后要「落到命中项上」，而不是机械还原旧坐标。
  // 旧实现只还原 prevY，但收藏/历史的命中项往往在往期区，还原后视口里仍是一片被隐藏的今日区 →
  // 用户感觉「跳不过去」。新逻辑：原位已能看到命中就不动，否则滚到第一条命中并轻微高亮。
  const _y=(window.pageYOffset||document.documentElement.scrollTop||0);
  applyFilter();
  syncTocActive(mode);
  if(!noScroll)keepViewportAfterFilter(_y,mode);
}
// 目录里的「我的收藏 / 浏览记录」与工具条按钮同步高亮
function syncTocActive(mode){
  var map={fav:'tocFavItem',history:'tocHistoryItem'};
  document.querySelectorAll('.toc-main-item').forEach(function(it){
    if(it.id==='tocFavItem'||it.id==='tocHistoryItem')return;
    it.classList.remove('active');
  });
  ['tocFavItem','tocHistoryItem'].forEach(function(id){
    var el=document.getElementById(id);
    if(el)el.classList.toggle('active',map[mode]===id);
  });
}
// 自身 + 所有祖先都没有 display:none / visibility:hidden 才算真可见。
// 不用 offsetParent：它依赖布局，父级 section 被 display:none 时行为不可靠，且无法在无布局环境校验。
function mdIsVisible(el){
  if(!el||el.nodeType!==1)return false;
  if(el.classList&&el.classList.contains('hidden'))return false;
  var n=el;
  while(n&&n.nodeType===1){
    if(n.style&&n.style.display==='none')return false;
    var st=(typeof window.getComputedStyle==='function')?window.getComputedStyle(n):null;
    if(st&&(st.display==='none'||st.visibility==='hidden'))return false;
    n=n.parentElement;
  }
  return true;
}
// 收集当前真实可见的命中条目
function collectVisibleMatches(){
  var out=[];
  document.querySelectorAll('.news-item').forEach(function(el){
    if(!mdIsVisible(el))return;
    out.push(el);
  });
  return out;
}
// 筛选后 0 命中：给一句明确反馈，避免「页面一片空白」被误判成坏了
function mdShowFilterEmpty(mode){
  var tip=document.getElementById('mdFilterEmptyTip');
  if(!tip){
    tip=document.createElement('div');
    tip.id='mdFilterEmptyTip';
    tip.className='md-filter-tip';
    document.body.appendChild(tip);
  }
  var msg;
  if(mode==='fav')msg='还没有收藏任何条目 —— 点条目右侧的 ★ 即可收藏';
  else if(mode==='history')msg='还没有浏览记录 —— 打开过的条目会自动记入这里';
  else if(mode==='unread')msg='所有条目都已读 —— 可点「↻ 全部恢复未读」';
  else if(mode==='new')msg='今日暂无新增条目';
  else if(mode==='special')msg='暂无带「战略」徽章的条目';
  else msg='没有符合当前条件的条目';
  tip.textContent=msg;
  tip.classList.add('show');
  clearTimeout(window.__mdTipT);
  window.__mdTipT=setTimeout(function(){try{tip.classList.remove('show')}catch(e){}},2600);
}
// 统一滚动出口，便于无布局环境下被替换校验
function mdScrollTo(y,smooth){
  try{
    if(smooth){ window.scrollTo({top:y,behavior:'smooth'}); }
    else{ window.scrollTo(0,y); }
  }catch(e){ try{window.scrollTo(0,y);}catch(e2){} }
}
function keepViewportAfterFilter(prevY,mode){
  mode=mode||filterMode;
  // 双 rAF：等 section 显隐 / 子分类折叠等样式落地后再量高度，否则会读到旧布局
  requestAnimationFrame(function(){requestAnimationFrame(function(){
    var maxY=Math.max(0,(document.documentElement.scrollHeight||0)-(window.innerHeight||0));
    if(mode==='none'){                       // 取消筛选：只还原位置，不主动跳
      mdScrollTo(Math.min(prevY,maxY),false);
      return;
    }
    var hits=collectVisibleMatches();
    if(!hits.length){                        // 0 命中：给出空态提示，不乱跳
      mdShowFilterEmpty(mode);
      return;
    }
    var vh=window.innerHeight||0, i, r;
    for(i=0;i<hits.length;i++){              // 视口内已有命中 → 不动（防止无谓抖动）
      r=hits[i].getBoundingClientRect();
      if(r.bottom>0&&r.top<vh*0.85)return;
    }
    var first=hits[0];
    var top=(window.pageYOffset||document.documentElement.scrollTop||0);
    var y=Math.max(0,Math.min(first.getBoundingClientRect().top+top-16,maxY));
    mdScrollTo(y,true);
    try{                                     // 轻微高亮，让用户确认「跳到这里了」
      first.classList.remove('md-focus-flash');
      void first.offsetWidth;
      first.classList.add('md-focus-flash');
      setTimeout(function(){first.classList.remove('md-focus-flash')},1400);
    }catch(e){}
  });});
}
// ===== 往期区日组自动展开（2026-09-09 凌晨）=====
// 往期区按「日组」折叠，条目被折叠时带内联 display:none。筛选/搜索时若放着不管，
// 命中项即使没被加 .hidden 也依然看不见 → 点「收藏/浏览记录」像是什么都没发生。
// 这里在进入筛选时临时展开全部日组，退出筛选时按快照还原用户原本的折叠状态。
var _dayGroupSnapshot=null;
function mdSetDayGroup(head,collapsed){
  if(!head)return;
  head.setAttribute('data-collapsed',String(!!collapsed));
  head.setAttribute('aria-expanded',String(!collapsed));
  var arrow=head.querySelector('.day-arrow'); if(arrow)arrow.textContent=collapsed?'▸':'▾';
  var n=head.nextElementSibling,cnt=0;
  while(n&&cnt<500){
    if(n.classList&&(n.classList.contains('day-group')||n.classList.contains('sub-cat')))break;
    if(n.classList&&n.classList.contains('news-item')){ n.style.display=collapsed?'none':''; cnt++; }
    n=n.nextElementSibling;
  }
}
function mdAutoExpandDayGroups(active){
  var heads=document.querySelectorAll('.day-group');
  if(!heads.length)return;
  if(active){
    if(_dayGroupSnapshot)return;                       // 已展开过，别重复覆盖快照
    _dayGroupSnapshot=[];
    heads.forEach(function(h){ _dayGroupSnapshot.push({h:h,collapsed:h.getAttribute('data-collapsed')==='true'}); });
    heads.forEach(function(h){ mdSetDayGroup(h,false); });
  }else if(_dayGroupSnapshot){
    _dayGroupSnapshot.forEach(function(r){ mdSetDayGroup(r.h,r.collapsed); });
    _dayGroupSnapshot=null;
  }
}
function applyFilter(){
  const favUrls=getFavUrls();
  const historyUrls=new Set(getHistory().map(h=>h.url));
  const readUrls=getReadSet();
  const mode=filterMode;
  // 筛选/搜索激活 → 临时展开往期日组，保证命中项真的能露出来
  mdAutoExpandDayGroups(mode!=='none'||!!newsSearchText);
  document.querySelectorAll('.news-item').forEach(el=>{
    let show=true;
    if(mode==='new')show=el.classList.contains('is-new');
    else if(mode==='special')show=el.classList.contains('is-special');
    else if(mode==='unread')show=!readUrls.has(el.dataset.url);
    else if(mode==='fav')show=favUrls.has(el.dataset.url);
    else if(mode==='history')show=historyUrls.has(el.dataset.url);
    else if(mode==='tag')show=!!tagFilter&&!!el.dataset.tags&&el.dataset.tags.split('|').includes(tagFilter);
    // 已归档收藏仅在"收藏/历史"筛选中可见
    if(el.classList.contains('arch-fav')&&mode!=='fav'&&mode!=='history')show=false;
    // 2026-09-11 IA评审 A2：矿种单字走语境消歧（表外词仍子串），避免点「金」把资金/基金/金融全捞进来
    if(show&&newsSearchText){
      if(!mdMineralHit(el.textContent||'',newsSearchText))show=false;
    }
    // 无筛选模式下，超过14天的旧闻默认折叠（搜索激活时穿透折叠，露出往期匹配项）
    if(show&&mode==='none'&&el.classList.contains('old-folded')&&!oldExpanded&&!newsSearchText)show=false;
    el.classList.toggle('hidden',!show);
  });
  mdApplySearchToRights();   // 2026-09-10 P1：矿权行同步参与搜索
  // 隐藏空子分类
  document.querySelectorAll('.sub-cat').forEach(cat=>{
    let hasVis=false,sib=cat.nextElementSibling;
    while(sib&&!sib.classList.contains('sub-cat')){
      if(sib.classList.contains('news-item')&&!sib.classList.contains('hidden')){hasVis=true;break}
      sib=sib.nextElementSibling;
    }
    cat.style.display=hasVis?'':'none';
  });
  // 收藏 / 浏览记录进入聚合视图：隐藏 today/archive，统一在 archivedFavSection 平铺
  const todaySec=document.getElementById('todaySection');
  const archiveSec=document.getElementById('archiveSection');
  const archFavSec=document.getElementById('archivedFavSection');
  if(mode==='fav'||mode==='history'){
    renderFavHistoryAggregate(mode);
    if(todaySec)todaySec.style.display='none';
    if(archiveSec)archiveSec.style.display='none';
    if(archFavSec)archFavSec.style.display='';
  } else {
    if(archFavSec)archFavSec.style.display='none';
    renderArchivedFavs(); // 恢复默认归档收藏列表
    // today/archive 显示交给 refreshSectionVisibility
  }
  refreshSectionVisibility();
  mdSyncSearchEmpty();
  mdSyncFilterState();
}

// 【2026-09-08 P0-2 修复】热榜 / AI 深度解析两个区块从上线起从未显示过。
// 根因：原逻辑只统计 .news-item，而热榜内容是 li.hot-item、AI 在 .ai-list 内，
// 计数恒为 0 → 被 display:none；且该判断只在 applyFilter 里跑一次，跑在异步渲染之前，
// 等数据渲染完再没有任何代码恢复显示。
// 修复：① 按各区块真实子元素判断 ② 抽成函数，异步渲染后由 mdRefreshSections() 重新评估。
// 2026-09-10 P0：搜索 0 命中 → 可操作空态（带清除入口），替代原先"整块消失"的观感
// 2026-09-10 P1：矿权行此前完全不参与全局搜索，搜"铜"只过滤新闻、矿权区纹丝不动。
// 抽成函数：① applyFilter 里随搜索一起跑 ② renderRightsSection 重渲染后再跑一次（否则 innerHTML 一刷就丢）。
function mdApplySearchToRights(){
  document.querySelectorAll(".rights-row").forEach(function(el){
    if(!newsSearchText){ el.classList.remove("hidden"); return; }
    // 2026-09-11 IA评审 A2：矿权行与新闻条目共用同一套矿种语义，避免点「金」误中金融类矿权行
    el.classList.toggle("hidden", !mdMineralHit(el.textContent||"",newsSearchText));
  });
}
function mdSyncSearchEmpty(){
  var box=document.getElementById("mdSearchEmpty");
  var anchor=document.getElementById("todaySection");
  if(!anchor)return;
  if(!newsSearchText){ if(box)box.style.display="none"; return; }
  var n=document.querySelectorAll(".news-item:not(.hidden),.rights-row:not(.hidden)").length;
  if(n>0){ if(box)box.style.display="none"; return; }
  if(!box){
    box=document.createElement("div"); box.id="mdSearchEmpty"; box.className="search-empty";
    anchor.parentNode.insertBefore(box, anchor);
  }
  var kw=String(newsSearchText||"").replace(/[<>&"]/g,"");
  box.innerHTML='<div class="se-icon">🔍</div>'
    +'<div class="se-title">没有匹配「'+kw+'」的条目</div>'
    +'<div class="se-tip">试试更短的关键词，或清除搜索查看全部</div>'
    +'<button class="se-btn" type="button" id="mdSearchClear">清除搜索</button>';
  var btn=document.getElementById("mdSearchClear");
  if(btn)btn.addEventListener("click",function(){
    var i=document.getElementById("nfSearch"); if(i)i.value="";
    newsSearchText=""; applyFilter();
    if(typeof updateNfCount==="function")updateNfCount();
  });
  box.style.display="";
}
// ==================== 2026-09-10 P2 ====================
// P2-2：目录 8 个条目 / 返回顶部 / 展开更早 都是 div+onclick，键盘完全不可达。
// 用 JS 统一补（而不是改 HTML）：fold-toggle 位于每日生成区，改 HTML 会被生成器冲掉，运行时补就没这问题。
function mdEnhanceKeyboard(){
  // 2026-09-11 IA评审 A5：筛选 chip 是 <span>，与目录项同理运行时补 role/tabindex/Enter，键盘可达（不改 <button>，避免 CSS 回归）
  document.querySelectorAll('.toc-main-item,.toc-back-top,.fold-toggle,.nf-chip').forEach(function(el){
    if(el.getAttribute('data-md-kb'))return;
    if(!el.hasAttribute('role'))el.setAttribute('role','button');
    if(!el.hasAttribute('tabindex'))el.setAttribute('tabindex','0');
    el.setAttribute('data-md-kb','1');
    el.addEventListener('keydown',function(e){
      if(e.key!=='Enter'&&e.key!==' '&&e.key!=='Spacebar')return;
      e.preventDefault(); el.click();
    });
  });
}
// P2-3：页面没有 main/header 地标，也没有标题层级（157 条新闻无法跳转导航）。
// 不改 DOM 结构（风险大且会碰生成区），改为运行时挂 role=heading + aria-level + section 的 aria-label。
function mdA11yLandmarks(){
  document.querySelectorAll('.section').forEach(function(sec){
    var t=sec.querySelector('.section-title');
    var label=t?(t.textContent||'').trim().replace(/\s+/g,' '):'';
    if(label&&!sec.getAttribute('aria-label'))sec.setAttribute('aria-label',label.slice(0,40));
    if(t&&!t.hasAttribute('role')){t.setAttribute('role','heading');t.setAttribute('aria-level','2');}
  });
  document.querySelectorAll('.sub-cat').forEach(function(c){
    if(!c.hasAttribute('role')){c.setAttribute('role','heading');c.setAttribute('aria-level','3');}
  });
  // 2026-09-10 补：真地标 + 「跳到主内容」。
  // 页面骨架全是 div，屏幕阅读器与键盘用户无法按地标跳转（157 条新闻只有 5 个标题）。
  // 生成器每天重建今日区/往期区，所以这里沿用 P0/P1/P2 的做法——JS 运行时补 role，
  // 不把结构写进生成区（否则明天就被冲掉）。
  try{
    var toc=document.getElementById('tocSidebar');
    if(toc&&!toc.getAttribute('aria-label'))toc.setAttribute('aria-label','目录导航');
    var rail=document.querySelector('.col-rail');
    if(rail&&!rail.getAttribute('aria-label'))rail.setAttribute('aria-label','侧栏：矿业热榜与近期会展');
    var hd=document.querySelector('.header');
    if(hd&&!hd.getAttribute('role'))hd.setAttribute('role','banner');
    var ft=document.querySelector('.footer');
    if(ft&&!ft.getAttribute('role'))ft.setAttribute('role','contentinfo');
    var main=document.querySelector('.container');
    if(main&&!main.getAttribute('role')){
      main.setAttribute('role','main');
      if(!main.id)main.id='mdMain';
      if(!document.getElementById('mdSkipLink')){
        var a=document.createElement('a');
        a.id='mdSkipLink'; a.className='md-skip-link'; a.href='#'+main.id;
        a.textContent='跳到主内容';
        document.body.insertBefore(a, document.body.firstChild);
      }
    }
  }catch(e){ console.warn('mdA11yLandmarks:', e); }
}
// P2-7a：筛选态没有全局指示和出口——切到「只看未读」后页面只剩一片，很容易忘了自己在筛选中。
function mdSyncFilterState(){
  var bar=document.getElementById('mdFilterState');
  var anchor=document.getElementById('todaySection');
  if(!anchor)return;
  var parts=[];
  if(filterMode==='new')parts.push('只看新增');
  else if(filterMode==='special')parts.push('只看专题');
  else if(filterMode==='unread')parts.push('只看未读');
  else if(filterMode==='fav')parts.push('只看收藏');
  else if(filterMode==='history')parts.push('浏览记录');
  else if(filterMode==='tag'&&tagFilter)parts.push('标签：'+tagFilter);
  if(newsSearchText)parts.push('搜索：'+newsSearchText);
  if(!parts.length){ if(bar)bar.style.display='none'; return; }
  if(!bar){
    bar=document.createElement('div'); bar.id='mdFilterState'; bar.className='filter-state';
    // 2026-09-11 IA评审 A6：筛选态变化需对读屏用户播报
    bar.setAttribute('role','status'); bar.setAttribute('aria-live','polite');
    anchor.parentNode.insertBefore(bar, anchor);
  }
  bar.innerHTML='<span class="fs-label">筛选中</span><span class="fs-tags">'+esc(parts.join(' · '))+'</span>'
    +'<button type="button" class="fs-clear" id="mdFilterClear">清除筛选</button>';
  var b=document.getElementById('mdFilterClear');
  if(b)b.addEventListener('click',function(){ mdClearAllFilters(); });
  bar.style.display='';
}
function mdClearAllFilters(){
  var i=document.getElementById('nfSearch'); if(i)i.value='';
  newsSearchText='';
  if(typeof setFilter==='function')setFilter('none'); else { filterMode='none'; tagFilter=null; }
  if(typeof updateNfCount==='function')updateNfCount();
  applyFilter();
}
// P2-7b：可撤销的轻提示（「全部标为已读」此前无确认也无撤销，点错只能手动一条条恢复）
var _mdToastTimer=null;
function mdUndoToast(msg, undo){
  var old=document.getElementById('mdToast'); if(old)old.remove();
  var t=document.createElement('div'); t.id='mdToast'; t.className='md-toast';
  // 2026-09-11 IA评审 A6：撤销提示是操作结果，需对读屏用户播报
  t.setAttribute('role','status'); t.setAttribute('aria-live','polite');
  t.innerHTML='<span>'+esc(msg)+'</span><button type="button" class="md-undo">撤销</button>';
  t.querySelector('.md-undo').addEventListener('click',function(){
    try{undo();}catch(e){} t.remove();
  });
  document.body.appendChild(t);
  clearTimeout(_mdToastTimer);
  _mdToastTimer=setTimeout(function(){ if(t.parentNode)t.remove(); }, 8000);
}
// P2-6：单列（≤1100px）时右栏沉底，热榜排在安装指引之后、会展还被隐藏。
// 跨栏重排不能靠 order（父节点不同），改为移动端把安装指引移到栅格末尾：
// 今日 → 往期 → 矿权 → 热榜 → 会展 → 安装指引。回到桌面宽度再还原。
var _mdGuideOrigin=null;
function mdMobileRailOrder(){
  var grid=document.querySelector('.news-grid');
  var guide=document.getElementById('installGuideSection');
  if(!grid||!guide)return;
  var narrow=false;
  try{ narrow=!!(window.matchMedia&&window.matchMedia('(max-width:1100px)').matches); }catch(e){}
  if(narrow){
    if(guide.parentNode!==grid){
      if(!_mdGuideOrigin)_mdGuideOrigin={parent:guide.parentNode,next:guide.nextSibling};
      grid.appendChild(guide);
    }
  }else if(_mdGuideOrigin){
    if(_mdGuideOrigin.next&&_mdGuideOrigin.next.parentNode===_mdGuideOrigin.parent){
      _mdGuideOrigin.parent.insertBefore(guide,_mdGuideOrigin.next);
    }else{
      _mdGuideOrigin.parent.appendChild(guide);
    }
    _mdGuideOrigin=null;
  }
}
function mdP2Init(){ mdEnhanceKeyboard(); mdA11yLandmarks(); mdMobileRailOrder(); }
if(document.readyState!=='loading'){
  setTimeout(mdP2Init,300);
}else{
  document.addEventListener('DOMContentLoaded',function(){ setTimeout(mdP2Init,300); });
}
var _mdResizeTimer=null;
window.addEventListener('resize',function(){
  clearTimeout(_mdResizeTimer);
  _mdResizeTimer=setTimeout(function(){ mdMobileRailOrder(); mdA11yLandmarks(); mdEnhanceKeyboard(); },200);
});
function refreshSectionVisibility(){
  // 聚合视图（收藏/浏览记录）由 applyFilter 显式控制各区块显隐，避免这里按子元素数量把
  // today/archive 重新显示出来，导致用户仍看到旧的折叠日组而非干净的聚合列表。
  const fm=document.body.dataset.filterMode;
  if(fm==='fav'||fm==='history')return;
  document.querySelectorAll('.section').forEach(sec=>{
    // 静态说明区：跳过新闻数判断常显
    if(sec.id==='installGuideSection'||sec.id==='archivedFavSection'||sec.id==='rightsSection')return;
    var vis;
    if(sec.id==='hotListSection'){
      vis=sec.querySelectorAll('li.hot-item').length;          // 热榜用 li.hot-item
    }else{
      // AI 深度解析区块已于 2026-09-08 移除（静态托管下 api 必 404），这里不再有 aiSection 分支
      vis=sec.querySelectorAll('.news-item:not(.hidden)').length;
    }
    sec.style.display=vis?'':'none';
  });
}
// 供异步渲染完成后回调（含多次延时兜底，覆盖 fetch 时序不确定的情况）
function mdRefreshSections(){
  try{ refreshSectionVisibility(); }catch(e){ console.warn('mdRefreshSections:',e); }
}
window.mdRefreshSections=mdRefreshSections;

// AI Key 自填入口的交互绑定（由 ai-disabled 渲染后调用）
function mdBindAiKeyBox(){
  var btn=document.getElementById('aiKeySave'), inp=document.getElementById('aiKeyInput');
  if(!btn||!inp) return;
  function save(){
    var v=(inp.value||'').trim();
    if(!window.mdSetDsKey(v)){
      alert('Key 格式不正确：应以 sk- 开头且长度足够。请到 DeepSeek 控制台复制完整 Key。');
      return;
    }
    try{ qaAiProbe(); }catch(e){}
    alert('已启用 AI 解析，页面将刷新以重新生成内容。');
    try{ location.reload(); }catch(e){}
  }
  btn.onclick=save;
  inp.onkeydown=function(e){ if(e.key==='Enter'){ save(); } };
}
window.mdBindAiKeyBox=mdBindAiKeyBox;
// 顶栏「筛选 ▾」下拉（2026-09-09）：收起只看新增 / 战略，减少常驻按钮
function toggleFilterDropdown(force){
  var menu=document.getElementById('filterDropdownMenu');
  if(!menu)return;
  var btn=document.querySelector('.nf-filter-toggle');
  var open=(typeof force==='boolean')?force:menu.hasAttribute('hidden');
  if(open){menu.removeAttribute('hidden');}else{menu.setAttribute('hidden','');}
  if(btn)btn.setAttribute('aria-expanded',open?'true':'false');
}
document.addEventListener('click',function(e){
  var dd=document.querySelector('.nf-filter-dropdown');
  if(!dd||dd.contains(e.target))return;          // 点触发按钮/菜单内不关闭
  var menu=document.getElementById('filterDropdownMenu');
  if(menu&&!menu.hasAttribute('hidden'))toggleFilterDropdown(false);
});
function toggleFavFilter(){clearView();setFilter(filterMode==='fav'?'none':'fav')}
function toggleHistoryFilter(){clearView();setFilter(filterMode==='history'?'none':'history')}
function showAll(){
  // noScroll=true：本函数自己要回顶部，不能让 setFilter 的 rAF 还原把页面拖回原处
  setFilter('none',true);
  document.body.removeAttribute('data-view');
  document.querySelectorAll('.toc-main-item').forEach(i=>i.classList.remove('active'));
  var all=document.querySelector('.toc-all'); if(all)all.classList.add('active');
  window.scrollTo({top:0,behavior:'smooth'});
}

// ===== 往期内容自动折叠：发布超过14天的旧闻默认隐藏（兜底，防止页面无限膨胀）=====
function foldOldArchive(){
  const arch=document.getElementById('archiveSection');
  const btn=document.getElementById('foldToggle');
  if(!arch)return;
  const now=new Date();
  const cutoff=new Date(now.getTime()-14*86400000);
  let n=0;
  arch.querySelectorAll('.news-item').forEach(el=>{
    if(el.classList.contains('old-folded')){n++;return}
    const meta=el.querySelector('.news-meta');
    const m=meta?meta.textContent.match(/(\d{1,2})-(\d{1,2})/):null;
    if(!m)return;
    const d=new Date(now.getFullYear(),+m[1]-1,+m[2]);
    if(d<cutoff&&!el.classList.contains('is-new')){el.classList.add('old-folded');n++}
  });
  if(btn){
    btn.style.display=n?'':'none';
    if(!oldExpanded)btn.textContent='▸ 展开更早内容（'+n+'条，发布超过14天）';
  }
}
function toggleOldFold(){
  oldExpanded=!oldExpanded;
  const btn=document.getElementById('foldToggle');
  const n=document.querySelectorAll('.old-folded').length;
  if(btn)btn.textContent=oldExpanded?'▾ 收起更早内容':'▸ 展开更早内容（'+n+'条，发布超过14天）';
  applyFilter();
}

// ===== 往期区可折叠抽屉（2026-09-07）=====
// 解决往期 78 条全平铺翻起来费劲：4 个子分类可折叠（行业动态、国际矿业动态默认折叠），
// 行业动态内部按天再分组（每组可独立折叠）。状态用 localStorage 记忆用户主动切换。
// 全部依赖现有 DOM 渲染（不动生成器），明天自动化生成新 HTML 仍生效。
const _AF_LS_CAT='mining_daily.archive.cat';   // 分类折叠状态：{name: bool}
const _AF_LS_DAY='mining_daily.archive.day';   // 日组折叠状态：{MM-DD: bool}
const _AF_DEFAULT_COLLAPSED=['行业动态','国际矿业动态'];   // 默认折叠的子分类（按名称包含判定）
function _afLoadMap(key){
  try{return JSON.parse(localStorage.getItem(key)||'{}')||{}}catch(e){return {}}
}
function _afSaveMap(key,m){try{localStorage.setItem(key,JSON.stringify(m))}catch(e){}}
function _afCatName(cat){
  // 提取分类名（去掉 emoji 与空白）。例："🏭 行业动态 10条" → "行业动态"
  const t=(cat.firstChild&&cat.firstChild.textContent)||cat.textContent||'';
  // sub-count 里的数字不影响：取到第一个 "数字+"条" 之前
  return t.replace(/[A-Za-z0-9\u4e00-\u9fa5]+(?:条新增|条)/,'').trim();
}
function _afToggleItems(collapsed, startNode, stopPredicate){
  let sib=startNode;
  while(sib && !stopPredicate(sib)){
    if(sib.classList && sib.classList.contains('day-group')){
      // 分类折叠时藏起整组；展开时显示日组标题，并恢复它自己的折叠状态
      sib.style.display=collapsed?'none':'';
      if(!collapsed){
        const isDayCollapsed=sib.getAttribute('data-collapsed')==='true';
        mdSetDayGroup(sib, isDayCollapsed);
      }
    }else if(sib.classList && sib.classList.contains('news-item')){
      // 分类折叠时藏起所有条目；展开时，超过14天的旧闻且未点「展开更早内容」保持隐藏，
      // 其余条目恢复显示（无日组的分类如「国际矿业动态」全靠这里展开）。
      if(collapsed){
        sib.style.display='none';
      }else if(sib.classList.contains('old-folded') && !oldExpanded){
        sib.style.display='none';
      }else{
        sib.style.display='';
      }
    }
    sib=sib.nextElementSibling;
  }
}
function initArchiveFold(){
  const arch=document.getElementById('archiveSection');
  if(!arch)return;
  const catMap=_afLoadMap(_AF_LS_CAT);
  const dayMap=_afLoadMap(_AF_LS_DAY);

  // 1) 改造每个 archive sub-cat 为可折叠
  const subcats=Array.from(arch.querySelectorAll('.sub-cat'));
  subcats.forEach(cat=>{
    const name=_afCatName(cat);
    cat._afName=name;   // 缓存：第二个 forEach（按日分组）需要复用；注 arrow 后 firstChild 不再是文本
    const isDefaultCollapsed=_AF_DEFAULT_COLLAPSED.some(k=>name.indexOf(k)>=0);
    if(!(name in catMap))catMap[name]=isDefaultCollapsed;   // 仅在用户未改过时跟随默认

    // 视觉：加可点击样式、展开/折叠三角、ARIA
    cat.classList.add('sub-cat-collapsible');
    cat.setAttribute('role','button');
    cat.setAttribute('tabindex','0');
    cat.setAttribute('data-collapsed', String(!!catMap[name]));
    cat.setAttribute('aria-expanded', String(!catMap[name]));

    // 注入三角 span（仅首次）
    let arrow=cat.querySelector('.cat-arrow');
    if(!arrow){
      arrow=document.createElement('span');
      arrow.className='cat-arrow';
      cat.insertBefore(arrow, cat.firstChild);
    }

    // 初始隐藏/显示其后的所有 news-item
    _afToggleItems(!!catMap[name], cat.nextElementSibling, el=>el.classList&&el.classList.contains('sub-cat'));

    const toggle=()=>{
      const next=!catMap[name];
      catMap[name]=next;
      _afSaveMap(_AF_LS_CAT, catMap);
      cat.setAttribute('data-collapsed', String(next));
      cat.setAttribute('aria-expanded', String(!next));
      _afToggleItems(next, cat.nextElementSibling, el=>el.classList&&el.classList.contains('sub-cat'));
    };
    cat.addEventListener('click', toggle);
    cat.addEventListener('keydown', e=>{
      if(e.key==='Enter'||e.key===' '||e.key==='Spacebar'){e.preventDefault();toggle()}
    });
  });

  // 2) 行业动态：按日期分日组（DOM 改造；只在 items>=2 时分组）
  subcats.forEach(cat=>{
    const name=cat._afName||_afCatName(cat);   // 优先用缓存的 name（避免 _afCatName 受 DOM 变更影响）
    if(name.indexOf('行业动态')<0)return;
    if(cat.getAttribute('data-day-grouped')==='1')return;   // 防重入
    cat.setAttribute('data-day-grouped','1');

    // 创建日组时，父级分类若正处于折叠态，对 day-group 标题自身也要隐藏
    // （_afToggleItems 之前已跑过，但那时 day-group 还没建）
    const parentCollapsed=!!catMap[name];

    // 收集本分类下所有 news-item（直至下一个 sub-cat）
    const items=[];
    let sib=cat.nextElementSibling;
    while(sib && !(sib.classList&&sib.classList.contains('sub-cat'))){
      if(sib.classList && sib.classList.contains('news-item'))items.push(sib);
      sib=sib.nextElementSibling;
    }
    if(items.length<2)return;   // 1 条不分组

    // 按日期分组（从 news-meta 文本提取 MM-DD）
    const groups={};
    items.forEach(el=>{
      const meta=el.querySelector('.news-meta');
      const m=meta?(meta.textContent.match(/(\d{1,2})-(\d{1,2})/)||[]):null;
      const key=m?(m[1].length===1?'0'+m[1]:m[1])+'-'+(m[2].length===1?'0'+m[2]:m[2]):'未标注';
      (groups[key]=groups[key]||[]).push(el);
    });

    // 按日期降序
    const dayKeys=Object.keys(groups).sort((a,b)=>{
      if(a==='未标注')return 1;if(b==='未标注')return -1;
      return a<b?1:a>b?-1:0;
    });

    // 在 cat 之后依次插入"日组标题 + 该日 items"
    let prevNode=cat;
    dayKeys.forEach(key=>{
      const itemsInDay=groups[key];
      // 用户偏好优先；未设则默认【折叠】，点日期才展开（避免「默认已展开、点一下反而收起」的反直觉）
      if(!(key in dayMap))dayMap[key]=true;

      const dayHead=document.createElement('div');
      dayHead.className='day-group';
      if(parentCollapsed)dayHead.style.display='none';   // 父级折叠时，日组标题也收起
      dayHead.setAttribute('role','button');
      dayHead.setAttribute('tabindex','0');
      dayHead.setAttribute('data-day', key);
      dayHead.setAttribute('data-collapsed', String(!!dayMap[key]));
      dayHead.setAttribute('aria-expanded', String(!dayMap[key]));
      dayHead.innerHTML='<span class="day-arrow">▾</span><span class="day-text">'+key+'</span><span class="day-count">'+itemsInDay.length+'条</span>';

      // 插入到 prevNode 之后
      prevNode.parentNode.insertBefore(dayHead, prevNode.nextSibling);
      prevNode=dayHead;

      // 把该日 items 移到 dayHead 之后
      itemsInDay.forEach(it=>{
        if(dayMap[key])it.style.display='none';
        prevNode.parentNode.insertBefore(it, prevNode.nextSibling);
        prevNode=it;
      });
      // 统一由 mdSetDayGroup 初始化：data-collapsed / aria / 箭头 / items 显示 全部对齐 dayMap 状态
      // （否则初始箭头写死 ▾ 与 data-collapsed=true 不一致，且 items 显示态需与折叠态同步）
      mdSetDayGroup(dayHead, dayMap[key]);

      const toggle=(e)=>{
        if(e && e.stopPropagation) e.stopPropagation();   // 避免冒泡到父分类触发整体折叠
        // 以真实显示态（data-collapsed）为状态源，而非闭包 dayMap。
        // 否则「筛选时 mdAutoExpandDayGroups 强制展开」只改了 DOM 显示却没同步 dayMap，
        // 之后点击 next=!dayMap 与显示态错位 → 点了不切换（「点了不显示内容」的放大版 bug）。
        const isCollapsed = dayHead.getAttribute('data-collapsed')==='true';
        const willCollapse = !isCollapsed;   // 当前折叠→展开(willCollapse=false)，当前展开→折叠(true)
        dayMap[key] = willCollapse;          // 记忆用户主动点击后的偏好（折叠=true 隐藏）
        _afSaveMap(_AF_LS_DAY, dayMap);
        dayHead.setAttribute('data-collapsed', String(willCollapse));
        dayHead.setAttribute('aria-expanded', String(!willCollapse));
        // 切换该日下 items（保留 old-folded 语义：超过14天旧闻且未展开更早内容时保持隐藏）
        let n=dayHead.nextElementSibling;let cnt=0;
        while(n && cnt<itemsInDay.length){
          if(n.classList && n.classList.contains('news-item')){
            if(willCollapse){ n.style.display='none'; }
            else if(n.classList.contains('old-folded') && !oldExpanded){ n.style.display='none'; }
            else { n.style.display=''; }
            cnt++;
          }
          n=n.nextElementSibling;
        }
      };
      dayHead.addEventListener('click', toggle);
      dayHead.addEventListener('keydown', e=>{
        if(e.key==='Enter'||e.key===' '||e.key==='Spacebar'){e.preventDefault();toggle()}
      });
    });
  });

  _afSaveMap(_AF_LS_CAT, catMap);
  _afSaveMap(_AF_LS_DAY, dayMap);
}

// 旧闻补录降级（2026-09-08 晚）：今日区 is-new 条目若原文发布日期（.news-meta「· MM-DD」）
// 距报告日超过 2 天，摘掉 NEW 徽章、换成灰色「补录」标——补录的漏稿不该顶着红标冒充「刚发生」。
// 只处理今日区（往期区本就无 NEW）；幂等，重复调用无副作用（降级后不再命中 is-new）。
function demoteStaleNew(){
  var anchor='';
  try{anchor=(typeof qaReportDate==='function')?(qaReportDate()||''):'';}catch(e){}
  if(!anchor||anchor.length<10)return;
  var base=new Date(+anchor.slice(0,4),+anchor.slice(5,7)-1,+anchor.slice(8,10));
  var todaySection=document.getElementById('todaySection');
  if(!todaySection)return;
  todaySection.querySelectorAll('.news-item.is-new').forEach(function(el){
    var meta=el.querySelector('.news-meta');
    if(!meta)return;
    var m=(meta.textContent||'').match(/(\d{2})-(\d{2})/);
    if(!m)return;
    var d=new Date(base.getFullYear(),+m[1]-1,+m[2]);
    if((base-d)/86400000<=2)return; // 2 天内算时效内，保留 NEW
    el.classList.remove('is-new');
    // 2026-09-08 晚：补录条目不再保留 is-special 底色强调（用户裁定：标个「补录」即可）。
    // is-special 是 initSpecial 给战略找矿条目加的浅底，与补录叠加会变成"旧闻反而高亮"。
    el.classList.remove('is-special');
    var b=el.querySelector('.badge-new');
    if(b){
      var tag=document.createElement('span');
      tag.className='badge-backfill';
      tag.textContent='补录';
      b.parentNode.replaceChild(tag,b);
    }
  });
}
// 子分类计数重算（2026-09-08 深夜）：子分类旁的「N条新增」是生成脚本写死的静态值，
// 会展条目被右栏收纳、旧闻被降级为「补录」之后都不会变，于是出现「3+16+13=32」与顶部
// 「28 今日新增」对不上的情况。这里按 DOM 实际重算：今日区=该子类内仍带 NEW 的条数，
// 往期区=该子类内实际条数。幂等，refresh 每次调用。
// 底部「更新时间」改读数据文件真实生成时间（2026-09-08 深夜）。
// 原先是生成脚本写死在 HTML 里的字符串，一天内多次改版/补录它都不动，读者无法判断数据新鲜度。
// 数据层 window.NEWS_DATA.updated 由 export_news_json.py 写入（如 "2026-09-08 10:37"）。
function applyDataUpdatedAt(){
  var el=document.getElementById('dataUpdatedAt');
  if(!el)return;
  var ts='';
  try{ ts=(window.NEWS_DATA&&window.NEWS_DATA.updated)||''; }catch(e){}
  if(ts) el.textContent=String(ts);
}
function syncSubCounts(){
  ['todaySection','archiveSection'].forEach(function(secId){
    var sec=document.getElementById(secId);
    if(!sec)return;
    var isToday=(secId==='todaySection');
    sec.querySelectorAll('.sub-cat').forEach(function(cat){
      var total=0, fresh=0, node=cat.nextElementSibling;
      while(node && !(node.classList&&node.classList.contains('sub-cat'))){
        if(node.classList&&node.classList.contains('news-item')&&!node.classList.contains('arch-fav')){
          total++;
          if(node.classList.contains('is-new'))fresh++;
        }
        node=node.nextElementSibling;
      }
      var c=cat.querySelector('.sub-count');
      if(c){
        if(isToday) c.textContent = fresh>0 ? (fresh+'条新增') : (total+'条');
        else c.textContent = total+'条';
      }
    });
  });
}
// 刷新显示状态
function refresh(){
  demoteStaleNew();
  const s=getReadSet();
  let unread=0,newUnread=0;
  document.querySelectorAll('.news-item:not(.arch-fav)').forEach(el=>{
    const isRead=s.has(el.dataset.url);
    el.classList.toggle('read',isRead);
    if(!isRead){unread++;if(el.classList.contains('is-new'))newUnread++}
  });
  // 矿权结果摘要不参与「今日新增」计数（data-rights-summary 标记）
  const newTotal=document.querySelectorAll('.news-item.is-new:not([data-rights-summary])').length;
  const allTotal=document.querySelectorAll('.news-item:not(.arch-fav)').length;
  document.getElementById('newCount').textContent=newTotal;
  document.getElementById('unreadCount').textContent=unread;
  // unreadBtnCount 已删（2026-09-08 深夜）：与左侧「N 条未读」统计数字重复
  // 2026-09-08 深夜：区块标题的「共N条」改按区块内实际条目数（含降级为「补录」的旧闻），
  // 新增数由顶部统计条负责。否则标题写「共28条」、下面却列着 31 条，读者会以为少了 3 条。
  const todayAll=document.querySelectorAll('#todaySection .news-item:not(.arch-fav)').length;
  document.getElementById('todayCount').textContent='共'+todayAll+'条';
  // 战略条目计数（专项区已于 2026-09-08 取消，is-special 条目现原位显示）
  const spAll=document.querySelectorAll('.news-item.is-special:not(.arch-fav)').length;
  const spNum=document.getElementById('specialCountNum');
  if(spNum)spNum.textContent=spAll;
  const tocCnt=document.getElementById('tocTodayCount');
  if(tocCnt){
    tocCnt.textContent=newTotal;
    // 「新鲜度」高亮：有内容时加 .has-fresh 触发脉冲，无内容时退化为灰色 .is-empty
    tocCnt.classList.toggle('has-fresh',newTotal>0);
    tocCnt.classList.toggle('is-empty',newTotal===0);
  }
  // 往期区标题旁的「N条」属于区块头部，不是侧栏数字，保留（用户感知的总量）
  const archTotal=document.querySelectorAll('#archiveSection .news-item').length;
  const archTitleCnt=document.getElementById('archiveCount');
  if(archTitleCnt)archTitleCnt.textContent=archTotal+'条';
  applyDataUpdatedAt();
  syncSubCounts();
  applyFavStates();
  updateFavCount();
  updateHistoryCount();
}

// 移动端检测：安卓/iPhone/鸿蒙等手机浏览器
const IS_MOBILE=/Android|iPhone|iPad|iPod|Mobile|HarmonyOS/i.test(navigator.userAgent);
// PWA 独立窗口检测：电脑/手机装了 PWA 后在 standalone 模式运行时
// （display-mode: standalone 是标准 API；window.navigator.standalone 是 iOS Safari 旧版兼容）
const IS_PWA=window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true;

// 点击事件：关键词标签筛选 / 标记已读+记录历史 / 收藏星标 / 单条恢复未读
document.addEventListener('click',e=>{
  // 关键词标签：点击筛选同类新闻，再点一次取消
  const chip=e.target.closest('.tag-chip');
  if(chip){
    e.preventDefault();e.stopPropagation();
    const tag=chip.dataset.tag;
    if(filterMode==='tag'&&tagFilter===tag)setFilter('none');
    else{tagFilter=tag;setFilter('tag')}
    return;
  }
  const star=e.target.closest('.btn-star');
  if(star){
    e.preventDefault();e.stopPropagation();
    const item=star.closest('.news-item');
    if(item&&item.dataset.url)toggleFav(item.dataset.url);
    return;
  }
  // 单条恢复未读按钮（preventDefault 防止冒泡触发其他逻辑）
  const undoBtn=e.target.closest('.btn-unread');
  if(undoBtn){
    e.preventDefault();e.stopPropagation();
    const item=undoBtn.closest('.news-item');
    if(item&&item.dataset.url)markUnread(item.dataset.url);
    return;
  }
  const a=e.target.closest('a[href]');
  if(a){
    // 统一外链策略：直接外站打开，不再走 iframe 浮窗。
    // 政府/媒体类网站多带 X-Frame-Options 禁止内嵌，iframe 体验不稳定；
    // PWA/移动端 target="_blank" 最可靠（2026-09-07 用户确认）。
    if(a.classList.contains('digest-link'))return;
    const item=a.closest('.news-item');
    if(item&&item.dataset.url)markRead(item.dataset.url);
    const href=a.getAttribute('href')||'';
    if(href.startsWith('javascript:')||href.startsWith('#'))return;
    // CSV 下载链直接下载，不拦截
    if(a.hasAttribute('download')||href.startsWith('blob:'))return;
    // <a> 已带 target="_blank"，直接放行，由浏览器/系统处理外站打开
  }
});


// 为每条新闻注入 ☆ 星标 + ↶ 标为未读 按钮
function injectStars(){
  document.querySelectorAll('.news-item').forEach(el=>{
    if(el.querySelector('.btn-star'))return;
    // 星标按钮（已在原代码中处理）
    const star=document.createElement('button');
    star.className='btn-star';
    star.innerHTML='☆';
    star.title='收藏/取消收藏';
    el.appendChild(star);
  });
  document.querySelectorAll('.news-item').forEach(el=>{
    if(el.querySelector('.btn-unread'))return;
    // 单条恢复未读按钮：仅「已读」条目显示，追加到条目末尾（2026-09-06：原「查看原文」按钮已删，不再有插入锚点）
    const undo=document.createElement('button');
    undo.type='button';
    undo.className='btn-unread';
    undo.innerHTML='↶ 标为未读';
    undo.title='只将本条恢复为未读（不影响其他新闻）';
    el.appendChild(undo);
  });
}

// ===== 自动关键词标签（重点提示词，按词典从标题+摘要提取）=====
const TAG_DICT=[
// 战略专项（新一轮找矿突破战略行动）——金色，词典置顶优先命中
{t:'找矿突破',c:'strategy'},{t:'新一轮找矿',c:'strategy'},{t:'战略性矿产',c:'strategy'},
{t:'关键矿产',c:'strategy'},{t:'增储上产',c:'strategy'},{t:'绿色勘查',c:'strategy'},
{t:'深地',c:'strategy'},{t:'深部找矿',c:'strategy'},{t:'AI找矿',c:'strategy'},
// 矿种
{t:'稀土',c:'metal'},{t:'黄金',c:'metal'},{t:'金矿',c:'metal'},{t:'白银',c:'metal'},
{t:'铜',c:'metal'},{t:'镍',c:'metal'},{t:'铅锌',c:'metal'},{t:'铝土矿',c:'metal'},
{t:'铅',c:'metal'},{t:'锌',c:'metal'},{t:'铝',c:'metal'},{t:'钨',c:'metal'},
{t:'钼',c:'metal'},{t:'锡',c:'metal'},{t:'锑',c:'metal'},{t:'锂',c:'metal'},
{t:'钴',c:'metal'},{t:'铀',c:'metal'},{t:'萤石',c:'metal'},{t:'锰',c:'metal'},
{t:'钛',c:'metal'},{t:'铌',c:'metal'},{t:'有色',c:'metal'},
// 矿权
{t:'探矿权',c:'rights'},{t:'采矿权',c:'rights'},{t:'矿业权',c:'rights'},
{t:'探转采',c:'rights'},{t:'协议出让',c:'rights'},{t:'招拍挂',c:'rights'},
{t:'挂牌',c:'rights'},{t:'拍卖',c:'rights'},{t:'转让',c:'rights'},{t:'出让',c:'rights'},
{t:'成交公示',c:'rights'},{t:'储量评审',c:'rights'},
// 勘查找矿
{t:'找矿',c:'explore'},{t:'新发现',c:'explore'},{t:'增储',c:'explore'},
{t:'资源量',c:'explore'},{t:'储量',c:'explore'},{t:'勘查',c:'explore'},{t:'勘探',c:'explore'},
{t:'矿床',c:'explore'},{t:'深部',c:'explore'},{t:'物探',c:'explore'},{t:'化探',c:'explore'},
{t:'钻探',c:'explore'},{t:'成矿',c:'explore'},
// 资本
{t:'并购',c:'capital'},{t:'收购',c:'capital'},{t:'重组',c:'capital'},{t:'股权',c:'capital'},
{t:'融资',c:'capital'},{t:'分红',c:'capital'},{t:'承购',c:'capital'},{t:'战略合作',c:'capital'},
{t:'招标',c:'capital'},
// 政策
{t:'征求意见',c:'policy'},{t:'管理办法',c:'policy'},{t:'出口管制',c:'policy'},
{t:'总量调控',c:'policy'},{t:'绿色矿山',c:'policy'},{t:'绿色低碳',c:'policy'},
{t:'规划',c:'policy'},{t:'政策',c:'policy'},{t:'法规',c:'policy'},{t:'通知',c:'policy'},
// 市场
{t:'景气指数',c:'market'},{t:'价格',c:'market'},{t:'产量',c:'market'},{t:'利润',c:'market'},
{t:'供应链',c:'market'},{t:'交易所',c:'market'},{t:'市场',c:'market'},{t:'贸易',c:'market'},
{t:'出口',c:'market'},{t:'进口',c:'market'},{t:'上涨',c:'market'},{t:'下跌',c:'market'},{t:'新高',c:'market'},
// 培训学术
{t:'培训',c:'edu'},{t:'研修',c:'edu'},{t:'研讨会',c:'edu'},{t:'大会',c:'edu'},{t:'会议',c:'edu'},
{t:'暑期学校',c:'edu'},{t:'学术',c:'edu'},{t:'标准',c:'edu'},
// 国际
{t:'国际',c:'global'},{t:'全球',c:'global'},{t:'海外',c:'global'},{t:'境外',c:'global'},
// 科技
{t:'人工智能',c:'tech'},{t:'智能制造',c:'tech'},{t:'数字化',c:'tech'},{t:'智能',c:'tech'},
{t:'创新',c:'tech'},{t:'科技',c:'tech'},{t:'技术',c:'tech'}
];
// 2026-09-11 视觉评审 F6：本表**只留文案**。配色已迁到 index.html 的 .tag-chip.tc-<类别> 段
// （亮/暗各一套，全部配对 ≥4.5）。原先在这里维护 color/bg 再于 injectTags() 内联下发，
// 内联样式恒压过 body.dark .tag-chip → 暗色下 11 组配色全部失效；且亮色另有 4 组不达 AA。
// 新增类别：在此加一项 label，并在 index.html 补 .tc-<类别> 的亮、暗两条规则。
const TAG_STYLE={
strategy:{label:'战略'},
metal:{label:'矿种'},
rights:{label:'矿权'},
explore:{label:'勘查'},
capital:{label:'资本'},
policy:{label:'政策'},
market:{label:'市场'},
edu:{label:'培训'},
global:{label:'国际'},
tech:{label:'科技'}
};
// 展示优先级（2026-09-06）：每条只展示 2 个标签，优先挑"信息量高"的类别——
// 战略专项 > 矿种 > 政策/矿权 > 其他泛化词（科技、市场…泛化词不占位，避免满屏同色标签）
// 注意：值必须从 1 起——若 strategy=0，比较器里的 `TAG_RANK[x]||9` 会因 0 是 falsy 而取到 9，
// 优先级最高的标签反而排到最后（2026-09-06 实测踩坑）
var TAG_RANK={strategy:1,metal:2,policy:3,rights:4,explore:5,capital:6,market:7,global:8,tech:9,edu:10};
// 提取规则：矿种类最多2个、其他类各1个、每条最多4个；已命中标签不再收其子串/父串（防"铅锌"又出"铅"）
function extractTagsFor(item){
  const title=item.querySelector('.news-title');
  const sum=item.querySelector('.news-summary');
  const text=((title?title.textContent:'')+' '+(sum?sum.textContent:''));
  const found=[],cnt={};
  for(const d of TAG_DICT){
    if(found.length>=4)break;
    const cap=d.c==='metal'?2:1;
    if((cnt[d.c]||0)>=cap)continue;
    if(!text.includes(d.t))continue;
    if(found.some(f=>f.t.includes(d.t)||d.t.includes(f.t)))continue;
    found.push(d);cnt[d.c]=(cnt[d.c]||0)+1;
  }
  // 返回前按类别优先级排序，保证展示位（前 TAG_MAX_SHOW 个）落在高信息量标签上
  return found.sort(function(a,b){return (TAG_RANK[a.c]||99)-(TAG_RANK[b.c]||99);});
}
// ===== 今日新增区：非今日发布日期的新闻加"原文发布"提示 =====
// 2026-09-06：徽章从 .news-head 移到 .news-meta 行 —— 头部一行塞不下时会把长标题
// 挤成窄条（手机端尤其明显）；日期本质是元信息，放 meta 行更合理
// 2026-09-06 简化：原文发布日期徽章已停用——meta 行里的「· MM-DD」本身就是原文发布日期，
// 再补一个「原文发布 MM-DD」是同一信息的重复展示。函数保留以便日后需要时改回一行调用。
// ==================== 新闻徽章：重要性分级 + 信源权威（9-06 新增）====================
// 分级复用热榜打分（来源权威 × 时效 × 关键词），不引入任何虚构指标。
// 2026-09-06 简化：只保留「重大」一档并全部置于末尾——「重要/关注」属主观噪音，
// 每档都标会让整页都是徽章，反而削弱「重大」的信号价值。
var LV_TABLE=[[125,'lv-major','重大']];
var AU_MAP={'自然资源部':'au-official','矿业权市场':'au-official','中国地质调查局':'au-official','全球矿产资源':'au-official','上海联合矿权交易所':'au-official','上海期货交易所':'au-official','中国有色金属工业协会':'au-assoc','中国黄金协会':'au-assoc','中国稀土行业协会':'au-assoc','中国地质学会':'au-assoc','中国煤炭工业协会':'au-assoc','中国冶金矿山企业协会':'au-assoc','中国石油和化学工业联合会':'au-assoc','中国矿业报':'au-assoc','中国有色网':'au-media','中国黄金网':'au-media','中国矿业网':'au-media','全球矿产资源网':'au-media','矿冶集团':'au-assoc','中国稀土集团':'au-official','中国黄金集团':'au-official','紫金矿业':'au-official'};
var AU_LABEL={'au-official':'官方','au-assoc':'协会','au-media':'媒体'};
function newsLevelOf(score){
  for(var i=0;i<LV_TABLE.length;i++){if(score>=LV_TABLE[i][0])return {cls:LV_TABLE[i][1],label:LV_TABLE[i][2]};}
  return null;   // 低于「关注」线不显示徽章，避免满屏噪音
}
// 打分表：优先复用热榜算法（口径与热榜一致）；QA_ROWS 尚未就绪时退回 news-data.js 原始行自算同一公式
function newsScoreMap(){
  var map={};
  try{
    var arr=computeHotNewsLocal(9999);
    for(var i=0;i<arr.length;i++){if(arr[i].u)map[arr[i].u]=arr[i].score;}
  }catch(e){}
  if(Object.keys(map).length)return map;
  var rows=(window.NEWS_DATA&&window.NEWS_DATA.news)||[];
  var anchor='';
  try{anchor=qaReportDate()||'';}catch(e){}
  if(!anchor){
    var n=new Date();
    anchor=n.getFullYear()+'-'+String(n.getMonth()+1).replace(/^(\d)$/,'0$1')+'-'+String(n.getDate()).replace(/^(\d)$/,'0$1');
  }
  var td=new Date(anchor+'T00:00:00');
  if(isNaN(td.getTime()))td=new Date();
  for(var j=0;j<rows.length;j++){
    var r=rows[j];
    if(!r||!r.u)continue;
    var d=String(r.d||'');
    if(d.length===5&&d.charAt(2)==='-')d=anchor.slice(0,4)+'-'+d;
    var diff=0;
    try{var dd=new Date(d+'T00:00:00');if(!isNaN(dd.getTime()))diff=Math.round((td-dd)/86400000);}catch(e){}
    if(diff<0)diff=0;
    var rec=Math.max(0,30-diff*4);
    var srcW=HOT_SRC_W[r.s]||3;
    var t=String(r.t||''),hot=false,nb=0,k;
    for(k=0;k<HOT_KW.length;k++){if(t.indexOf(HOT_KW[k])>=0){hot=true;break;}}
    if(!hot){for(k=0;k<NORMAL_KW.length;k++){if(t.indexOf(NORMAL_KW[k])>=0){nb=5;break;}}}
    map[r.u]=srcW*10+rec+(hot?20:0)+nb;
  }
  return map;
}
function injectNewsBadges(){
  var scoreMap={};
  try{scoreMap=newsScoreMap();}catch(e){console.warn('[badge] 打分失败：',(e&&e.message)||e);}
  document.querySelectorAll('.news-item').forEach(function(el){
    if(el.querySelector('.badge-level')||el.querySelector('.badge-authority'))return;
    var meta=el.querySelector('.news-meta');
    if(!meta)return;
    var srcEl=meta.querySelector('.src');
    var srcName=srcEl?String(srcEl.textContent||'').trim():'';
    var url=el.dataset.url||'';
    var sc=scoreMap[url];
    if(typeof sc==='number'){
      var lv=newsLevelOf(sc);
      if(lv){
        var b=document.createElement('span');
        b.className='badge-level '+lv.cls;
        b.textContent=lv.label;
        b.title='情报价值 '+sc+' 分（来源权威 × 时效 × 关键词）→ '+lv.label;
        meta.appendChild(b);
      }
    }
    // 2026-09-06 简化：不再注入「官方/协会/媒体」信源等级徽章——
    // meta 行里已经写明具体来源名（自然资源部、中国地质调查局…），再标等级属常识重复。
    // 分级映射表 AU_MAP/AU_LABEL 保留（热榜打分仍用来源权重）。
  });
}
// ==================== 今日情报简报（9-06 新增）====================
// 数据来自 morning_report.json（每日随日报生成，sections 内已含 signals / anomalies / sentiment）。
// 铁律：取不到就整块不显示，绝不编造任何判断或数字。
function briefEsc(s){
  return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
// 极简 Markdown：先整段转义，再还原加粗/列表/段落，杜绝 HTML 注入
function briefMd(md){
  var lines=String(md||'').split(/\r?\n/);
  var out=[],buf=[],ul=false;
  function flushP(){if(buf.length){out.push('<p>'+buf.join('<br>')+'</p>');buf=[];}}
  function closeUl(){if(ul){out.push('</ul>');ul=false;}}
  for(var i=0;i<lines.length;i++){
    var t=lines[i].trim();
    if(!t){flushP();closeUl();continue;}
    // 整行只有一个加粗段（如 **政策与产业：**）→ 渲染成分节小标题，便于扫读
    var secM=t.match(/^\*\*([^*]{2,20})\*\*\s*$/);
    if(secM){flushP();closeUl();out.push('<div class="brief-sec">'+briefEsc(secM[1])+'</div>');continue;}
    t=briefEsc(t).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
    if(/^[-*]\s+/.test(t)){
      flushP();
      if(!ul){out.push('<ul>');ul=true;}
      out.push('<li>'+t.replace(/^[-*]\s+/,'')+'</li>');
    }else{closeUl();buf.push(t);}
  }
  flushP();closeUl();
  return out.join('');
}
function renderBrief(d){
  var strip=document.getElementById('briefStrip');
  if(!strip||!d||typeof d!=='object')return;
  var sec=d.sections||{};
  var news=d.top_news||sec.headlines||[];
  var alerts=(sec.anomalies&&sec.anomalies.alerts)||[];
  var metals=(sec.signals&&sec.signals.metals)||[];
  var sent=sec.sentiment||null;
  var rep=String(d.report||'');
  if(!rep.trim()&&!news.length&&!alerts.length&&!metals.length)return;
  var dEl=document.getElementById('briefDate');
  if(dEl)dEl.textContent=d.date?('数据日期 '+d.date):'';
  var sEl=document.getElementById('briefSub');
  if(sEl){
    // 有 stats 就报今日收录量，说明简报覆盖的是当日全部内容（不只是行情）
    var st=d.stats||{};
    var n=st.new_count;
    // 2026-09-11 IA评审 A7：底部「首页」与顶部「推荐」同目的地，文案对齐为「推荐」（data-go 仍为 home，导航逻辑不变）
    sEl.textContent=(typeof n==='number'&&n>0)
      ? ('今日收录 '+n+' 条 · 按分类摘要')
      : '每日 9:30 随日报生成';
  }
  var main=document.getElementById('briefMain');
  if(main){
    // 2026-09-08 晚：风险提示节已按用户要求整体移除（数据层模板同步删除），即便历史 JSON 里带着也不渲染
    var body=rep.replace(/^\*\*总览：\*\*\s*/,'').trim();
    var ri=body.indexOf('**风险提示：**');
    if(ri>=0)body=body.slice(0,ri).trim();
    // 注意：不要再截断「今日头条」等分节——简报定位是当日全部内容的分类摘要，
    // 之前因「今日5件事」卡而截断，去重删卡后只剩行情段，非价格内容全被吞掉（2026-09-06 事故）
    var h=briefMd(body);
    main.innerHTML=h||'<div class="brief-empty">今日简报暂未生成</div>';
  }
  setupBriefClamp();
  // 「今日5件事」卡已移除（与下方「今日要闻」重复）；top_news 仍参与简报区显隐判断
  strip.hidden=false;
}
// 简报内容按需折叠：分类摘要可能很长（10+ 条），默认只露出头部，避免把价格板块和新闻推到屏幕外
function setupBriefClamp(){
  var main=document.getElementById('briefMain'),btn=document.getElementById('briefMore');
  if(!main||!btn)return;
  main.classList.remove('brief-clamp');
  btn.hidden=true;
  var LIMIT=420;
  var apply=function(){
    if(main.scrollHeight>LIMIT){
      main.classList.add('brief-clamp');
      btn.hidden=false;
      var n=main.querySelectorAll('li').length;
      btn.textContent='展开全部'+(n?('（'+n+' 条）'):'');
      btn.dataset.open='0';
    }else{btn.hidden=true;main.classList.remove('brief-clamp');}
  };
  apply();
  // 字体/宽度变化后重新判定一次，避免小屏折叠阈值算错
  setTimeout(apply,300);
  btn.onclick=function(){
    var open=btn.dataset.open==='1';
    if(open){main.classList.add('brief-clamp');btn.dataset.open='0';btn.textContent='展开全部'+(main.querySelectorAll('li').length?('（'+main.querySelectorAll('li').length+' 条）'):'');}
    else{main.classList.remove('brief-clamp');btn.dataset.open='1';btn.textContent='收起';}
  };
}
function loadBrief(){
  var strip=document.getElementById('briefStrip');
  // 2026-09-10 P1-6：加载时先显示骨架屏微光占位，渲染完成后由 renderBrief 整体替换
  var m0=document.getElementById('briefMain');
  // 2026-09-11 视觉 C6：骨架屏内联 margin:7px → var(--s2)（8px，4 的倍数）
  if(m0){ m0.innerHTML='<div class="skeleton" style="height:14px;width:92%;margin:var(--s2) 0"></div>'
    +'<div class="skeleton" style="height:14px;width:78%;margin:var(--s2) 0"></div>'
    +'<div class="skeleton" style="height:14px;width:85%;margin:var(--s2) 0"></div>'
    +'<div class="skeleton" style="height:14px;width:62%;margin:var(--s2) 0"></div>'; }
  // 2026-09-09：简报区改为默认显示「加载中」占位，避免空白跳变；
  // 去掉 Date.now() 缓存击穿，让 SW 的 SWR 能命中预缓存。{cache:'reload'} 只用于
  // 后台网络请求绕过浏览器 HTTP 缓存，不影响 SW 先返回缓存秒开。
  // 2026-09-10 P2：加 8 秒超时兜底，避免网络/SW 异常时永远停在「加载中…」
  var _briefTimer=setTimeout(function(){
    var m=document.getElementById('briefMain');
    if(m&&(m.querySelector('.skeleton')||/加载中/.test(m.textContent||''))){
      m.innerHTML='<div class="brief-empty">简报加载较慢，可稍后刷新；不影响下方新闻与价格。</div>';
    }
  },8000);
  fetch('morning_report.json',{cache:'reload'})
    .then(function(r){return r.ok?r.json():null;})
    .then(function(d){clearTimeout(_briefTimer);if(d)renderBrief(d);})
    .catch(function(){
      console.warn('[brief] morning_report.json 不可用，简报区保持隐藏');
      if(strip)strip.hidden=true;
    });
}
// ==================== 阅读模式（9-06 新增：只留判断 / 5件事 / 价格 / 今日新闻）====================
function toggleReadingMode(){
  var on=document.body.classList.toggle('reading-mode');
  var btn=document.getElementById('readingToggle');
  if(btn){btn.classList.toggle('active',on);btn.textContent=on?'退出':'阅读';}
  try{lsSet('readingMode',on?'1':'0');}catch(e){}
  if(on){try{window.scrollTo({top:0,behavior:'smooth'});}catch(e){window.scrollTo(0,0);}}
}
function restoreReadingMode(){
  var v=null;
  try{v=localStorage.getItem('readingMode');}catch(e){}
  if(v!=='1')return;
  document.body.classList.add('reading-mode');
  var btn=document.getElementById('readingToggle');
  if(btn){btn.classList.add('active');btn.textContent='退出';}
}
document.addEventListener('keydown',function(e){
  if((e.key==='Escape'||e.key==='Esc')&&document.body.classList.contains('reading-mode'))toggleReadingMode();
});
var TAG_MAX_SHOW=2;   // 每条新闻最多展示 2 个关键词标签（其余仍写入 dataset 供筛选，避免满屏彩色标签）
function injectTags(){
  document.querySelectorAll('.news-item').forEach(el=>{
    if(el.querySelector('.news-tags'))return;
    const tags=extractTagsFor(el);
    el.dataset.tags=tags.map(t=>t.t).join('|');
    if(!tags.length)return;
    const wrap=document.createElement('div');
    wrap.className='news-tags';
    tags.slice(0,TAG_MAX_SHOW).forEach(tg=>{   // 只展示最具代表性的前 N 个，其余仍参与筛选
      const st=TAG_STYLE[tg.c]||{label:'关键词'};
      const chip=document.createElement('span');
      // 2026-09-11 F6：配色改由 CSS 类驱动（.tc-<类别>），不再内联注入 color/background。
      // 内联样式恒压过 body.dark .tag-chip，是暗色 11 组配色全部失效的根因。
      chip.className='tag-chip tc-'+(TAG_STYLE[tg.c]?tg.c:'default');
      chip.textContent='#'+tg.t;
      chip.dataset.tag=tg.t;
      chip.title=st.label+'：'+tg.t+'（点击筛选同类新闻）';
      wrap.appendChild(chip);
    });
    const head=el.querySelector('.news-head');
    if(head)head.insertAdjacentElement('afterend',wrap);
    else el.prepend(wrap);
  });
}
function setChipActive(tag){
  document.querySelectorAll('.tag-chip').forEach(c=>c.classList.toggle('chip-active',!!tag&&c.dataset.tag===tag));
}

// ===== 目录点击跳转 =====
function scrollToSection(id,el){
  // 跳转到section时，若处于筛选模式则自动恢复全部内容
  if(filterMode!=='none'){
    setFilter('none');
    document.querySelectorAll('.toc-main-item').forEach(i=>i.classList.remove('active'));
  }
  const target=document.getElementById(id);
  if(target){
    const offset=80;
    const top=target.getBoundingClientRect().top+window.pageYOffset-offset;
    window.scrollTo({top,behavior:'smooth'});
  }
  document.querySelectorAll('.toc-main-item').forEach(i=>{
    if(i!==el||i.dataset.target!==id)i.classList.remove('active');
  });
  if(el)el.classList.add('active');
}

// ===== 目录视图切换（2026-09-09）：点击只渲染目标区块，避免长页面滚动等待 =====
function switchView(view, el){
  if(document.body.dataset.view===view){ showAll(); return; } // 再次点击同一项 → 返回全部
  if(filterMode!=='none'){ setFilter('none', true); }           // 视图切换前先清跨区块筛选，避免叠加混乱
  if(view==='all'){ document.body.removeAttribute('data-view'); }
  else { document.body.dataset.view=view; }
  document.querySelectorAll('.toc-main-item').forEach(function(i){i.classList.remove('active');});
  var all=document.querySelector('.toc-all');
  if(el){ el.classList.add('active'); }
  else if(view==='all'&&all){ all.classList.add('active'); }
  // 视图切换后滚动到目标区块顶部，让用户立刻看到内容变化
  var targetTop=0, headerOffset=100;
  var targetId={today:'todaySection',archive:'archiveSection',rights:'rightsSection',install:'installGuideSection'}[view];
  if(targetId){
    var targetEl=document.getElementById(targetId);
    if(targetEl) targetTop=Math.max(0,targetEl.offsetTop-headerOffset);
  }
  window.scrollTo({top:targetTop,behavior:'smooth'});
}
function clearView(){ document.body.removeAttribute('data-view'); }

// ===== 滚动监听：当前区块高亮 =====
let lastActiveId=null;
function updateActiveSection(){
  if(document.body.dataset.view)return; // 视图模式下高亮由 switchView 控制，滚动监听不干扰
  const sections=['hotListSection','todaySection','archiveSection','rightsSection','installGuideSection'];
  const offset=120;
  let current=sections[0];
  for(const id of sections){
    const el=document.getElementById(id);
    if(el&&el.getBoundingClientRect().top<=offset)current=id;
  }
  if(current!==lastActiveId){
    lastActiveId=current;
    document.querySelectorAll('.toc-main-item').forEach(i=>{
      i.classList.toggle('active',i.dataset.target===current);
    });
  }
}
window.addEventListener('scroll',updateActiveSection,{passive:true});
// ===== 矿业热榜（9-03 新增，类似今日头条热榜） =====
// 2026-09-08 晚改造：仿头条「换一换」——去重后的完整候选池存 __hotPool，
// 每页显示 HOT_N 条，点击「换一换」翻页（循环），条目不够一页时按钮自动隐藏。
var __hotPool=[], __hotPage=0;
function renderHotNews(d){
  var body=document.getElementById('hotListBody');
  if(!body)return;
  var arr=(d&&Array.isArray(d.hot))?d.hot:[];
  // 热榜与「今日要闻」互斥（同一条不重复出现）+ 跨源同事件去重；不再提前截断，整池保留供换一换轮换。
  if(arr.length){
    try{
      var dp=(typeof computeDigestPicks==='function')?(computeDigestPicks()||[]):[];
      var chosen=[],i2,j2,dup;
      for(i2=0;i2<arr.length;i2++){
        var n0=arr[i2];dup=false;
        // 会展类条目已归入左侧「近期会展」迷你卡，热榜不再重复展示
        if(!dup&&typeof window.__expoIsExpo==='function'){
          try{ if(window.__expoIsExpo(n0.t))dup=true; }catch(e){}
        }
        for(j2=0;j2<dp.length;j2++){
          if(mdTitleSim(dp[j2].t,n0.t)>=0.5||(dp[j2].u&&n0.u&&dp[j2].u===n0.u)){dup=true;break;}
        }
        if(!dup)for(j2=0;j2<chosen.length;j2++){ if(mdTitleSim(chosen[j2].t,n0.t)>=0.5){dup=true;break;} }
        if(!dup)chosen.push(n0);
      }
      __hotPool=chosen;
    }catch(e){ __hotPool=arr.slice(0); }
  }else{
    __hotPool=[];
  }
  __hotPage=0;
  renderHotPage();
}
function renderHotPage(){
  var body=document.getElementById('hotListBody');
  if(!body)return;
  var cnt=document.getElementById('hotListCount');
  if(!__hotPool.length){
    body.innerHTML='<li class="hotlist-empty">今日热榜暂无数据（新闻源未更新）</li>';
    if(cnt)cnt.textContent='0条';
    var b0=document.getElementById('hotRefreshBtn');
    if(b0)b0.style.display='none';
    return;
  }
  var pages=Math.ceil(__hotPool.length/mdHotCount());
  if(__hotPage>=pages)__hotPage=0;
  var show=__hotPool.slice(__hotPage*mdHotCount(),__hotPage*mdHotCount()+mdHotCount());
  // 徽章口径（2026-09-08 晚定案）：
  //   热 = 标题命中 HOT_KW 热词表（突破/重大/战略/首次/关键矿产…），打分 +20 → computeHotNewsLocal 的 n.hot
  //   新 = 发布日期 === 报告日（qaReportDate，兼容 MM-DD 短格式归一化），即当日发布
  //   两者都命中则并排显示，热在前。热度条已按用户要求移除（装饰意义不大）。
  var anchor=(typeof qaReportDate==='function')?(qaReportDate()||''):'';
  if(!anchor){
    var _now=new Date();
    anchor=_now.getFullYear()+'-'+String(_now.getMonth()+1).replace(/^(\d)$/,'0$1')+'-'+String(_now.getDate()).replace(/^(\d)$/,'0$1');
  }
  body.innerHTML=show.map(function(n,idx){
    var t=String(n.t||'').replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});
    var s=n.s?String(n.s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];}):'';
    var u=String(n.u||'#').replace(/"/g,'&quot;');
    var dStr=n.d?' · '+String(n.d).slice(5):'';
    var nD=n.d?String(n.d):'';
    if(nD.length===5&&nD.charAt(2)==='-')nD=anchor.slice(0,4)+'-'+nD;
    var isNew=!!nD&&nD===anchor;
    var fire=n.hot?'<span class="hot-fire">🔥 热</span>':'';
    var fresh=isNew?'<span class="hot-new">新</span>':'';
    // 徽章放在标题之后内联排（2026-09-08 深夜）：原来放在标题前且徽章为块级，会独占一行
    return '<li class="hot-item" data-url="'+u+'">'
      +'<div class="hot-body">'
      +'<div class="hot-line">'
      +'<a class="hot-title" href="'+safeHref(u)+'" target="_blank" rel="noopener">'+t+'</a>'
      +fire+fresh
      +'</div>'
      +'<div class="hot-meta"><span>'+s+'</span><span>'+dStr+'</span></div>'
      +'</div></li>';
  }).join('');
  var btn=document.getElementById('hotRefreshBtn');
  if(btn)btn.style.display=(pages>1)?'':'none';
}
function hotShuffle(){
  var pages=Math.ceil(__hotPool.length/mdHotCount());
  if(pages<=1)return;
  __hotPage=(__hotPage+1)%pages;
  renderHotPage();
  var body=document.getElementById('hotListBody');
  if(body&&body.classList){
    body.classList.remove('hl-swap');
    try{ void body.offsetWidth; }catch(e){}
    body.classList.add('hl-swap');
  }
}
(function(){
  var btn=document.getElementById('hotRefreshBtn');
  if(btn)btn.addEventListener('click',hotShuffle);
})();
// ===== 热榜本地兜底（2026-09-04 新增）=====
// 背景：站点有两种运行形态——带后端 server.py 的部署，以及 GitHub Pages 这类纯静态托管。
// 纯静态下 /api/hot-news 不存在，不做兜底热榜就会显示"加载失败"。
// 这里把 server.py 的 _compute_hot_news 算法（来源权重×10 + 时效分 + 热词加成）原样移植到前端，
// 用全库 QA_ROWS 本地计算，保证两种部署形态下热榜口径一致。权重常量与 server.py 同步。
var HOT_SRC_W={'自然资源部':12,'中国地质调查局':10,'中国地质学会':8,'中国有色金属工业协会':8,'中国黄金协会':8,'中国稀土行业协会':7,'中国有色网':7,'矿业权市场':6,'全球矿产资源':5,'上海联合矿权交易所':5,'上海期货交易所':6,'中国矿业报':7,'中国矿业网':6,'中国黄金集团':6,'紫金矿业':5,'中国黄金网':6,'矿冶集团':6,'中国稀土集团':7,'中国煤炭工业协会':6,'中国石油和化学工业联合会':6,'中国冶金矿山企业协会':7,'中国地质大学':5};
var HOT_KW=['突破','重大','战略','世界第一','首次','关键矿产','新一轮','标志性','历史最好','历史新高','刷新','龙头','全球第一','亚洲第一','国内首台','首套','首发','首发阵容'];
var NORMAL_KW=['找矿','勘查','探矿','重要','规划','增量','分红','成果','进展','签约','投产','扩建','增资','中标','出让','成交','创','新高','领先'];
function computeHotNewsLocal(n){
  n=n||10;
  // 2026-09-11 加固：数据源不再只认 QA_ROWS。QA_ROWS 由中段的 qaInitData() 填充，
  // 若顶层代码在中途抛错导致它没跑，此前这里会 `QA_ROWS.length` TypeError →
  // 热榜显示「加载失败」，把真正的根因（初始化中断）伪造成「热榜坏了」。
  // 现在退化为直接读 window.NEWS_DATA.news（同一份全库数据，口径一致）。
  var rows=(window.QA_ROWS&&window.QA_ROWS.length)?window.QA_ROWS:((window.NEWS_DATA&&window.NEWS_DATA.news)||[]);
  var anchor=qaReportDate()||'';
  var today=anchor;
  if(!today){
    var now=new Date();
    today=now.getFullYear()+'-'+String(now.getMonth()+1).replace(/^(\d)$/,'0$1')+'-'+String(now.getDate()).replace(/^(\d)$/,'0$1');
  }
  var td=new Date(today+'T00:00:00');
  if(isNaN(td.getTime()))td=new Date();
  var scored=[];
  for(var i=0;i<rows.length;i++){
    var r=rows[i];
    var t=String(r.t||'').trim(),s=String(r.s||'').trim(),u=String(r.u||'').trim(),d=String(r.d||'').trim();
    if(!t||!u||!d)continue;
    if(d.length===5&&d.charAt(2)==='-')d=today.slice(0,4)+'-'+d;
    var diff=0;
    try{var dd=new Date(d+'T00:00:00');if(!isNaN(dd.getTime()))diff=Math.round((td-dd)/86400000);}catch(e){diff=0;}
    if(diff<0)diff=0;
    var rec=Math.max(0,30-diff*4);
    var srcW=HOT_SRC_W[s]||3;
    var hot=false,hotB=0,k;
    for(k=0;k<HOT_KW.length;k++){if(t.indexOf(HOT_KW[k])>=0){hot=true;hotB=20;break;}}
    var normB=0;
    if(!hot){for(k=0;k<NORMAL_KW.length;k++){if(t.indexOf(NORMAL_KW[k])>=0){normB=5;break;}}}
    scored.push({d:d,t:t,s:s,u:u,score:srcW*10+rec+hotB+normB,hot:hot});
  }
  scored.sort(function(a,b){if(b.score!==a.score)return b.score-a.score;return b.d<a.d?-1:(b.d>a.d?1:0);});
  var seen={},out=[];
  for(var j=0;j<scored.length;j++){
    if(seen[scored[j].u])continue;
    seen[scored[j].u]=1;out.push(scored[j]);
    if(out.length>=n)break;
  }
  for(var m=0;m<out.length;m++)out[m].rank=m+1;
  return out;
}
function fetchHotNews(){
  fetch('api/hot-news?v='+Date.now(),{cache:'no-store'})
    .then(function(r){return r.ok?r.json():null;})
    .then(function(d){
      if(d&&Array.isArray(d.hot)&&d.hot.length){renderHotNews(d);return;}
      renderHotNews({hot:computeHotNewsLocal(mdHotCount()*4),local:true});
    })
    .catch(function(){
      // 纯静态部署（GitHub Pages）没有后端接口 → 退回全库本地计算，热榜功能不缺失
      try{
        var arr=computeHotNewsLocal(mdHotCount()*4);
        if(arr.length){renderHotNews({hot:arr,local:true});return;}
      }catch(e){console.warn('computeHotNewsLocal:',e);}
      var body=document.getElementById('hotListBody');
      if(body)body.innerHTML='<li class="hotlist-empty">热榜加载失败，请稍后刷新</li>';
    });
}
// ===== 今日要闻摘要条（9-04 新增，纯前端：从全库挑当日关键信息，按来源权威×关键信息词打分）=====
// 2026-09-08 改造：
//   ① 跨源同事件去重——同一新闻被多家网站报道（URL 不同、标题几乎一样）时只留分数最高的一条；
//   ② 优先"当日发布"，不足再用"今日收录"补，并对非当日条目标注日期，
//      避免读者看到旧新闻却以为发生在今天（原逻辑是"今日收录"优先，旧稿也会进要闻）。
var HOT_N=5;      // 矿业热榜条数（桌面默认 4~5 条）
// ① 移动端热榜显示 10 条、桌面保持 5 条（用户要求手机端内容更充实）
function mdHotCount(){ return (window.innerWidth<=768)?10:5; }
// 视口跨越 768px 时重算热榜条数（手机 10 / 桌面 5）
(function(){
  var _t; window.addEventListener('resize',function(){ clearTimeout(_t); _t=setTimeout(function(){ if(__hotPool&&__hotPool.length){ renderHotPage(); } },200); });
})();
var DIGEST_N=4;   // 今日要闻条数
window.__digestPicks=null;   // 缓存要闻选中项，供热榜排除（两栏互斥不重复）

// 标题归一化：只保留中英文与数字，去掉标点/空格/书名号，便于相似比较
function mdNormTitle(t){return String(t||'').replace(/[^一-龥A-Za-z0-9]/g,'');}
// 标题相似度：2-gram Jaccard。含子串关系视为高相似（同一事件的不同报道标题常互相包含）
function mdTitleSim(a,b){
  a=mdNormTitle(a);b=mdNormTitle(b);
  if(!a||!b)return 0;
  if(a===b)return 1;
  if(a.indexOf(b)>=0||b.indexOf(a)>=0)return 0.95;
  var A={},B={},i,k,inter=0,uni=0;
  for(i=0;i<a.length-1;i++)A[a.substr(i,2)]=1;
  for(i=0;i<b.length-1;i++)B[b.substr(i,2)]=1;
  for(k in A){uni++;if(B[k])inter++;}
  for(k in B){if(!A[k])uni++;}
  return uni?inter/uni:0;
}
// 从候选数组里挑 n 条，跳过与已选标题相似（>=0.5）的条目
function mdPickDistinct(cands,n){
  var picks=[];
  for(var i=0;i<cands.length;i++){
    var dup=false;
    for(var j=0;j<picks.length;j++){
      if(mdTitleSim(picks[j].r.t,cands[i].r.t)>=0.5){dup=true;break;}
    }
    if(!dup)picks.push(cands[i]);
    if(picks.length>=n)break;
  }
  return picks;
}
// 要闻选条：返回条目数组（供要闻与热榜共用，保证两栏互斥）
function computeDigestPicks(){
  if(window.__digestPicks)return window.__digestPicks;
  var anchor=qaReportDate();
  function ok(r){return r.c!=='并购与投资'&&r.t&&r.u;}
  // 1) 优先"当日发布"的条目
  var pool=QA_ROWS.filter(function(r){return ok(r)&&r.d===anchor;});
  // 2) 不足 DIGEST_N 时，用"今日收录但非当日发布"的按分数补齐
  if(pool.length<DIGEST_N){
    var extra=QA_ROWS.filter(function(r){return ok(r)&&r.n===anchor&&r.d!==anchor;})
      .sort(function(a,b){return digestScore(b)-digestScore(a);});
    for(var i=0;i<extra.length&&pool.length<DIGEST_N*3;i++)pool.push(extra[i]);
  }
  // 3) 仍为空则退回全库最新一天
  if(!pool.length){
    var max='';QA_ROWS.forEach(function(r){if(ok(r)&&r.d&&r.d>max)max=r.d;});
    pool=QA_ROWS.filter(function(r){return ok(r)&&r.d===max;});
  }
  var cands=pool.map(function(r){return {r:r,sc:digestScore(r)};})
    .sort(function(a,b){return b.sc-a.sc||(b.r.d||'').localeCompare(a.r.d||'');});
  window.__digestPicks=mdPickDistinct(cands,DIGEST_N).map(function(p){return p.r;});
  return window.__digestPicks;
}
var DIGEST_SRC=[[ '自然资源部',30],['新华社',26],['新华网',26],['人民日报',26],['工信部',24],['发展改革委',24],['中国地质调查局',24],['商务部',20],['财政部',20],['中国黄金协会',18],['中国矿业报',18],['中国有色金属工业协会',16],['SMM',14],['矿业界',12]];
var DIGEST_KW=[['找矿突破',30],['新发现',26],['储量',24],['投产',20],['政策',20],['印发',18],['突破',16],['开工',16],['并购',14],['万吨',12],['稀土',10],['锗',10],['镓',10],['钨',8],['锂',8],['铜',6],['金',6],['银',5]];
function digestScore(r){
  var s=0;
  DIGEST_SRC.forEach(function(p){if((r.s||'').indexOf(p[0])>=0)s=Math.max(s,p[1]);});
  var hay=(r.t||'')+' '+(r.m||'');
  DIGEST_KW.forEach(function(p){if(hay.indexOf(p[0])>=0)s+=p[1];});
  (r.g||[]).forEach(function(t){if(t==='政策'||t==='找矿')s+=10;});
  return s;
}
function digestEsc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function renderDigest(){
  var list=document.getElementById('digestList'),dateEl=document.getElementById('digestDate');
  if(!list)return;
  var anchor=qaReportDate(),week=['日','一','二','三','四','五','六'];
  if(dateEl){
    var dt=anchor?new Date(anchor+'T00:00:00'):new Date();
    dateEl.textContent=(anchor?anchor.replace(/-/g,'.'):(dt.getFullYear()+'.'+(dt.getMonth()+1)+'.'+dt.getDate()))+' 星期'+week[dt.getDay()];
  }
  // 选条逻辑见 computeDigestPicks()：优先当日发布 → 今日收录补齐 → 全库最新一天；并做跨源同事件去重
  var picks=computeDigestPicks();
  if(!picks.length){
    list.innerHTML='<li class="digest-empty">暂无可提取的要闻（全库为空）</li>';
    return;
  }
  list.innerHTML=picks.map(function(r){
    // 非当日发布的条目标注日期，避免读者误以为是今天的新闻
    var dtag=(r.d&&r.d!==anchor)?'<span class="digest-dtag">'+digestEsc(String(r.d).slice(5))+'</span>':'';
    return '<li data-url="'+digestEsc(r.u)+'"><a class="digest-link" href="'+safeHref(r.u)+'" target="_blank" rel="noopener" title="'+digestEsc(r.t)+'">'+digestEsc(r.t)+'</a>'+dtag+'</li>';
  }).join('');
}

// ===== AI 深度解析（9-04 新增，依赖 deepseek API key）=====
function aiEsc(s){
  return String(s||'').replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});
}
function renderAiAnalyze(d){
  var body=document.getElementById('aiBody');
  var cnt=document.getElementById('aiCount');
  if(!body)return;
  if(!d){body.innerHTML='<div class="ai-empty">AI 解析加载失败，请稍后刷新</div>';if(cnt)cnt.textContent='加载失败';return;}
  if(d.enabled===false){
    // 未配置 key
    body.innerHTML='<div class="ai-disabled">🤖 AI 解析未配置 API Key'
      +'<div class="ai-keybox">'
      +'<input type="password" id="aiKeyInput" aria-label="DeepSeek API Key" placeholder="粘贴你的 DeepSeek Key（sk- 开头）" autocomplete="off" spellcheck="false">'
      +'<button type="button" id="aiKeySave">启用</button>'
      +'</div>'
      +'<div class="ai-keytip">Key 仅保存在你本机浏览器（localStorage），不上传、不进代码库；每台设备填一次即可。'
      +'未配置时自动使用本地检索摘要，页面其余功能不受影响。</div></div>';
    setTimeout(mdBindAiKeyBox,0);
    if(cnt)cnt.textContent='未配置';
    return;
  }
  var items=Array.isArray(d.items)?d.items:[];
  if(!items.length){
    body.innerHTML='<div class="ai-empty">今日暂无 AI 解析（可能是新闻源未更新或配额已用完）</div>';
    if(cnt)cnt.textContent='0条';
    return;
  }
  body.innerHTML=items.map(function(n){
    var title=aiEsc(n.title);
    var src=aiEsc(n.src||'');
    var url=aiEsc(n.url||'#');
    var sum=aiEsc(n.summary||'—');
    var ins=aiEsc(n.insight||'—');
    var risk=aiEsc(n.risk||'无');
    var riskClass=risk==='无'?'':'risk';
    return '<div class="ai-item">'
      +'<div class="ai-item-head">'
      +(src?'<span class="ai-item-src">'+src+'</span>':'')
      +'<a class="ai-item-title" href="'+url+'" target="_blank" rel="noopener">'+title+'</a>'
      +'</div>'
      +'<div class="ai-item-rows">'
      +'<div class="ai-row"><span class="ai-label">要点</span><span class="ai-text">'+sum+'</span></div>'
      +'<div class="ai-row"><span class="ai-label">启示</span><span class="ai-text">'+ins+'</span></div>'
      +'<div class="ai-row '+riskClass+'"><span class="ai-label">风险</span><span class="ai-text">'+risk+'</span></div>'
      +'</div></div>';
  }).join('');
  if(cnt)cnt.textContent=items.length+'条'+(d.cached?'（缓存）':'');
  if(d.quota_left!=null&&d.quota_limit){
    var q=document.createElement('div');
    q.className='ai-quota';
    q.textContent='今日 AI 配额：剩余 '+d.quota_left+' / '+d.quota_limit+' 次';
    body.appendChild(q);
  }
}

// 本地兜底：纯静态托管（GitHub Pages）无后端 / 无 DEEPSEEK_API_KEY 时，
// 基于本地 news-data.js 生成「今日新闻按板块汇总」，替换"需服务端支持"空状态。
function localAiSummary(){
  var body=document.getElementById('aiBody');
  var cnt=document.getElementById('aiCount');
  if(!body)return;
  var news=(window.NEWS_DATA&&window.NEWS_DATA.news)||[];
  var today=qaReportDate();
  var todays=news.filter(function(r){
    var n=r.n||r.first_seen||'';
    var d=r.d||r.orig_date_full||'';
    return n===today || d===today;
  });
  if(!todays.length){
    body.innerHTML='<div class="ai-empty">本地检索：今日暂无新增新闻（纯静态托管，未接入 AI 服务端）。行情、热榜与问答均为本地计算。</div>';
    if(cnt)cnt.textContent='本地';
    return;
  }
  var order=[], groups={};
  todays.forEach(function(r){
    var c=r.c||r.category||'其他';
    if(!groups[c]){groups[c]=[];order.push(c);}
    groups[c].push(r);
  });
  var html=order.map(function(c){
    var items=groups[c].map(function(r){
      var u=aiEsc(r.u||r.url||'#');
      var t=aiEsc(r.t||r.title||'');
      var s=aiEsc(r.s||r.source||'');
      return '<div style="margin:2px 0"><a class="ai-item-title" href="'+u+'" target="_blank" rel="noopener">'+t+'</a>'+(s?' <span class="ai-item-src">'+s+'</span>':'')+'</div>';
    }).join('');
    return '<div class="ai-item">'
      +'<div class="ai-item-head"><span class="ai-item-src">'+aiEsc(c)+'</span><span style="margin-left:auto;color:var(--ink-500);font-size: var(--fs-meta)">'+groups[c].length+'条</span></div>'
      +'<div class="ai-item-rows"><div class="ai-row"><span class="ai-text">'+items+'</span></div></div>'
      +'</div>';
  }).join('');
  // 2026-09-11 视觉 C5：内联 #888 → var(--ink-500)（沿用页面颜色变量，随深色模式联动）；6px → var(--r-md)
  body.innerHTML='<div style="padding:6px 10px;color:#b45309;background:#fffbeb;border-radius:var(--r-md);margin-bottom:8px;font-size: var(--fs-body)">以下为本地检索生成的今日新闻汇总（纯静态托管，AI 深度解读需服务端 DEEPSEEK_API_KEY）：</div>'+html;
  if(cnt)cnt.textContent='本地 '+todays.length+'条';
}

function fetchAiAnalyze(){
  fetch('api/ai-analyze?v='+Date.now(),{cache:'no-store'})
    .then(function(r){return r.ok?r.json():null;})
    .then(function(d){
      if(d && d.enabled!==false) renderAiAnalyze(d);
      else localAiSummary(); // 服务端未配置 key 或纯静态托管 404 → 本地 news-data.js 兜底
    })
    .catch(function(){
      // 纯静态部署（GitHub Pages）无后端、也无 DEEPSEEK_API_KEY → 用本地检索兜底，不再显示"需服务端支持"
      localAiSummary();
    });
}

// 2026-09-11 事故修复：初始化单点故障隔离。
// 此前这是一串平铺调用，任何一步抛异常都会中断整个 app.js 顶层流程 →
// 后面的 fetchHotNews / loadBrief / renderDigest / 价格补丁全部不执行，
// 页面表现为「静态内容正常，热榜/简报/要闻永久停在加载中」，且无任何报错提示。
// 改为逐步隔离：单步失败只记录并继续，其余功能不受影响（错误会显示在页面横幅上）。
mdSafeStep('initSpecial',initSpecial);   // 战略徽章标记（专项区已于 2026-09-08 取消，此处不再搬移 DOM）
mdSafeStep('fetchHotNews',fetchHotNews);   // 9-03 矿业热榜 Top 10
mdSafeStep('injectTags',injectTags);
mdSafeStep('injectStars',injectStars);
mdSafeStep('renderArchivedFavs',renderArchivedFavs);
mdSafeStep('foldOldArchive',foldOldArchive);
mdSafeStep('initArchiveFold',initArchiveFold);   // 往期区 4 个子分类可折叠抽屉 + 行业动态按日折叠（2026-09-07）
// injectOrigDateBadges();   // 2026-09-06 停用（与 meta 日期重复）
mdSafeStep('loadBrief',loadBrief);
mdSafeStep('restoreReadingMode',restoreReadingMode);
mdSafeStep('applyFilter',applyFilter);
mdSafeStep('refresh',refresh);
// ===== PWA 安装引导（克制入口：PC顶部按钮 + 移动端底部浮条）=====
// 平台判断
const IS_STANDALONE=window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true;
const IS_IOS=/iPhone|iPad|iPod/i.test(navigator.userAgent);
const IS_ANDROID=/Android/i.test(navigator.userAgent);
const IS_MOBILE_UA=/Android|iPhone|iPad|iPod|Mobile|HarmonyOS/i.test(navigator.userAgent);

// 捕获浏览器安装提示（Chrome/Edge/Android）
window.__deferredPrompt=null;
window.addEventListener('beforeinstallprompt',function(e){
  e.preventDefault();
  window.__deferredPrompt=e;
  showPwaInstallPrompt();
});

// 安装完成后隐藏入口
window.addEventListener('appinstalled',function(){
  window.__deferredPrompt=null;
  hidePwaInstallPrompt();
  mdHideInstallIfStandalone();
});

function mdHideInstallIfStandalone(){
  // 已作为独立应用安装（桌面 PWA / iOS 主屏幕）时，隐藏所有安装引导入口
  if(!IS_STANDALONE)return;
  var toc=document.getElementById('tocInstallItem');
  if(toc)toc.style.display='none';
  var guide=document.getElementById('installGuideSection');
  if(guide)guide.style.display='none';
}

function hidePwaInstallPrompt(){
  var pcBtn=document.getElementById('pwaHeaderBtn');
  if(pcBtn)pcBtn.hidden=true;
  var mbBar=document.getElementById('mobileInstallBar');
  if(mbBar)mbBar.hidden=true;
  document.body.classList.remove('has-install-bar');
}

function showPwaInstallPrompt(){
  if(IS_STANDALONE){ hidePwaInstallPrompt(); return; }
  // 用户曾关闭过（localStorage 长期记忆），不再打扰
  try{ if(localStorage.getItem('pwa-install-bar-dismissed')==='1') return; }catch(e){}

  if(IS_MOBILE_UA){
    // 移动端：底部浮条
    var bar=document.getElementById('mobileInstallBar');
    var btn=document.getElementById('mobileInstallBtn');
    var txt=document.getElementById('mobileInstallText');
    if(!bar)return;
    if(IS_IOS){
      txt.textContent='Safari 点“分享”→“添加到主屏幕”，像 App 一样使用';
      btn.textContent='如何添加';
      btn.onclick=function(){ alert('① 点 Safari 底部“分享”按钮（□↑）\n② 上滑找到“添加到主屏幕”\n③ 点“添加”即可'); };
    }else{
      txt.textContent='安装到主屏幕，离线也能看日报';
      btn.textContent='安装';
      btn.onclick=function(){ triggerPwaInstall(); };
    }
    bar.hidden=false;
    document.body.classList.add('has-install-bar');
    var close=document.getElementById('mobileInstallClose');
    if(close)close.onclick=function(){ bar.hidden=true; document.body.classList.remove('has-install-bar'); try{localStorage.setItem('pwa-install-bar-dismissed','1');}catch(e){} };
  }else{
    // 电脑端：顶部按钮
    var pcBtn=document.getElementById('pwaHeaderBtn');
    if(pcBtn){
      pcBtn.hidden=false;
      pcBtn.onclick=function(){ triggerPwaInstall(); };
    }
  }
}

// 2026-09-10：安装引导「延迟触发」——首次进入不立即弹，降低首屏打扰
// 触发条件（满足任一即一次性弹出）：滚动超过 80% 视口 / 发生一次点击或按键 / 停留 ≥ 8 秒
// 已安装（IS_STANDALONE）或用户曾关闭（localStorage 记忆）则跳过；beforeinstallprompt 仍即时弹出（浏览器安装就绪事件）
function mdArmInstallPromptDeferred(){
  if(IS_STANDALONE) return;
  try{ if(localStorage.getItem('pwa-install-bar-dismissed')==='1') return; }catch(e){}
  var fired=false;
  var timer=setTimeout(fire, 8000);
  function fire(){
    if(fired) return;
    fired=true;
    cleanup();
    showPwaInstallPrompt();
  }
  function onScroll(){
    if(window.scrollY > window.innerHeight*0.8) fire();
  }
  function cleanup(){
    window.removeEventListener('scroll', onScroll, {passive:true});
    window.removeEventListener('click', fire);
    window.removeEventListener('keydown', fire);
    clearTimeout(timer);
  }
  window.addEventListener('scroll', onScroll, {passive:true});
  window.addEventListener('click', fire);
  window.addEventListener('keydown', fire);
}

function toggleInstallGuide(){
  var body=document.getElementById('guideBody');
  var btn=document.getElementById('guideToggle');
  if(!body||!btn)return;
  if(body.style.display==='none'){
    body.style.display='';
    btn.textContent='收起 ▲';
  }else{
    body.style.display='none';
    btn.textContent='展开 ▼';
  }
}
function triggerPwaInstall(){
  if(window.__deferredPrompt){
    window.__deferredPrompt.prompt();
    window.__deferredPrompt.userChoice.then(function(choice){
      window.__deferredPrompt=null;
      if(choice&&choice.outcome==='accepted'){
        hidePwaInstallPrompt();
      }
    });
  }else{
    // 无浏览器提示时（如 Firefox/Safari），给手动指引
    if(IS_IOS){
      alert('请按以下步骤添加到主屏幕：\n① 点 Safari 底部“分享”按钮（□↑）\n② 上滑找到“添加到主屏幕”\n③ 点“添加”');
    }else{
      alert('请按以下步骤添加：\n① 点浏览器右上角“⋮”菜单\n② 选择“安装应用 / 添加到桌面”\n③ 确认添加');
    }
  }
}

// 2026-09-10 P0：移动端结构重构（运行时注入，避开生成区）
// 顶部：轻量 App Bar（品牌+日期）+ 6 分类 Tab（推荐/今日/价格/热榜/矿权/往期），分类控制内容过滤
// 底部：4 全局动作 Tab（首页/搜索/AI/我的）；搜索/AI 移出顶部，避免与底部导航重合
// 仅 ≤768px 通过 CSS 显示；桌面隐藏，不影响现有顶部目录条与双栏布局

// 分类选择：写入 body[data-md-cat]，CSS 据此显隐对应区块；收藏/浏览记录视图(data-filter-mode)下不干预
function mdSelectCat(cat){
  var top=document.getElementById('mdTop'); if(!top) return;
  document.body.classList.remove('md-search-open');
  document.body.classList.remove('md-top-hidden');
  document.body.setAttribute('data-md-cat',cat);
  [].forEach.call(top.querySelectorAll('.mctab'),function(b){
    var on=b.getAttribute('data-cat')===cat;
    b.classList.toggle('active',on);
    try{ b.setAttribute('aria-selected',on?'true':'false'); }catch(e){}
  });
  mdSyncNav(cat);
}
// 同步底部主导航高亮（首页/价格/矿权 ↔ 顶部分类；热榜/往期无对应底部项）
function mdSyncNav(cat){
  var bar=document.getElementById('mobileTabBar'); if(!bar) return;
  var goMap={'tuijian':'home','price':'price','rights':'rights'};
  var go=goMap[cat]||null;
  [].forEach.call(bar.querySelectorAll('.mtab'),function(b){
    b.classList.toggle('active', go!==null && b.getAttribute('data-go')===go);
  });
}
// ④ 推荐/往期按日期硬切分：标记往期中与推荐追更窗口重叠的条目（渲染期过滤，不改生成脚本）
function mdMarkArchiveDups(){
  try{
    var today=document.getElementById('todaySection'); if(!today) return;
    var set={};
    today.querySelectorAll('.news-item .news-meta').forEach(function(m){ var mm=m.textContent.match(/(\d{2})-(\d{2})/); if(mm) set[mm[1]+'-'+mm[2]]=1; });
    var arc=document.getElementById('archiveSection'); if(!arc) return;
    arc.querySelectorAll('.news-item').forEach(function(it){
      var m=it.querySelector('.news-meta'); if(!m) return;
      var mm=m.textContent.match(/(\d{2})-(\d{2})/);
      if(mm && set[mm[1]+'-'+mm[2]]) it.classList.add('md-dup');
    });
  }catch(e){}
}
// 顶部搜索图标：定位到推荐页资讯检索条并展开筛选 chip
function mdOpenSearch(){
  document.body.classList.remove('md-top-hidden');
  if(document.body.getAttribute('data-md-cat')!=='tuijian'){ mdSelectCat('tuijian'); }
  var bar=document.getElementById('newsFilterBar');
  if(bar){
    var open=document.body.classList.toggle('md-search-open');
    if(open){
      var chips=document.getElementById('nfChips'); if(chips) chips.classList.add('show');
      var s=document.getElementById('nfSearch'); if(s){ try{ s.focus(); }catch(e){} }
    }
  }
}

// 顶栏收藏/历史红点：集合非空即显示（移动端常驻图标上的待查看提示）
function mdUpdateFavBadges(){
  try{
    var fb=document.getElementById('mdFavBadge'); if(fb) fb.classList.toggle('show', !!(window.getFavs&&getFavs().length>0));
    var hb=document.getElementById('mdHistBadge'); if(hb) hb.classList.toggle('show', !!(window.getHistory&&getHistory().length>0));
  }catch(e){}
}
// ① 顶栏智能吸顶：下滚隐藏、上滑/到顶重现（阅读时让出空间，分类栏随顶栏整体可见）
// 2026-09-11 P0：隐藏只走 transform（不动布局，避免整列内容跳动）；滞后阈值 12px 抗惯性滚动抖动。
var mdTopLastY=0, mdTopTick=false, mdTopBarH=0;
function mdTopOnScroll(){
  var y=window.pageYOffset||document.documentElement.scrollTop||0;
  var maxY=Math.max(0,(document.documentElement.scrollHeight||0)-(window.innerHeight||0));
  if(y<80 || maxY<120){ document.body.classList.remove('md-top-hidden'); mdTopLastY=y; return; }
  if(mdTopBarH && y<=mdTopBarH){ document.body.classList.remove('md-top-hidden'); mdTopLastY=y; return; }
  if(y>mdTopLastY+12){ document.body.classList.add('md-top-hidden'); }
  else if(y<mdTopLastY-12){ document.body.classList.remove('md-top-hidden'); }
  mdTopLastY=y;
}
// 顶部 App Bar + 分类 Tab（注入到 body 最前，sticky 吸顶；skip-link 之后以保证其为 body 首个元素）
function mdMobileTopTabs(){
  if(document.getElementById('mdTop')) return;
  var top=document.createElement('div'); top.id='mdTop';
  var dateTxt='';
  try{ var d=document.querySelector('.date-badge'); if(d) dateTxt=d.textContent.trim(); }catch(e){}
  var cats=[['tuijian','推荐'],['hot','热榜'],['archive','往期'],['meeting','会议']];
  var html='<div class="md-top-brand"><span class="md-brand">⛏️ 矿业新闻日报</span><span class="md-date">'+dateTxt+'</span>'
    +'<button class="md-fav-btn" id="mdFavBtn" type="button" aria-label="我的收藏">'
    +'<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9 6.8 19.1l1-5.8L3.5 9.2l5.9-.9z"/></svg>'
    +'<span class="md-badge" id="mdFavBadge"></span>'
    +'</button>'
    +'<button class="md-fav-btn" id="mdHistBtn" type="button" aria-label="浏览记录">'
    +'<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>'
    +'<span class="md-badge" id="mdHistBadge"></span>'
    +'</button>'
    +'<button class="md-search-btn" id="mdSearchBtn" type="button" aria-label="搜索新闻">'
    +'<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>'
    +'</button></div><div class="md-cat-bar" role="tablist" aria-label="内容分类">';
  for(var i=0;i<cats.length;i++){ html+='<button class="mctab" role="tab" data-cat="'+cats[i][0]+'">'+cats[i][1]+'</button>'; }
  html+='</div>';
  top.innerHTML=html;
  var skip=document.getElementById('mdSkipLink');
  if(skip && skip.parentNode){ skip.parentNode.insertBefore(top, skip.nextSibling); }
  else { document.body.insertBefore(top, document.body.firstChild); }
  try{ mdTopBarH=top.offsetHeight||0; document.documentElement.style.setProperty('--md-top-h', (mdTopBarH||96)+'px'); }catch(e){}
  top.querySelector('.md-cat-bar').addEventListener('click',function(e){
    var b=e.target.closest('.mctab'); if(!b) return;
    mdSelectCat(b.getAttribute('data-cat'));
    try{ window.scrollTo({top:0,behavior:'smooth'}); }catch(e){ window.scrollTo(0,0); }
  });
  var sb=document.getElementById('mdSearchBtn');
  if(sb) sb.addEventListener('click', mdOpenSearch);
  var fb=document.getElementById('mdFavBtn');
  if(fb) fb.addEventListener('click', function(){ var s=document.getElementById('mineSheet'); if(s) s.hidden=true; if(typeof toggleFavFilter==='function') toggleFavFilter(); });
  var hb=document.getElementById('mdHistBtn');
  if(hb) hb.addEventListener('click', function(){ var s=document.getElementById('mineSheet'); if(s) s.hidden=true; if(typeof toggleHistoryFilter==='function') toggleHistoryFilter(); });
  mdUpdateFavBadges();
  document.addEventListener('click',function(e){ if(e.target.closest && (e.target.closest('.btn-star')||e.target.closest('.news-title'))){ setTimeout(mdUpdateFavBadges,0); } });
  if(window.addEventListener) window.addEventListener('storage', mdUpdateFavBadges);
  mdSelectCat('tuijian');
  try{ window.addEventListener('scroll',function(){ if(!mdTopTick){ mdTopTick=true; requestAnimationFrame(function(){ mdTopOnScroll(); mdTopTick=false; }); } },{passive:true}); }catch(e){}
}

// 底部 4 主导航 Tab（首页/价格/矿权/我的，内联 SVG 图标；AI 改回右下悬浮球，搜索提到顶栏）
function mdMobileTabBar(){
  if(document.getElementById('mobileTabBar')) return;
  var SVG_HOME='<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v9h4v-5h4v5h4v-9"/></svg>';
  var SVG_PRICE='<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20V9M9 20V4M14 20v-6M19 20V7"/></svg>';
  var SVG_RIGHTS='<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 3h8l4 4v14H7z"/><path d="M15 3v4h4"/><path d="M10 12h6M10 16h6"/></svg>';
  var SVG_USER='<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/></svg>';
  var SVG_QA='<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v11H9l-5 4V5z"/></svg>';
  var bar=document.createElement('nav');
  bar.id='mobileTabBar'; bar.setAttribute('aria-label','移动端主导航');
  bar.innerHTML='<button class="mtab" data-go="home"><span class="mi">'+SVG_HOME+'</span><span>首页</span></button>'
    +'<button class="mtab" data-go="price"><span class="mi">'+SVG_PRICE+'</span><span>价格</span></button>'
    +'<button class="mtab" data-go="qa"><span class="mi">'+SVG_QA+'</span><span>问</span></button>'
    +'<button class="mtab" data-go="rights"><span class="mi">'+SVG_RIGHTS+'</span><span>矿权</span></button>'
    +'<button class="mtab" data-go="mine"><span class="mi">'+SVG_USER+'</span><span>我的</span></button>';
  var sheet=document.createElement('div'); sheet.id='mineSheet'; sheet.hidden=true;
  sheet.innerHTML='<button data-act="fav">★ 我的收藏</button>'+
    '<button data-act="history">🕘 浏览记录</button>'+
    '<button data-act="theme">🌓 深色 / 浅色</button>'+
    '<div class="mine-install" id="mineInstallCard"></div>'+
    '<button data-act="top">⬆️ 返回顶部</button>';
  sheet.innerHTML+='<div class="mine-meta" id="mineMeta"></div>';
  document.body.appendChild(bar); document.body.appendChild(sheet);
  try{ var _dm=document.getElementById('mineMeta'); if(_dm){ var _du=document.getElementById('dataUpdatedAt'); _dm.textContent='数据更新时间：'+(_du?_du.textContent.trim():'—')+' · 信息聚合展示，版权归原机构所有'; } }catch(e){}
  mdRenderInstallCard();
  function setActive(go){ [].forEach.call(bar.querySelectorAll('.mtab'),function(b){ b.classList.toggle('active', go!==null && b.getAttribute('data-go')===go); }); }
  // 2026-09-11 优化③：非首页隐藏分类栏时，品牌行显示当前 tab 名给位置感
  var MD_BRAND_NAMES={'home':'⛏️ 矿业新闻日报','price':'价格','rights':'矿权','qa':'问','mine':'我的'};
  function mdSetBrandForTab(go){ var brand=document.querySelector('#mdTop .md-brand'); if(brand) brand.textContent=MD_BRAND_NAMES[go]||MD_BRAND_NAMES.home; }
  // 统一 tab 切换逻辑（点击 / 初始化恢复共用）；autoOpen 控制问/我的浮层是否在「恢复」时自动展开
  function activateTab(go, autoOpen){
    document.body.classList.toggle('md-hide-catbar', go!=='home');
    mdSetBrandForTab(go);
    sheet.hidden=true;
    if(go!=='qa' && typeof qaFloatClose==='function'){ try{ qaFloatClose(); }catch(e){} }
    if(go==='home'){ mdSelectCat('tuijian'); }
    else if(go==='price'){ mdSelectCat('price'); }
    else if(go==='rights'){ mdSelectCat('rights'); }
    else if(go==='qa'){
      if(autoOpen && typeof qaFloatToggle==='function') qaFloatToggle();
      var _qp=document.getElementById('qaFloat');
      setActive(_qp && _qp.classList.contains('open') ? 'qa' : null);
      return;
    } else if(go==='mine'){
      if(autoOpen){ sheet.hidden=false; setActive('mine'); }
      else { setActive(null); }
      return;
    }
    setActive(go);
    try{ window.scrollTo({top:0,behavior:'smooth'}); }catch(e){ window.scrollTo(0,0); }
  }
  bar.addEventListener('click',function(e){
    var b=e.target.closest('.mtab'); if(!b) return;
    var go=b.getAttribute('data-go');
    activateTab(go, true);
    // 2026-09-11 优化①：记住上次停留的内容 tab（问/我的为浮层，不持久化）
    if(go==='home'||go==='price'||go==='rights'){ try{ localStorage.setItem('md_last_tab', go); }catch(e){} }
  });
  sheet.addEventListener('click',function(e){
    var b=e.target.closest('button[data-act]'); if(!b) return;
    sheet.hidden=true;
    var act=b.getAttribute('data-act');
    if(act==='fav'){ if(typeof toggleFavFilter==='function') toggleFavFilter(); }
    else if(act==='history'){ if(typeof toggleHistoryFilter==='function') toggleHistoryFilter(); }
    else if(act==='theme'){ if(typeof toggleTheme==='function') toggleTheme(); }
    else if(act==='top'){ window.scrollTo(0,0); }
  });
  document.addEventListener('click',function(e){
    if(sheet.hidden) return;
    if(e.target.closest('#mineSheet')||(e.target.closest('.mtab')&&e.target.closest('.mtab').getAttribute('data-go')==='mine')) return;
    sheet.hidden=true; setActive(null);
  });
  // 2026-09-11 优化①：初始化恢复上次停留的内容 tab（问/我的为浮层不持久化，回退首页）
  var mdSavedTab='home';
  try{ var _s=localStorage.getItem('md_last_tab'); if(_s==='home'||_s==='price'||_s==='rights') mdSavedTab=_s; }catch(e){}
  activateTab(mdSavedTab, false);
}
// ⑧ 我的面板：内联安装分步卡（按 iOS/Android 自动识别；已安装置灰）
function mdRenderInstallCard(){
  var el=document.getElementById('mineInstallCard'); if(!el) return;
  if(IS_STANDALONE){
    el.innerHTML='<div class="mine-install-title">✅ 已安装到主屏幕</div><div class="mine-install-note">日报已作为独立应用运行，可随时从主屏图标进入。</div>';
    return;
  }
  if(IS_IOS){
    el.innerHTML='<div class="mine-install-title">📱 安装到主屏幕</div><div class="mine-install-note">① 点 Safari 底部「分享 □↑」<br>② 上滑找到「添加到主屏幕」<br>③ 点「添加」即可</div>';
    return;
  }
  el.innerHTML='<div class="mine-install-title">📲 安装到主屏幕</div><div class="mine-install-note">浏览器菜单（⋮）→「安装应用 / 添加到主屏幕」→ 确认添加。</div>';
  try{
    if(window.__deferredPrompt){
      var b=document.createElement('button'); b.type='button'; b.className='mine-install-btn'; b.textContent='立即安装';
      b.onclick=function(){ try{ triggerPwaInstall(); }catch(e){} };
      el.appendChild(b);
    }
  }catch(e){}
}
// ⑨ 会议会展：运行时注入 #meetingSection（置于 #rightsSection 之后，避开生成区），从全库抽取会展类新闻
function mdInitMeetingSection(){
  try{
    if(document.getElementById('meetingSection')) return;
    var rs=document.getElementById('rightsSection'); if(!rs) return;
    var sec=document.createElement('div'); sec.className='section'; sec.id='meetingSection'; sec.style.display='none';
    sec.innerHTML='<div class="section-title"><span class="icon">📅</span> 会议会展<span class="news-count" id="meetingCount"></span></div><div class="meeting-body"></div>';
    if(rs.nextSibling) rs.parentNode.insertBefore(sec, rs.nextSibling); else rs.parentNode.appendChild(sec);
    mdRenderMeetingSection();
  }catch(e){}
}
function mdRenderMeetingSection(){
  var sec=document.getElementById('meetingSection'); if(!sec) return;
  var body=sec.querySelector('.meeting-body'); if(!body) return;
  if(!window.QA_ROWS||!QA_ROWS.length){ body.innerHTML='<div class="meeting-empty">会议会展内容加载中…</div>'; return; }
  // 2026-09-11 IA评审 A4：暂缓实施，见下方注释（已回退）。
  // 起因：≤1100px 时侧栏会展迷你卡的 vault 迁移不执行（侧栏 IIFE 早退），会展条目留在今日主列表，
  //       会议 tab 又从这里独立取数 → 同一场会两处出现。
  // 但"按主列表 URL 过滤会议 tab"在移动端会把会议 tab 清空（因为移动端所有会展条目都在主列表里），
  // 属比"重复"更差的净回归；桌面端 vault 迁移已把会展条目移出主列表，过滤又是空操作。
  // → 结论：本方案恒为空操作或净负，已回退。若要消除移动端重复，正解是让 vault 迁移在移动端也执行
  //   （与 2026-09-08 用户明确要求「移动端侧栏退化为横条时条目留在原位」冲突，需产品决策），
  //   而不是在会议 tab 侧做过滤。详见 reviews/ux-ia-product-2026-09-11.md 的 A4 条目。
  var seen={}, items=[];
  for(var i=0;i<QA_ROWS.length;i++){
    var r=QA_ROWS[i]; var t=String(r.t||'').trim();
    if(!t||!r.u) continue;
    var expo=false; try{ expo=(typeof isExpo==='function')?isExpo(t):(window.__expoIsExpo&&window.__expoIsExpo(t)); }catch(e){}
    if(!expo) continue;
    if(seen[r.u]) continue; seen[r.u]=1;
    items.push(r);
  }
  var cnt=document.getElementById('meetingCount'); if(cnt) cnt.textContent=items.length+'条';
  if(!items.length){ body.innerHTML='<div class="meeting-empty">暂无会议会展相关新闻</div>'; return; }
  body.innerHTML=items.map(function(r){
    var t=esc(String(r.t||'')); var u=safeHref(String(r.u||'#')); var s=esc(String(r.s||'')); var d=String(r.d||'');
    return '<div class="news-item" data-url="'+u+'"><div class="news-head"><span class="dot"></span><a class="news-title" href="'+u+'" target="_blank" rel="noopener">'+t+'</a></div><div class="news-meta"><span class="src">'+s+'</span> · '+(d?d.slice(5):'')+'</div></div>';
  }).join('');
}
// ⑥ 移动端问答面板头部「✕」改为返回箭头（沉浸式全屏）
function mdQaMobileBackArrow(){
  try{ if(window.innerWidth<=768){ var cb=document.querySelector('#qaFloat .pchart-close'); if(cb){ cb.textContent='‹'; cb.setAttribute('aria-label','返回'); } } }catch(e){}
}
// 2026-09-10 修复：数据看门狗。
// 事故复盘——SW/sw.js 异常时 news-data.js 取不到 → window.NEWS_DATA 为 undefined，
// 各渲染函数在 `if(!window.NEWS_DATA) return` 处静默返回，页面就永久停在「热榜加载中…／
// 简报加载中…／要闻提取中…」占位，用户完全看不出是失败还是慢。此处 9 秒后兜底：
// 仍未拿到数据则改写占位为明确提示 + 「重试」按钮（若数据已就绪则直接跳过，不影响正常渲染）。
function mdDataWatchdog(){
  if(window.__mdDataWatchdog)return; window.__mdDataWatchdog=true;
  setTimeout(function(){
    try{
      if(window.NEWS_DATA&&window.NEWS_DATA.news&&window.NEWS_DATA.news.length)return;
      var msg='数据加载失败，请检查网络后重试';
      var btn=' <button type="button" class="md-data-retry" style="margin-left:8px;border:1px solid var(--line-2,#d8dee6);background:transparent;color:inherit;border-radius:4px;padding:2px 10px;font-size:12px;cursor:pointer">重试</button>';
      var hot=document.getElementById('hotListBody');
      if(hot&&hot.querySelector('.hotlist-loading')){ hot.innerHTML='<li class="hotlist-loading">'+msg+btn+'</li>'; }
      // 2026-09-11 IA评审 A3：只替换 #digestList 列表内容，保留 .digest-head（今日/要闻/日期），
      // 且不再把 li 直接塞进 div（非法结构）。注意：注释里别写带尖括号的标签字面量，
      // preflight_check.py 的 div 收支检查历史上会把 app.js 拼进去扫，见该文件 2026-09-11 说明。
      var dg=document.getElementById('digestList');
      if(dg&&dg.querySelector('.digest-empty')){ dg.innerHTML='<li class="digest-empty">'+msg+btn+'</li>'; }
      var bm=document.getElementById('briefMain');
      if(bm&&/加载中/.test(bm.textContent||'')){ bm.innerHTML='<div class="brief-empty">'+msg+btn+'</div>'; }
      var rs=document.querySelectorAll('.md-data-retry');
      for(var i=0;i<rs.length;i++){ rs[i].addEventListener('click',function(){ try{location.reload();}catch(e){} }); }
    }catch(e){}
  },9000);
}

// 2026-09-10 P1-4 / P1-5 / P1-6：上次看到分隔线、简报折叠、无网络空态
function mdInsertLastSeen(){
  try{
    var url=null; try{ url=localStorage.getItem('md_last_seen_url'); }catch(e){}
    if(!url) return;
    if(document.getElementById('mdLastSeen')) return;
    var items=document.querySelectorAll('#todaySection .news-item');
    var target=null;
    for(var i=0;i<items.length;i++){
      var a=items[i].querySelector('.news-title');
      if(a && (a.getAttribute('href')||'')===url){ target=items[i]; break; }
    }
    if(!target) return;
    if(target.previousElementSibling && target.previousElementSibling.id==='mdLastSeen') return;
    var div=document.createElement('div'); div.className='md-lastseen'; div.id='mdLastSeen';
    div.innerHTML='<span>上次看到</span>';
    target.parentNode.insertBefore(div, target);
  }catch(e){}
}
function mdRecordLastSeen(){
  document.addEventListener('click',function(e){
    var a=e.target.closest && e.target.closest('.news-title'); if(!a) return;
    try{ localStorage.setItem('md_last_seen_url', a.getAttribute('href')||''); }catch(er){}
  },true);
}
function mdInitOfflineBanner(){
  try{
    var ob=document.createElement('div'); ob.id='mdOffline';
    ob.innerHTML='📡 网络已断开，正在显示已缓存的日报内容';
    document.body.appendChild(ob);
    function upd(){ ob.classList.toggle('show', !navigator.onLine); }
    window.addEventListener('online', upd); window.addEventListener('offline', upd); upd();
  }catch(e){}
}
// 页面加载后再判断一次（处理 iOS 等不触发 beforeinstallprompt 的场景）
window.addEventListener('DOMContentLoaded',function(){
  // 刷新/重载后强制回到顶部（配合 <head> 里的 history.scrollRestoration='manual'）
  try{ window.scrollTo(0,0); }catch(e){}
  // 移动端：顶部 App Bar + 分类 Tab + 底部 4 全局动作 Tab（仅 ≤768px 通过 CSS 显示；桌面隐藏）
  mdMobileTopTabs();
  mdMobileTabBar();
  mdMarkArchiveDups();
  // ⑨ 会议会展区块注入；⑥ 移动端问答头部返回箭头
  mdInitMeetingSection();
  mdQaMobileBackArrow();
  // 数据看门狗：9s 内仍未拿到 NEWS_DATA 时把「加载中…」占位改成明确提示 + 重试
  mdDataWatchdog();
  // P1-4 / P1-5 / P1-6：上次看到分隔线、简报折叠、无网络空态
  mdRecordLastSeen();
  mdInitOfflineBanner();
  var bt=document.getElementById('briefToggle');
  if(bt)bt.addEventListener('click',function(){ var s=document.getElementById('briefStrip'); if(s)s.classList.toggle('brief-collapsed'); });
  mdInsertLastSeen(); setTimeout(mdInsertLastSeen, 400);
  if(IS_STANDALONE){ hidePwaInstallPrompt(); mdHideInstallIfStandalone(); return; }
  // iOS / 桌面未触发 beforeinstallprompt 时，延迟到用户首次交互（滚动/点击/按键）或停留 ≥8s 再提示，降低首屏打扰
  mdArmInstallPromptDeferred();
});
// ===== 版本戳记录：仅持久化当前 build，不做硬刷新 =====
// 2026-09-10 优化后，「刷新即最新」的职责已重新分配，杜绝循环刷新：
//   ① SW fetch HTML 走 SWR（秒开缓存 + 后台 cache:'reload' 拉新），内容每次加载即最新；
//   ② SW 注册 URL 固定为 './sw.js'（不带 build-version 查询串），避免缓存 HTML 的版本戳与
//     当前 SW 不一致时被浏览器当成「不同注册」而反复 install→activate 形成 ~10s 刷新死循环；
//   ③ 新 SW activate 后只 postMessage('SW_UPDATED') 通知页面，页面用一次性标志决定是否刷新
//      （只有真出现新 SW 版本时刷一次，平时浏览零刷新；不再强制 clients.navigate）。
// 含 build-version 的旧方案会在多版本并存时无限循环刷新，已废弃。
(function(){
  try{
    var m=document.querySelector('meta[name="build-version"]');
    if(!m)return;
    var v=m.getAttribute('content');
    var k='md_build_ver';
    try{lsSet(k,v);}catch(e){}   // 仅记录当前版本，供其它逻辑判断，不触发刷新
  }catch(e){}
})();
// 清掉 SW 缓存的站点数据，强制下次导航从网络拉最新（避免 stale-while-revalidate 反复返回旧 HTML 造成刷新横跳）
// 2026-09-10 修复：原实现删除所有 /mining-daily/ 缓存——包括「当前版本」刚预缓存好的那一份。
// install 的预缓存每个 SW 版本只跑一次，reload 并不会把它补回来，于是出现一段「缓存被清空」的窗口；
// 若此刻网络不稳/离线，news-data.js 取不到 → window.NEWS_DATA 为 undefined → 各区块永久停在「加载中…」。
// 改为只删「非当前版本」的旧缓存：保留 mining-daily-<当前 build-version>（与 sw.js 的 CACHE_NAME 口径一致）。
function _clearHtmlCache(){
  try{
    if('caches' in window&&window.caches&&window.caches.keys){
      var keep='mining-daily-';
      try{var m=document.querySelector('meta[name="build-version"]');if(m)keep+=m.getAttribute('content');}catch(e){}
      window.caches.keys().then(function(ks){
        ks.forEach(function(name){
          if(/mining-daily/.test(name)&&name!==keep){ window.caches.delete(name).catch(function(){}); }
        });
      }).catch(function(){});
    }
  }catch(e){}
}
// ===== PWA：注册 Service Worker（可安装成App + 离线可看）=====
// 2026-09-02：新版 SW 激活后自动 reload，保证所有人打开就是最新版，无需手动清缓存
if('serviceWorker' in navigator){
  window.addEventListener('load',function(){
    // 2026-09-10 优化：注册 URL 固定，不再拼 build-version 查询串。
    // 浏览器对 SW 脚本自身的更新检查本来就会按 no-cache 重新校验，故 CDN 缓存旧 sw.js
    // 不会阻碍检测；而带 ?v= 反而会让「缓存 HTML 的版本戳 ≠ 当前 SW」时产生多个注册导致死循环刷新。
    navigator.serviceWorker.register('./sw.js').catch(function(){
      // 2026-09-10 修复：注册失败通常意味着 sw.js 本身不可解析/不可用（例如被写坏成语法错误）。
      // 此时浏览器会继续沿用旧的 SW，而旧 SW 喂的是旧的/不完整的缓存 → 页面区块停在「加载中…」。
      // 兜底自愈：清掉失效注册与本站缓存，再重载一次去拿全新资源（每会话最多一次 + 仅在线时，防循环与误清）。
      try{
        if(navigator.onLine===false)return;
        if(sessionStorage.getItem('md_sw_selfheal')==='1')return;
        sessionStorage.setItem('md_sw_selfheal','1');
        var _jobs=[];
        if(navigator.serviceWorker.getRegistrations){
          _jobs.push(navigator.serviceWorker.getRegistrations().then(function(rs){
            return Promise.all(rs.map(function(r){return r.unregister();}));
          }));
        }
        if('caches' in window&&window.caches&&window.caches.keys){
          _jobs.push(window.caches.keys().then(function(ks){
            return Promise.all(ks.filter(function(n){return /mining-daily/.test(n);})
              .map(function(n){return window.caches.delete(n);}));
          }));
        }
        Promise.all(_jobs).then(function(){
          console.warn('[sw] 注册失败，已清理失效 SW/缓存并重载一次');
          try{location.reload();}catch(e){}
        });
      }catch(e){}
    });
    // 收到"新版已就绪"通知 → 自动刷新一次（一次性标志防重复/死循环）。
    // activate 已不再强制 navigate，这里就是唯一刷新来源；仅在确实换了新的 sw.js 时触发。
    navigator.serviceWorker.addEventListener('message',function(ev){
      if(ev.data&&ev.data.type==='SW_UPDATED'&&!window.__swReloaded){
        window.__swReloaded=true;
        // 先写当前 build-version，避免新页面加载后版本戳自愈再触发一次硬刷新（双刷新闪屏）
        try{var _m=document.querySelector('meta[name="build-version"]');if(_m)lsSet('md_build_ver',_m.getAttribute('content'));}catch(e){}
        _clearHtmlCache();
        try{location.reload();}catch(e){}
      }
    });
    // 发现 sw.js 有更新 → 通知它立刻接管（无需等用户关掉所有标签页）
    navigator.serviceWorker.getRegistration().then(function(reg){
      if(reg)reg.update().catch(function(){});
    }).catch(function(){});
  });
}
// ===== 新闻问答检索条（2026-09-01 新增，纯前端，零依赖）=====
// 数据源双通道：① window.NEWS_DATA（news-data.js 全库）② 从页面 DOM 提取（兜底，100% 可用）
var QA_MINERALS='铜 镍 铅 锌 铝 金 银 稀土 钨 钼 锡 锑 锂 钴 钛 铀 锰 钒 铬 镁 铌 钽 镓 锗 铟 铼 镉 铋 硒 碲 铂 钯 铁'.split(' ');
var QA_TOPICS='政策 找矿 矿权 市场 技术 安全 国际'.split(' ');
// 2026-09-04 方案B 消歧：单字矿种（金/银/铁/钨/钼…）正文子串易误命中
// 「有色金属/资金/金融/关键金属」等无关词，故这些矿种的正文匹配须出现在
// 矿产语境词中才算命中；多字矿种直接用朴素子串，误命中风险低。
var QA_BODY_TERMS={
  '金':['黄金','金价','金矿','沪金','现货金','伦敦金','金条','足金','金资源','黄金股','金价的','金企','黄金业','黄金价格','金价创','金矿股','金矿权','采金','产金','黄金产','黄金需'],
  '银':['白银','银价','银矿','沪银','现货银','银条','足银','银资源','银精矿','采银','产银'],
  '铁':['铁矿石','铁精矿','铁矿山','铁矿','生铁','铸铁','铁精粉','铁合金','铁业','铁精','铁选','采铁','产铁','铁资源','铁砂'],
  '钨':['钨矿','钨价','钨精矿','钨资源','黑钨','白钨','采钨','产钨'],
  '钼':['钼矿','钼价','钼精矿','钼资源','采钼','产钼'],
  '锡':['锡价','锡矿','锡资源','锡精矿','采锡','产锡'],
  '锑':['锑矿','锑价','锑资源','锑精矿','采锑','产锑'],
  '钛':['钛矿','钛价','钛资源','钛精矿','海绵钛','采钛','产钛'],
  '铀':['铀矿','铀价','铀资源','采铀','产铀','铀浓缩'],
  '锰':['锰矿','锰价','锰资源','锰精矿','采锰','产锰'],
  '钒':['钒矿','钒价','钒资源','钒钛','采钒','产钒'],
  '铬':['铬矿','铬价','铬资源','铬铁','采铬','产铬'],
  '镁':['镁矿','镁价','镁资源','镁砂','采镁','产镁','镁合金'],
  '镓':['镓矿','镓价','镓资源','采镓','产镓'],
  '锗':['锗矿','锗价','锗资源','采锗','产锗'],
  '铟':['铟矿','铟价','铟资源','采铟','产铟'],
  '铼':['铼矿','铼价','铼资源','采铼','产铼'],
  '镉':['镉矿','镉价','镉资源','采镉','产镉'],
  '铋':['铋矿','铋价','铋资源','采铋','产铋'],
  '硒':['硒矿','硒价','硒资源','采硒','产硒'],
  '碲':['碲矿','碲价','碲资源','采碲','产碲'],
  '铂':['铂矿','铂价','铂金','铂资源','采铂','产铂'],
  '钯':['钯矿','钯价','钯金','钯资源','采钯','产钯']
};
// 方案C（2026-09-04）：中文同义/分词映射。纯子串匹配下「铝矿」捞不到「铝土矿」（"铝""土""矿"都不连续）。
// 把互为同义的矿种/商品词放进同组，搜任一词时扩展到整组做 OR 子串匹配，双向互通。
// 仅对落在表内的词生效；未收录的词（如单字「金」）仍走朴素子串，不影响既有逻辑。
var QA_ALIAS=[
  ['铝矿','铝土矿'],
  ['铁矿','铁矿石','铁精矿','铁矿山'],
  ['铜矿','铜精矿','铜矿石'],
  ['金矿','金矿石','黄金矿'],
  ['锂矿','锂辉石','锂云母','盐湖锂','锂精矿'],
  ['铅锌','铅锌矿'],
  ['镍矿','镍精矿','镍矿石'],
  ['钴矿','钴','钴精矿'],
  ['锡矿','锡','锡精矿'],
  ['稀土','稀土矿','稀土资源'],
  ['钼矿','钼','钼精矿'],
  ['钨矿','钨','钨精矿'],
  ['萤石','萤石矿'],
  ['石墨','石墨矿'],
  ['磷矿','磷矿石'],
  ['钾','钾盐','钾肥','钾矿'],
  ['镁矿','镁','镁砂'],
  ['锰矿','锰','锰精矿'],
  ['钒矿','钒','钒钛'],
  ['铬矿','铬','铬铁'],
  ['锗矿','锗'],
  ['镓矿','镓'],
  ['铟矿','铟'],
  ['铼矿','铼'],
  ['镉矿','镉'],
  ['铋矿','铋'],
  ['硒矿','硒'],
  ['碲矿','碲'],
  ['铀矿','铀'],
  ['锑矿','锑'],
  ['钛矿','钛','海绵钛'],
  ['找矿','地质找矿','找矿突破'],
  ['矿权','矿业权'],
  ['锂价','碳酸锂','氢氧化锂','锂盐'],
  ['铜价','铜','铜价'],
  ['铝价','铝','铝价'],
  ['金矿股','黄金股','黄金板块']
];
// 构建扁平查表：词 → 该组全部词（用于搜索时扩展）
var QA_ALIAS_MAP={};
QA_ALIAS.forEach(function(g){g.forEach(function(w){QA_ALIAS_MAP[w]=g;});});
// 搜索词扩展：在表中则展开为整组，否则原词（仍是长度1的数组）
function qaExpand(w){return QA_ALIAS_MAP[w]?QA_ALIAS_MAP[w]:[w];}
var QA_ROWS=[],QA_SRC='',QA_UPDATED='',QA_TREND=false;

function qaReportDate(){
  var t=document.querySelector('#todaySection .section-title');
  if(t){var m=t.textContent.match(/(\d{4}-\d{2}-\d{2})/);if(m)return m[1];}
  var h=(document.title||'').match(/(\d{4}-\d{2}-\d{2})/);
  if(h)return h[1];
  var d=new Date(),p=function(n){return n<10?'0'+n:''+n;};
  return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate());
}
// MM-DD 补年份：以日报日期为锚，补全后若晚于锚点则年份减一（跨年回卷）
function qaFullDate(mmdd,anchor){
  if(!mmdd||!anchor)return '';
  var y=anchor.slice(0,4),full=y+'-'+mmdd;
  if(full>anchor)full=(parseInt(y,10)-1)+'-'+mmdd;
  return full;
}
function qaFromDom(){
  var anchor=qaReportDate(),out=[],seen={};
  document.querySelectorAll('.news-item').forEach(function(el){
    var a=el.querySelector('a.news-title');
    if(!a)return;
    var u=el.dataset.url||a.getAttribute('href')||'';
    if(!u||seen[u])return;               // 专项区/今日区可能重复，按 URL 去重
    seen[u]=1;
    var meta=el.querySelector('.news-meta'),sum=el.querySelector('.news-summary');
    var srcEl=meta?meta.querySelector('.src'):null,raw=meta?meta.textContent:'';
    var d='',dm=raw.match(/(\d{4}-\d{2}-\d{2})/);
    if(dm)d=dm[1];
    else{var m2=raw.match(/(\d{2})-(\d{2})/);if(m2)d=qaFullDate(m2[1]+'-'+m2[2],anchor);}
    out.push({d:d,t:(a.textContent||'').trim(),s:srcEl?(srcEl.textContent||'').trim():'',u:u,
              g:(el.dataset.tags||'').split('|').filter(Boolean),c:'',m:sum?(sum.textContent||'').trim():''});
  });
  return out;
}
function qaInitData(){
  if(window.NEWS_DATA&&window.NEWS_DATA.news&&window.NEWS_DATA.news.length){
    QA_ROWS=window.NEWS_DATA.news;QA_SRC='full';QA_UPDATED=window.NEWS_DATA.updated||'';
  }else{QA_ROWS=qaFromDom();QA_SRC='dom';QA_UPDATED='';}
  var cnt={};
  QA_ROWS.forEach(function(r){
    // 2026-09-04 方案B：矿种/主题计数改为「标签命中 OR 正文命中(消歧后)」去重计数，
    // 与 qaFilter 的筛选口径一致，下拉括号数字即真实筛出条数。
    QA_MINERALS.forEach(function(m){if(qaMineralHit(r,m))cnt[m]=(cnt[m]||0)+1;});
    QA_TOPICS.forEach(function(t){if((r.g||[]).indexOf(t)>=0||qaHay(r).indexOf(t)>=0)cnt[t]=(cnt[t]||0)+1;});
  });
  var ms=document.getElementById('qaFloatMineral'),ts=document.getElementById('qaFloatTopic');
  QA_MINERALS.forEach(function(m){if(cnt[m]){var o=document.createElement('option');o.value=m;o.textContent=m+' ('+cnt[m]+')';if(ms)ms.appendChild(o);}});
  QA_TOPICS.forEach(function(t){if(cnt[t]){var o=document.createElement('option');o.value=t;o.textContent=t+' ('+cnt[t]+')';if(ts)ts.appendChild(o);}});
}
function qaHay(r){return [r.t||'',r.m||'',r.s||'',r.c||'',(r.g||[]).join(' ')].join(' ');}
// 矿种命中：标签含 X 直接命中；否则看正文——单字矿种须落在矿产语境词中（QA_BODY_TERMS），
// 多字矿种用朴素子串，避免「金」误中「有色金属/资金」之类无关词。
// 2026-09-11 IA评审 A2：从 qaMineralHit 抽出纯文本版，供 DOM 侧 chip/矿权行复用同一套矿种语义
// （落在 QA_BODY_TERMS 的词须命中矿产语境词；表外词仍走朴素子串）。
function mdMineralHit(text,key){
  key=String(key==null?'':key).toLowerCase();
  if(!key)return true;
  var t=String(text==null?'':text).toLowerCase();
  if(t.indexOf(key)<0)return false;
  var terms=QA_BODY_TERMS[key];
  if(!terms)return true;
  for(var i=0;i<terms.length;i++){ if(t.indexOf(terms[i])>=0)return true; }
  return false;
}
function qaMineralHit(r,key){
  if((r.g||[]).indexOf(key)>=0)return true;
  return mdMineralHit(qaHay(r),key);
}
function qaFilter(rows,words,mineral,topic,from,mode){
  return rows.filter(function(r){
    // 2026-09-04 方案B：矿种筛选改为「标签含 X OR 正文含 X(单字矿种须落在矿产语境词)」，
    // 消除纯标签匹配导致的漏筛；同时对单字矿种做消歧，避免「金」误中「有色金属/资金」。
    if(mineral&&!qaMineralHit(r,mineral))return false;
    if(topic){
      var tTag=(r.g||[]).indexOf(topic)>=0, tBody=qaHay(r).indexOf(topic)>=0;
      if(!tTag&&!tBody)return false;
    }
    if(from&&(!r.d||r.d<from))return false;
    if(words.length){
      var hay=qaHay(r);
      // 方案C：每个关键词 w 扩展为其同义词组，hay 含任一同义词即算该词命中（保留 and/or 语义）
      var ok=(mode==='or')
        ?words.some(function(w){return qaExpand(w).some(function(a){return hay.indexOf(a)>=0;});})
        :words.every(function(w){return qaExpand(w).some(function(a){return hay.indexOf(a)>=0;});});
      if(!ok)return false;
    }
    return true;
  }).sort(function(a,b){return (b.d||'').localeCompare(a.d||'');});
}
function qaTrendText(rows){
  var cnt={},order=[];
  rows.forEach(function(r){var k=r.d||'未知日期';if(!(k in cnt)){cnt[k]=0;order.push(k);}cnt[k]++;});
  order.sort();
  var max=0;order.forEach(function(k){if(cnt[k]>max)max=cnt[k];});
  return order.map(function(k){
    var n=Math.max(1,Math.round(cnt[k]/max*30));
    return k+'  '+new Array(n+1).join('#')+'  '+cnt[k];
  }).join('\n');
}
function qaEsc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
// 关键词高亮：先转义再对（含同义词）的词包裹 <mark>，避免 XSS
function qaHi(text,words){
  var esc=qaEsc(text);
  if(!words||!words.length)return esc;
  var terms={};
  words.forEach(function(w){qaExpand(w).forEach(function(a){if(a)terms[a]=1;});});
  var arr=Object.keys(terms).filter(Boolean).sort(function(a,b){return b.length-a.length;});
  if(!arr.length)return esc;
  var re=new RegExp('('+arr.map(function(t){return qaEsc(t).replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}).join('|')+')','g');
  return esc.replace(re,'<mark>$1</mark>');
}
// 摘要片段：截取正文前若干字，尽量在句末/空格处断开，过长加省略号
function qaSnippet(m){
  var s=(m||'').trim();
  if(!s)return '';
  var max=56;
  if(s.length>max){
    var cut=s.slice(0,max);
    var idx=Math.max(cut.lastIndexOf('。'),cut.lastIndexOf('，'),cut.lastIndexOf(' '));
    s=(idx>20?cut.slice(0,idx+1):cut)+'…';
  }
  return s;
}
// qaRender 已迁移至悬浮球（qaFloatSearch），不再渲染到主内容区 qaResult

// qaReset 已迁移至悬浮球（qaFloatReset)

// ===== AI 智能问答（2026-09-05 方案 B：前端直连 DeepSeek，共享 key 内嵌）=====
// 背景：本页是 GitHub Pages 纯静态站点、无后端服务器；所有后端（Cloudflare/腾讯云/华为云/阿里云）
// 要么被公司网络墙、要么受国内 ICP 备案限制，故改「前端直连 DeepSeek」。
// 【2026-09-08 安全整改】移除内嵌共享 Key。
// 原因：本页是 GitHub Pages 公开静态页，任何人 curl 都能拿到源码；「XOR+Base64 混淆」不是加密，
// 有心人按 F12 即可逆推出真实 Key —— 原内嵌的共享 Key 视为已泄露，请到 DeepSeek 控制台作废。
// 现状：AI 功能保留，改为「使用者自填 Key」模式，取 key 的优先级为
//   ① localStorage('MD_DS_KEY')：每位使用者填自己的 Key，只存在本人浏览器，不上传、不入库
//   ② window.MD_AI_ENDPOINT：自建后端代理地址（Key 放代理侧环境变量），公司网络若可达可启用
//   ③ 都没有 → 返回 ''，AI 区块自动降级为本地检索摘要（localAiSummary），页面其余功能不受影响
var QA_API_BASE='https://mining-daily-qa.netlify.app';
var MD_AI_KEY_STORE='MD_DS_KEY';
function getDsKey(){
  try{
    var k=localStorage.getItem(MD_AI_KEY_STORE)||'';
    k=k.replace(/\s+/g,'');
    // 基本形态校验，避免误填导致每次请求都 401
    return /^sk-[A-Za-z0-9_-]{16,}$/.test(k)?k:'';
  }catch(e){return '';}
}
// 使用者自填入口：AI 区块未配置时由 AI 区块渲染调用；也挂到 window 便于控制台/后续 UI 调用
function mdSetDsKey(k){
  try{
    k=(k||'').replace(/\s+/g,'');
    if(!/^sk-[A-Za-z0-9_-]{16,}$/.test(k)) return false;
    localStorage.setItem(MD_AI_KEY_STORE,k);
    return true;
  }catch(e){return false;}
}
function mdClearDsKey(){ try{ localStorage.removeItem(MD_AI_KEY_STORE); }catch(e){} }
window.mdSetDsKey=mdSetDsKey; window.mdClearDsKey=mdClearDsKey; window.getDsKey=getDsKey;

// 初始化步骤隔离器（2026-09-11）：任一步异常都不再中断后续初始化。
// 错误同时：① 写入 window.__mdErrors 供 index.html 横幅展示；② console.error 便于排查。
function mdSafeStep(label,fn){
  try{ fn(); }
  catch(e){
    var msg=(e&&(e.message||e))?String(e.message||e):'未知错误';
    try{ (window.__mdErrors=window.__mdErrors||[]).push(label+' → '+msg); }catch(e2){}
    try{ console.error('[mdInit] 步骤失败但已跳过：'+label+' — '+msg,e); }catch(e2){}
    try{ if(window.mdShowBootWarn)window.mdShowBootWarn(label+' 初始化失败：'+msg); }catch(e2){}
  }
}

(function(){
  mdSafeStep('qaInitData',qaInitData);
  mdSafeStep('injectNewsBadges',injectNewsBadges);   // 依赖 QA_ROWS（由 qaInitData 赋值），必须在其之后调用
  mdSafeStep('renderDigest',renderDigest);
  mdSafeStep('setupCardOpen',setupCardOpen);   // 整张卡片点击打开原文（标题/按钮仍各自处理）
  mdSafeStep('qaAiProbe',qaAiProbe);
  mdSafeStep('renderLmePrices',renderLmePrices);
  // P0-2：热榜/AI 的数据由异步 fetch 渲染，applyFilter 跑在它们之前。
  // 这里在多个时点重新评估区块可见性，确保渲染完成后能真正显示出来。
  [0,300,1200,3000].forEach(function(d){ setTimeout(function(){ mdSafeStep('mdRefreshSections',mdRefreshSections); },d); });
  // 2026-09-11：顶层初始化完成信标——index.html 的内联兜底据此判断是否需要补渲染
  window.__mdInitDone=true;
})();
// ===== LME 6 大基本金属价格（2026-09-02 新增，数据源 lme-data.js，由 fetch_lme.py 每日更新）=====
// 2026-09-06 晚改版：价格区为上下两行（首行 priceCardsShfe=国内+金银锂钴，次行 priceCardsLme=LME，
// 两行金属顺序一致），本函数按 data-slug 精确匹配填充；只动 LME 六个 slug，国内卡不受影响
function renderLmePrices(){
  try{
    var lmeCards=document.querySelectorAll('[data-slug="lcpt"],[data-slug="lalt"],[data-slug="lznt"],[data-slug="lldt"],[data-slug="lnkt"],[data-slug="ltnt"]');
    if(!lmeCards.length)return;
    var D=(typeof LME_DATA!=='undefined')?LME_DATA:null;
    if(!D||!D.metals||!D.metals.length){
      lmeCards.forEach(function(card){var c=card.querySelector('.pc-chg');if(c)c.textContent='暂无数据';});
      return;
    }
    var map={};
    D.metals.forEach(function(m){map[m.slug]=m;});
    // 2026-09-11 修复（价格卡数值 ≠ lme_data.json，方向反转）：
    // 2026-09-04 起这里会把卡片价覆盖成走势图（PRICE_HISTORY）的末两点，用意是消除
    // 「卡片价」与「走势图末点」两张价的观感差。但 PRICE_HISTORY 的 LME 序列来自东财
    // push2his 日K，伦敦开市后（北京 08:00 起）会多出一根「当日尚未收盘」的盘中 bar；
    // 而 lme_data.json 由 06:00 在伦敦闭市窗口生成，其 price 是最近一个已收盘交易日的
    // 收盘价。两者都挂当日日期，09-09 加的 `lastDate < dRef` 守卫因此放行，
    // 盘中价覆盖了收盘价 → 涨跌方向反转（锡 54115 ▼-1565 被改成 54825 ▲+710）。
    // 且此处是就地改写 LME_DATA 对象，连带 qaPriceBrief() 的问答答案一起出错。
    // 现改为：价格卡数值唯一来源 = LME_DATA（对应 test_data_integrity.js 的契约与项目红线，
    // 禁止跨源覆盖）。「卡片 / 走势图一致」改由数据侧保证——fetch_price_history.py 不再
    // 输出未收盘的 LME bar，走势图末点因此与 LME_DATA 的收盘价天然相等。
    // 注：null 价一律走下方 `-- / 暂无数据` 分支，绝不回填历史点位（09-09 P0 教训）。
    lmeCards.forEach(function(card){
      var m=map[card.getAttribute('data-slug')];
      var v=card.querySelector('.pc-value'),c=card.querySelector('.pc-chg');
      if(!v||!c)return;
      if(!m||m.price==null){v.textContent='--';c.textContent=(m&&m.err)?m.err:'暂无数据';return;}
      v.textContent=Number(m.price).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
      var chg=Number(m.chg||0),pct=Number(m.chg_pct||0);
      var cls=chg>0?'up':(chg<0?'down':'flat'), arrow=chg>0?'▲':(chg<0?'▼':'■');
      var sign=chg>0?'+':'';
      c.textContent=arrow+' '+sign+chg.toFixed(2)+' ('+sign+pct.toFixed(2)+'%)';
      card.className='price-card '+cls;
    });
    // 更新顶部 note
    var note=document.getElementById('priceStripNote');
    if(note&&D.updated){
      var dt=D.updated.substring(0,10);
      note.textContent=dt+' 更新 · 点击卡片看走势';
    }
  }catch(e){console.warn('renderLmePrices:',e);}
}
var QA_AI_ON=false,QA_AI_BUSY=false,QA_LEFT=0,QA_AI_PROBE_OK=false;
function qaAiProbe(){
  // 2026-09-08：Key 不再内嵌（公开静态页藏不住）。改为使用者自填，存 localStorage；
  // 有 Key 点亮 AI 按钮，无 Key 走本地知识库兜底，页面其余功能不受影响。
  var b=document.getElementById('qaFloatAi');
  // 2026-09-08 晚修正：优先走 Netlify 代理（Key 在平台环境变量），无需使用者自填 Key，
  // 此时按钮不应显示「AI 本地」误导；仅当既无代理又无自填 Key 时才降级提示。
  if(getDsKey()||(typeof QA_API_BASE!=='undefined'&&QA_API_BASE)){
    QA_AI_ON=true;
    if(b){b.disabled=false;b.textContent='✨ AI 回答';
      b.title='让 AI 读完相关新闻后组织语言作答（Enter 检索 / 点此 AI 问答）';}
  }else{
    QA_AI_ON=false;
    if(b){b.disabled=false;b.textContent='✨ AI 本地';
      b.title='未配置 AI 服务，点击将使用本地知识库兜底回答';}
  }
}
// 从自由文本问题中提取已知的矿种/主题词（取自检索下拉词表），用于 RAG 上下文检索。
// 中文无空格，整句做关键词几乎命中为空；提取词表词后语义更准。
function qaExtractTerms(q){
  var out=[],seen={};
  ['qaFloatMineral','qaFloatTopic'].forEach(function(id){
    var sel=document.getElementById(id);
    if(!sel||!sel.options)return;
    for(var i=0;i<sel.options.length;i++){
      var v=sel.options[i].value;
      if(v&&q.indexOf(v)>=0&&!seen[v]){seen[v]=1;out.push(v);}
    }
  });
  return out;
}
// 从问题中切分出可用于相关性打分的检索词
// ① 优先命中矿种/主题词表中的完整词；② 中文长串拆 2~4 字滑动窗口，避免整句当作一个 token
var QA_STOPWORDS='与 相关 新闻 的 是 在 有 和 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着 没有 看 好 自己 这 那 什么 怎么 为什么 多少 哪些 几 条 篇 报 道 最新 最近 一下 给我 关于 请 问 吗 呢 了 吧 啊 哦 嗯'.split(' ');
function qaTokenize(q){
  var tokens=[],seen={};
  function add(w){if(w&&w.length>=1&&!seen[w]&&QA_STOPWORDS.indexOf(w)<0){seen[w]=1;tokens.push(w);}}
  // ① 矿种/主题词表命中
  QA_MINERALS.concat(QA_TOPICS).forEach(function(w){
    if(q.indexOf(w)>=0){add(w);}
  });
  // ② 按非中英数字字符切分
  var segs=q.replace(/[^\u4e00-\u9fa5a-zA-Z0-9]/g,' ').split(/\s+/).filter(Boolean);
  segs.forEach(function(seg){
    if(seg.length<=4){add(seg);}
    else {
      // 中文长串拆 2~4 字滑动窗口，提取潜在实体词（如「紫金矿业」→ 紫金/金矿/矿业/紫金矿业）
      var chars=seg.replace(/[^\u4e00-\u9fa5]/g,'').split('');
      for(var i=0;i<chars.length;i++){
        for(var len=2;len<=4 && i+len<=chars.length;len++){
          add(chars.slice(i,i+len).join(''));
        }
      }
    }
  });
  return tokens;
}
// 按问题与新闻条目的相关性打分排序（全库 RAG，不再无脑取最新 N 条）
function qaRankByRelevance(q,rows){
  var tokens=qaTokenize(q);
  if(!tokens.length)return rows.slice();
  var now=new Date();
  return rows.map(function(r){
    var title=String(r.t||''),body=qaHay(r),tags=(r.g||[]).join(' ');
    var score=0,hitParts=[],hitTokens=[],titleHits=0,tagsHits=0;
    tokens.forEach(function(t){
      var isSingleChinese=(t.length===1 && /[\u4e00-\u9fa5]/.test(t));
      var titleScore,tagScore,bodyScore;
      if(isSingleChinese){
        // 单字矿种（金/银/铁…）在标题中必须出现在矿产语境词里才给高分，否则大幅降级
        titleScore=3; tagScore=2; bodyScore=1;
        if(QA_BODY_TERMS[t] && title.indexOf(t)>=0){
          var ctx=QA_BODY_TERMS[t],hasCtx=false;
          for(var k=0;k<ctx.length;k++){if(title.indexOf(ctx[k])>=0){hasCtx=true;break;}}
          if(!hasCtx){titleScore=1;}
        }
      }else if(t.length>=4){
        titleScore=15; tagScore=9; bodyScore=4;
      }else if(t.length===3){
        titleScore=12; tagScore=7; bodyScore=3;
      }else{
        titleScore=10; tagScore=6; bodyScore=3;
      }
      if(title.indexOf(t)>=0){score+=titleScore;titleHits++;hitTokens.push(t);if(hitParts.indexOf('title')<0)hitParts.push('title');}
      else if(tags.indexOf(t)>=0){score+=tagScore;tagsHits++;hitTokens.push(t);if(hitParts.indexOf('tags')<0)hitParts.push('tags');}
      else if(body.indexOf(t)>=0){score+=bodyScore;hitTokens.push(t);if(hitParts.indexOf('body')<0)hitParts.push('body');}
    });
    // 连续完整词额外奖励：如「紫金矿业」整体出现，比拆成「紫金」+「矿业」更相关
    if(q.indexOf(title)>=0){score+=15;}
    // 多 token 同时命中 title/tags 再奖励
    if((titleHits+tagsHits)>=2){score+=8;}
    // 时效性：越新略加分，但相关性权重占主导
    var d=String(r.d||'');
    if(d){
      try{
        var dd=new Date(d+'T00:00:00');
        if(!isNaN(dd.getTime())){
          var days=Math.max(0,(now-dd)/86400000);
          score+=Math.max(0,10-days)*0.3;
        }
      }catch(e){}
    }
    r._score=score;r._hitParts=hitParts;r._hitTokens=hitTokens;
    return {r:r,score:score,hit:hitParts.length>0};
  }).sort(function(a,b){
    // 优先按相关性倒序；同分按日期倒序
    if(b.score!==a.score)return b.score-a.score;
    return String(b.r.d||'').localeCompare(String(a.r.d||''));
  }).map(function(x){return x.r;});
}
// qaAskAI 已删除：主内容区 AI box 随「新闻问答」检索条一并移除；悬浮球的 AI 回答由 qaFloatAsk 接管

// ===== 价格卡走势图（9-04 新增，数据源 price-history.js，由 fetch_price_history.py 每日更新）=====
// 设计：缺数据时优雅降级提示，不影响行情卡本身；涨红跌绿配色
function pcSeries(slug){
  try{var H=window.PRICE_HISTORY;if(!H||!H.series)return null;return H.series[slug]||null;}catch(e){return null;}
}
function pcFmt(v){return Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});}
function pcChartOpen(slug){
  var mask=document.getElementById('pchartMask');if(!mask)return;
  // 弹层无障碍（2026-09-05 补）：声明对话框语义 + 锁定背景滚动 + 记录来源焦点以便关闭后归还
  mask.setAttribute('role','dialog');
  mask.setAttribute('aria-modal','true');
  if(!mask.classList.contains('open')){
    window.PC_CHART_LAST_FOCUS=document.activeElement;
    document.body.style.overflow='hidden';
  }
  var nameEl=document.getElementById('pchartName'),subEl=document.getElementById('pchartSub'),
      svgEl=document.getElementById('pchartSvg'),tb=document.getElementById('pchartTable'),
      lg=document.getElementById('pchartLegend');
  var s=pcSeries(slug);
  if(!s||!s.points||s.points.length<2){
    nameEl.textContent='走势暂缺';
    subEl.textContent='';
    lg.innerHTML='<span>该品种暂无连续日K数据（电解钴为 SMM 现货报价无连续盘；其余品种由每日抓取累积，个别时段可能缺失）。</span>';
    svgEl.innerHTML='';tb.innerHTML='';
    mask.classList.add('open');return;
  }
  window.PC_CHART_SLUG=slug;      // 记录当前品种，供主题切换时重绘
  var H=window.PRICE_HISTORY,pts=s.points.slice(-8),n=pts.length;
  var closes=pts.map(function(p){return p[1];});
  var first=closes[0],last=closes[n-1];
  var up=last>=first,color=up?'#e74c3c':'#27ae60';
  var pct=first?((last-first)/first*100):0;
  var hi=Math.max.apply(null,closes),lo=Math.min.apply(null,closes);
  nameEl.textContent=s.name;
  subEl.textContent=s.unit+' · 近'+n+'个交易日 · 东方财富日K · 更新于 '+(H.updated||'');
  lg.innerHTML='<span>最新 <b style="color:'+color+'">'+pcFmt(last)+'</b></span>'
    +'<span>区间涨跌 <b style="color:'+color+'">'+(up?'+':'')+pct.toFixed(2)+'%</b></span>'
    +'<span>区间最高 <b>'+pcFmt(hi)+'</b></span>'
    +'<span>区间最低 <b>'+pcFmt(lo)+'</b></span>';
  // ---- SVG 折线 ----
  // 2026-09-05 修复：
  //   ① 原固定 viewBox 宽 580，在 360px 手机上整体缩放约 0.5 倍，
  //      日期/坐标文字实际只有约 5px 根本看不清 —— 改为按容器实际宽度 1:1 绘制；
  //   ② 网格线、坐标轴文字、数据点为硬编码浅色，暗色模式下刺眼或看不见 —— 改为随主题取色
  mask.classList.add('open');                       // 先显示，才能测到真实容器宽度
  var DARK=document.body.classList.contains('dark');
  var C_GRID=DARK?'#2c3845':'#eef2f5',
      C_AXIS=DARK?'#8296a8':'#95a5a6',
      C_DOT =DARK?'#1e2733':'#ffffff',
      C_DATE=DARK?'#94a3b8':'#7f8c8d';
  var hostW=svgEl.clientWidth||(window.innerWidth-72)||360;
  var W=Math.max(300,Math.min(580,Math.round(hostW)));
  var narrow=W<430;                                // 窄屏：压缩高度、加大字号、只留首尾日期
  var Hh=narrow?200:235,L=narrow?52:58,R=14,T=18,B=30,FS=narrow?12:11;
  var span=(hi-lo)||1;lo-=span*0.08;hi+=span*0.08;span=hi-lo;
  function X(i){return L+i*(W-L-R)/(n-1);}
  function Y(v){return T+(1-(v-lo)/span)*(Hh-T-B);}
  var poly='',dots='',grid='',xlab='';
  [hi,lo].forEach(function(v,i2){
    grid+='<line x1="'+L+'" y1="'+Y(v)+'" x2="'+(W-R)+'" y2="'+Y(v)+'" stroke="'+C_GRID+'" stroke-width="1"/>'
        +'<text x="'+(L-6)+'" y="'+(Y(v)+3.5)+'" text-anchor="end" font-size="'+FS+'" fill="'+C_AXIS+'">'+pcFmt(v)+'</text>';
  });
  closes.forEach(function(v,i2){
    poly+=(i2?' ':'')+X(i2).toFixed(1)+','+Y(v).toFixed(1);
    dots+='<circle cx="'+X(i2).toFixed(1)+'" cy="'+Y(v).toFixed(1)+'" r="'+(narrow?3.6:3.2)+'" fill="'+C_DOT+'" stroke="'+color+'" stroke-width="2"><title>'+pts[i2][0]+'  收 '+pcFmt(v)+'</title></circle>';
  });
  pts.forEach(function(p,i2){
    // 窄屏点位密集，只标首尾两个日期，避免文字互相重叠
    var show = narrow ? (i2===0||i2===n-1) : (i2===0||i2===n-1||i2===Math.floor((n-1)/2));
    if(show)
      xlab+='<text x="'+X(i2).toFixed(1)+'" y="'+(Hh-8)+'" text-anchor="middle" font-size="'+FS+'" fill="'+C_DATE+'">'+p[0].slice(5)+'</text>';
  });
  var area='M'+X(0).toFixed(1)+','+Y(closes[0]).toFixed(1)+' '+closes.map(function(v,i2){return 'L'+X(i2).toFixed(1)+','+Y(v).toFixed(1);}).join(' ')
          +' L'+X(n-1).toFixed(1)+','+(Hh-B)+' L'+X(0).toFixed(1)+','+(Hh-B)+' Z';
  svgEl.innerHTML='<svg viewBox="0 0 '+W+' '+Hh+'" width="100%" style="display:block" role="img" aria-label="'+s.name+'近'+n+'日收盘价走势">'
    +'<defs><linearGradient id="pcGrad" x1="0" y1="0" x2="0" y2="1">'
    +'<stop offset="0" stop-color="'+color+'" stop-opacity="0.18"/><stop offset="1" stop-color="'+color+'" stop-opacity="0.02"/></linearGradient></defs>'
    +grid+'<path d="'+area+'" fill="url(#pcGrad)"/>'
    +'<polyline points="'+poly+'" fill="none" stroke="'+color+'" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>'
    +dots+xlab+'</svg>';
  // ---- 明细表（最新在上）----
  var h='<tr><th>日期</th><th>收盘</th><th>日涨跌</th></tr>';
  for(var i=n-1;i>=0;i--){
    var chg=i>0?((closes[i]-closes[i-1])/closes[i-1]*100):null;
    h+='<tr><td>'+pts[i][0]+'</td><td>'+pcFmt(closes[i])+'</td><td>'
      +(chg==null?'<span style="color:'+C_AXIS+'">—</span>'
                 :'<span class="'+(chg>=0?'pchart-up':'pchart-down')+'">'+(chg>=0?'+':'')+chg.toFixed(2)+'%</span>')
      +'</td></tr>';
  }
  tb.innerHTML=h;
  mask.classList.add('open');
  // 打开后把焦点移进弹层，键盘用户可直接用 ESC / 回车关闭
  var cbtn=mask.querySelector('.pchart-close');
  if(cbtn)setTimeout(function(){try{cbtn.focus();}catch(e){}},50);
}
function pcChartClose(){
  var m=document.getElementById('pchartMask');
  if(!m||!m.classList.contains('open'))return;
  m.classList.remove('open');
  document.body.style.overflow='';      // 恢复背景滚动
  window.PC_CHART_SLUG=null;
  // 焦点归还给打开它的价格卡，键盘用户不会丢失位置
  try{
    var f=window.PC_CHART_LAST_FOCUS;
    if(f&&f.focus)f.focus();
  }catch(e){}
}
(function(){
  document.querySelectorAll('.price-cards').forEach(function(box){
    box.addEventListener('click',function(e){
      var card=e.target?e.target.closest('.price-card'):null;if(!card)return;
      var slug=card.getAttribute('data-slug');if(slug)pcChartOpen(slug);
    });
    // 键盘可达（2026-09-05 补）：此前价格卡是裸 div，Tab 不到、回车也打不开
    box.addEventListener('keydown',function(e){
      if(e.key!=='Enter'&&e.key!==' ')return;
      var card=e.target?e.target.closest('.price-card'):null;if(!card)return;
      e.preventDefault();
      var slug=card.getAttribute('data-slug');if(slug)pcChartOpen(slug);
    });
  });
  document.querySelectorAll('.price-card').forEach(function(card){
    if(!card.getAttribute('data-slug'))return;      // 电解钴无日 K，不可点
    card.setAttribute('tabindex','0');
    card.setAttribute('role','button');
    var nm=(card.querySelector('.pc-name')||{}).textContent||'';
    card.setAttribute('aria-label','查看 '+nm.replace(/\s+/g,' ').trim()+' 近8个交易日价格走势');
  });
})();
// ===== 左下角问答悬浮球（9-04 新增，复用全库 QA_ROWS 与 /api/qa 能力）=====
var QA_FLOAT_BUSY=false;
function qaFloatToggle(){
  var p=document.getElementById('qaFloat'),b=document.getElementById('qaFab');
  if(!p)return;
  var open=p.classList.toggle('open');
  if(b)b.classList.toggle('on',open);
  if(open){var i=document.getElementById('qaFloatInput');if(i)setTimeout(function(){i.focus();},80);qaStopBreathe();}
}
function qaFloatClose(){
  var p=document.getElementById('qaFloat');if(p)p.classList.remove('open');
  var b=document.getElementById('qaFab');if(b)b.classList.remove('on');
}
// 点击/拖动区分：短距离移动视为点击，否则视为拖动并阻止打开面板
var QA_FAB_MOVED=false;
var QA_FAB_DRAG=null;
var QA_FAB_TOUCH_DONE=false;   // 触摸链路已自行处理点击，避免浏览器补发的 click 重复触发
// 2026-09-06 移动端修复要点：
//   触摸时绝不能在 touchstart 调 preventDefault()，否则浏览器不再合成 click，
//   内联 onclick 永远不执行 —— 表现为"手机上悬浮球点不动，电脑上正常"。
//   正确做法：touchstart 只记录起点；touchmove 判定真的移动了才 preventDefault 阻止页面滚动；
//   touchend 若未发生移动则直接手动触发开合，不依赖浏览器补发 click。
// 按下瞬间是否处于半隐藏状态：点击判定必须以"按下时"为准，
// 否则（触摸设备上）按下即归位、抬手时就变成展开态，会跳过"唤出"直接弹面板。
var QA_FAB_PRESS_TUCKED=null;
function qaFabClick(ev){
  var press=(typeof QA_FAB_PRESS_TUCKED==='boolean')?QA_FAB_PRESS_TUCKED:QA_FAB_TUCKED;
  QA_FAB_PRESS_TUCKED=null;
  if(QA_FAB_TOUCH_DONE){QA_FAB_TOUCH_DONE=false;if(ev&&ev.preventDefault)ev.preventDefault();return false;}
  if(QA_FAB_MOVED){if(ev&&ev.preventDefault)ev.preventDefault();if(ev&&ev.stopPropagation)ev.stopPropagation();return false;}
  qaFabActivate(press);
}
// 悬浮球点击的统一入口：半隐藏状态下先唤出，展开状态下才开合面板
function qaFabActivate(wasTucked){
  var tucked=(typeof wasTucked==='boolean')?wasTucked:QA_FAB_TUCKED;
  if(tucked){
    // 桌面（真·指针设备）鼠标悬停时球已由 CSS 滑出，点击意为开面板，不必先唤出。
    // 触摸设备 tap 后 :hover 会短暂匹配，故用 (hover:hover) 排除，避免手机上跳过唤出。
    var canHover=false;
    try{canHover=!!(window.matchMedia&&window.matchMedia('(hover: hover) and (pointer: fine)').matches);}catch(e){}
    var hovering=false;
    if(canHover){try{var b0=document.getElementById('qaFab');hovering=!!(b0&&b0.matches&&b0.matches(':hover'));}catch(e){}}
    if(!hovering){qaFabUntuck();return;}
  }
  qaFloatToggle();
}
function qaFabIsTouch(ev){return !!ev&&typeof ev.type==='string'&&ev.type.indexOf('touch')===0;}
// 布局位置（不含 transform）：半隐藏时 getBoundingClientRect 会被 translateX 带偏，不能直接用
function qaFabLayoutLeft(b){
  var v=parseFloat(b.style.left);
  if(!isNaN(v))return v;
  return b.offsetLeft||0;
}
function qaFabLayoutBottom(b){
  var v=parseFloat(b.style.bottom);
  if(!isNaN(v))return v;
  var bh=b.offsetHeight||50;
  return Math.max(window.innerHeight-(b.offsetTop||0)-bh,0);
}
function qaFabStartDrag(ev){
  var b=document.getElementById('qaFab');if(!b)return;
  var isTouch=qaFabIsTouch(ev);
  if(isTouch&&ev.touches.length!==1)return;
  var point=isTouch?ev.touches[0]:ev;
  QA_FAB_PRESS_TUCKED=QA_FAB_TUCKED;
  QA_FAB_DRAG={el:b,startX:point.clientX,startY:point.clientY,origLeft:qaFabLayoutLeft(b),origBottom:qaFabLayoutBottom(b)};
  QA_FAB_MOVED=false;
  b.classList.add('dragging');
  if(isTouch){
    document.addEventListener('touchmove',qaFabDrag,{passive:false});
    document.addEventListener('touchend',qaFabStopDrag,{passive:false});
    document.addEventListener('touchcancel',qaFabStopDrag,{passive:false});
  }else{
    document.addEventListener('mousemove',qaFabDrag);document.addEventListener('mouseup',qaFabStopDrag);
    ev.preventDefault();   // 仅桌面：阻止拖拽时选中文本
  }
}
function qaFabDrag(ev){
  if(!QA_FAB_DRAG)return;
  var point=ev.touches?ev.touches[0]:ev;
  var dx=point.clientX-QA_FAB_DRAG.startX, dy=point.clientY-QA_FAB_DRAG.startY;
  if(Math.abs(dx)<4&&Math.abs(dy)<4)return;   // 手指轻微抖动不算拖动
  if(ev.cancelable)ev.preventDefault();       // 确认是拖动后才阻止页面滚动
  // 从半隐藏状态起拖：真正移动了才归位，点击（未移动）时保持收起以便"唤出"
  if(!QA_FAB_MOVED&&QA_FAB_PRESS_TUCKED&&QA_FAB_TUCKED)qaFabUntuck();
  QA_FAB_MOVED=true;
  var b=QA_FAB_DRAG.el, vw=window.innerWidth, vh=window.innerHeight, bw=b.offsetWidth||160, bh=b.offsetHeight||50;
  // 允许向左右各拖出球体 55%：拖出屏幕边缘松手即进入半隐藏；没拖出去就留在原位
  var minLeft=-Math.round(bw*0.55), maxLeft=Math.max(vw-bw*0.45,0);
  var left=Math.min(Math.max(QA_FAB_DRAG.origLeft+dx,minLeft),maxLeft);
  var bottom=Math.min(Math.max(QA_FAB_DRAG.origBottom-dy,0),Math.max(vh-bh,0));
  b.style.left=left+'px'; b.style.bottom=bottom+'px'; b.style.top='auto';
}
function qaFabStopDrag(ev){
  if(!QA_FAB_DRAG)return;
  var b=QA_FAB_DRAG.el;
  var wasTouch=qaFabIsTouch(ev);
  document.removeEventListener('mousemove',qaFabDrag);document.removeEventListener('mouseup',qaFabStopDrag);
  document.removeEventListener('touchmove',qaFabDrag,{passive:false});
  document.removeEventListener('touchend',qaFabStopDrag,{passive:false});
  document.removeEventListener('touchcancel',qaFabStopDrag,{passive:false});
  if(b)b.classList.remove('dragging');
  QA_FAB_DRAG=null;
  if(QA_FAB_MOVED&&b){
    // 拖出屏幕边缘 → 半隐藏；否则只记录位置
    var bw=b.offsetWidth||160, vw=window.innerWidth;
    var l=qaFabLayoutLeft(b);
    if(l<=0)qaFabTuck('left');
    else if(l+bw>=vw-1)qaFabTuck('right');
    else{qaFabUntuckState();qaFabSavePos();}
  }
  if(wasTouch&&!QA_FAB_MOVED){
    // 移动端：直接开合，不再等浏览器补发 click（补发了也会被标记拦掉）
    QA_FAB_TOUCH_DONE=true;
    setTimeout(function(){QA_FAB_TOUCH_DONE=false;},600);
    if(ev&&ev.cancelable)ev.preventDefault();
    var press=QA_FAB_PRESS_TUCKED;QA_FAB_PRESS_TUCKED=null;
    qaFabActivate(press);
    return;
  }
  QA_FAB_PRESS_TUCKED=null;
  // 300ms 后复位移动标记，避免后续 click 被误拦截
  setTimeout(function(){QA_FAB_MOVED=false;},300);
}
// ===== 悬浮球半隐藏：吸边收起 / 点击唤出（2026-09-06 新增）=====
// 拖出屏幕左右边缘松手 → 球体只剩 26px 把手贴边；点击把手唤出；桌面鼠标悬停也会滑出。
// 状态用 transform 表达，left/bottom 始终是"展开时"的贴边位置，位置记忆不受影响。
var QA_FAB_TUCKED=false;
var QA_FAB_SIDE='left';
function qaFabApplyTuck(){
  var b=document.getElementById('qaFab');if(!b)return;
  b.classList.toggle('tucked',QA_FAB_TUCKED);
  b.classList.toggle('tuck-left',QA_FAB_SIDE==='left');
  b.classList.toggle('tuck-right',QA_FAB_SIDE==='right');
  b.title=QA_FAB_TUCKED?'已收起 · 点击唤出悬浮球（拖到屏幕边缘可再次收起）':'新闻检索 / AI 问答（可拖动；拖出屏幕边缘即收起）';
}
function qaFabSaveTuck(){
  try{if(window.localStorage)lsSet('qaFabTuck',JSON.stringify({t:QA_FAB_TUCKED,s:QA_FAB_SIDE}));}catch(e){}
}
function qaFabRestoreTuck(){
  try{
    var raw=window.localStorage&&localStorage.getItem('qaFabTuck');if(!raw)return;
    var o=JSON.parse(raw);QA_FAB_TUCKED=!!o.t;QA_FAB_SIDE=(o.s==='right'?'right':'left');
  }catch(e){}
}
// 仅收回状态、不写存储（拖回可视区时用）
function qaFabUntuckState(){QA_FAB_TUCKED=false;qaFabApplyTuck();}
function qaFabTuck(side){
  var b=document.getElementById('qaFab');if(!b)return;
  var bw=b.offsetWidth||160, vw=window.innerWidth;
  QA_FAB_SIDE=(side==='right'?'right':'left');
  b.style.left=(QA_FAB_SIDE==='left'?0:Math.max(vw-bw,0))+'px';
  b.style.top='auto';
  QA_FAB_TUCKED=true;
  qaFabApplyTuck();qaFabSavePos();qaFabSaveTuck();
}
function qaFabUntuck(){qaFabUntuckState();qaFabSavePos();qaFabSaveTuck();}
function qaFabSavePos(){
  try{
    var b=document.getElementById('qaFab');if(!b)return;
    // 用布局位置（不含 transform），否则半隐藏时存进去的 left 是负数，刷新后球会在屏幕外
    lsSet('qaFabPos',JSON.stringify({left:qaFabLayoutLeft(b),bottom:qaFabLayoutBottom(b)}));
  }catch(e){}
}
function qaFabRestorePos(){
  try{
    var raw=localStorage.getItem('qaFabPos');if(!raw)return;
    var pos=JSON.parse(raw), b=document.getElementById('qaFab');if(!b)return;
    var vw=window.innerWidth, vh=window.innerHeight, bw=b.offsetWidth||160, bh=b.offsetHeight||50;
    var left=Math.min(Math.max(pos.left||16,0),Math.max(vw-bw,0));
    var bottom=Math.min(Math.max(pos.bottom||16,0),Math.max(vh-bh,0));
    b.style.position='fixed';b.style.left=left+'px';b.style.bottom=bottom+'px';b.style.top='auto';
  }catch(e){}
}
function qaStopBreathe(){
  try{var b=document.getElementById('qaFab');if(b)b.classList.remove('breathe');}catch(e){}
  try{if(window.localStorage)lsSet('qaFabSeen','1');}catch(e){}
}
// ===== 悬浮球拖拽 + 尺寸记忆 =====
// 拖拽把手=整个面板任意非交互位置（头部/边框/结果空白区均可拖）；
// 输入框/筛选/按钮/链接/关闭键/趋势图/右下角原生缩放柄 不触发拖拽。
var QA_DRAGGING=null;
var QA_DRAG_EXCLUDE='input,select,button,a,textarea,[contenteditable],.qa-fsel,.qa-fchip,.pchart-close,.qa-trend,.qa-src,.qa-msg-bubble,.qa-float-body,.qa-float-foot,.qa-float-btn,.qa-resize-handle';
function qaFloatStartDrag(ev){
  if(window.innerWidth && window.innerWidth<=768) return;
  var p=document.getElementById('qaFloat'); if(!p||!p.classList.contains('open'))return;
  // 交互元素不触发拖拽，保证内部可选择/点击/输入
  if(ev.target.closest && ev.target.closest(QA_DRAG_EXCLUDE))return;
  // 预留右下角 18px 给原生 resize 缩放柄
  var r=p.getBoundingClientRect(), ex=ev.clientX-r.left, ey=ev.clientY-r.top;
  if(ex>=r.width-18 && ey>=r.height-18)return;
  var isTouch=!!ev.type&&ev.type.indexOf('touch')===0;
  if(isTouch&&ev.touches.length!==1)return;
  var point=isTouch?ev.touches[0]:ev;
  QA_DRAGGING={el:p,startX:point.clientX,startY:point.clientY,origLeft:r.left,origTop:r.top};
  p.style.position='fixed'; p.style.bottom='auto'; p.style.cursor='grabbing';
  if(isTouch){
    document.addEventListener('touchmove',qaFloatDrag,{passive:false});
    document.addEventListener('touchend',qaFloatStopDrag,{passive:false});
    document.addEventListener('touchcancel',qaFloatStopDrag,{passive:false});
  }else{
    document.addEventListener('mousemove',qaFloatDrag); document.addEventListener('mouseup',qaFloatStopDrag);
    ev.preventDefault();   // 仅桌面：阻止拖拽时选中文本
  }
}
function qaFloatDrag(ev){
  if(!QA_DRAGGING)return;
  var point=ev.touches?ev.touches[0]:ev;
  var dx=point.clientX-QA_DRAGGING.startX, dy=point.clientY-QA_DRAGGING.startY;
  if(Math.abs(dx)<4&&Math.abs(dy)<4)return;
  if(ev.cancelable)ev.preventDefault();
  var el=QA_DRAGGING.el, w=el.offsetWidth||440, h=el.offsetHeight||560;
  var vw=window.innerWidth, vh=window.innerHeight;
  var left=Math.min(Math.max(QA_DRAGGING.origLeft+dx,0),Math.max(vw-w,0));
  var top=Math.min(Math.max(QA_DRAGGING.origTop+dy,0),Math.max(vh-h,0));
  el.style.left=left+'px'; el.style.top=top+'px';
}
function qaFloatStopDrag(ev){
  if(!QA_DRAGGING)return;
  document.removeEventListener('mousemove',qaFloatDrag); document.removeEventListener('mouseup',qaFloatStopDrag);
  document.removeEventListener('touchmove',qaFloatDrag,{passive:false});
  document.removeEventListener('touchend',qaFloatStopDrag,{passive:false});
  document.removeEventListener('touchcancel',qaFloatStopDrag,{passive:false});
  var p=QA_DRAGGING.el; if(p)p.style.cursor='';
  qaFloatSavePos(); QA_DRAGGING=null;
}
function qaFloatSavePos(){
  try{
    var p=document.getElementById('qaFloat'); if(!p)return;
    var rect=p.getBoundingClientRect();
    lsSet('qaFloatPos',JSON.stringify({left:rect.left,top:rect.top}));
  }catch(e){}
}
function qaFloatRestorePos(){
  try{
    var raw=localStorage.getItem('qaFloatPos'); if(!raw)return;
    var pos=JSON.parse(raw), p=document.getElementById('qaFloat'); if(!p)return;
    var vw=window.innerWidth, vh=window.innerHeight, w=p.offsetWidth||440, h=p.offsetHeight||560;
    var left=Math.min(Math.max(pos.left,0),Math.max(vw-w,0));
    var top=Math.min(Math.max(pos.top,0),Math.max(vh-h,0));
    p.style.position='fixed'; p.style.left=left+'px'; p.style.top=top+'px'; p.style.bottom='auto';
  }catch(e){}
}
// 2026-09-06 补：qaFloatStopResize() 一直在调用此函数，但此前从未定义，
// 每次缩放结束都会抛 ReferenceError（缩放本身靠 ResizeObserver 兜底才没丢尺寸）
function qaFloatSaveSize(){
  try{
    var p=document.getElementById('qaFloat'); if(!p)return;
    if(window.localStorage)lsSet('qaFloatSize',JSON.stringify({width:p.offsetWidth,height:p.offsetHeight}));
  }catch(e){}
}
function qaFloatObserveSize(){
  try{
    var p=document.getElementById('qaFloat'); if(!p||!window.ResizeObserver)return;
    var ro=new ResizeObserver(function(){
      try{lsSet('qaFloatSize',JSON.stringify({width:p.offsetWidth,height:p.offsetHeight}));}catch(e){}
    });
    ro.observe(p);
  }catch(e){}
}
function qaFloatRestoreSize(){
  try{
    var raw=localStorage.getItem('qaFloatSize'); if(!raw)return;
    var sz=JSON.parse(raw), p=document.getElementById('qaFloat'); if(!p||!sz.width||!sz.height)return;
    p.style.width=sz.width+'px'; p.style.height=sz.height+'px';
  }catch(e){}
}
// ===== 面板四边四角自定义缩放 =====
var QA_RESIZING=null;
function qaFloatAddResizeHandles(){
  var p=document.getElementById('qaFloat'); if(!p||p.querySelector('.qa-resize-handle'))return;
  ['n','s','e','w','ne','nw','se','sw'].forEach(function(dir){
    var d=document.createElement('div'); d.className='qa-resize-handle qa-resize-'+dir; d.dataset.dir=dir;
    p.appendChild(d);
  });
}
function qaFloatStartResize(ev){
  if(ev.target.closest && ev.target.closest('input,select,button,a,textarea,[contenteditable]'))return;
  var h=ev.target.closest && ev.target.closest('.qa-resize-handle'); if(!h)return;
  var p=document.getElementById('qaFloat'); if(!p)return;
  var isTouch=!!ev.type&&ev.type.indexOf('touch')===0;
  if(isTouch&&ev.touches.length!==1)return;
  var pt=isTouch?ev.touches[0]:ev;
  var dir=h.dataset.dir||'se';
  var r=p.getBoundingClientRect();
  QA_RESIZING={el:p,dir:dir,startX:pt.clientX,startY:pt.clientY,startW:r.width,startH:r.height,startL:r.left,startT:r.top,minW:300,minH:260};
  if(isTouch){
    document.addEventListener('touchmove',qaFloatResize,{passive:false});
    document.addEventListener('touchend',qaFloatStopResize,{passive:false});
    document.addEventListener('touchcancel',qaFloatStopResize,{passive:false});
  }else{
    document.addEventListener('mousemove',qaFloatResize); document.addEventListener('mouseup',qaFloatStopResize);
  }
  if(ev.cancelable)ev.preventDefault();
  ev.stopPropagation();   // 缩放优先，别让面板拖拽抢走
}
function qaFloatResize(ev){
  if(!QA_RESIZING)return;
  var pt=ev.touches?ev.touches[0]:ev;
  var o=QA_RESIZING, p=o.el, dx=pt.clientX-o.startX, dy=pt.clientY-o.startY;
  var vw=window.innerWidth, vh=window.innerHeight;
  var w=o.startW, h=o.startH, l=o.startL, t=o.startT;
  if(o.dir.indexOf('e')>=0){w=Math.min(Math.max(o.startW+dx,o.minW),vw-l-8);}
  if(o.dir.indexOf('s')>=0){h=Math.min(Math.max(o.startH+dy,o.minH),vh-t-8);}
  if(o.dir.indexOf('w')>=0){var newW=Math.min(Math.max(o.startW-dx,o.minW),vw-16); l=Math.min(Math.max(o.startL+o.startW-newW,0),o.startL+o.startW-o.minW); w=newW;}
  if(o.dir.indexOf('n')>=0){var newH=Math.min(Math.max(o.startH-dy,o.minH),vh-16); t=Math.min(Math.max(o.startT+o.startH-newH,0),o.startT+o.startH-o.minH); h=newH;}
  p.style.width=w+'px'; p.style.height=h+'px'; p.style.left=l+'px'; p.style.top=t+'px'; p.style.bottom='auto';
  if(ev.cancelable)ev.preventDefault();
}
function qaFloatStopResize(ev){
  if(!QA_RESIZING)return;
  document.removeEventListener('mousemove',qaFloatResize); document.removeEventListener('mouseup',qaFloatStopResize);
  document.removeEventListener('touchmove',qaFloatResize,{passive:false});
  document.removeEventListener('touchend',qaFloatStopResize,{passive:false});
  document.removeEventListener('touchcancel',qaFloatStopResize,{passive:false});
  QA_RESIZING=null; qaFloatSavePos(); qaFloatSaveSize();
}
function qaFloatScroll(){
  var b=document.getElementById('qaFloatBody');if(b)b.scrollTop=b.scrollHeight;
}
// 轻量 Markdown → HTML（仅支持回答常见格式：加粗、列表、标题、代码、引用、链接）
// ===== 2026-09-11：Markdown 表格渲染 =====
// 此前 qaMdRender 完全不认识竖线字符：模型按提示词输出的表格会被渲染成裸竖线
// （竖线拼成的表头 + 分隔行），读者看到的是「格式乱」而不是表格。
// 判定规则收紧为「当前行含竖线 且 下一行是分隔行」，避免把正文里的竖线误判成表格。
function qaMdIsTableSep(l){
  return /^[\s|:-]{3,}$/.test(l) && l.indexOf('-')>=0 && l.indexOf('|')>=0;
}
function qaMdSplitRow(l){
  // 按竖线拆列，但跳过行内代码 <code>…</code> 内的竖线——
  // 否则 `| \`x|y\` | 2 |` 会被拆成 4 列、把 </code> 挤到错误的单元格里。
  var s=String(l).trim().replace(/^\|/,'').replace(/\|$/,'');
  var cells=[],cur='',inCode=false;
  for(var i=0;i<s.length;i++){
    if(s.substr(i,6)==='<code>'){inCode=true;cur+='<code>';i+=5;continue;}
    if(s.substr(i,7)==='</code>'){inCode=false;cur+='</code>';i+=6;continue;}
    if(s.charAt(i)==='|'&&!inCode){cells.push(cur.trim());cur='';continue;}
    cur+=s.charAt(i);
  }
  cells.push(cur.trim());
  return cells;
}
function qaMdTableHtml(rows){
  var head=qaMdSplitRow(rows[0]),al=qaMdSplitRow(rows[1]||'');
  var st=function(a){return /^:-+:$/.test(a)?' style="text-align:center"':(/^-+:$/.test(a)?' style="text-align:right"':'');};
  var h='<div class="qa-table-wrap"><table><thead><tr>';
  head.forEach(function(c,i){h+='<th'+st(al[i]||'')+'>'+c+'</th>';});
  h+='</tr></thead><tbody>';
  for(var r=2;r<rows.length;r++){
    var cells=qaMdSplitRow(rows[r]);
    h+='<tr>';
    for(var j=0;j<head.length;j++){h+='<td'+st(al[j]||'')+'>'+(cells[j]||'')+'</td>';}
    h+='</tr>';
  }
  return h+'</tbody></table></div>';
}
function qaMdRender(md){
  if(!md)return '';
  var text=esc(md).replace(/\r\n/g,'\n');
  var codes=[], placeholders=[];
  text=text.replace(/```([\s\S]*?)```/g,function(m,code){
    var i=codes.length;
    codes.push('<pre><code>'+esc(code.replace(/^```\s*\n?|```$/g,'').replace(/^\n+|\n+$/g,''))+'</code></pre>');
    placeholders.push('__CODE_BLOCK_'+i+'__');
    return placeholders[i];
  });
  text=text.replace(/`([^`]+)`/g,'<code>$1</code>');
  text=text.replace(/^#### (.*$)/gim,'<h4>$1</h4>');
  text=text.replace(/^### (.*$)/gim,'<h3>$1</h3>');
  text=text.replace(/^## (.*$)/gim,'<h2>$1</h2>');
  text=text.replace(/^# (.*$)/gim,'<h1>$1</h1>');
  text=text.replace(/^&gt; (.*$)/gim,'<blockquote>$1</blockquote>');
  text=text.replace(/!\[([^\]]*)\]\(([^)]+)\)/g,function(m,a,u){var s=qaSafeUrl(u);return s?'<img src="'+s+'" alt="'+a+'" style="max-width:100%">':'';});
  text=text.replace(/\[([^\]]+)\]\(([^)]+)\)/g,function(m,t,u){var s=qaSafeUrl(u);if(!s)return t;return '<a href="'+s+'" target="_blank" rel="noopener" onclick="window.open(this.href,\'_blank\',\'noopener,noreferrer\');return false;">'+t+'</a>';});
  text=text.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
  text=text.replace(/__([^_]+)__/g,'<strong>$1</strong>');
  text=text.replace(/\*([^*]+)\*/g,'<em>$1</em>');
  text=text.replace(/_([^_]+)_/g,'<em>$1</em>');
  var lines=text.split('\n');
  var out=[], inList=false, listType='ul';
  function flushList(){if(inList){out.push('</'+listType+'>');inList=false;}}
  for(var li=0;li<lines.length;li++){
    var line=lines[li];
    // 2026-09-11：表格块（表头行 + 分隔行 → <table>）
    if(line.indexOf('|')>=0 && li+1<lines.length && qaMdIsTableSep(lines[li+1])){
      var trows=[];
      var _hc=qaMdSplitRow(lines[li]).length;
      while(li<lines.length && lines[li].trim() && lines[li].indexOf('|')>=0){
        // 单元格数多于表头 ⇒ 多半是紧跟表格的普通句子（含竖线），结束表格交给正文，避免截断丢字
        if(trows.length>=2 && qaMdSplitRow(lines[li]).length>_hc)break;
        trows.push(lines[li]);li++;
      }
      li--;
      flushList();
      out.push('');out.push(qaMdTableHtml(trows));out.push('');
      continue;
    }
    var t=line.trim();
    if(!t){flushList();out.push('');continue;}
    if(/^<(h[1-4]|pre|blockquote|img|div|table)/.test(line)){flushList();out.push(line);continue;}
    if(/^__CODE_BLOCK_/.test(line)){flushList();out.push(line);continue;}
    var ul=line.match(/^[\*\-]\s+(.*)$/);
    var ol=line.match(/^(\d+)\.\s+(.*)$/);
    if(ul){
      if(!inList||listType!=='ul'){flushList();out.push('<ul>');listType='ul';}
      inList=true;out.push('<li>'+ul[1]+'</li>');
    }else if(ol){
      if(!inList||listType!=='ol'){flushList();out.push('<ol>');listType='ol';}
      inList=true;out.push('<li>'+ol[2]+'</li>');
    }else{
      flushList();out.push(line);
    }
  }
  flushList();
  var html=out.join('\n');
  codes.forEach(function(c,i){html=html.replace(placeholders[i],c);});
  return html.split(/\n\n+/).filter(Boolean).map(function(b){
    b=b.trim();
    if(/^<(h[1-4]|pre|blockquote|ul|ol|div|table)/.test(b))return b;
    return '<p>'+b.replace(/\n/g,'<br>')+'</p>';
  }).join('\n');
}
function qaFmtTime(ts){
  try{var d=new Date(Number(ts));var p=function(n){return (n<10?'0':'')+n;};
    return p(d.getMonth()+1)+'-'+p(d.getDate())+' '+p(d.getHours())+':'+p(d.getMinutes());}catch(e){return '';}
}
function qaFloatAdd(role,html,meta,opts){
  opts=opts||{};
  var body=document.getElementById('qaFloatBody');if(!body)return null;
  var d=document.createElement('div');d.className='qa-msg '+role;
  var bubbleHtml='<div class="qa-msg-bubble">'+(opts.md?qaMdRender(html):(opts.html?html:qaEsc(html).replace(/\n/g,'<br>')))+'</div>';
  var actions='';
  if(role==='ai'&&opts.actions!==false){
    actions='<div class="qa-msg-actions">'+
      '<button class="qa-msg-action" type="button" title="复制回答" onclick="qaCopyAi(this)">📋 复制</button>'+
      (opts.canRetry?'<button class="qa-msg-action" type="button" title="重新生成" onclick="qaRetryAi(this)">🔄 重新生成</button>':'')+
      '</div>';
  }
  var m=meta?'<div class="qa-msg-meta">'+qaEsc(meta)+'</div>':'';
  var t=opts.ts?'<div class="qa-msg-time">'+qaFmtTime(opts.ts)+'</div>':'';
  d.innerHTML=bubbleHtml+m+t+actions;
  d.dataset.raw=html||'';
  d.dataset.md=opts.md?'1':'';
  // 2026-09-06 记录渲染格式，历史恢复时按原样渲染（否则检索结果 HTML 会被 md 渲染器转义成裸文本）
  d.dataset.fmt=opts.html?'html':(opts.md?'md':'text');
  if(opts.q)d.dataset.q=opts.q;
  if(opts.ctx)d.dataset.ctx=JSON.stringify(opts.ctx||[]);
  if(opts.ts)d.dataset.ts=String(opts.ts);
  body.appendChild(d);qaFloatScroll();return d;
}
function qaExportHistory(btn){
  try{
    var body=document.getElementById('qaFloatBody');if(!body)return;
    var msgs=body.querySelectorAll('.qa-msg');
    var lines=['=== 矿业新闻日报 · 问答导出 ===','时间：'+new Date().toLocaleString('zh-CN'),''];
    msgs.forEach(function(el){
      var role=el.classList.contains('user')?'【问】':'【答】';
      var raw=el.dataset.raw||'';
      if(raw)lines.push(role+' '+raw.replace(/\n+/g,'\n'));
    });
    var txt=lines.join('\n');
    navigator.clipboard.writeText(txt).then(function(){
      if(btn){btn.textContent='已复制';setTimeout(function(){btn.textContent='📤 导出';},1500);}
    },function(){
      if(btn){btn.textContent='复制失败';setTimeout(function(){btn.textContent='📤 导出';},1500);}
    });
  }catch(e){}
}
// ===== Phase D：语音输入（Web Speech API，不支持的浏览器自动隐藏按钮）=====
var QA_REC=null;
var QA_MIC_ICON='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:block;margin:auto"><rect x="9" y="2" width="6" height="11" rx="3"></rect><path d="M12 18v3"></path><path d="M5 10v2a7 7 0 0 0 14 0v-2"></path></svg>';
function qaGetRec(){return (typeof window!=='undefined')?(window.SpeechRecognition||window.webkitSpeechRecognition||null):null;}
function qaInitMic(){
  var btn=document.getElementById('qaFloatMic');
  if(!btn)return;
  if(!qaGetRec()){btn.style.display='none';return;}
  btn.innerHTML=QA_MIC_ICON;
  btn.addEventListener('click',qaToggleMic);
}
function qaToggleMic(){
  var btn=document.getElementById('qaFloatMic'),inp=document.getElementById('qaFloatInput');
  var SR=qaGetRec();
  if(!SR){if(btn)btn.style.display='none';return;}
  if(QA_REC&&QA_REC.active){try{QA_REC.stop();}catch(e){}return;}
  var rec;
  try{rec=new SR();}catch(e){return;}
  QA_REC=rec;rec.lang='zh-CN';rec.interimResults=true;rec.continuous=false;rec.maxAlternatives=1;
  rec.onresult=function(ev){
    var txt='';
    for(var i=0;i<ev.results.length;i++){txt+=ev.results[i][0].transcript;}
    if(inp)inp.value=txt;
  };
  rec.onerror=function(e){
    if(btn){btn.classList.remove('on');btn.innerHTML=QA_MIC_ICON;}
    QA_REC=null;
    var msg=(e&&e.error==='not-allowed')?'麦克风权限被拒绝':((e&&e.error)||'未知错误');
    qaFloatAdd('ai','🎤 语音识别失败（'+msg+'）。请检查浏览器麦克风权限，或直接在输入框键入。','',{md:false});
  };
  rec.onend=function(){if(btn){btn.classList.remove('on');btn.innerHTML=QA_MIC_ICON;}QA_REC=null;};
  try{rec.start();if(btn){btn.classList.add('on');btn.textContent='⏹';}}catch(e){QA_REC=null;}
}
// ===== Phase E：本地价格快照注入 RAG（AI 可答「铜价 / LME铝」等，无需外部 Key）=====
var QA_METAL_SLUGS={
  '铜':['cum','lcpt'],'铝':['alm','lalt'],'锌':['znm','lznt'],'铅':['pbm','lldt'],
  '镍':['nim','lnkt'],'锡':['snm','ltnt'],'金':['au9999'],'黄金':['au9999'],
  '银':['agtd'],'白银':['agtd'],'锂':['lcm'],'碳酸锂':['lcm']
};
function qaSlugUnit(slug){
  if(/^l(cpt|alt|znt|ldt|nkt|tnt)/.test(slug))return '美元/吨';
  if(slug==='au9999')return '元/克';
  if(slug==='agtd')return '元/千克';
  return '元/吨';
}
function qaPriceBrief(q){
  if(!q)return '';
  var q2=q.replace(/\s/g,'');
  if(!/价|报价|涨跌|行情|LME|期货|美元|吨|走势|多少钱|收报|现价|价格/.test(q2))return '';
  var hits=[];
  for(var name in QA_METAL_SLUGS){ if(q2.indexOf(name)>=0)hits.push(name); }
  if(!hits.length)return '';
  var H=(typeof window!=='undefined'&&window.PRICE_HISTORY)?window.PRICE_HISTORY:null;
  var D=(typeof window!=='undefined'&&window.LME_DATA)?window.LME_DATA:null;
  var Dmap={};
  if(D&&D.metals)D.metals.forEach(function(m){Dmap[m.slug]=m;});
  var lines=[],seen={};
  hits.forEach(function(name){
    QA_METAL_SLUGS[name].forEach(function(slug){
      if(seen[slug])return;seen[slug]=1;
      var info=null;
      if(Dmap[slug]){var m=Dmap[slug];
        info={label:m.name,val:m.price,chg:m.chg,chg_pct:m.chg_pct,unit:m.unit||qaSlugUnit(slug)};
      }else if(H&&H.series&&H.series[slug]&&H.series[slug].points&&H.series[slug].points.length){
        var pts=H.series[slug].points,n=pts.length,last=pts[n-1],prev=pts[n-2];
        var val=last[1],date=last[0],chg=(n>1&&typeof prev[1]==='number')?(val-prev[1]):null;
        info={label:H.series[slug].name,val:val,chg:chg,chg_pct:(chg!=null&&prev[1])?chg/prev[1]*100:null,unit:qaSlugUnit(slug),date:date};
      }
      if(info){
        var s=info.label+'：'+(typeof info.val==='number'?info.val.toLocaleString('en-US'):info.val)+' '+info.unit;
        if(info.date)s+='（'+info.date+'）';
        if(info.chg!=null&&typeof info.chg==='number'){
          var sign=info.chg>=0?'+':'';
          s+='，日涨跌 '+sign+info.chg.toFixed(2)+(info.chg_pct!=null?('（'+sign+info.chg_pct.toFixed(2)+'%）'):'');
        }
        lines.push(s);
      }
    });
  });
  return lines.join('\n');
}
function qaFloatSearch(){
  var inp=document.getElementById('qaFloatInput');if(!inp)return;
  var q=(inp.value||'').trim();
  var mineral=(document.getElementById('qaFloatMineral')||{}).value||'';
  var topic=(document.getElementById('qaFloatTopic')||{}).value||'';
  var range=parseInt((document.getElementById('qaFloatRange')||{}).value,10)||0;
  if(q){qaFloatAdd('user',q,'',{md:false});inp.value='';}
  if(!q&&!mineral&&!topic&&!range){
    // 未输入条件时不弹提示词式消息，静默返回即可
    return;
  }
  var words=q?q.split(/\s+/).filter(Boolean):[],from='';
  if(range>0){
    var max='';QA_ROWS.forEach(function(r){if(r.d&&r.d>max)max=r.d;});
    if(max){var dt=new Date(max+'T00:00:00');dt.setDate(dt.getDate()-range+1);from=dt.toISOString().slice(0,10);}
  }
  var hits=qaFilter(QA_ROWS,words,mineral,topic,from,'and'),relaxed=false;
  if(!hits.length&&words.length>1){hits=qaFilter(QA_ROWS,words,mineral,topic,from,'or');relaxed=true;}
  var html='';
  if(!hits.length){
    var sugg=qaSuggestChips(words);
    html='<div>全库未检索到匹配内容。<b>这不等于「没有发生」</b>——本库由日报每日追加，存在抓取缺口。</div>';
    if(sugg)html+='<div class="qa-sug-row">建议减少关键词，或试试：'+sugg+'</div>';
  }else{
    var cond=[];
    if(words.length)cond.push('关键词「'+qaEsc(q)+'」'+(relaxed?'（已放宽为任一词）':'（同时含）'));
    if(mineral)cond.push('矿种='+qaEsc(mineral));
    if(topic)cond.push('主题='+qaEsc(topic));
    if(from)cond.push(from+' 起');
    // 按相关度重排（仅当用户输入了关键词；仅有筛选条件时保持原顺序）
    if(q)hits=qaRankByRelevance(q,hits);
    html='<div>找到 <b>'+hits.length+'</b> 条相关新闻'+(cond.length?' · '+cond.join(' · '):'')+(q?'（按相关度排序）':'')+'：</div>';
    if(QA_TREND)html+='<div class="qa-trend">'+qaEsc(qaTrendText(hits))+'</div>';
    // 渲染全部命中结果（qa-float-body 可滚动）；设 100 条安全上限防止极端关键词
    var lim=Math.min(hits.length,100);
    for(var i=0;i<lim;i++){
      var r=hits[i];
      var snip=qaSnippet(r.m);
      html+='<a class="qa-msg-item" href="'+qaEsc(r.u)+'" target="_blank" rel="noopener">'+
        '<span class="qd">'+qaEsc(r.d||'????-??-??')+'</span>'+
        '<span class="qt">'+qaHi(r.t,words)+'</span>'+
        (snip?'<span class="qm">'+qaHi(snip,words)+'</span>':'')+
        '<span class="qs">'+qaEsc(r.s||'')+'</span></a>';
    }
    if(hits.length>lim)html+='<div style="margin-top:4px;color:#6b7a89">为防列表过长，仅显示前 '+lim+' 条；共 '+hits.length+' 条命中，请缩小关键词 / 矿种 / 时间范围查看其余。</div>';
  }
  qaFloatAdd('ai',html,'全库 '+QA_ROWS.length+' 条 · 检索于本地，不经任何服务',{html:true});
  qaSaveHistory();
}
// 0 结果时的兜底建议：推荐与 query 字符相近的矿种/主题，点击直接套用筛选重搜
function qaSuggestChips(words){
  var pool=QA_MINERALS.concat(QA_TOPICS);
  var near=[];
  (words||[]).forEach(function(w){
    pool.forEach(function(p){
      if(p!==w&&(p.indexOf(w)>=0||w.indexOf(p)>=0)&&near.indexOf(p)<0)near.push(p);
    });
  });
  var list=near.length?near.slice(0,8):QA_MINERALS.slice(0,8);
  return list.map(function(p){
    return '<span class="qa-sug" role="button" tabindex="0" onclick="qaSugPick(\''+qaEsc(p)+'\')">'+qaEsc(p)+'</span>';
  }).join('');
}
function qaSugPick(m){
  var sel=document.getElementById('qaFloatMineral');
  if(sel)sel.value=m;
  qaFloatSearch();
}
var QA_AI_FALLBACK=[
  [['铜','Cu'],'铜（Cu）是有色金属中的重要品种，广泛应用于电力、建筑、交通等领域。'],
  [['铝','Al','铝土矿'],'铝（Al）具有轻质、耐腐蚀等特性，广泛应用于航空航天、汽车制造、包装容器等领域。中国铝土矿资源对外依存度较高，广西、河南、贵州、山西是主要产区。'],
  [['锌','Zn'],'锌（Zn）主要用于镀锌钢板、合金制造和电池。'],
  [['铅','Pb'],'铅（Pb）主要用于铅酸蓄电池、辐射防护材料。'],
  [['镍','Ni'],'镍（Ni）是不锈钢和动力电池的关键金属，新能源车带动需求快速增长。'],
  [['锡','Sn'],'锡（Sn）主要用于焊锡和电子封装，半导体景气度直接影响其需求。'],
  [['锂','Li'],'锂（Li）被称为"白色石油"，是新能源动力电池的核心原材料。中国是全球最大锂消费国。'],
  [['稀土'],'稀土是 17 种金属元素的统称，中国是全球最大的稀土生产国和供应国。'],
  [['金','黄金'],'黄金兼具商品、货币、避险三重属性，央行购金、地缘冲突是金价的核心驱动。'],
  [['铁矿','铁矿石'],'铁矿石是钢铁工业的核心原料，中国是全球最大进口国，对外依存度高。'],
  [['新一轮','找矿','突破','战略'],'新一轮找矿突破战略行动已取得阶段性成果：铜、铝、锂、钴、镍等关键矿产新增资源量稳步提升。'],
  [['关键矿产','战略性矿产'],'关键矿产对国家经济安全和国防至关重要，中国"十四五"明确将 24 种矿产列为战略性矿产。'],
  [['勘查','勘探'],'矿产勘查分为预查、普查、详查、勘探 4 个阶段，铝土矿等矿种勘查深度按 DZ/T 0202-2020 等规范执行。'],
  [['矿权','采矿权','探矿权'],'矿业权包括探矿权和采矿权，出让方式分招拍挂与协议出让。'],
  [['DZ/T','规范','标准'],'地质矿产领域现行重要标准：DZ/T 0202-2020（铝土矿）、DZ/T 0204-2020（铜铅锌银）、DZ/T 0205-2020（稀有金属）等。'],
];
function qaAiLocalAnswer(q,ctx){
  var text='';
  // 1) 若有相关新闻，基于新闻生成摘要
  if(ctx&&ctx.length){
    var byDate=ctx.slice(0,5);
    text='根据本地新闻库中 '+ctx.length+' 条相关条目，整理要点如下：\n\n';
    var pts=[];
    byDate.forEach(function(r,i){
      pts.push((i+1)+'. ['+(r.d||'')+'] '+(r.t||'')+(r.s?'（'+r.s+'）':''));
    });
    text+=pts.join('\n')+'\n\n';
  }
  // 2) 关键词兜底
  for(var i=0;i<QA_AI_FALLBACK.length;i++){
    var kws=QA_AI_FALLBACK[i][0],ans=QA_AI_FALLBACK[i][1];
    for(var j=0;j<kws.length;j++){
      if(q.indexOf(kws[j])>=0){text+=ans;break;}
    }
  }
  if(!text){
    text='关于「'+q+'」，本地暂未匹配到精确答案。可尝试关键词：铜/铝/锌/铅/镍/锡/锂/稀土/找矿/矿权。';
  }
  return text;
}
function qaFloatAsk(retryMode,ctxOverride){
  if(QA_FLOAT_BUSY)return;
  var inp=document.getElementById('qaFloatInput'),btn=document.getElementById('qaFloatAi');
  var q=inp?(inp.value||'').trim():'';
  if(!q){qaFloatAdd('ai','请先输入问题，例如「最近有哪些稀土政策」「锂价为什么大跌」。','',{md:false});return;}
  QA_FLOAT_BUSY=true;
  if(btn){btn.disabled=true;btn.textContent='思考中…';}
  if(!retryMode){qaFloatAdd('user',q,'',{md:false,ts:Date.now()});qaSaveHistory();}
  if(inp)inp.value='';
  var _ctx=ctxOverride;
  var _dateIntent=qaDetectDateIntent(q);
  // 2026-09-11：问题里写了相对时间窗（近三天/近一周/本周…）时，以问题为准
  var _rangeIntent=_dateIntent?null:qaDetectRangeIntent(q);
  if(!_ctx){
    var _min=(document.getElementById('qaFloatMineral')||{}).value||'';
    var _top=(document.getElementById('qaFloatTopic')||{}).value||'';
    var _rg=parseInt((document.getElementById('qaFloatRange')||{}).value,10)||0;
    var _ext=qaExtractTerms(q);
    var _minSel=_ext.filter(function(t){return QA_MINERALS.indexOf(t)>=0;})[0]||'';
    var _topSel=_ext.filter(function(t){return QA_TOPICS.indexOf(t)>=0;})[0]||'';
    var _from='';
    if(_dateIntent){
      // 日期意图：只看当天（或最近 1 天）新闻，避免滚动到历史条目
      _from=_dateIntent;
      _rg=0;
    }else{
      var _max='';QA_ROWS.forEach(function(r){if(r.d&&r.d>_max)_max=r.d;});
      if(_rangeIntent)_rg=qaRangeDays(_rangeIntent,_max);
      if(_rg>0&&_max){_from=qaShiftDate(_max,_rg-1);}
    }
    var _filtered=qaFilter(QA_ROWS,[],_minSel||_min,_topSel||_top,_from,'and');
    // 日期意图：不过度依赖相关性排序，直接按日期降序取当天前 15 条
    _ctx=_dateIntent?_filtered.slice(0,15):qaRankByRelevance(q,_filtered).slice(0,20);
  }
  // 2026-09-06：传给 AI 前先按相关性阈值过滤，避免 AI 正文混入无关条目
  // 日期意图：跳过通用阈值过滤，直接保留当天条目（已按日期严格过滤）
  _ctx=_dateIntent?_ctx:qaFilterRelevant(_ctx,q);
  // 2026-09-06 晚：多轮追问上下文 + 宽泛问题引导标记（B / C）
  // 日期意图：不使用历史 conv，避免「紫金矿业」等前序追问污染当前「今天新增」理解
  var _conv=_dateIntent?[]:qaBuildConv();
  var _broad=_dateIntent?false:qaIsBroadQuery(q);
  // 2026-09-11 P1：答案缓存（同机稳定复现；数据版本变化自动失效）；retryMode / ctxOverride 不走缓存
  _qaCacheKey=(!retryMode && !ctxOverride)?qaCacheKey(q,_minSel||_min,_topSel||_top,_from,_rg,_dateIntent):'';
  if(_qaCacheKey && !retryMode){
    var _hit=qaCacheGet(_qaCacheKey);
    if(_hit){
      var msg=qaFloatAdd('ai','（命中本地答案缓存，正在渲染…）','答案缓存命中',{md:false,actions:false,ts:Date.now()});
      _qaPath='缓存';_qaModel='deepseek-chat';_qaT0=Date.now();
      qaFinishAnswer(_hit.text,msg.querySelector('.qa-msg-bubble'),msg,q,_hit.ctx||_ctx,_hit.dateIntent||_dateIntent);
      QA_FLOAT_BUSY=false; if(btn){btn.disabled=false;btn.textContent='✨ AI 回答';}
      return;
    }
  }
  _qaCacheKey=_qaCacheKey||qaCacheKey(q,_minSel||_min,_topSel||_top,_from,_rg,_dateIntent);
  var meta='正在从全库 '+QA_ROWS.length+' 条新闻中检索相关条目并组织答案，请稍候…';
  var msg=qaFloatAdd('ai','正在从全库 '+QA_ROWS.length+' 条新闻中检索相关条目并组织答案，请稍候（通常 10~30 秒）…',meta,{md:false,actions:false,ts:Date.now()});
  qaDeepseekCall(q,_ctx,msg,btn,_conv,_broad,_dateIntent,_rangeIntent);
  return;
}
// 安全清洗外链：只允许 http/https，拦截 javascript:/data:/vbscript: 等危险协议，并转义引号
function qaSafeUrl(u){
  if(!u)return '';
  u=String(u).trim();
  if(/^\s*(javascript|data|vbscript):/i.test(u))return '';
  if(/^https?:\/\//i.test(u))return u.replace(/"/g,'%22');
  return '';
}
// 按相关性阈值过滤条目，用于传给 AI 的上下文和底部参考来源（避免混入低相关条目）
function qaFilterRelevant(ctx,q){
  if(!ctx||!ctx.length)return [];
  var scores=ctx.map(function(c){return c._score||0;});
  var maxScore=Math.max.apply(null,scores);
  var threshold=Math.max(6, maxScore*0.6);
  var relevant=ctx.filter(function(c){return (c._score||0)>=threshold;});
  // 兜底 1：若强相关不足 3 条，放宽到 score>=6 的前 10 条
  if(relevant.length<3){
    relevant=ctx.filter(function(c){return (c._score||0)>=6;}).slice(0,10);
  }
  // 兜底 2：仍不足 3 条，则取 score>0 的前 10 条
  if(relevant.length<3){
    relevant=ctx.filter(function(c){return (c._score||0)>0;}).slice(0,10);
  }
  return relevant.slice(0,10);
}
// 2026-09-06 晚（B）：从对话浮窗 DOM 还原最近的多轮上下文，供 AI 追问时连贯作答。
// 规则：取最近若干条 user/assistant 消息；去掉末尾的 user 消息（即本次正在问的问题，
// 稍后会作为带资料的最终 user 消息单独发送），只保留最近 4 条（2 轮）。
function qaBuildConv(){
  var body=document.getElementById('qaFloatBody');if(!body)return [];
  var msgs=body.querySelectorAll('.qa-msg');
  var turns=[];
  msgs.forEach(function(el){
    if(!el.classList.contains('user')&&!el.classList.contains('ai'))return;
    var role=el.classList.contains('user')?'user':'assistant';
    var raw=el.dataset.raw||'';
    if(!raw)return;
    // 跳过「正在检索…」这类临时占位（一般已替换，但保险起见）
    if(/^正在从全库.*检索相关条目/.test(raw))return;
    turns.push({role:role,content:raw});
  });
  // 去掉末尾的 user 消息（本次问题），保留历史轮次
  while(turns.length && turns[turns.length-1].role==='user') turns.pop();
  if(turns.length>4) turns=turns.slice(turns.length-4);
  return turns;
}
// 2026-09-06 晚（C）：判断问题是否过于宽泛（如「最近有什么新闻」），需先引导筛选再给概览。
// 2026-09-07：识别用户想直接看「今天/今日/最新新增新闻」的查询，
// 命中时按日期过滤当天条目，不走通用 RAG 与多轮上下文（避免历史追问污染）。
function qaDetectDateIntent(q){
  if(!q)return null;
  var q2=q.replace(/\s/g,'');
  var todayRe=/^(今天|今日|本日)(新[增加]|有|出|更|发布|更新)?(的|了|些|啥|什么)?(新[增加]|新闻|消息|动态|资讯|报道|内容|条目|信息)?$/;
  var latestRe=/^(最新|最近)(新[增加]|新闻|消息|动态|资讯|报道|内容|条目|信息)$/;
  var showTodayRe=/^(看看|给我|列出|显示|总结|概括|汇总|整理|归纳)?(今天|今日|本日|最新|最近)?(新[增加]|新闻|消息|动态|资讯|报道|内容|条目|信息)$/;
  if(todayRe.test(q2)||latestRe.test(q2)||showTodayRe.test(q2)){
    var anchor=qaReportDate();
    return anchor;
  }
  return null;
}
// 2026-09-11：相对时间窗解析（近N天/近N日/近N周/近N个月 + 本周/本月）。
// 此前只识别「今天/最新」，用户问「近三天矿权交易」会被当成普通检索 →
// 走全库相关性 Top-20 → 标题里的时间窗是模型自己写的，两台电脑结果不一致。
function qaDetectRangeIntent(q){
  if(!q)return null;
  var q2=q.replace(/\s/g,'');
  if(/(本|这|当)周/.test(q2))return {week:true,label:'本周'};
  if(/(本|这|当)(个)?月/.test(q2))return {month:true,label:'本月'};
  var m=q2.match(/(近|最近|过去|前)([0-9]{1,3}|[一二两三四五六七八九十]+)(天|日|周|星期|个月|月)/);
  if(!m)return null;
  var raw=m[2],n=0;
  if(/^[0-9]+$/.test(raw)){n=parseInt(raw,10);}
  else{
    var D={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9};
    if(raw==='十'){n=10;}
    else if(raw.charAt(0)==='十'){n=10+(D[raw.charAt(1)]||0);}
    else if(raw.charAt(raw.length-1)==='十'){n=(D[raw.charAt(0)]||0)*10;}
    else if(raw.length===2){n=(D[raw.charAt(0)]||0)*10+(D[raw.charAt(1)]||0);}
    else{n=D[raw]||0;}
  }
  if(!n||n<1||n>90)return null;
  var unit=m[3];
  var days=(unit==='周'||unit==='星期')?n*7:((unit==='个月'||unit==='月')?n*30:n);
  return {days:days,n:n,unit:unit,label:'近'+raw+unit};
}
// 日期回退：一律用本地日期字段拼字符串，绝不用 toISOString()——
// 后者会把 '2026-09-11T00:00:00'（本地 UTC+8）序列化成 '2026-09-10T16:00:00Z'，
// slice(0,10) 得到 09-10，「近 N 天」实际多算一天（2026-09-11 实测）。
function qaShiftDate(ymd,minusDays){
  var d=new Date(ymd+'T12:00:00');
  if(isNaN(d.getTime()))return '';
  d.setDate(d.getDate()-minusDays);
  var p=function(n){return (n<10?'0':'')+n;};
  return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate());
}
// 把「本周/本月」换算成天数（锚点用数据最新日期，不依赖客户端时钟）
function qaRangeDays(ri,maxDate){
  if(!ri)return 0;
  if(ri.days)return ri.days;
  if(!maxDate)return 0;
  var d=new Date(maxDate+'T12:00:00');
  if(isNaN(d.getTime()))return 0;
  if(ri.week)return ((d.getDay()+6)%7)+1;
  if(ri.month)return d.getDate();
  return 0;
}
function qaIsBroadQuery(q){
  if(!q)return false;
  var q2=q.replace(/\s/g,'');
  var hasEntity=(qaExtractTerms(q).length>0)
    || /紫金|中铝|洛钼|洛阳钼业|山东黄金|江西铜业|中国铝业|五矿|必和必拓|力拓|淡水河谷|嘉能可|西部矿业|铜陵有色|云南铜业|神火|天山铝业/.test(q);
  if(q2.length<=5 && !hasEntity) return true;
  // 形如「最近/近期/最新 +（有/啥/什么/哪些） + 新闻/动态/消息/资讯/报道/情况/进展/热点」
  if(/^(最近|近期|最新|这两天|这几天|今天|本周|本月|今年以来|今年)?(有|有啥|有什么|有哪|啥|什么|哪些|哪些方面的|关于)?(新闻|消息|动态|资讯|报道|热点|情况|进展|更新|内容|信息)$/.test(q2)) return true;
  if(/^(新闻|消息|动态|资讯|报道|热点|情况|进展|更新|内容|信息)$/.test(q2) && !hasEntity) return true;
  return false;
}
// AI 回答下方自动附「参考来源」可点击列表，按相关性梯度过滤，避免混入低相关条目
// 2026-09-06 晚（D）：按板块（c.s）分组展示，扫读更快
function qaDsSourcesHtml(ctx,q){
  var relevant=qaFilterRelevant(ctx,q);
  // 2026-09-06 晚：按 URL 去重，避免同一链接跨板块重复出现
  var _seen={},_rel2=[];
  relevant.forEach(function(c){var u=c.u||c.url||'';if(u){if(_seen[u])return;_seen[u]=1;} _rel2.push(c);});
  relevant=_rel2;
  var liOf=function(c){
    var u=c.u||c.url||'',t=c.t||'新闻';
    if(!u)return '';
    var safe=qaSafeUrl(u);if(!safe)return '';
    // 2026-09-06：去掉原内联 onclick 直接 window.open 的写法，统一走全局点击委托分流
    //（允许嵌入的站内浮窗打开；禁止嵌入的弹提示引导跳原站）
    return '<li><a href="'+safe+'" target="_blank" rel="noopener">'+qaEsc(t)+'</a>'+(c.d?' <span class="qa-src-date">'+qaEsc(c.d)+'</span>':'');
  };
  if(!relevant.length)return '';
  // 按板块分组（保持首次出现顺序 ≈ 相关性/时效序），组内按日期倒序
  var groups={},order=[];
  relevant.forEach(function(c){
    var g=c.s||'其他';
    if(!groups[g]){groups[g]=[];order.push(g);}
    groups[g].push(c);
  });
  var countHtml='<span class="qa-sources-count">已为您从全库中筛选出 <b>'+Math.min(relevant.length,10)+'</b> 条相关条目</span>';
  var html='<div class="qa-msg-sources"><div class="qa-sources-title">📚 参考来源（点击查看原文）</div>'+countHtml;
  order.forEach(function(g){
    var items=groups[g].map(liOf).filter(Boolean);
    if(!items.length)return;
    html+='<div class="qa-src-group"><div class="qa-src-group-title">'+qaEsc(g)+'</div><ul>'+items.join('')+'</ul></div>';
  });
  html+='</div>';
  return html;
}
// ===== Phase C：追问建议 + 内联引用 =====
// 把 AI 正文里的「（媒体，日期）」解析为可点链接，跳到对应来源（基于 ctx 的 媒体+日期->url 映射）
function qaInlineRefs(html,ctx){
  if(!ctx||!ctx.length)return html;
  var map={};
  ctx.forEach(function(c){
    var s=(c.s||'').trim(),d=(c.d||''),u=c.u||c.url||'';
    if(!u||!d)return;
    if(s)map[(s+'|'+d).toLowerCase()]=u;
  });
  if(!Object.keys(map).length)return html;
  return html.replace(/（([^，（）]+?)，\s*(\d{4}-\d{2}-\d{2})）|\(([^，()]+?),\s*(\d{4}-\d{2}-\d{2})\)/g,function(m,zm,zd,em,ed){
    var media=(zm||em||'').trim(),date=(zd||ed||'');
    if(!media||!date)return m;
    var u=map[(media+'|'+date).toLowerCase()];
    if(!u){
      for(var k in map){var p=k.split('|');if(p[1]===date&&(p[0].indexOf(media)>=0||media.indexOf(p[0])>=0)){u=map[k];break;}}
    }
    if(!u)return m;
    var safe=qaSafeUrl(u);if(!safe)return m;
    return '<a class="qa-inref" href="'+safe+'" target="_blank" rel="noopener" title="查看来源：'+qaEsc(media)+' '+date+'">'+m+'</a>';
  });
}
// 基于问题/上下文生成 2~3 个可点追问
function qaFollowUps(q,ctx){
  var ups=[];
  var _row={g:[''],t:q,m:q,s:q,c:q};
  var m=QA_MINERALS.filter(function(x){return qaMineralHit(_row,x)||q.indexOf(x)>=0;})[0];
  var t=QA_TOPICS.filter(function(x){return q.indexOf(x)>=0;})[0];
  if(m){ups.push(m+'最新价格走势');ups.push(m+'近期重大并购');ups.push(m+'勘查突破进展');}
  if(t)ups.push(t+'相关政策梳理');
  ups.push('今日新增了哪些矿业新闻');
  ups.push('最近一周矿业热点');
  var seen={},out=[];
  ups.forEach(function(u){if(!seen[u]){seen[u]=1;out.push(u);}});
  return out.slice(0,3);
}
function qaAppendFollowUps(msg,ups){
  if(!msg||!ups||!ups.length)return;
  if(msg.querySelector('.qa-followups'))return;
  var html='<div class="qa-followups"><span class="qa-fu-label">继续追问 ▸</span>'+
    ups.map(function(u){return '<button class="qa-fu-chip" type="button" onclick="qaFollowAsk(this)">'+qaEsc(u)+'</button>';}).join('')+'</div>';
  msg.insertAdjacentHTML('beforeend',html);
}
function qaFollowAsk(btn){
  var inp=document.getElementById('qaFloatInput');
  if(inp)inp.value=(btn.textContent||'').trim();
  qaFloatAsk();
}
// ===== Phase B：AI 流式输出（SSE 边收边渲染，向后兼容非流式）=====
// 统一收尾：内联引用 + 参考来源 + meta + dataset + 追问 chips + 复制/重试按钮
function qaFinishAnswer(text,bubble,msg,q,ctx,ok,dateIntent){
  if(bubble)bubble.innerHTML=qaInlineRefs(qaMdRender(text),ctx);
  var src=qaDsSourcesHtml(ctx,q);
  if(src&&bubble)bubble.insertAdjacentHTML('afterend',src);
  if(msg){
    var _ms=_qaT0?((Date.now()-_qaT0)/1000).toFixed(1):'';
    var meta=ok
      ? ('DeepSeek · 通路='+(_qaPath||'代理')+' · 模型='+(_qaModel||'deepseek-chat')+(_ms?(' · 用时 '+_ms+'s'):'')+' · 已参考 '+(ctx?ctx.length:0)+' 条'+(dateIntent?(' '+dateIntent+' 本地新闻'):' 相关本地新闻'))
      : ('本地知识库兜底 · 通路='+(_qaPath||'本地兜底')+(_ms?(' · 用时 '+_ms+'s'):'')+' · 全库 '+QA_ROWS.length+' 条');
    var mm=msg.querySelector('.qa-msg-meta');if(mm)mm.textContent=meta;
    msg.dataset.raw=text;msg.dataset.md='1';msg.dataset.fmt='md';msg.dataset.q=q;msg.dataset.ctx=JSON.stringify(ctx||[]);qaAppendFollowUps(msg,qaFollowUps(q,ctx));
    var actions='<div class="qa-msg-actions">'+
      '<button class="qa-msg-action" type="button" title="复制回答" onclick="qaCopyAi(this)">📋 复制</button>'+
      (ok?'<button class="qa-msg-action" type="button" title="重新生成" onclick="qaRetryAi(this)">🔄 重新生成</button>':'')+
      '</div>';
    if(!msg.querySelector('.qa-msg-actions')){
      var metaEl=msg.querySelector('.qa-msg-meta');
      if(metaEl)metaEl.insertAdjacentHTML('afterend',actions);
      else msg.insertAdjacentHTML('beforeend',actions);
    }
  }
  if(ok && _qaCacheKey){ qaCachePut(_qaCacheKey,{text:text,ctx:ctx||[],dateIntent:dateIntent,u:QA_UPDATED||''}); }
  qaFloatScroll();qaSaveHistory();
}
// 代理模式下：优先尝试 SSE 流式；若边缘函数尚未启用流式（返回 JSON），自动回退 JSON 解析
function qaTryStreamOrJson(url,headers,body,bubble,msg,q,ctx,dateIntent,ac,to,btn){
  fetch(url,{method:'POST',headers:headers,body:body,signal:ac.signal})
    .then(function(r){
      var ct=(r.headers&&r.headers.get)?r.headers.get('content-type'):'';
      if(/text\/event-stream/.test(ct) && r.body){
        qaStreamPump(r,bubble,msg,q,ctx,dateIntent,ac,to,btn);
        return;
      }
      return r.json().then(function(d){return {ok:r.ok,status:r.status,d:d||{}};},function(){return {ok:false,status:0,d:{}};})
        .then(function(res){ qaApplyJson(res,bubble,msg,q,ctx,dateIntent); });
    })
    .catch(function(e){
      var la=qaAiLocalAnswer(q,ctx);
      var why=(e&&e.name==='AbortError')?'响应超时（>35s）':((e&&e.message)||e||'网络错误');
      _qaPath='本地兜底';
      qaFinishAnswer(la+'\n\n[DeepSeek 调用失败（'+why+'），已切换本地知识库回答]',bubble,msg,q,ctx,false,dateIntent);
      clearTimeout(to);QA_FLOAT_BUSY=false;if(btn){btn.disabled=false;btn.textContent='✨ AI 回答';}
    });
}
// 解析非流式 JSON 响应（含 401/错误文案），与流式共用 qaFinishAnswer
function qaApplyJson(res,bubble,msg,q,ctx,dateIntent){
  var d=res.d,text='',ok=false;
  if(!res.ok){
    var em=(d&&d.error&&d.error.message)||'请求失败，请稍后重试。';
    if(res.status===401||/authentication|invalid.*key|api key/i.test(em)){
      text='⚠️ **API Key 已失效或被吊销**，AI 暂时无法回答。\n\n请联系网页维护者更新 DeepSeek API Key 后重试；你也可以切换到「检索」面板直接查看本地新闻。';
    }else{
      text='DeepSeek 调用失败：'+em+'\n\n可点「🔄 重新生成」重试，或切换到「检索」面板查看本地新闻。';
    }
  }else{
    var content=((((d.choices||[])[0]||{}).message||{}).content||'').trim();
    if(!content){text='模型未返回内容';}else{text=content;ok=true;}
  }
  qaFinishAnswer(text,bubble,msg,q,ctx,ok,dateIntent);
}
// 读取 SSE 流，逐 token 渲染；结束再做一次内联引用终处理
function qaStreamPump(r,bubble,msg,q,ctx,dateIntent,ac,to,btn){
  var acc='';
  var reader=r.body.getReader(),dec=new TextDecoder('utf-8'),buf='';
  function finish(text,ok){
    clearTimeout(to);QA_FLOAT_BUSY=false;if(btn){btn.disabled=false;btn.textContent='✨ AI 回答';}
    qaFinishAnswer(text,bubble,msg,q,ctx,ok,dateIntent);
  }
  function pump(){
    return reader.read().then(function(res){
      if(res.done)return;
      buf+=dec.decode(res.value,{stream:true});
      var idx;
      while((idx=buf.indexOf('\n\n'))>=0){
        var evt=buf.slice(0,idx);buf=buf.slice(idx+2);
        var line=evt.split('\n').filter(function(l){return l.indexOf('data:')===0;})[0];
        if(!line)continue;
        var payload=line.slice(5).trim();
        if(payload==='[DONE]')continue;
        try{
          var j=JSON.parse(payload);
          var c=(j.choices&&j.choices[0]&&j.choices[0].delta&&j.choices[0].delta.content)||j.content||'';
          if(c){acc+=c;if(bubble)bubble.innerHTML=qaMdRender(acc);}
        }catch(e){}
      }
      return pump();
    });
  }
  pump().then(function(){
    if(bubble)bubble.innerHTML=qaInlineRefs(qaMdRender(acc),ctx);
    finish(acc||'(模型未返回内容)',!!acc);
  }).catch(function(e){
    var why=(e&&e.name==='AbortError')?'响应超时（>35s）':((e&&e.message)||'网络错误');
    if(acc){ if(bubble)bubble.innerHTML=qaInlineRefs(qaMdRender(acc),ctx); finish(acc,true); }
    else{ _qaPath='本地兜底'; var la=qaAiLocalAnswer(q,ctx); finish(la+'\n\n[DeepSeek 流式调用失败（'+why+'），已切换本地知识库回答]',false); }
  });
}
// 2026-09-11 P1：回答元信息（通路 / 模型 / 用时），供 meta 行展示，使「同问题不同答案」可被解释
var _qaPath='',_qaModel='',_qaT0=0,_qaCacheKey='';
function qaDeepseekCall(q,ctxRaw,msg,btn,conv,broad,dateIntent,rangeIntent){
  // 2026-09-06：AI 上下文再次按相关性阈值过滤，确保正文和参考来源只出现强相关内容
  // 日期意图：已在 qaFloatAsk 中按日期严格过滤，不再做通用相关性过滤，避免误删当天条目
  var ctx=dateIntent?(ctxRaw||[]):qaFilterRelevant(ctxRaw||[],q);
  var bubble=msg?msg.querySelector('.qa-msg-bubble'):null;
  // 2026-09-11：把「本次条目实际日期范围」明确交给模型，禁止它自己编时间窗
  var _dsDates=(ctx||[]).map(function(c){return c&&c.d;}).filter(Boolean).sort();
  var _dsWin=_dsDates.length?(_dsDates[0]+' 至 '+_dsDates[_dsDates.length-1]):'';
  var system=('你是资深矿业行业分析师，服务于「矿业新闻日报」产品。'
    +'回答用中文、简洁专业、结构化呈现（优先用要点列表或小标题，避免一大段文字）。'
    +'若提供了相关新闻条目，请先对这些条目进行系统整理和归纳，再按主题/维度给出综合性回答；不要简单逐条复述每条新闻的标题或全文。'
    +'请严格只基于这些条目作答；不要引用、不要列出任何与问题无直接关联的条目；若条目与问题关联度不足，直接忽略即可，不要在回答正文中以"补充说明""其余条目""其他新闻"等形式解释为何无关。'
    +'引用具体新闻时，请在相关结论后用括号标注来源媒体与发布日期（如"（全球矿产资源网，2026-09-04）"），便于与底部参考来源对照；不要在回答正文中插入 Markdown 链接——系统会自动在回答底部列出可点击的参考来源。'
    +'若提供的条目均与问题无关或没有提供相关新闻，请明确说明"本地新闻库暂未找到直接相关的报道"，并建议用户换关键词或查证官方信息；不要基于通用知识编造具体数据、价格或政策细节。'
    +'不要编造数据、价格或政策细节；不要复制"以上信息来自公开公告"之类的注水结语。');
  // 2026-09-06 晚（C）：宽泛问题先提示可按矿种/主题/时间筛选，再按板块给概览
  if(broad){
    system+='\n\n若用户问题较宽泛（例如"最近有什么新闻"），请先一句话提示"可按矿种 / 主题 / 时间筛选以获得更精准结果"，再按板块（行情 / 政策与产业 / 勘查与技术 / 矿权市场 / 风险提示）给出近期概览，用分组要点呈现，不要逐条罗列全部新闻。';
  }
  // 2026-09-07：日期意图（如"今天新增内容"）直接按日期过滤，不关联前序上下文
  if(dateIntent){
    system+='\n\n用户问题明确指向「'+dateIntent+' 当日新增新闻」。请只基于提供的当日条目作答：先一句话总述今日新增条数与主要板块分布，再按板块/主题分组总结要点；不要引入前序对话中的任何实体（如紫金矿业），不要回答与今日条目无关的内容。若当日无新增条目，请明确说明"本地新闻库显示 '+dateIntent+' 暂无新增报道"。';
  }
  // 2026-09-09 Phase E：价格快照注入提示
  system+='\n若问题涉及具体金属价格，且用户消息中提供了「本地价格快照」，请基于快照作答并标注数据日期与单位，说明这是日报本地快照（非实时行情）；不要编造快照之外的价格。';
  // 2026-09-06 晚（B）：多轮追问——把历史轮次作为前置对话，使追问能理解"它""这家"等指代
  // 2026-09-11：格式契约 + 时间窗硬约束（此前格式随采样漂移、标题里的时间窗由模型自编）
  system+='\n\n【输出格式（硬性要求）】'
    +'\n1) 凡涉及分类计数、构成、对比（如「类型分布」「矿种数量」「涨跌对比」），必须用 Markdown 表格：第一行表头，第二行分隔行（形如 |---|---|），每行列数一致，不要用 HTML；'
    +'\n2) 其余内容用「小标题 + 要点列表」，不要写成长段散文；'
    +'\n3) 只输出 Markdown 与纯文本，不要输出 HTML 标签，也不要用代码块包裹整篇回答；'
    +'\n4) 若用户问题含相对时间（如「近三天」「最近一周」），一律以下方给出的【条目日期范围】为准，不得自行推算或改写该区间。';
  // 2026-09-11 P1：历史轮次仅用于指代消解，其格式不作本次样式参考（消除「上轮写表格→本轮回表格」的跨机格式差异）
  system+='\n\n【多轮上下文说明】下方历史对话仅用于理解指代（如「上述矿权」「那笔交易」「它」），其格式与结构**不作**为本次回答的样式参考。本次回答必须严格遵循上方【输出格式（硬性要求）】，不要因为历史回答是表格/列表/散文就延续其样式；若历史回答与本次问题无关，直接忽略即可。';
  var dsMessages=[{role:'system',content:system}];
  if(conv&&conv.length){
    conv.forEach(function(t){ dsMessages.push({role:t.role,content:t.content}); });
  }
  var user='用户问题：'+q+'\n\n';
  if(ctx&&ctx.length){
    if(dateIntent){
      user+='以下为 '+dateIntent+' 的本地新增新闻条目（已按日期筛选）。请先总述条数与板块分布，再按板块/主题分组总结要点，不要逐条复述标题：\n';
    }else{
      user+='以下为本地检索到的相关新闻条目（已按问题相关性筛选，仅包含与问题直接相关的条目）。请先系统整理这些条目，再按主题/维度给出综合性回答，不要逐条复述：\n';
    }
    ctx.forEach(function(c,i){
      var d=c.d||'',t=c.t||'',s=c.s||'',u=c.u||c.url||'';
      user+=(i+1)+'. ['+d+'] '+t+(s?('（'+s+'）'):'')+(u?(' 链接：'+u):'')+'\n';
    });
    user+='\n';
    if(_dsWin){user+='【条目日期范围（唯一可引用的时间范围）】'+_dsWin+'，共 '+ctx.length+' 条。若回答中需要说明时间跨度，必须照抄本区间，不要自行推算或改写。\n';}
  // 2026-09-11 P1：相对时间窗超出本地数据覆盖时，明确告知，避免误以为窗口完整
  if(rangeIntent){
    var _maxD='';QA_ROWS.forEach(function(r){if(r.d&&r.d>_maxD)_maxD=r.d;});
    if(_maxD && _maxD < qaReportDate()){
      user+='（注：本地新闻库最新条目发布于 '+_maxD+'，早于提问所指窗口终点，可引用范围以上方【条目日期范围】为上限，未覆盖完整'+rangeIntent.label+'。）\n';
    }
  }
  }else{
    if(dateIntent){
      user+='（本地新闻库显示 '+dateIntent+' 暂无新增报道；请直接说明无新增，并建议用户换日期或关键词。）\n\n';
    }else{
      user+='（本地新闻库暂未找到直接相关的报道，请基于通用知识简要回答，并建议用户换关键词或查证官方信息。）\n\n';
    }
  }
  // 2026-09-09 Phase E：价格快照注入 RAG 上下文
  var priceBrief=qaPriceBrief(q);
  if(priceBrief){user+='\n\n以下为本地价格快照（单位见各条，仅供参考、非实时行情）：\n'+priceBrief+'\n';}
  user+='请直接给出回答，无需寒暄。'
  if(bubble)bubble.innerHTML='<div class="qa-thinking"><span class="qa-dot"></span>DeepSeek 正在组织答案（约 10~30 秒，可先浏览上方参考来源）…</div>';
  // 2026-09-06 晚：35s 超时兜底，避免 DeepSeek 卡住时面板长期转圈
  var _ac=new AbortController();var _to=setTimeout(function(){_ac.abort();},35000);
  // 2026-09-08：两种调用方式，优先走代理
  //   ① 代理模式（推荐 / 默认）：QA_API_BASE 指向 Netlify 边缘函数，Key 存在平台环境变量里。
  //      本页是 GitHub Pages 公开静态页，任何写进页面的 Key 都等于公开（curl 即得），
  //      故统一走代理——同事打开即用，无需自己填 Key。代理透传 DeepSeek 原始响应，
  //      因此下面的解析逻辑与直连完全一致。
  //   ② 直连模式（兜底）：仅当未配置代理地址时，才使用使用者自填的 Key（localStorage）。
  var _proxyBase=(typeof QA_API_BASE!=='undefined'&&QA_API_BASE)?String(QA_API_BASE).replace(/\/+$/,''):'';
  _qaPath=_proxyBase?'代理':'直连';_qaModel='deepseek-chat';_qaT0=_qaT0||Date.now();
  var _dsMessages=dsMessages.concat([{role:'user',content:user}]);
  var _url,_headers,_body;
  if(_proxyBase){
    _url=_proxyBase+'/api/qa';
    _headers={'Content-Type':'application/json','Accept':'text/event-stream'};
    _body=JSON.stringify({messages:_dsMessages,max_tokens:1500,temperature:0,stream:true});
    // Phase B：优先流式；边缘函数未更新时 qaTryStreamOrJson 自动回退 JSON
    qaTryStreamOrJson(_url,_headers,_body,bubble,msg,q,ctx,dateIntent,_ac,_to,btn);
    return;
  }
  // 2026-09-11 P1：直连也走流式（与代理一致），失败 / 非流自动回退 JSON
  _url='https://api.deepseek.com/chat/completions';
  _headers={'Content-Type':'application/json','Accept':'text/event-stream','Authorization':'Bearer '+getDsKey()};
  _body=JSON.stringify({model:'deepseek-chat',messages:_dsMessages,max_tokens:1500,temperature:0,stream:true});
  qaTryStreamOrJson(_url,_headers,_body,bubble,msg,q,ctx,dateIntent,_ac,_to,btn);
  return;
}
// ===== 问答历史记忆（本地 localStorage）=====
var QA_HISTORY_KEY='qa_history_v1';
var QA_HISTORY_MAX=50;
function qaLoadHistory(){
  try{
    var s=localStorage.getItem(QA_HISTORY_KEY);
    if(!s)return;
    var list=JSON.parse(s);
    if(!Array.isArray(list))return;
    var body=document.getElementById('qaFloatBody');if(!body)return;
    body.innerHTML='';
    list.forEach(function(it){
      // 2026-09-06 修复：按保存时的渲染格式恢复。此前 ai 类消息一律 {md:true}，
      // qaMdRender 第一步会把检索结果的 <a> 卡片整体转义 → 刷新后"回答变裸 HTML"。
      // 旧记录无 fmt 字段时保持 md 兼容（真正的 AI 回答不受影响）。
      // 旧记录无 fmt 字段：内容以 "<" 开头的按 HTML 渲染（修复存量坏数据），否则按 md
      var f=it.fmt||(it.role==='search'?'html':(/^\s*</.test(it.html||'')?'html':'md'));
      var ropts=f==='html'?{html:true,ts:it.ts}:(f==='text'?{md:false,ts:it.ts}:{md:true,ts:it.ts});
      if(it.role==='user')qaFloatAdd('user',it.html,'',{md:false,ts:it.ts});
      else if(it.role==='ai')qaFloatAdd('ai',it.html,it.meta||'',Object.assign({canRetry:it.canRetry!==false,actions:it.canRetry!==false,q:it.q||'',ctx:it.ctx||[]},ropts));
      else if(it.role==='search')qaFloatAdd('ai',it.html,it.meta||'',{html:true,ts:it.ts});
    });
  }catch(e){}
}
function qaSaveHistory(){
  try{
    var body=document.getElementById('qaFloatBody');if(!body)return;
    var msgs=body.querySelectorAll('.qa-msg');
    var out=[];
    msgs.forEach(function(el){
      var role=el.classList.contains('user')?'user':(el.classList.contains('ai')?'ai':'');
      if(!role)return;
      var metaEl=el.querySelector('.qa-msg-meta');
      var meta=metaEl?metaEl.textContent:'';
      var raw=el.dataset.raw||'';
      var ts=el.dataset.ts?Number(el.dataset.ts):0;
      if(role==='ai'){
        out.push({role:'ai',html:raw,meta:meta,ts:ts,fmt:el.dataset.fmt||'',q:el.dataset.q||'',ctx:el.dataset.ctx||'',canRetry:!!el.querySelector('.qa-msg-actions')});
      }else{
        out.push({role:'user',html:raw,meta:meta,ts:ts});
      }
    });
    if(out.length>QA_HISTORY_MAX)out=out.slice(out.length-QA_HISTORY_MAX);
    lsSet(QA_HISTORY_KEY,JSON.stringify(out));
  }catch(e){}
}
// 2026-09-11 P1：相同「问题 + 筛选 + 数据版本」的答案缓存，避免重复调用、并使同一问题在同机稳定复现
var QA_CACHE_KEY='qa_answer_cache_v1',QA_CACHE_MAX=30;
function qaCacheKey(q,m,t,from,rg,di){
  return JSON.stringify({q:q||'',m:m||'',t:t||'',from:from||'',rg:rg||0,di:di||'',u:QA_UPDATED||''});
}
function qaCacheGet(k){
  try{ var s=lsGet(QA_CACHE_KEY); if(!s)return null; var map=JSON.parse(s); if(!map||!map[k])return null;
    if(map[k].u!==(QA_UPDATED||''))return null; return map[k]; }catch(e){ return null; }
}
function qaCachePut(k,v){
  try{ var s=lsGet(QA_CACHE_KEY); var map=s?JSON.parse(s):{}; if(!map||typeof map!=='object')map={};
    map[k]=v; var ks=Object.keys(map);
    if(ks.length>QA_CACHE_MAX){ ks.slice(0,ks.length-QA_CACHE_MAX).forEach(function(x){ delete map[x]; }); }
    lsSet(QA_CACHE_KEY,JSON.stringify(map)); }catch(e){}
}
// 欢迎语（2026-09-08 晚：原「本地新闻库 N 条。」信息量为零，改为说明面板能力）
function qaWelcomeText(){
  var up=QA_UPDATED?('（更新于 '+QA_UPDATED+'）'):'';
  return '👋 本地新闻库共 '+QA_ROWS.length+' 条'+up+'。'
    +'\n\n输入关键词点「检索」全库查找原文；点「AI」让 AI 读完相关新闻后作答；'
    +'也可先用上方矿种 / 主题 / 时间筛选缩小范围。';
}
function qaClearHistory(){
  try{localStorage.removeItem(QA_HISTORY_KEY);}catch(e){}
  var body=document.getElementById('qaFloatBody');if(!body)return;
  body.innerHTML='';
  qaFloatAdd('ai',qaWelcomeText(),'本地知识库 · 零依赖',{md:true});
}
function qaCopyAi(btn){
  var msg=btn.closest('.qa-msg');if(!msg)return;
  var raw=msg.dataset.raw||'';
  try{
    navigator.clipboard.writeText(raw).then(function(){
      btn.textContent='已复制';setTimeout(function(){btn.textContent='📋 复制';},1500);
    },function(){
      btn.textContent='复制失败';setTimeout(function(){btn.textContent='📋 复制';},1500);
    });
  }catch(e){btn.textContent='复制失败';setTimeout(function(){btn.textContent='📋 复制';},1500);}
}
function qaRetryAi(btn){
  var msg=btn.closest('.qa-msg');if(!msg)return;
  var q=msg.dataset.q||'',ctx=msg.dataset.ctx||'[]';
  if(!q)return;
  try{ctx=JSON.parse(ctx)||[];}catch(e){ctx=[];}
  var inp=document.getElementById('qaFloatInput');if(inp)inp.value=q;
  var body=document.getElementById('qaFloatBody');if(!body||!body.contains(msg))return;
  body.removeChild(msg);
  qaFloatAsk(true,ctx);
}
function qaFloatReset(){
  var i=document.getElementById('qaFloatInput');if(i)i.value='';
  ['qaFloatMineral','qaFloatTopic'].forEach(function(id){var e=document.getElementById(id);if(e)e.value='';});
  var rg=document.getElementById('qaFloatRange');if(rg)rg.value='0';
  QA_TREND=false;
  var tb=document.getElementById('qaFloatTrend');if(tb){tb.classList.remove('on');tb.setAttribute('aria-pressed','false');}
}

// ===== 2026-09-06 晚：日报 PDF 导出（打印样式见 </style> 内 @media print）=====
function exportPdf(){
  try{
    document.querySelectorAll('.old-folded').forEach(function(el){el.classList.remove('old-folded');});
    var ft=document.getElementById('foldToggle');if(ft)ft.style.display='none';
  }catch(e){}
  var done=false;
  function restore(){ if(done)return; done=true; try{foldOldArchive();}catch(e){} }
  window.onafterprint=restore;
  setTimeout(function(){try{window.print();}catch(e){restore();}},80);
}

// ===== 2026-09-07：新闻列表搜索 + 快捷矿种/类别筛选 + CSV 导出（渲染层，不动 gen_today.py）=====
function setupNewsFilterBar(){
  if(document.getElementById('newsFilterBar'))return;
  var today=document.getElementById('todaySection'); if(!today)return;
  var bar=document.createElement('div'); bar.id='newsFilterBar'; bar.className='news-filter-bar';
  // 2026-09-11 IA评审 A6：#nfCount 匹配条数是操作结果，加 role=status/aria-live 供读屏播报
  bar.innerHTML='<div class="nf-search-wrap"><input class="nf-search" id="nfSearch" type="search" placeholder="搜索标题 / 摘要 / 来源…" aria-label="搜索新闻">'
    +'<button class="nf-clear" id="nfClear" type="button" aria-label="清除搜索" hidden>✕</button></div>'
    +'<button class="nf-toggle" id="nfToggle" type="button" aria-label="展开或收起筛选" aria-expanded="false">筛选 <span class="nf-toggle-ico">▾</span></button>'
    +'<div class="nf-chips" id="nfChips">'
    +'<span class="nf-chip active" data-kw="">全部</span>'
    +'<span class="nf-chip nf-chip-metal" data-kw="金">金</span>'
    +'<span class="nf-chip nf-chip-metal" data-kw="铜">铜</span>'
    +'<span class="nf-chip nf-chip-metal" data-kw="铝">铝</span>'
    +'<span class="nf-chip nf-chip-metal" data-kw="铅锌">铅锌</span>'
    +'<span class="nf-chip nf-chip-metal" data-kw="镍">镍</span>'
    +'<span class="nf-chip nf-chip-metal" data-kw="锡">锡</span>'
    +'<span class="nf-chip nf-chip-metal" data-kw="锂">锂</span>'
    +'<span class="nf-chip nf-chip-metal" data-kw="钴">钴</span>'
    +'<span class="nf-chip" data-kw="矿权">矿权</span>'
    +'<span class="nf-chip" data-kw="政策">政策</span>'
    +'<span class="nf-chip" data-kw="勘查">勘查</span>'
    +'<span class="nf-chip" data-kw="技术">技术</span>'
    +'<span class="nf-chip" data-kw="风险">风险</span>'
    +'</div><span class="nf-count" id="nfCount" role="status" aria-live="polite"></span>';
  today.parentNode.insertBefore(bar, today);
  var input=document.getElementById('nfSearch');
  var cl=document.getElementById('nfClear');
  input.addEventListener('input',function(){
    newsSearchText=(input.value||'').trim().toLowerCase();
    if(cl)cl.hidden=!input.value;
    document.querySelectorAll('.nf-chip').forEach(function(x){x.classList.toggle('active', x.getAttribute('data-kw')==='');});
    applyFilter(); updateNfCount();
  });
  if(cl)cl.addEventListener('click',function(){
    if(!input.value){ document.body.classList.remove('md-search-open'); return; }
    input.value=''; newsSearchText=''; if(!document.body.classList.contains('md-search-open')) cl.hidden=true;
    document.querySelectorAll('.nf-chip').forEach(function(x){x.classList.toggle('active', x.getAttribute('data-kw')==='');});
    applyFilter(); updateNfCount();
  });
  document.getElementById('nfChips').addEventListener('click',function(e){
    var c=e.target.closest('.nf-chip'); if(!c)return;
    var kw=c.getAttribute('data-kw')||'';
    var cur=document.querySelector('.nf-chip.active');
    var activeKw=cur?cur.getAttribute('data-kw'):'';
    if(kw===''||kw===activeKw){ newsSearchText=''; input.value=''; if(cl)cl.hidden=true; }
    else { newsSearchText=kw.toLowerCase(); input.value=''; }
    document.querySelectorAll('.nf-chip').forEach(function(x){x.classList.toggle('active', x.getAttribute('data-kw')===newsSearchText);});
    applyFilter(); updateNfCount();
  });
  var tog=document.getElementById('nfToggle');
  if(tog) tog.addEventListener('click',function(){
    var c=document.getElementById('nfChips'); if(!c) return;
    var open=c.classList.toggle('show');
    tog.setAttribute('aria-expanded', open?'true':'false');
  });
}
function updateNfCount(){
  var el=document.getElementById('nfCount'); if(!el)return;
  // 2026-09-11 IA评审 A2：计数口径与空态 mdSyncSearchEmpty 一致（含矿权行），避免「匹配 0 条」与矿权命中同屏
  el.textContent= newsSearchText? ('匹配 '+document.querySelectorAll('.news-item:not(.hidden),.rights-row:not(.hidden)').length+' 条') : '';
}
// CSV 导出（价格 / 矿权），纯前端生成，不依赖后端
function downloadCsv(filename, rows){
  if(!rows||rows.length<2){ alert('暂无可导出的数据'); return; }
  var csv='\uFEFF';
  rows.forEach(function(r){
    csv+=r.map(function(c){
      var s=(c==null?'':String(c));
      s=s.replace(/\r?\n/g,' ').replace(/"/g,'""');
      if(/[",\n;]/.test(s)) s='"'+s+'"';
      return s;
    }).join(',')+'\r\n';
  });
  var blob=new Blob([csv],{type:'text/csv;charset=utf-8;'});
  var url=URL.createObjectURL(blob);
  var a=document.createElement('a'); a.href=url; a.download=filename;
  a.className='csv-download'; a.setAttribute('data-no-overlay','1');
  a.addEventListener('click',function(e){ e.stopPropagation(); });
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  setTimeout(function(){URL.revokeObjectURL(url);},1000);
}
function csvDate(){ var d=new Date(); return d.getFullYear()+('-'+(d.getMonth()+1)).slice(-2)+('-'+d.getDate()).slice(-2); }
function exportPriceCsv(){
  var rows=[['市场','品种','代码','价格','单位','涨跌']];
  ['priceCardsShfe','priceCardsLme'].forEach(function(id){
    var wrap=document.getElementById(id); if(!wrap)return;
    var market= id==='priceCardsLme'?'LME':'上期所';
    wrap.querySelectorAll('.price-card').forEach(function(card){
      var name=(card.querySelector('.pc-name')||{}).textContent||'';
      var tag=(card.querySelector('.pc-tag')||{}).textContent||'';
      var val=(card.querySelector('.pc-value')||{}).textContent||'';
      var unit=(card.querySelector('.pc-unit')||{}).textContent||'';
      var chg=(card.querySelector('.pc-chg')||{}).textContent||'';
      var variety=name.split(tag).join('').trim();
      rows.push([market, variety, tag, val, unit, chg]);
    });
  });
  downloadCsv('矿业日报_金属价格_'+csvDate()+'.csv', rows);
}
function exportRightsCsv(){
  // 2026-09-08 修正：原实现从 DOM 表格逐行读，而表格受 RIGHTS_COLLAPSE_AT 折叠限制
  // 只渲染前 8 条，导致导出的 CSV 也只有 8 条（全库其实有几十条），用户误拿到全量。
  // 改为从渲染时暴露的「筛选后全量」__rightsFullList 生成；DOM 读取仅作兜底。
  var rows=[['矿种','标题','地区','出让方式','价格(万元)','竞得人/保证金(万元)','面积(km²)','日期','链接']];
  function c(v){ return (v==null||v==='')?'—':String(v).replace(/\s+/g,' ').trim(); }
  function dd(d){ return d?String(d).slice(5):'—'; }
  var full=window.__rightsFullList;
  if(full && full.length){
    full.forEach(function(r){
      var price='—', second='—';
      if(r.rightsType==='result'){ price=(r.dealPrice!=null?r.dealPrice:'—'); second=r.bidder||'—'; }
      else if(r.rightsType==='transfer'){ price='—'; second=(r.transferor||'—')+' → '+(r.transferee||'—'); }
      else { price=(r.price==null?'—':r.price); second=(r.deposit==null?'—':r.deposit); }
      rows.push([
        c(r.mineral), c(r.it&&r.it.t), c(r.region), c(r.method),
        c(price), c(second), c(r.area), dd(r.deadline), (r.it&&r.it.u)||''
      ]);
    });
  }else{
    // 2026-09-08 深夜：表格视图已删，数据源不可用时直接提示（__rightsFullList 由 renderRightsSection 始终填充）
    alert('矿权数据未加载，请刷新页面后重试');
  }
  if(rows.length<=1){ alert('当前筛选条件下没有可导出的矿权数据'); return; }
  downloadCsv('矿业日报_矿权出让_'+csvDate()+'.csv', rows);
}
function setupExportButtons(){
  var head=document.querySelector('.price-strip-head');
  if(head && !document.getElementById('priceCsvBtn')){
    var b=document.createElement('button'); b.id='priceCsvBtn'; b.className='nf-export-btn';
    b.type='button'; b.textContent='⬇ 价格CSV'; b.onclick=function(e){ if(e){e.stopPropagation();} exportPriceCsv(); }; head.appendChild(b);
  }
  var rtb=document.querySelector('.rights-toolbar');
  if(rtb && !document.getElementById('rightsCsvBtn')){
    var b2=document.createElement('button'); b2.id='rightsCsvBtn'; b2.className='nf-export-btn';
    b2.type='button'; b2.textContent='⬇ 矿权CSV'; b2.onclick=function(e){ if(e){e.stopPropagation();} exportRightsCsv(); }; rtb.appendChild(b2);
  }
}
if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', function(){ setupNewsFilterBar(); setupExportButtons(); });
else { setupNewsFilterBar(); setupExportButtons(); }

/* ===== 会展预告（2026-09-08 改造：主区独立区块 → 左侧栏迷你卡）=====
   背景：候选池里会议/论坛/展会/年会类条目占比高（SMM 源尤其多），但它们不是
   「行业事件」，混在今日新增里会挤掉真正的行情与项目动态。
   原做法：在主区新建 #expoSection 把条目搬过去 → 占主区一整块，要滚到中段才看得到。
   现做法：桌面端把条目收进左侧栏「近期会展」迷你卡，打开页面即可见；
           条目本身移入隐藏容器（仍在 DOM 内，保留已读/收藏/搜索），主区不再重复出现。
   移动端（<=1100px）侧栏退化为顶部横条，迷你卡不展示，条目留在原位。
   判定 = 会展词 ∩ 动作词 − 实质事件词（避免把「矿业大会宣布新探矿权出让」误搬走）。 */
(function(){
  var EXPO_WORDS=['大会','年会','论坛','峰会','研讨会','博览会','展会','展览会','推介会',
                  '交流会','洽谈会','对接会','沙龙','展览','会议'];
  var EXPO_ACTION=['召开','举行','举办','开幕','落幕','收官','闭幕','将于','即将','预告',
                   '报名','邀请','倒计时','参展','参会','圆满','启幕','直播','议程','出席'];
  var EXPO_SKIP=['收购','投产','勘探','发现','涨价','签约','中标','获批','事故','停产',
                 '复产','产量','利润','业绩预告','资源量','储量','矿权','出让','挂牌',
                 '拍卖','减产','罢工','禁令','关税','出口管制','复产','投产','增产'];
  function isDesktop(){ try{ return !(window.matchMedia&&window.matchMedia('(max-width:1100px)').matches); }catch(e){ return true; } }
  function titleOf(el){var a=el.querySelector('.news-title');return a?(a.textContent||''):'';}
  function urlOf(el){var a=el.querySelector('.news-title');return a?(a.getAttribute('href')||'#'):'#';}
  function dateOf(el){
    var m=((el.querySelector('.news-meta')||{}).textContent||'').match(/(\d{1,2})-(\d{1,2})/);
    return m?m[0]:'';
  }
  function isExpo(t){
    if(!t) return false;
    var i,hit=false;
    for(i=0;i<EXPO_WORDS.length;i++){ if(t.indexOf(EXPO_WORDS[i])>=0){hit=true;break;} }
    if(!hit) return false;
    for(i=0;i<EXPO_SKIP.length;i++){ if(t.indexOf(EXPO_SKIP[i])>=0) return false; }
    for(i=0;i<EXPO_ACTION.length;i++){ if(t.indexOf(EXPO_ACTION[i])>=0) return true; }
    // 会议本体名（如「…发展论坛」「第八届全球铝土矿大会」）没有任何动作词，
    // 但带「届」或以会展词收尾，同样属于会展条目。
    if(t.indexOf('届')>=0) return true;
    for(i=0;i<EXPO_WORDS.length;i++){
      var w=EXPO_WORDS[i];
      if(t.length>=w.length && t.lastIndexOf(w)===t.length-w.length) return true;
    }
    return false;
  }
  function init(){
    try{
      var box=document.getElementById('expoMini');
      var ul=document.getElementById('expoMiniList');
      var secs=[document.getElementById('todaySection'),document.getElementById('archiveSection')];
      var picked=[];
      secs.forEach(function(sec){
        if(!sec) return;
        Array.prototype.slice.call(sec.querySelectorAll('.news-item')).forEach(function(el){
          if(isExpo(titleOf(el))) picked.push(el);
        });
      });
      if(!picked.length) return;
      // 跨源去重：同一场会议常被多家媒体报道，标题高度相似只留最早一条
      // （与今日要闻 mdPickDistinct 同一套相似度，复用 window.mdTitleSim）
      var sim=(typeof window.mdTitleSim==='function')?window.mdTitleSim:null;
      if(sim){
        var uniq=[];
        for(var pi=0;pi<picked.length;pi++){
          var dup=false;
          for(var pj=0;pj<uniq.length;pj++){
            if(sim(titleOf(uniq[pj]),titleOf(picked[pi]))>=0.5){dup=true;break;}
          }
          if(!dup)uniq.push(picked[pi]);
        }
        picked=uniq;
      }
      var html='';
      // 2026-09-08 晚：全量展示（列表限高 185px 滚动），去掉「另有 N 场会议」死文本——
      // 有多少展多少，放不下用户自己滚，条目链接全部可点。
      picked.forEach(function(el){
        var t=titleOf(el).trim(),u=urlOf(el),d=dateOf(el);
        html+='<li><a href="'+safeHref(u)+'" target="_blank" rel="noopener" title="'+esc(t)+'">'+esc(t)+'</a>'
            +(d?'<span class="expo-mini-date">'+esc(d)+'</span>':'')+'</li>';
      });
      // 桌面端侧栏迷你卡：仅桌面展示；移动端隐藏（列表由「会议」tab 承担）。
      if(isDesktop() && box && ul){ ul.innerHTML=html; box.style.display=''; }
      // 条目移入隐藏容器：仍在 DOM 内（保留已读/收藏/搜索），但主区不再重复展示。
      // 关键：移动端也必须执行本步，否则会展条目既出现在主信息流、又在「会议」tab 出现双份（A4 重复根因）。
      // —— 不按主列表 URL 过滤「会议」tab（移动端会清空该 tab），正解即让 vault 迁移在移动端也执行。
      var vault=document.getElementById('expoVault');
      if(!vault){ vault=document.createElement('div'); vault.id='expoVault'; vault.style.display='none'; document.body.appendChild(vault); }
      picked.forEach(function(el){ el.classList.remove('is-new'); vault.appendChild(el); });
      if(typeof refresh==='function'){ try{refresh();}catch(e){} }
    }catch(e){}
  }
  if(document.readyState==='loading')
    document.addEventListener('DOMContentLoaded',function(){ setTimeout(init,0); });
  else setTimeout(init,0);
  window.__expoIsExpo=isExpo;
})();

/* ===== 主题切换（2026-09-05 新增）=====
   手动切换后写入 localStorage，之后不再跟随系统；
   系统主题变化时，仅对"从未手动选择过"的用户自动跟随。 */
function applyTheme(mode){
  var dark = mode === 'dark';
  document.body.classList.toggle('dark', dark);
  var btn = document.getElementById('themeToggle');
  if(btn){
    var lightOpt = btn.querySelector('.theme-option.light');
    var darkOpt = btn.querySelector('.theme-option.dark');
    if(lightOpt) lightOpt.classList.toggle('active', !dark);
    if(darkOpt) darkOpt.classList.toggle('active', dark);
    btn.setAttribute('title', dark ? '切换到浅色模式' : '切换到深色模式');
    btn.setAttribute('aria-label', btn.getAttribute('title'));
  }
  // 走势图若正开着，用新主题配色重绘一次
  try{ if(window.PC_CHART_SLUG) pcChartOpen(window.PC_CHART_SLUG); }catch(e){}
}
function toggleTheme(){
  var dark = !document.body.classList.contains('dark');
  applyTheme(dark ? 'dark' : 'light');
  try{ lsSet('md_theme', dark ? 'dark' : 'light'); }catch(e){}
}
(function(){
  // 同步图标状态（class 已由 body 开头的初始化脚本设好）
  applyTheme(document.body.classList.contains('dark') ? 'dark' : 'light');
  // 未手动选择过时，跟随系统主题变化
  try{
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    var onChange = function(e){
      var saved = null;
      try{ saved = localStorage.getItem('md_theme'); }catch(err){}
      if(!saved) applyTheme(e.matches ? 'dark' : 'light');
    };
    if(mq.addEventListener) mq.addEventListener('change', onChange);
    else if(mq.addListener) mq.addListener(onChange);
  }catch(e){}
})();


;

// 问答浮窗 DOM 就绪后统一初始化（必须放在 #qaFab/#qaFloat HTML 之后）
(function(){
  // 筛选器：矿种 / 主题 / 时间变化即触发检索
  ['qaFloatMineral','qaFloatTopic'].forEach(function(id){
    var e=document.getElementById(id);if(e)e.addEventListener('change',qaFloatSearch);
  });
  var rg=document.getElementById('qaFloatRange');if(rg)rg.addEventListener('change',qaFloatSearch);
  var tb=document.getElementById('qaFloatTrend');
  if(tb)tb.addEventListener('click',function(){QA_TREND=!QA_TREND;tb.classList.toggle('on',QA_TREND);tb.setAttribute('aria-pressed',QA_TREND?'true':'false');qaFloatSearch();});
  var rs=document.getElementById('qaFloatReset');if(rs)rs.addEventListener('click',qaFloatReset);

  // 首次进入呼吸提示
  try{
    var _reduce=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var _seen=window.localStorage&&localStorage.getItem('qaFabSeen');
    if(!_seen&&!_reduce){
      var _fb=document.getElementById('qaFab');
      if(_fb){
        _fb.classList.add('breathe');
        setTimeout(function(){if(_fb.classList.contains('breathe'))qaStopBreathe();},9000);
      }
    }
  }catch(e){}

  // 恢复上次位置与尺寸，并挂载拖拽
  try{qaFloatRestoreSize();qaFloatRestorePos();}catch(e){}
  try{qaFabRestorePos();qaFabRestoreTuck();qaFabApplyTuck();}catch(e){}
  var _fab=document.getElementById('qaFab');
  if(_fab){
    _fab.addEventListener('mousedown',qaFabStartDrag);
    _fab.addEventListener('touchstart',qaFabStartDrag,{passive:false});
  }
  // 窗口缩放 / 手机旋转：把悬浮球重新夹回可视区（半隐藏时保持所在边）
  window.addEventListener('resize',function(){
    try{
      var _b=document.getElementById('qaFab');if(!_b)return;
      var _vw=window.innerWidth,_vh=window.innerHeight,_bw=_b.offsetWidth||160,_bh=_b.offsetHeight||50;
      var _l=Math.min(Math.max(qaFabLayoutLeft(_b),0),Math.max(_vw-_bw,0));
      var _bm=Math.min(Math.max(qaFabLayoutBottom(_b),0),Math.max(_vh-_bh,0));
      _b.style.left=_l+'px';_b.style.bottom=_bm+'px';_b.style.top='auto';
      if(QA_FAB_TUCKED)qaFabTuck(QA_FAB_SIDE);
    }catch(e){}
  });
  var _panel=document.getElementById('qaFloat');
  if(_panel){
    qaFloatAddResizeHandles();
    // 缩放把手优先；拖拽把手=整个面板除交互元素/缩放柄
    _panel.addEventListener('mousedown',qaFloatStartResize);
    _panel.addEventListener('mousedown',qaFloatStartDrag);
    // 移动端：缩放柄也要能拖（此前只绑了 mousedown，手机上完全无法改变面板大小）
    _panel.addEventListener('touchstart',qaFloatStartResize,{passive:false});
    _panel.addEventListener('touchstart',qaFloatStartDrag,{passive:false});
  }
  qaFloatObserveSize();

  // 初始化会话：加载历史或显示引导
  var fb=document.getElementById('qaFloatBody');
  if(fb){
    if(fb.children.length)fb.innerHTML='';
    qaLoadHistory();
    if(!fb.children.length){
      qaFloatAdd('ai',qaWelcomeText(),'本地知识库 · 零依赖',{md:true});
    }
  }

  // 输入框快捷键与按钮事件
  var inp=document.getElementById('qaFloatInput');
  if(inp){
    inp.addEventListener('keydown',function(e){
      if(e.key==='Enter'){e.preventDefault();qaFloatSearch();}
      if(e.key==='Escape')qaFloatClose();
    });
  }
  var sb=document.getElementById('qaFloatSearch');if(sb)sb.addEventListener('click',qaFloatSearch);
  var ab=document.getElementById('qaFloatAi');if(ab)ab.addEventListener('click',qaFloatAsk);
  // 2026-09-08 晚修复：qaAiProbe 此前只在脚本解析期调用（那时 #qaFloatAi 还没渲染，b 恒为 null，
  // 探针从未生效过）；面板 DOM 就绪后这里补一次，按钮文案/提示才能按「代理可用/需自填 Key」正确显示。
  try{ qaAiProbe(); }catch(e){}
  try{ qaInitMic(); }catch(e){}
  document.addEventListener('keydown',function(e){
    if(e.key!=='Escape')return;
    pcChartClose();
    qaFloatClose();
  });
})();

;

/* ===== 2026-09-08 价格区增强 =====
   ① 今日异动排行条：自动挑出当日涨/跌最大的品种
   ② 「昨」角标：无当日数据的品种（如电解钴 SMM 现货）打标，与实时价区分
   ③ 按涨跌排序开关：异动品种浮顶，默认顺序可随时切回
   说明：角标与名次一律用 CSS 伪元素 + 属性渲染（不写进 textContent），
        因此价格 CSV 导出、价格预警解析读到的数据不受影响。 */
(function(){
  if(window.__mdPriceEnhanceLoaded)return;
  window.__mdPriceEnhanceLoaded=true;
  var IDS=['priceCardsShfe','priceCardsLme'];
  var origOrder={};
  var sortMode='default';

  function cards(id){
    var w=document.getElementById(id);
    return w?Array.prototype.slice.call(w.querySelectorAll('.price-card')):[];
  }
  function pctOf(card){
    var c=card.querySelector('.pc-chg');
    if(!c)return null;
    var m=(c.textContent||'').match(/(-?\d+(?:\.\d+)?)\s*%/);
    if(!m)return null;
    var p=parseFloat(m[1]);
    if(isNaN(p))return null;
    if(card.classList.contains('down')&&p>0)p=-p;
    return p;
  }
  function nameOf(card){
    var n=card.querySelector('.pc-name');
    if(!n)return '';
    var tag=n.querySelector('.pc-tag');
    var txt=n.textContent||'';
    if(tag)txt=txt.split(tag.textContent).join('');
    return txt.replace(/\s+/g,'').trim();
  }
  function snapshot(force){
    IDS.forEach(function(id){
      var w=document.getElementById(id);
      if(!w)return;
      var prev=origOrder[id];
      if(!force&&prev&&prev.length&&w.contains(prev[0]))return;   // 节点仍在线，不重复快照
      origOrder[id]=cards(id);
    });
  }
  /* ② 昨角标 */
  function staleMark(){
    IDS.forEach(function(id){
      cards(id).forEach(function(card){
        var p=pctOf(card);
        card.classList.toggle('stale', p===null);
      });
    });
  }

  /* ① 异动排行条 */
  /* 异动条与排序开关统一收进标题行下方的独立工具行，避免与标题挤一行导致折行 */
  function ensureToolbar(){
    var st=document.getElementById('priceStrip');
    var tb=st?st.querySelector('.price-toolbar'):null;
    if(!tb){
      tb=document.createElement('div');
      tb.className='price-toolbar';
      var head=st?st.querySelector('.price-strip-head'):null;
      if(head&&head.parentNode)head.parentNode.insertBefore(tb,head.nextSibling);
      else if(st)st.insertBefore(tb,st.firstChild);
    }
    return tb;
  }
  function topMovers(){
    var strip=document.getElementById('priceStrip');
    if(!strip)return;
    var items=[];
    IDS.forEach(function(id){
      cards(id).forEach(function(card){
        var p=pctOf(card);
        if(p===null)return;
        items.push({n:nameOf(card),p:p,lme:id==='priceCardsLme'});
      });
    });
    var box=document.getElementById('priceTopMovers');
    if(items.length<2){ if(box&&box.parentNode)box.parentNode.removeChild(box); return; }
    var ups=items.filter(function(x){return x.p>0;}).sort(function(a,b){return b.p-a.p;});
    var downs=items.filter(function(x){return x.p<0;}).sort(function(a,b){return a.p-b.p;});
    var pick=[];
    if(ups[0])pick.push(ups[0]);
    if(downs[0])pick.push(downs[0]);
    var lmeUp=ups.filter(function(x){return x.lme;})[0];
    if(lmeUp&&pick.length<3&&!pick.some(function(x){return x.n===lmeUp.n;}))pick.push(lmeUp);
    if(pick.length<2&&ups[1])pick.push(ups[1]);
    if(!pick.length)return;
    var html=pick.map(function(x){
      return '<span class="mv '+(x.p>0?'up':'down')+'">'+esc(x.n)+' <b>'+(x.p>0?'+':'')+x.p.toFixed(2)+'%</b></span>';
    }).join('<span class="mv-sep">|</span>');
    if(!box){
      box=document.createElement('div');
      box.id='priceTopMovers';
      box.className='top-movers';
      ensureToolbar().appendChild(box);
    }
    box.innerHTML='<span>🔥 今日异动</span><span class="mv-sep">|</span>'+html;
  }

  /* ③ 排序开关 */
  function setSort(mode){
    sortMode=mode;
    var bar=document.getElementById('priceSortBar');
    if(bar)bar.querySelectorAll('.sortbtn').forEach(function(b){
      b.classList.toggle('on', b.getAttribute('data-mode')===mode);
    });
    IDS.forEach(function(id){
      var w=document.getElementById(id);
      if(!w)return;
      var arr=(origOrder[id]||cards(id)).slice();
      if(mode==='pct'){
        arr.sort(function(a,b){
          var pa=pctOf(a),pb=pctOf(b);
          if(pa===null&&pb===null)return 0;
          if(pa===null)return 1;
          if(pb===null)return -1;
          return pb-pa;
        });
        arr.forEach(function(c,i){ c.setAttribute('data-rank',String(i+1)); w.appendChild(c); });
      }else{
        arr.forEach(function(c){ c.removeAttribute('data-rank'); w.appendChild(c); });
      }
    });
  }
  function sortBar(){
    if(document.getElementById('priceSortBar'))return;
    var strip=document.getElementById('priceStrip');
    if(!strip)return;
    var bar=document.createElement('div');
    bar.id='priceSortBar';
    bar.className='sortbar';
    bar.innerHTML='<button type="button" class="sortbtn on" data-mode="default">默认顺序</button>'
                 +'<button type="button" class="sortbtn" data-mode="pct">按涨跌排序</button>';
    bar.addEventListener('click',function(e){
      var b=e.target&&e.target.closest?e.target.closest('.sortbtn'):null;
      if(!b)return;
      setSort(b.getAttribute('data-mode'));
    });
    ensureToolbar().appendChild(bar);
  }

  function run(){
    try{
      snapshot(false);
      staleMark();
      topMovers();
      sortBar();
      if(sortMode!=='default')setSort(sortMode);   // 价格异步刷新后保持当前排序
    }catch(err){ console.warn('priceEnhance:',err); }
  }
  window.__mdPriceEnhance=run;
  run();
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',run);
  setTimeout(run,1200);
  setTimeout(run,3000);
})();

// 2026-09-11：app.js「求值完成」信标 —— 必须留在本文件最后一行。
// 诊断价值：线上若看到 __mdBooted=true 而 __mdAppEvaluated 缺失，即说明脚本在求值中途抛错中断
// （09-10 / 09-11 三轮事故都是这个形态）。过去没有任何可观测手段，只能靠猜。
window.__mdAppEvaluated=true;
// 求值完成后立即重算横幅状态：清除加载窗口内可能残留的任何误报（双保险）。
// 此时 mdDegraded() 必返回 ''（app 已执行），mdSyncBanner 会隐藏 error 红条，
// 并把单组件标注 / info 条对齐到 app 真实渲染后的状态。
try{ if(typeof window.mdSyncBanner==='function') window.mdSyncBanner(); }catch(e){}
