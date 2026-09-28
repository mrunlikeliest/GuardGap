FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install -r requirements.lock
COPY pyproject.toml README.md ./
COPY guardgap ./guardgap
RUN pip install --no-deps . && useradd --uid 10001 --create-home guardgap && mkdir -p /data && chown guardgap:guardgap /data
USER 10001
ENV DATABASE_URL=sqlite:////data/guardgap.db PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/healthz',timeout=3)"
CMD ["python", "-m", "guardgap", "serve", "--host", "0.0.0.0"]
