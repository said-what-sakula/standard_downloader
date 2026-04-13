# ── 后端镜像（官方 Playwright Python，Ubuntu 22.04）────────────────────────────
# 使用官方镜像：内置 Playwright 1.57.0 + Chromium，不受宿主机 glibc 版本限制
FROM mcr.microsoft.com/playwright/python:v1.57.0-jammy

WORKDIR /app

# 安装时区数据（tzlocal 依赖 zoneinfo 数据库，官方镜像未内置）
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata && \
    ln -fs /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata && \
    rm -rf /var/lib/apt/lists/*

# 使用国内 pip 镜像加速安装
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# ── 依赖安装（单独一层，利用 Docker 缓存）─────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── 应用代码 ──────────────────────────────────────────────────────────────────
COPY backend/    ./backend/
COPY downloaders/ ./downloaders/

# 预建日志和下载目录
RUN mkdir -p logs download

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
