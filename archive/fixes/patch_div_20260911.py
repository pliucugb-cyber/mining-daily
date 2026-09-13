# -*- coding: utf-8 -*-
"""修复 index.html 中因 fix_links_20260911.py 正则误吞导致的破损 news-item。

症状：往期区出现
  <div class="news-item" data-url="...473839<span class="src">中国有色金属报</span> · 09-08</div>
        <div class="news-summary">...</div></div>
（丢了 news-head / news-meta 两个开标签），多出 1 个 </div>，preflight div 收支不平衡。

该条目与稍后生成出来的同 URL 条目重复（同一篇镁行业新标准报道），且原始 URL 已由
fix_links 就地改写，重新生成时又按新 URL 生成了一条完整条目 → 直接删除这条破损残片。

修完就地做 div 收支自检（栈法，排除 script/style），通过才 os.replace 落盘。
"""
import io, os, re

os.chdir(r'C:\Users\中铝矿业投并部\mining-daily')
P = 'index.html'

h = io.open(P, encoding='utf-8').read()
ORIG = len(h)

# 1) 删除破损残片
pat = re.compile(
    r'<div class="news-item"[^>]{0,200}?473839<span class="src">中国有色金属报</span>'
    r'.{0,80}?</div><div class="news-summary">.{0,800}?</div></div>', re.S)
h2, k = pat.subn('', h)
assert k == 1, '破损残片匹配数不符：%d' % k

# 2) 顺手确认没有再残留 473839 的破损写法
assert '473839<span' not in h2, '仍存在 473839 破损写法'

# 3) div 收支自检（与 preflight_check.check_div_balance 同算法）
def strip_keep_lines(t):
    t = re.sub(r'<script\b[^>]*>.*?</script>', lambda m: re.sub(r'[^\n]', '', m.group(0)), t, flags=re.S)
    t = re.sub(r'<style\b[^>]*>.*?</style>', lambda m: re.sub(r'[^\n]', '', m.group(0)), t, flags=re.S)
    return t

c = strip_keep_lines(h2)
stack, extra = [], 0
for m in re.finditer(r'<div\b[^>]*>|</div>', c):
    if m.group(0) == '</div>':
        if stack:
            stack.pop()
        else:
            extra += 1
    else:
        stack.append(1)
assert extra == 0 and not stack, 'div 仍不平衡：extra=%d unclosed=%d' % (extra, len(stack))

buf = h2.encode('utf-8')
assert len(buf) > ORIG * 0.9, 'index.html 疑似被截断'
with io.open(P + '.tmp', 'w', encoding='utf-8') as f:
    f.write(h2)
os.replace(P + '.tmp', P)
print('patched: removed=%d size %d -> %d' % (k, ORIG, len(h2)))
