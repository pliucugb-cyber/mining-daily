# -*- coding: utf-8 -*-
"""
检索器主副本同步工具

主版本（生产侧，日报自动化在用）：
    <本脚本同级>/query_news.py
副本（专家包内，随包分发，必须自包含）：
    %USERPROFILE%/.workbuddy/plugins/marketplaces/my-experts/plugins/
        mine-news-expert/skills/mine-news-kb/scripts/query_news.py

为什么是双份而不是合并成一份：
    专家包必须自包含才能 zip 分发（引用外部路径会在同事机器上断链）；
    主版本必须留在生产侧（日报自动化不能反向依赖专家包，否则专家包一删日报就挂）。
    两边生命周期不同，只能靠同步保证一致。

用法：
    python deploy_query_news.py            # 有差异则覆盖同步，并复验
    python deploy_query_news.py --check    # 只检查，不写入
    python deploy_query_news.py --diff     # 显示差异内容后再同步
    python deploy_query_news.py --force    # 即使 hash 一致也强制覆盖
"""
import os
import sys
import shutil
import hashlib
import difflib

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(HERE, 'query_news.py')

EXPERT_REL = os.path.join(
    '.workbuddy', 'plugins', 'marketplaces', 'my-experts', 'plugins',
    'mine-news-expert', 'skills', 'mine-news-kb', 'scripts', 'query_news.py')
COPY = os.path.join(os.path.expanduser('~'), EXPERT_REL)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def read_lines(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.readlines()


def main():
    args = set(sys.argv[1:])

    if not os.path.isfile(MAIN):
        print('[错误] 主版本不存在: %s' % MAIN, file=sys.stderr)
        return 1
    if not os.path.isfile(COPY):
        print('[错误] 专家包副本不存在: %s' % COPY, file=sys.stderr)
        print('       请确认专家包目录是否完整，或是否改名/改路径。', file=sys.stderr)
        return 1

    h_main = sha256(MAIN)
    h_copy = sha256(COPY)
    same = (h_main == h_copy)

    print('主版本 : %s' % MAIN)
    print('        sha256 %s' % h_main[:12])
    print('副本   : %s' % COPY)
    print('        sha256 %s' % h_copy[:12])

    if same:
        print('\n✅ 两边一致，无需同步。')
        if not args & {'--force'}:
            return 0
        print('（--force 已指定，强制覆盖）')

    if args & {'--diff'}:
        print('\n--- 差异（主版本 → 副本）---')
        for line in difflib.unified_diff(
                read_lines(COPY), read_lines(MAIN),
                fromfile='副本', tofile='主版本', n=2):
            print(line.rstrip('\n'))
        print('--- 差异结束 ---')

    if args & {'--check'}:
        print('\n⚠️  两边不一致，需要同步（--check 模式未写入）。')
        print('   改完主版本后运行：python deploy_query_news.py')
        return 1

    shutil.copy2(MAIN, COPY)
    if sha256(COPY) != h_main:
        print('\n[错误] 同步后校验失败，请检查文件权限。', file=sys.stderr)
        return 1

    print('\n✅ 已同步并复验一致。')
    print('   建议回归：python "%s" --stats' % COPY)
    return 0


if __name__ == '__main__':
    sys.exit(main())
