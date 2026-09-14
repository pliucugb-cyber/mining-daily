# -*- coding: utf-8 -*-
"""B' judge/repair 层：数字落地校验 + 有界修复一次 + 分级输出。

直接复用 verify_numbers（WB 与 B' 共用同一份校验），避免重复实现。
分级：
  auto    —— 通过，自动发布；
  review  —— 无源文基准或需人工点一眼（残差，分级发布闸）；
  dropped —— 数字严重失实且修复后仍不符，丢弃不发布（避免带病公开）。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from verify_numbers import verify_summary

_REPAIR_SYS = ("你是矿业新闻事实核查员。给定一条摘要与其源文，若摘要中数字与源文不符，"
               "只能依据源文修正摘要里的数字，不得改写其他内容、不得引入源文没有的信息。"
               "输出修正后的完整摘要。")


def judge_repair(items, llm_client, src_map, report):
    """items: list[(meta, summary)]；src_map: {url: 源文}。
    返回 (graded, stats)：graded=list[(meta, summary, grade)]；grade∈{auto,review,dropped}。"""
    graded = []
    stats = {'auto': 0, 'review': 0, 'dropped': 0}
    for meta, summary in items:
        url = meta.get('url', '')
        source = src_map.get(url, '')
        if not source:
            # 无基准：保守交人工（skeptical default，宁可人工看）
            graded.append((meta, summary, 'review'))
            stats['review'] += 1
            continue
        miss = verify_summary(summary, source)
        if not miss:
            graded.append((meta, summary, 'auto'))
            stats['auto'] += 1
            continue
        # 有未落地数字 -> 有界修复一次（只基于源文，严禁无界改写）
        repair_prompt = ('摘要：%s\n\n源文：%s\n\n请依据源文修正摘要中不符的数字，输出修正后完整摘要。'
                         % (summary, source[:1500]))
        fixed = None
        try:
            fixed = llm_client.chat(repair_prompt)
        except Exception as e:
            print('[judge] 修复调用失败 %s: %s' % (url, e))
        if fixed:
            miss2 = verify_summary(fixed, source)
            if not miss2:
                graded.append((meta, fixed, 'auto'))
                stats['auto'] += 1
                continue
            # 修复后仍失败 -> 丢弃（避免带病发布），留档供人工复盘
            graded.append((meta, fixed, 'dropped'))
            stats['dropped'] += 1
            print('[judge] 丢弃（修复后仍数字不符）：%s' % url)
        else:
            graded.append((meta, summary, 'dropped'))
            stats['dropped'] += 1
    print('[judge] 分级 auto=%d review=%d dropped=%d' % (stats['auto'], stats['review'], stats['dropped']))
    return graded, stats
