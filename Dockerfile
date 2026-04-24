FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends git openssh-client && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /root/.ssh && \
    ssh-keyscan github.com bitbucket.org gitlab.com >> /root/.ssh/known_hosts 2>/dev/null

WORKDIR /app

COPY pyproject.toml requirements.txt ./
COPY transync/ transync/
COPY config.default.yaml ./

RUN pip install --no-cache-dir .

RUN mkdir -p /root/.transync/repos && \
    transync init

EXPOSE 8090

CMD ["python", "-c", "from transync.config import load_config; from transync.web import create_app; app = create_app(load_config()); app.run(host='0.0.0.0', port=8090)"]
