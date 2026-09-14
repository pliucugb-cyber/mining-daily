FROM python:3.11-slim

# 装 git（拉候选池/推 gh-pages）+ cron（定时跑）
RUN apt-get update && apt-get install -y --no-install-recommends git cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# 时区设中国（日报按北京时间生成）
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 激活前填 DEEPSEEK_API_KEY / LME_TOKEN（见 .env.example）
COPY .env /app/.env

# 定时：容器已设 Asia/Shanghai，cron 按本地时区 = 北京时间 06:15 跑 B' pipeline
RUN echo "15 6 * * * root cd /app && /usr/local/bin/python -m bprime.pipeline >> /var/log/bprime.log 2>&1" > /etc/cron.d/bprime \
    && chmod 0644 /etc/cron.d/bprime \
    && crontab /etc/cron.d/bprime

# 前台运行 cron（容器不退）
CMD ["cron", "-f"]
