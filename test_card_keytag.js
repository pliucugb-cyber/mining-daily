// 单元测试：cardKeyTag 自动标签规则（修复审查方反馈的"机构价格预测误标重大政策"）
// 直接抽取 app.js 中的 cardKeyTag 函数源码，在沙箱里 eval 后断言标签口径。
// 运行：NODE_PATH=<repo>/node_modules node test_card_keytag.js
const fs = require('fs');
const path = require('path');

const APP = path.join(__dirname, 'app.js');
const src = fs.readFileSync(APP, 'utf8');

// 抽取 function cardKeyTag(...) { ... }（函数级闭括号在列 0）
const start = src.indexOf('function cardKeyTag');
if (start < 0) { console.error('FAIL 未找到 cardKeyTag'); process.exit(1); }
const open = src.indexOf('{', start);
const close = src.indexOf('\n}', open); // 顶层闭括号（列0），内层均为缩进
if (close < 0) { console.error('FAIL 未找到 cardKeyTag 函数闭括号'); process.exit(1); }
const body = src.slice(open + 1, close);
const cardKeyTag = new Function('txt', 'cat', body);

let pass = 0, fail = 0;
function check(name, got, want) {
  const ok = got === want;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + '  got=[' + got + '] want=[' + want + ']');
  ok ? pass++ : fail++;
}

// 市场/并购类目：价格预测 / 投行观点 必须标"机构观点"，且不得标"重大政策""供应风险"
check('[T1] 花旗预测关键矿产(市场)→机构观点', cardKeyTag('花旗预测关键矿产价格走势', 'market'), '机构观点');
check('[T2] 高盛上调铜价目标价(市场)→机构观点', cardKeyTag('高盛上调铜价目标价', 'market'), '机构观点');
check('[T3] 摩根研报看跌锂(并购)→机构观点', cardKeyTag('摩根研报看跌锂价', 'capital'), '机构观点');
check('[T4] 市场类价格预测不得误标政策', cardKeyTag('机构预测关键矿产需求', 'market'), '机构观点');
check('[T5] 市场类供应词不得误标供应风险', cardKeyTag('某矿罢工停产(市场动态)', 'market'), '');
check('[T6] 市场类真实重大并购仍保留重点', cardKeyTag('紫金矿业收购海外铜矿', 'capital'), '重点');

// 政策/其他类目：政策关键词仍正确标"重大政策"，供应风险仍生效
check('[T7] 国务院关键矿产法案(政策)→重大政策', cardKeyTag('国务院发布关键矿产法案', 'policy'), '重大政策');
check('[T8] 232条款出口管制(政策)→重大政策', cardKeyTag('美国232条款出口管制', 'policy'), '重大政策');
check('[T9] 找矿突破(勘查)→找矿突破', cardKeyTag('探获大型铜矿增储', 'explore'), '找矿突破');
check('[T10] 罢工停产(勘查)→供应风险仍生效', cardKeyTag('某矿罢工停产', 'explore'), '供应风险');
check('[T11] 无关键词→空', cardKeyTag('一般行业动态', 'market'), '');
check('[T12] 空文本→空', cardKeyTag('', 'policy'), '');

console.log('\n===== 汇总 =====');
console.log('  通过 ' + pass + ' / 失败 ' + fail);
process.exit(fail ? 1 : 0);
