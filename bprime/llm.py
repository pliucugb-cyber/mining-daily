# -*- coding: utf-8 -*-
"""DeepSeek LLM 客户端（纯标准库，零第三方依赖）。

- 真实模式：urllib 调 /chat/completions（无 requests 依赖，云服务器直接跑）。
- MOCK 模式：无 DEEPSEEK_API_KEY 或 --mock 时，用确定性离线 Provider 跑通流程，
  便于本地"搭通待激活"、不花 token、不依赖网络。

代码资产化：真实与 mock 同一份接口，激活只是把 key 填上。
"""
import json
import re
import sys
import os
import urllib.request
import urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bprime import config

_SYSTEM = ("你是矿业资讯速览的中文编辑。读取给定信源原文，撰写 100-200 字中文摘要："
           "只陈述事实、保留关键数字与单位、不编造、不添加原文没有的信息。"
           "境外源须中文意译、保留英文原题、注明币种。输出纯摘要文本，不要解释、不要标题。")


def _chat_real(model, api_key, base_url, messages, temperature=0.3):
    body = json.dumps({'model': model, 'messages': messages,
                       'temperature': temperature, 'max_tokens': 600}).encode('utf-8')
    req = urllib.request.Request(base_url.rstrip('/') + '/chat/completions', data=body,
                                 headers={'Authorization': 'Bearer ' + api_key,
                                          'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        return data['choices'][0]['message']['content'].strip()
    except urllib.error.HTTPError as e:
        raise RuntimeError('DeepSeek HTTP %s: %s' % (e.code, e.read().decode('utf-8', 'ignore')[:300]))
    except Exception as e:
        raise RuntimeError('DeepSeek 调用失败: %s' % e)


def _chat_mock(messages, temperature=0.3):
    user = messages[-1]['content'] if messages else ''
    src = user.split('原文：', 1)[1] if '原文：' in user else ''
    src = src.strip()
    # 仅取原文前段作离线草稿（数字随原文带单位，便于 verify_numbers 落地校验通过）
    head = re.sub(r'\s+', ' ', src[:160])
    return '【离线草稿·待激活】%s' % head


class LLM:
    def __init__(self, mock=False):
        self.mock = mock or not config.DEEPSEEK_API_KEY
        if self.mock:
            print('[llm] MOCK 模式（无 DEEPSEEK_API_KEY 或 --mock）：离线确定性输出，不花 token')
        else:
            print('[llm] 真实模式：%s model=%s' % (config.DEEPSEEK_BASE_URL, config.DEEPSEEK_MODEL))

    def chat(self, user_prompt, temperature=0.3):
        messages = [{'role': 'system', 'content': _SYSTEM},
                    {'role': 'user', 'content': user_prompt}]
        if self.mock:
            return _chat_mock(messages, temperature)
        return _chat_real(config.DEEPSEEK_MODEL, config.DEEPSEEK_API_KEY,
                          config.DEEPSEEK_BASE_URL, messages, temperature)
