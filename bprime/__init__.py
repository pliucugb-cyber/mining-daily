# -*- coding: utf-8 -*-
"""B' 无人化矿业日报骨架（代码资产化、订阅后置、待激活）。

架构：fetch(复用 fetch_news.py) -> generate(DeepSeek 批量写摘要) ->
judge/repair(数字落地校验 + 有界修复) -> 渲染(复用 generate_common) -> deploy(复用 deploy_pages.py)。

与 WB 当前模式的根本区别：生成逻辑是固定代码、模型只填空，
不依赖每日 LLM 临时写脚本。代码与云账号解耦——将来买轻量服务器 +
充 DEEPSEEK_API_KEY 即"激活"，不是重新造。
"""
__version__ = '0.1.0'
