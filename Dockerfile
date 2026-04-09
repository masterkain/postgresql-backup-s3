FROM postgres:18.3-alpine3.22

LABEL maintainer="Claudio Poli <claudio@icorete.ch>" \
      description="Runs a Python script to backup PostgreSQL databases to S3."

# Set the working directory
WORKDIR /app

# Create a non-root user and group
# Using -S for system user/group (no password, no home dir needed)
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
RUN chown appuser:appgroup /app

# Install runtime dependencies for the Python backup script.
RUN apk update && apk add --no-cache \
    aws-cli \
    tini \
    python3 \
    gzip \
    openssl \
    && rm -rf /var/cache/apk/*

# Copy only the Python script needed
COPY backup.py ./

# Set correct ownership and permissions for the scripts
# Ensure the non-root user can execute run.sh
RUN chown appuser:appgroup backup.py

# Switch to the non-root user
USER appuser

# Define environment variables (defaults primarily for documentation)
# Removed S3_S3V4 as it's usually not needed
ENV S3_BUCKET="" \
    S3_ENDPOINT="" \
    S3_REGION="us-west-1" \
    S3_PREFIX="backup" \
    POSTGRES_DATABASE="" \
    POSTGRES_HOST="" \
    POSTGRES_PORT="5432" \
    POSTGRES_USER="" \
    DELETE_OLDER_THAN="" \
    LOG_LEVEL="INFO"

# Use tini as the entrypoint, executing the python script directly
ENTRYPOINT ["/sbin/tini", "--", "python3", "backup.py"]

CMD []
