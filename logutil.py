# -*- coding: utf-8 -*-
"""
logutil.py — 全仓库统一的日志出口。

背景
----
仓库里 47 个 Python 脚本历史上全部用 print()，没有日志级别、没有时间戳，
排查 06:00 自动化失败时只能靠肉眼分辨哪一步的输出。本模块提供统一格式：

    [08:52:00] INFO  fetch_news: 抓取完成 42 条

设计约束（改这里前先看）
------------------------
1. **默认写 stdout，不是 stderr。**
   标准库 logging 默认走 stderr，但本仓库的自动化/人工运维是靠「读命令输出」
   判断成败的，很多地方只捕获 stdout。把既有输出挪去 stderr 会让它们静默失效。
   需要 stderr 时设环境变量 MINING_LOG_STREAM=stderr。

2. **MINING_LOG_PLAIN=1 可一键退回裸消息**（不加时间戳/级别/名字），
   输出与改造前的 print() 逐字节一致。这是应急开关：万一自动化里存在
   `grep '^✅'` 这类行首锚定的匹配，设这个变量即可恢复，无需回滚代码。

3. 绝不自动给根 logger 装 handler、也不调 basicConfig——
   被 import 时不产生任何副作用，print() 老脚本 import 它也不会被污染。

用法
----
    from logutil import get_logger
    log = get_logger('fetch_news')
    log.info('抓取完成 %d 条', n)      # 用 %s 惰性格式化，别用 f-string
    log.warning('源 %s 超时', name)
    log.error('写入失败'); raise

新增脚本一律用本模块；历史脚本保留 print()，见 requirements.txt 顶部说明。
"""
import logging
import os
import sys

__all__ = ['get_logger', 'LOG_FORMAT', 'DATE_FORMAT']

DATE_FORMAT = '%H:%M:%S'
LOG_FORMAT = '[%(asctime)s] %(levelname)-5s %(name)s: %(message)s'
PLAIN_FORMAT = '%(message)s'

# 已创建的 logger 缓存，避免重复 addHandler
_REGISTRY = {}


class _DisplayNameFilter(logging.Filter):
    """把 logger 的真实名字改回展示名。

    logging.getLogger(name) 是**按名字全局单例**的：同一个 name 取两次拿到的是
    同一个对象，后一次 addHandler 会覆盖前一次。所以「同名但输出流不同」的两个
    logger（典型：正常输出走 stdout、错误走 stderr）必须底层用不同的内部名字，
    否则二者会串到同一个流上。内部名字加后缀区分，再用本 filter 把 record.name
    改回用户看到的展示名，输出格式不受影响。
    """

    def __init__(self, display_name):
        super().__init__()
        self._display_name = display_name

    def filter(self, record):
        record.name = self._display_name
        return True


def _target_stream():
    """默认 stdout（与 print 一致）；MINING_LOG_STREAM=stderr 时改 stderr。"""
    return sys.stderr if os.environ.get('MINING_LOG_STREAM', '').lower() == 'stderr' else sys.stdout


def _plain_mode():
    return os.environ.get('MINING_LOG_PLAIN', '') not in ('', '0', 'false', 'False')


def get_logger(name=None, stream=None):
    """取一个统一格式的 logger。

    name   省略时取调用方脚本的文件名（去 .py），输出里能直接看出是哪一步。
    stream 显式指定输出流。给原来就 `print(..., file=sys.stderr)` 的错误分支用，
           保留它原本走 stderr 的行为，不要把错误混进正常输出。

    线程安全：logging 自带锁；此处只多一层 dict 查找。
    """
    global _CONFIGURED
    if name is None:
        name = os.path.splitext(os.path.basename(sys.argv[0] or 'run'))[0] or 'run'

    target = stream if stream is not None else _target_stream()
    key = (name, getattr(target, 'name', id(target)))
    if key in _REGISTRY:
        return _REGISTRY[key]

    fmt = PLAIN_FORMAT if _plain_mode() else LOG_FORMAT
    handler = logging.StreamHandler(stream=target)
    handler.setFormatter(logging.Formatter(fmt, datefmt=DATE_FORMAT))

    # 内部名字带流后缀，避免同名不同流的 logger 互相覆盖 handler（见 _DisplayNameFilter）
    internal = f'{name}|{getattr(target, "name", id(target))}'
    logger = logging.getLogger(internal)
    logger.setLevel(logging.DEBUG)
    logger.handlers[:] = [handler]
    logger.addFilter(_DisplayNameFilter(name))
    # 关键：不要让日志往上冒泡到 root，否则 root 被 basicConfig 后会打两遍
    logger.propagate = False

    _REGISTRY[key] = logger
    return logger


if __name__ == '__main__':
    log = get_logger('logutil')
    log.debug('debug 级')
    log.info('info 级')
    log.warning('warning 级')
    log.error('error 级')
