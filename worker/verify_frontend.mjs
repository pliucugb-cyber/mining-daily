// verify_frontend.mjs —— 验证前端 qaFloatAsk 的 RAG 流程（jsdom 真 DOM）
// 确认：AI 开启时，qaFloatAsk 把本地检索到的相关新闻作为 context POST 给绝对 URL 的 /api/qa
import { readFileSync } from 'node:fs';
const { JSDOM } = await import('file:///c:/Users/%E4%B8%AD%E9%93%9D%E7%9F%BF%E4%B8%9A%E6%8A%95%E5%B9%B6%E9%83%A8/.workbuddy/binaries/node/workspace/node_modules/jsdom/lib/api.js');

const html = readFileSync('C:/Users/中铝矿业投并部/mining-daily/index.html', 'utf8');
const news = readFileSync('C:/Users/中铝矿业投并部/mining-daily/news-data.js', 'utf8');
const lme  = readFileSync('C:/Users/中铝矿业投并部/mining-daily/lme-data.js', 'utf8');
const ph   = readFileSync('C:/Users/中铝矿业投并部/mining-daily/price-history.js', 'utf8');

const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://x.test/' });
const w = dom.window, d = w.document;

w.fetch = () => Promise.reject(new Error('no-net'));
try { Object.defineProperty(w.navigator, 'serviceWorker', { value: { register: () => Promise.resolve({}), addEventListener(){}, removeEventListener(){} }, configurable: true }); } catch (e) {}
try { w.matchMedia = () => ({ matches: false, addEventListener(){}, removeEventListener(){} }); } catch (e) {}
w.ResizeObserver = class { observe(){} disconnect(){} };

function inject(code){ try { w.eval(code); } catch(e){} }
inject(news); inject(lme); inject(ph);

const re = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g;
let m, all = '';
while ((m = re.exec(html)) !== null) { if (m[1].trim()) all += m[1] + '\n'; }

// 确保关键 DOM 元素存在（index.html 已有，但单独抽取需要最小结构）
// 这里直接 eval 完整内联脚本，qaInitData 会从 window.NEWS_DATA 填充 QA_ROWS
w.eval(all + '\n;try{qaInitData();}catch(e){}');

const res = {};
const captured = {};
// mock fetch：捕获 /api/qa POST 的 body
w.fetch = (url, opts) => {
  captured.url = url;
  captured.opts = opts;
  if (opts && opts.body) { try { captured.body = JSON.parse(opts.body); } catch(e){} }
  return Promise.resolve({ ok: true, json: () => Promise.resolve({ answer: 'AI 模拟回答', source: 'deepseek', cited: (captured.body&&captured.body.context||[]).length, refs: [] }) });
};

// 取需要的元素
const fab = d.getElementById('qaFab');
const floatEl = d.getElementById('qaFloat');
const aiBtn = d.getElementById('qaFloatAi');
const input = d.getElementById('qaFloatInput');
const body = d.getElementById('qaFloatBody');

res.hasEls = !!(fab && floatEl && aiBtn && input && body);

// 配置真实 worker 地址 + 模拟探测成功
w.QA_API_BASE = 'https://mining-daily-qa.test.workers.dev';
w.QA_AI_ON = true;
// 若无 AI 按钮文本，补一个；直接设置可用
if (aiBtn) { aiBtn.disabled = false; }

// 输入问题并触发 qaFloatAsk
input.value = '铝土矿最近有什么进展';
try { w.qaFloatAsk(); } catch (e) { res.err = String(e); }

// qaFloatAsk 是异步的（内部 fetch.then），等待微任务
await new Promise((r) => setTimeout(r, 50));

res.apiUrl = captured.url || null;
res.apiMethod = captured.opts && captured.opts.method;
res.question = captured.body && captured.body.question;
res.contextIsArray = Array.isArray(captured.body && captured.body.context);
res.contextLen = (captured.body && captured.body.context || []).length;
// 验证 context 里的确含与"铝土矿"相关的新闻（qaFilter 命中）
res.contextSample = (captured.body && captured.body.context || []).slice(0, 2).map((c) => (c.t || '') + '|' + (c.u || ''));

res.debugTerms = w.qaExtractTerms ? w.qaExtractTerms('铝土矿最近有什么进展') : 'fn-missing';
res.debugAllTitles = (captured.body && captured.body.context || []).map((c) => (c.t || '') + (c.t && c.t.indexOf('铝') >= 0 ? '【含铝】' : ''));
res.PASS = res.hasEls && res.apiUrl === 'https://mining-daily-qa.test.workers.dev/api/qa' &&
           res.apiMethod === 'POST' && res.question === '铝土矿最近有什么进展' &&
           res.contextIsArray && res.contextLen > 0;

console.log('FRONTEND_TEST=' + JSON.stringify(res, null, 2));
process.exit(res.PASS ? 0 : 1);
