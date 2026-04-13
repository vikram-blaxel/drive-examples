FROM python:3.11-slim

COPY --from=ghcr.io/blaxel-ai/sandbox:latest /sandbox-api /usr/local/bin/sandbox-api

# System packages + prerequisites for security tools
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    gnupg \
    netcat-openbsd \
    libpq-dev \
    postgresql \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Trivy — vulnerability scanner for dependencies, containers, misconfigs, and secrets
RUN wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key \
      | gpg --dearmor | tee /usr/share/keyrings/trivy.gpg > /dev/null && \
    echo "deb [signed-by=/usr/share/keyrings/trivy.gpg] https://aquasecurity.github.io/trivy-repo/deb generic main" \
      | tee /etc/apt/sources.list.d/trivy.list && \
    apt-get update && apt-get install -y trivy && rm -rf /var/lib/apt/lists/*

# Gitleaks — detect secrets and credentials committed to git history
RUN curl -sSfL https://raw.githubusercontent.com/gitleaks/gitleaks/master/scripts/install.sh \
    | sh -s -- -b /usr/local/bin

# Python security tools
RUN pip install --no-cache-dir \
    bandit \
    semgrep \
    safety \
    pip-audit

# Python code quality tools
RUN pip install --no-cache-dir \
    ruff \
    pylint \
    mypy

# Python test tools
RUN pip install --no-cache-dir \
    pytest \
    pytest-cov \
    coverage

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
