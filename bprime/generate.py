# -*- coding: utf-8 -*-
"""B' 生成器：读候选池 -> 调 LLM 批量写中文摘要。

固定 prompt，不依赖每日 LLM 写脚本（这是与 WB 当前模式的根本区别：
代码固定、模型填空）。复用 generate_common.bucket 做分类。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bprime import config, llm


def _prompt_for(meta, source_text):
    foreign = '（境外源，须中文意译、保留英文原题、注明币种）' if meta.get('foreign') else ''
    return ('请为以下矿业新闻撰写摘要%s：\n标题：%s\n来源：%s\n原文：%s'
            % (foreign, meta.get('title', ''), meta.get('source', ''), source_text[:1500]))


def generate_summaries(candidates, llm_client, report):
    """candidates: list[dict]（候选池 item：url/title/summary/content/foreign/source/category/date）
    返回 list[(meta, summary)]。"""
    out = []
    for c in candidates:
        src = c.get('content') or c.get('summary') or ''
        prompt = _prompt_for(c, src)
        summary = llm_client.chat(prompt)
        meta = {k: c.get(k) for k in ('url', 'title', 'source', 'foreign',
                                      'category', 'date', 'orig_title')}
        out.append((meta, summary))
    print('[generate] 生成 %d 条摘要' % len(out))
    return out
