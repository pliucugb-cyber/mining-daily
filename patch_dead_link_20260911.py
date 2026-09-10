# -*- coding: utf-8 -*-
"""删除 index.html 中重复且已 404 的旧条目（中国有色金属工业协会 61959）。

背景：fix_links_20260911.py 里的 OLD_MG 常量写成了 .../61959.htm（少了 l），
所以 index.html 中真实存在的 .../61959.html 条目没被替换掉，与换源后的
cnmn 473839 条目重复同题。该 cnmn 条目为有效镜像，本条目 404 → 删除。

删除后做 div 收支自检（栈法，排除 script/style），通过才 os.replace 落盘。
"""
import io, os, re

os.chdir(r'C:\Users\中铝矿业投并部\mining-daily')
P = 'index.html'
DEAD = 'https://www.chinania.org.cn/html/hangyexinwen/guoneixinwen/2026/0908/61959.html'

h = io.open(P, encoding='utf-8').read()
ORIG = len(h)

pat = re.compile(r'<div class="news-item"[^>]*' + re.escape(DEAD) + r'.*?</div></div>', re.S)
h2, k = pat.subn('', h)
assert k == 1, '命中数不符：%d' % k
assert DEAD not in h2, '仍残留旧 URL'


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
print('patched: removed=%d size %d -> %d items=%d' % (
    k, ORIG, len(h2), len(re.findall(r'<div class="news-item', h2))))
