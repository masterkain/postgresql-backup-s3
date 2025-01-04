# docker build -t masterkain/postgresql-backup-s3:latest -f Dockerfile .
# docker run masterkain/postgresql-backup-s3:latest

# Use Python on Alpine Linux as the base image
FROM python:3-alpine

# Set the working directory to /app
WORKDIR /app

# Install necessary packages
RUN apk update && apk add --no-cache postgresql16-client gzip && pip3 install --no-cache-dir --upgrade pip awscli

# Set environment variables with default values where applicable
ENV S3_ACCESS_KEY_ID= \
  S3_SECRET_ACCESS_KEY= \
  S3_BUCKET= \
  S3_ENDPOINT= \
  S3_REGION=us-west-1 \
  S3_PREFIX=backup \
  S3_S3V4="yes" \
  POSTGRES_HOST= \
  POSTGRES_PORT=5432 \
  POSTGRES_USER= \
  POSTGRES_PASSWORD= \
  ENCRYPTION_PASSWORD= \
  DELETE_OLDER_THAN=

# Add the run script and the Python backup script to the container
ADD run.sh backup.py ./

# Ensure the run script is executable
RUN chmod +x run.sh

# Set the entry point to the run script and default command to execute the Python backup script
ENTRYPOINT ["./run.sh"]
CMD ["python3", "backup.py"]
