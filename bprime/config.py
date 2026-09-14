# -*- coding: utf-8 -*-
"""B' 配置：全部来自环境变量，与任何云账号解耦（代码资产化、订阅后置）。

激活只需：在服务器/容器里 export DEEPSEEK_API_KEY=... 与 LME_TOKEN=...，
无需改任何代码。
"""
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env(path=None):
    """零依赖加载 .env（仅本地调试用；docker/服务器用真实 env 变量时此函数无害跳过）。"""
    path = path or os.path.join(_ROOT, '.env')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass


_load_env()

# DeepSeek 兼容 OpenAI 协议；国内可达、无需翻墙
DEEPSEEK_BASE_URL = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
# 默认 deepseek-chat（即 v4-flash，非思考模式，够用且便宜）；judge 如需更强可换 deepseek-reasoner
DEEPSEEK_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')

# LME 行情 token（fetch_news 用）
LME_TOKEN = os.environ.get('LME_TOKEN', '')

# 数字落地校验守门：1=未落地即中止发布
STRICT = os.environ.get('VERIFY_NUMBERS_STRICT', '0') == '1'

# 报告日期 YYYY-MM-DD；空=今天
REPORT_DATE = os.environ.get('REPORT_DATE', '')


def report_today():
    import datetime
    return REPORT_DATE or datetime.date.today().isoformat()
