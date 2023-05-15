# docker build -t masterkain/postgresql-backup-s3:latest -f Dockerfile .
# docker run masterkain/postgresql-backup-s3:latest

FROM ruby:3.2-alpine

RUN apk update && apk add coreutils postgresql15-client python3 py3-pip openssl curl && pip3 install --upgrade pip && pip3 install awscli && curl -L --insecure https://github.com/odise/go-cron/releases/download/v0.0.6/go-cron-linux.gz | zcat >/usr/local/bin/go-cron && chmod u+x /usr/local/bin/go-cron && apk del curl && rm -rf /var/cache/apk/*

ENV S3_ACCESS_KEY_ID=
ENV S3_SECRET_ACCESS_KEY=
ENV S3_BUCKET=
ENV S3_ENDPOINT=
ENV S3_REGION=us-west-1
ENV S3_PREFIX=backup
ENV S3_S3V4="yes"

ENV POSTGRES_HOST=
ENV POSTGRES_PORT=5432
ENV POSTGRES_USER=
ENV POSTGRES_PASSWORD=

ENV ENCRYPTION_PASSWORD=
ENV DELETE_OLDER_THAN=

ADD run.sh run.sh
ADD backup.rb backup.rb

CMD ["sh", "run.sh"]
