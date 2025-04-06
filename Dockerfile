FROM python:3.13-alpine3.21

LABEL maintainer="Claudio Poli <claudio@icorete.ch>" \
      description="Runs a Python script to backup PostgreSQL databases to S3."

# Set the working directory
WORKDIR /app

# Create a non-root user and group
# Using -S for system user/group (no password, no home dir needed)
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
RUN chown appuser:appgroup /app

# Install system dependencies
# - Use postgresql-client for broader compatibility
# - Add openssl explicitly as it's used by the script
# - Add tini as a lightweight init system
# - Combine update, install, and cleanup in one layer
RUN apk update && apk add --no-cache \
    tini \
    postgresql-client \
    gzip \
    openssl \
    && rm -rf /var/cache/apk/*

# Install Python dependencies (AWS CLI)
# Run pip install in a separate layer after system dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir awscli

# Copy only the Python script needed
COPY backup.py ./

# Set correct ownership and permissions for the scripts
# Ensure the non-root user can execute run.sh
RUN chown appuser:appgroup backup.py

# Switch to the non-root user
USER appuser

# Define environment variables (defaults primarily for documentation)
# Removed S3_S3V4 as it's usually not needed
ENV S3_ACCESS_KEY_ID="" \
    S3_SECRET_ACCESS_KEY="" \
    S3_BUCKET="" \
    S3_ENDPOINT="" \
    S3_REGION="us-west-1" \
    S3_PREFIX="backup" \
    POSTGRES_HOST="" \
    POSTGRES_PORT="5432" \
    POSTGRES_USER="" \
    POSTGRES_PASSWORD="" \
    ENCRYPTION_PASSWORD="" \
    DELETE_OLDER_THAN="" \
    LOG_LEVEL="INFO"

# Use tini as the entrypoint, executing the python script directly
ENTRYPOINT ["/sbin/tini", "--", "python3", "backup.py"]

# CMD is now effectively redundant as ENTRYPOINT specifies the full command,
# but leaving it empty or commented out is fine.
# CMD ["python3", "backup.py"]
CMD []
