FROM python:3.13.16-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock requirements-ai.lock .
ARG INSTALL_AI=false
RUN pip install --no-cache-dir -r requirements.lock && useradd --create-home --uid 10001 app
RUN if [ "$INSTALL_AI" = "true" ]; then pip install --no-cache-dir -r requirements-ai.lock; fi
RUN mkdir -p /var/lib/ppi/private /var/lib/ppi/backups /var/lib/ppi/restores \
    && chown -R app:app /var/lib/ppi
COPY --chown=app:app . .
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--config", "gunicorn.conf.py"]
