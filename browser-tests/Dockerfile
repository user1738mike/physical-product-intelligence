FROM mcr.microsoft.com/playwright:v1.64.1-noble
USER root
RUN apt-get update && apt-get install -y --no-install-recommends libnss3-tools \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /tests
COPY package.json package-lock.json ./
RUN npm ci && mkdir -p /home/pwuser/.pki/nssdb \
    && chown -R pwuser:pwuser /tests /home/pwuser/.pki
COPY --chown=pwuser:pwuser . .
USER pwuser
ENTRYPOINT ["sh", "/tests/run.sh"]
