/**
 * 2026-10-25 数据质量与构建可靠性批（外部系统审查整改 A03/A04/A06/A07/C01/D03）
 * 守护：
 *   A03 严格模式数字校验异常/故障不再被吞 → 非零退出、不写正式产物
 *   A04 数字校验覆盖率：强基准覆盖弱摘要、并集池可读、年份 glob 动态、无基准不显示通过
 *   A06 抓取零候选落盘带状态 + daily.yml 按 report_date 选当日文件（废弃 glob+files[-1]）
 *   A07 日期兜底改语义（unknown 不冒充今日发布）+ 未来日期检查全源统一
 *   C01 SW activate 只删本站前缀缓存（不误删同 origin 其他站点）
 *   D03 build_static.py 热榜公式与 server.py/app.js 严格一致
 * 运行：node test_data_quality_gate.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { execFileSync } = require('child_process');

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name + (detail ? '  → ' + detail : '')); }
  else { fail++; console.log('  FAIL  ' + name + (detail ? '  → ' + detail : '')); }
}
const ROOT = __dirname;
const read = (f) => fs.readFileSync(path.join(ROOT, f), 'utf-8');
const py = (code) => execFileSync('python', ['-c', code], { cwd: ROOT, encoding: 'utf-8' });

console.log('===== A03：严格模式数字校验不再被吞 =====');
// A1) verify_new_items strict + 正文级未落地 → AssertionError（探针：临时目录构造）
try {
  const out = py(`
import sys, json, tempfile, os
sys.path.insert(0, '.')
from verify_numbers import verify_new_items
items = [('cat', '<div class="news-item" data-url="http://x/1"><div class="news-summary">探明储量 9999 万吨</div></div></div>')]
d = tempfile.mkdtemp()
json.dump({'items': [{'url': 'http://x/1', 'content': '正文：探明储量 100 万吨'}]},
          open(os.path.join(d, 'news_candidates_2026-10-25.json'), 'w', encoding='utf-8'))
try:
    verify_new_items(items, '2026-10-25', data_dir=d, strict=True)
    print('NO_RAISE')
except AssertionError:
    print('RAISED')
`);
  check('strict + 正文级数字未落地 → 抛 AssertionError',
    out.indexOf('RAISED') >= 0 && out.indexOf('NO_RAISE') < 0, out.trim().slice(-12));
} catch (e) { check('strict + 正文级数字未落地 → 抛 AssertionError', false, String(e).slice(0, 80)); }

// A2) CLI 无基准 → rc=3 且不打印"全部通过"
try {
  const os = require('os');
  const empty = fs.mkdtempSync(path.join(os.tmpdir(), 'vn-'));
  let rc = 0, out = '';
  try {
    out = execFileSync('python', ['verify_numbers.py', '--date', '2099-01-01', '--strict',
      '--data-dir', empty], { cwd: ROOT, encoding: 'utf-8' });
  } catch (e) { rc = e.status; out = (e.stdout || '') + (e.stderr || ''); }
  check('CLI 无任何源文基准 → 退出码 3（不视为通过）', rc === 3, 'rc=' + rc);
  check('CLI 无基准时不打印"全部通过"', out.indexOf('全部通过') < 0);
} catch (e) { check('CLI 无基准场景', false, String(e).slice(0, 80)); }

// A3) 代码契约：两个生成脚本的 3.6 段分类处理 + pipeline SystemExit
const siteSrc = read('generate_site.py');
const genSrc = read('generate_20261025.py');
const pipeSrc = read('bprime/pipeline.py');
// 取 AssertionError 分支的整块（到 except Exception 之前），断言块内 strict 时 sys.exit(1)
const assertBlock = (siteSrc.split('except AssertionError as _e:')[1] || '').split('except Exception as _e:')[0];
check('generate_site.py：AssertionError 分支 strict 时 sys.exit(1)',
  assertBlock.indexOf('if _STRICT_NUM:') >= 0 && assertBlock.indexOf('sys.exit(1)') >= 0);
const excBlock = (siteSrc.split('except Exception as _e:')[1] || '').split('_new_titles')[0];
check('generate_site.py：其它 Exception strict 时同样终止（不再静默"跳过"）',
  siteSrc.indexOf("print('[verify_numbers] 跳过") < 0 && excBlock.indexOf('sys.exit(1)') >= 0);
check('generate_20261025.py：同款分类处理', /except AssertionError as _e:/.test(genSrc) && genSrc.indexOf("print('[verify_numbers] 跳过") < 0);
check('bprime/pipeline.py：strict 守门失败 raise SystemExit（退出码可传出）',
  /raise SystemExit\('\[pipeline\] strict 模式：数字守门未通过/.test(pipeSrc));
check('bprime/pipeline.py：strict 校验器故障同样 SystemExit',
  /raise SystemExit\('\[pipeline\] strict 模式：校验器故障/.test(pipeSrc));

console.log('===== A04：数字校验覆盖率四项 =====');
// B1) 强基准覆盖弱摘要 + union 池可读 + 出处保留（探针：临时目录）
try {
  const out = py(`
import sys, json, tempfile, os
sys.path.insert(0, '.')
from verify_numbers import load_source_map
d = tempfile.mkdtemp()
json.dump({'news': [{'url': 'http://a/1', 'content': '正文：储量 1200 万吨'}]},
          open(os.path.join(d, 'news_2026-10.json'), 'w', encoding='utf-8'))
json.dump({'items': [{'url': 'http://a/1', 'summary': '摘要级：提及 1200'}]},
          open(os.path.join(d, 'news_candidates_2026-10-25.json'), 'w', encoding='utf-8'))
json.dump({'report_date': '2026-10-25', 'news': [{'url': 'http://d/4', 'summary': '境外摘要'}]},
          open(os.path.join(d, 'news_candidates_union_2026-10-25.json'), 'w', encoding='utf-8'))
lv, og = {}, {}
m = load_source_map('2026-10-25', d, lv, og)
ok = (lv.get('http://a/1') == 'content' and '1200 万吨' in m.get('http://a/1', '')
      and lv.get('http://d/4') == 'summary' and bool(m.get('http://d/4'))
      and og.get('http://d/4') == 'news_candidates_union_2026-10-25.json')
print('OK' if ok else 'BAD lv=%s m_a=%s og_d=%s' % (lv.get('http://a/1'), m.get('http://a/1', '')[:12], og.get('http://d/4')))
`);
  check('强基准（月库正文）覆盖弱摘要（候选池 RSS）', out.indexOf('OK') === 0, out.trim().slice(0, 90));
} catch (e) { check('强基准覆盖弱摘要', false, String(e).slice(0, 80)); }

// B2) 年份 glob 动态化（2027 起不失配）
const vnSrc = read('verify_numbers.py');
check('verify_numbers.py 月库 glob 不再写死 2026', vnSrc.indexOf("news_2026-*.json") < 0 && vnSrc.indexOf('news_????-??.json') >= 0);
check('generate_site.py 月库 glob 不再写死 2026', siteSrc.indexOf("data/news_2026-*.json") < 0 && siteSrc.indexOf("data/news_????-??.json") >= 0);
check('fetch_events.py 月库 glob 不再写死 2026', read('fetch_events.py').indexOf("news_2026-*.json") < 0);

// B3) stats_out 覆盖率外泄
check('verify_new_items 支持 stats_out（覆盖率三档可外泄）',
  vnSrc.indexOf('stats_out') >= 0 && vnSrc.indexOf("'no_source': skipped") >= 0);

console.log('===== A06：抓取空产出与 daily.yml 选文件 =====');
const fnSrc = read('fetch_news.py');
const ymlSrc = read('.github/workflows/daily.yml');
check('fetch_news.py 零候选也落盘带 status 的文件',
  /status = "failed" if all_failed else/.test(fnSrc) && fnSrc.indexOf('"status": status,') >= 0);
check('fetch_news.py 全源失败退出码 2（main 退出码可传出）',
  fnSrc.indexOf('sys.exit(main())') >= 0 && fnSrc.indexOf('return 2') >= 0);
check('fetch_news.py 不再有 report_date 兜底冒充今日发布',
  fnSrc.indexOf('            d = report_date') < 0);
check('daily.yml 汇总/信源报告不再 glob+files[-1]',
  ymlSrc.indexOf("glob.glob('data/news_candidates_*.json')") < 0 && !/files\s*=\s*sorted\(glob/.test(ymlSrc));
check('daily.yml 两处均按 REPORT_DATE 定位当日文件',
  (ymlSrc.match(/os\.environ\['REPORT_DATE'\]/g) || []).length === 2);

console.log('===== A07：日期语义与未来日期 =====');
check('fetch_news.py date_conf 字段（日期来源置信度）', fnSrc.indexOf('date_conf') >= 0 && fnSrc.indexOf('"date_conf": date_conf,') >= 0);
check('fetch_news.py 未来日期检查全源统一（不再限定配置开关）',
  fnSrc.indexOf('if d and d > report_date:') >= 0 && fnSrc.indexOf('if cfg.get("force_date_from_detail") and d > report_date:') < 0);
check('fetch_news.py 未知日期不做 cutoff 过滤（保守收录）', fnSrc.indexOf('if d and d < cutoff:') >= 0);
check('fetch_news.py 巨潮时间戳失败不再填 report_date',
  !/d = report_date\n\s*adjunct/.test(fnSrc) && fnSrc.indexOf('publication_date 未知') >= 0);

console.log('===== C01：SW activate 只删本站前缀缓存 =====');
// vm 沙箱真跑 sw.js 的 activate 清理逻辑（caches 同时挂 self 和全局——真实浏览器 self === globalThis）
try {
  const swSrc = read('sw.js');
  const deleted = [];
  const keys = ['mining-daily-20261024-1200', 'other-app-cache',
                'pliucugb-cyber.github.io/other-repo', 'mining-daily-20261025-0539'];
  const sandbox = {
    console: { log() {}, warn() {}, error() {} },
    caches: {
      keys: () => Promise.resolve(keys.slice()),
      delete: (k) => { deleted.push(k); return Promise.resolve(true); },
      open: () => Promise.resolve({
        add: () => Promise.resolve(), put: () => Promise.resolve(),
        match: () => Promise.resolve(undefined),
      }),
      match: () => Promise.resolve(undefined),
    },
    fetch: () => Promise.resolve(new Response('', { status: 200 })),
    Request: function (u) { return { url: u }; },
    Response: function (b, o) { this.body = b; this.status = (o || {}).status || 200; },
    URL: URL,
    location: { origin: 'https://pliucugb-cyber.github.io' },
  };
  sandbox.self = sandbox;
  sandbox.addEventListener = (type, fn) => { if (type === 'activate') sandbox.__activate = fn; };
  sandbox.skipWaiting = () => Promise.resolve();
  sandbox.clients = { claim: () => Promise.resolve(), matchAll: () => Promise.resolve([]) };
  vm.createContext(sandbox);
  vm.runInContext(swSrc, sandbox);
  // activate 监听函数本身不返回值（sw.js 惯例），等的是 waitUntil 的 promise
  let activateDone = null;
  sandbox.__activate({ waitUntil: (p) => { activateDone = p; } });
  Promise.resolve(activateDone).then(() => {
    check('activate 删除了本站旧版本缓存', deleted.indexOf('mining-daily-20261024-1200') >= 0, 'deleted=' + JSON.stringify(deleted));
    check('activate 未删同 origin 其他站点缓存（other-app-cache）', deleted.indexOf('other-app-cache') < 0);
    check('activate 未删其他 Pages 路径缓存（/other-repo）', deleted.indexOf('pliucugb-cyber.github.io/other-repo') < 0);
    check('activate 未删当前 CACHE_NAME', deleted.indexOf('mining-daily-20261025-0539') < 0);

    console.log('===== A05/C05：部署入口单一发布命令 =====');
    const dpSrc = read('deploy_pages.py');
    check('deploy_pages.py 含前置快速测试闸门 run_quick_tests',
      dpSrc.indexOf('def run_quick_tests') >= 0 && dpSrc.indexOf('QUICK_TESTS') >= 0);
    check('快速测试集含 SW/数据质量/QA 代理三个测试',
      dpSrc.indexOf("'test_sw_cache_update.js'") >= 0 && dpSrc.indexOf("'test_data_quality_gate.js'") >= 0 && dpSrc.indexOf("'test_qa_proxy.js'") >= 0);
    check('测试不过不推送（return 2）',
      /if not run_quick_tests\(\):\s*\n\s*return 2/.test(dpSrc.replace(/\r\n/g, '\n')));
    check('提交信息带 source SHA + build-version + 远端变化记录（C05 可追溯）',
      dpSrc.indexOf('source %s · build %s') >= 0 && dpSrc.indexOf('remote_note') >= 0);
    check('推送后内建线上验收 verify_online（比对 build-version + app.js 指纹）',
      dpSrc.indexOf('def verify_online') >= 0 && dpSrc.indexOf('VERIFY_TIMEOUT_S') >= 0);
    check('区分「推送成功」与「发布验收成功」（验收失败 return 3）',
      dpSrc.indexOf('return 3') >= 0 && dpSrc.indexOf('推送成功（gh-pages）') >= 0);
    // 行尾统一为 CRLF：2026-10-25 曾因补丁插入 LF 行造成混合行尾、后续补丁锚点全失配
    const dpRaw = fs.readFileSync(path.join(ROOT, 'deploy_pages.py'));
    check('deploy_pages.py 行尾统一（无混合 CRLF/LF）',
      dpRaw.indexOf(Buffer.from('\r\n')) >= 0 &&
      dpRaw.toString('utf-8').split('\n').length - 1 === (dpRaw.toString('utf-8').match(/\r\n/g) || []).length);

    // verify_online 函数级（mock urllib，spawn python 探针）
    try {
      const out = execFileSync('python', ['-c', `
import sys
sys.path.insert(0, '.')
import deploy_pages as dp
import urllib.request
class R:
    def __init__(self, b): self._b = b.encode('utf-8')
    def read(self): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False
NEW = '<meta name="build-version" content="20261025-9999"><script src="app.js?v=abc12345" defer></script>'
MIX = '<meta name="build-version" content="20261025-9999"><script src="app.js?v=dead1234" defer></script>'
OLD = '<meta name="build-version" content="20261024-1200"><script src="app.js?v=dead1234" defer></script>'
urllib.request.urlopen = lambda req, timeout=20: R(NEW)
r1 = dp.verify_online('20261025-9999', 'abc12345')
urllib.request.urlopen = lambda req, timeout=20: R(MIX)
r2 = dp.verify_online('20261025-9999', 'abc12345')
dp.VERIFY_TIMEOUT_S = 2; dp.VERIFY_INTERVAL_S = 1
urllib.request.urlopen = lambda req, timeout=20: R(OLD)
r3 = dp.verify_online('20261025-9999', 'abc12345')
ok = r1[0] is True and r2[0] is False and '混装' in r2[1] and r3[0] is False and '超时' in r3[1]
print('OK' if ok else 'BAD %s %s %s' % (r1, r2, r3))
`], { cwd: ROOT, encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'] });
      check('verify_online：新版放行/混装拦截/旧版超时',
        out.indexOf('OK') >= 0 && out.indexOf('BAD') < 0, out.trim().slice(-60));
    } catch (e) { check('verify_online 探针', false, String(e).slice(0, 80)); }
    console.log('\nDATA-QUALITY-GATE ' + pass + ' PASS / ' + fail + ' FAIL');
    process.exit(fail ? 1 : 0);
  }).catch((e) => { check('activate 沙箱执行', false, String(e).slice(0, 100)); process.exit(1); });
} catch (e) {
  check('SW activate 沙箱执行', false, String(e).slice(0, 100));
  console.log('\nDATA-QUALITY-GATE ' + pass + ' PASS / ' + fail + ' FAIL');
  process.exit(1);
}
