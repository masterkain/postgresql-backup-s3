
# postgres-backup-s3

This Docker container facilitates the backup of PostgreSQL databases to AWS S3 and supports on-demand execution.

## Basic Usage

To run the container with necessary environment variables, use the following command:

```sh
docker run -e S3_ACCESS_KEY_ID=key -e S3_SECRET_ACCESS_KEY=secret -e S3_BUCKET=my-bucket -e S3_PREFIX=backup -e POSTGRES_DATABASE=dbname -e POSTGRES_USER=user -e POSTGRES_PASSWORD=password -e POSTGRES_HOST=localhost masterkain/postgres-backup-s3
```

## Kubernetes Deployment

Deploy this container within a Kubernetes cluster by setting up the deployment as shown below. Be sure to update the environment variables according to your configuration needs.

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgres-backup
  namespace: postgres
spec:
  schedule: "0 1 * * *"
  failedJobsHistoryLimit: 1
  successfulJobsHistoryLimit: 1
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: backup
              image: masterkain/postgresql-backup-s3:16.0.2
              imagePullPolicy: IfNotPresent
              env:
              - name: POSTGRES_HOST
                value: "postgres-postgresql.postgres.svc.cluster.local"
              - name: POSTGRES_PORT
                value: "5432"
              - name: POSTGRES_PASSWORD
                value: "xxxx"
              - name: POSTGRES_USER
                value: "postgres"
              - name: S3_ACCESS_KEY_ID
                value: "xxxx"
              - name: S3_REGION
                value: "fr-par"
              - name: S3_SECRET_ACCESS_KEY
                value: "xxxx"
              - name: S3_BUCKET
                value: "k8s-db-backups"
              - name: S3_ENDPOINT
                value: "" # optional
              - name: S3_PREFIX
                value: "microk8s"
              - name: DELETE_OLDER_THAN
                value: "30 days ago"

```

## Environment Variables

Configure the container using the following environment variables:

| Variable               | Default     | Required | Description |
|------------------------|-------------|----------|-------------|
| `POSTGRES_DATABASE`    |             | Yes      | Database to backup or 'all' for backing up all databases. |
| `POSTGRES_HOST`        |             | Yes      | PostgreSQL server host. |
| `POSTGRES_PORT`        | `5432`      | No       | PostgreSQL server port. |
| `POSTGRES_USER`        |             | Yes      | PostgreSQL user name. |
| `POSTGRES_PASSWORD`    |             | Yes      | PostgreSQL password. |
| `POSTGRES_EXTRA_OPTS`  |             | No       | Additional options for PostgreSQL. |
| `S3_ACCESS_KEY_ID`     |             | Yes      | AWS access key. |
| `S3_SECRET_ACCESS_KEY` |             | Yes      | AWS secret access key. |
| `S3_BUCKET`            |             | Yes      | S3 bucket name. |
| `S3_PREFIX`            | `backup`    | No       | Prefix path under the bucket. |
| `S3_REGION`            | `us-west-1` | No       | AWS S3 bucket region. |
| `S3_ENDPOINT`          |             | No       | Custom endpoint URL for S3 API-compatible services like Minio. |
| `ENCRYPTION_PASSWORD`  |             | No       | Password for encrypting the backup. |
| `DELETE_OLDER_THAN`    |             | No       | Automatically delete backups older than the specified duration. **Warning**: This deletes files under the S3_PREFIX. |
