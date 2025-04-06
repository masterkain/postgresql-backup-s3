# postgres-backup-s3

This Docker container facilitates the backup of PostgreSQL databases to AWS S3. It supports on-demand execution, optional encryption of backups, and an intelligent cleanup mechanism that retains backups for databases that are no longer active.

## Features

- **Backup All or Single Database:**
  Back up all non-template databases or a specific database by setting the `POSTGRES_DATABASE` environment variable.

- **PostgreSQL Version Tagging:**
  The script automatically determines the PostgreSQL server version and appends a version prefix (e.g., `pg17`) to the backup path in S3.

- **Optional Encryption:**
  Provide an `ENCRYPTION_PASSWORD` to encrypt backups using AES-256-CBC encryption.

- **S3 Upload:**
  Backup files are automatically uploaded to an AWS S3 bucket. A custom S3 endpoint is supported for S3-compatible services like Minio.

- **Intelligent Cleanup:**
  When enabled via the `DELETE_OLDER_THAN` variable, the script cleans up backups older than a specified duration. **Note:** Backups corresponding to databases that are no longer active (i.e. not present during the latest backup run) will be retained for historical reference.

## Basic Usage

To run the container with the necessary environment variables, use the following command:

```console
docker run \
  -e S3_ACCESS_KEY_ID=your-key \
  -e S3_SECRET_ACCESS_KEY=your-secret \
  -e S3_BUCKET=my-bucket \
  -e S3_PREFIX=backup \
  -e POSTGRES_DATABASE=your_database \  # Optional: omit to backup all non-template databases
  -e POSTGRES_USER=your_user \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_HOST=your_postgres_host \
  -e ENCRYPTION_PASSWORD=optional_encryption_password \  # Optional: enable backup encryption
  -e DELETE_OLDER_THAN="30 days ago" \  # Optional: delete backups older than 30 days (only if the database is still active)
  masterkain/postgres-backup-s3
```

## Kubernetes Deployment

Deploy this container within a Kubernetes cluster using a CronJob. Adjust the environment variables as needed:

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
              image: masterkain/postgresql-backup-s3:17.0.4
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
                - name: S3_SECRET_ACCESS_KEY
                  value: "xxxx"
                - name: S3_BUCKET
                  value: "k8s-db-backups"
                - name: S3_REGION
                  value: "fr-par"
                - name: S3_ENDPOINT
                  value: ""  # Optional: custom S3 endpoint (e.g., for Minio)
                - name: S3_PREFIX
                  value: "k3s"
                - name: DELETE_OLDER_THAN
                  value: "30 days"
                - name: ENCRYPTION_PASSWORD
                  value: "optional_encryption_password"  # Optional: enable encryption
```

## Environment Variables

| Variable               | Default     | Required | Description |
|------------------------|-------------|----------|-------------|
| `POSTGRES_DATABASE`    | _(none)_    | No       | Name of the database to back up. If not set, all non-template databases will be backed up. |
| `POSTGRES_HOST`        | _(none)_    | Yes      | PostgreSQL server host. |
| `POSTGRES_PORT`        | `5432`      | No       | PostgreSQL server port. |
| `POSTGRES_USER`        | _(none)_    | Yes      | PostgreSQL user name. |
| `POSTGRES_PASSWORD`    | _(none)_    | Yes      | PostgreSQL user's password. |
| `S3_ACCESS_KEY_ID`     | _(none)_    | Yes      | AWS access key ID. |
| `S3_SECRET_ACCESS_KEY` | _(none)_    | Yes      | AWS secret access key. |
| `S3_BUCKET`            | _(none)_    | Yes      | AWS S3 bucket name where backups will be stored. |
| `S3_PREFIX`            | `backup`    | No       | Path prefix inside the bucket for storing backups. The PostgreSQL version prefix (e.g., `pg13`) is appended. |
| `S3_REGION`            | `us-west-1` | No       | AWS region for the S3 bucket. |
| `S3_ENDPOINT`          | _(none)_    | No       | Custom S3 endpoint URL for S3-compatible services (e.g., Minio). |
| `ENCRYPTION_PASSWORD`  | _(none)_    | No       | Password for encrypting the backup file using AES-256-CBC encryption. |
| `DELETE_OLDER_THAN`    | _(none)_    | No       | Duration (e.g., "30 days") after which backups will be deleted from S3 **if** the database is still active. Backups for databases that no longer exist will be retained. |

## How It Works

1. **Database Backup:**
   The script uses `pg_dump` to back up the specified database(s) (or all non-template databases) and compresses the output using gzip. The dump file is named using the pattern `databaseName_timestamp.sql.gz`.

2. **Optional Encryption:**
   If an `ENCRYPTION_PASSWORD` is provided, the script encrypts the dump file with AES-256-CBC using OpenSSL. The encrypted file will have an additional `.enc` extension.

3. **S3 Upload:**
   The resulting backup file is uploaded to the specified S3 bucket under the path defined by `S3_PREFIX` (with the PostgreSQL version appended). A custom endpoint can be used for S3-compatible services.

4. **Intelligent Cleanup:**
   When `DELETE_OLDER_THAN` is set, the script lists existing backups in S3 and deletes those older than the specified duration. However, it will **skip deletion** for any backup whose database is not present in the current backup list. This ensures that backups for dropped or inactive databases are retained for historical reference.

## Notes

- **File Naming Convention:**
  Backups are named in the format:
  `databaseName_timestamp.sql.gz` (or with an extra `.enc` if encryption is enabled).
  The cleanup process relies on this convention to identify the associated database.

- **AWS & PostgreSQL Credentials:**
  Ensure that your AWS credentials and PostgreSQL credentials are correct and have the necessary permissions.

- **Retention Policy:**
  The cleanup operation only deletes backups for databases that are currently active. If a database is dropped, its historical backups are preserved.

## License

MIT License
