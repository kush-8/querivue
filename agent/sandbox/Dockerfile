# Querivue sandbox execution environment
# Built for isolated Python/SQL execution with strict resource controls

FROM python:3.12-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    bubblewrap \
    && rm -rf /var/lib/apt/lists/*

# Install DuckDB
RUN pip install --no-cache-dir duckdb==1.0.0 pyarrow==16.0.0

# Install Python packages for data analysis and visualization
RUN pip install --no-cache-dir \
    pandas==3.1.1 \
    plotly==7.1.0 \
    kaleido==1.5.2 \
    pillow==13.0.0

# Create sandbox user
RUN groupadd -r sandbox && useradd -r -g sandbox -d /home/sandbox -s /bin/bash sandbox
RUN mkdir -p /home/sandbox && chown sandbox:sandbox /home/sandbox

# Create working directories
RUN mkdir -p /workspace/inputs /workspace/scratch /workspace/outputs /workspace/quarantine /workspace/validator \
    && chown -R sandbox:sandbox /workspace

# Switch to sandbox user
USER sandbox
WORKDIR /workspace

# Set environment
ENV PYTHONPATH=/workspace/scratch \
    QUERIVUE_EVIDENCE_DIR=/workspace/inputs \
    QUERIVUE_OUTPUT_DIR=/workspace/outputs \
    HOME=/home/sandbox

# Default command
CMD ["python3", "-c", "print('Sandbox ready')"]