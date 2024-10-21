#!/usr/bin/env python3

import datetime
import logging
import os
import subprocess
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def fail(message):
    logging.error(message)
    sys.exit(1)


def check_environment_variables(required_vars):
    for var in required_vars:
        if not os.getenv(var):
            fail(f"You need to set the {var} environment variable.")
        else:
            logging.info(f"{var} is set.")


def run_command(command):
    logging.info(f"Running command: {command}")
    try:
        result = subprocess.run(command, shell=True, text=True, capture_output=True, check=True)
        logging.info("Command output: " + result.stdout.strip())
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {e.stderr.strip()}")
        return None


def get_postgres_version(postgres_opts):
    command = f"psql {postgres_opts} -d postgres -t -c 'SHOW server_version;'"
    version_output = run_command(command)
    if version_output:
        # Extract major version part (e.g., '13' from '13.3')
        major_version = version_output.split()[0].split(".")[0]
        version_prefix = f"pg{major_version}"
        logging.info(f"PostgreSQL server version determined: {version_prefix}")
        return version_prefix
    else:
        logging.error("Failed to determine PostgreSQL server version.")
        return None


def list_databases(postgres_opts):
    if os.getenv("POSTGRES_DATABASE"):
        logging.info(f"Backing up specific database: {os.getenv('POSTGRES_DATABASE')}")
        return [os.getenv("POSTGRES_DATABASE")]
    else:
        logging.info("Listing all databases...")
        command = f"psql {postgres_opts} -d postgres -t -A -c 'SELECT datname FROM pg_database WHERE datistemplate = false'"
        output = run_command(command)
        databases = output.split() if output else []
        logging.info(f"Databases found: {databases}")
        return databases


def dump_database(db_name, postgres_opts, dest_file):
    logging.info(f"Dumping database: {db_name}")
    command = f"pg_dump {postgres_opts} {db_name} -Fc -O -x > {dest_file}"
    try:
        subprocess.run(command, shell=True, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logging.info(f"Database {db_name} dumped successfully to {dest_file}")
        return dest_file
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to dump database {db_name}: {e.stderr.strip()}")
        return None


def encrypt_dump(src_file, password):
    if src_file is None:
        return None
    logging.info(f"Encrypting dump file: {src_file}")
    enc_file = f"{src_file}.enc"
    command = f"openssl enc -aes-256-cbc -in {src_file} -out {enc_file} -k {password}"
    try:
        subprocess.run(command, shell=True, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.remove(src_file)
        logging.info(f"Encrypted file created: {enc_file}")
        return enc_file
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to encrypt file {src_file}: {e.stderr.strip()}")
        return None


def upload_to_s3(src_file, bucket, prefix, endpoint_option=""):
    if not src_file:
        return
    logging.info(f"Uploading {src_file} to S3: s3://{bucket}/{prefix}/{src_file}")
    command = f"aws s3 cp {endpoint_option} {src_file} s3://{bucket}/{prefix}/{src_file}"
    try:
        subprocess.run(command, shell=True, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logging.info(f"File {src_file} uploaded successfully")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to upload file {src_file} to S3: {e.stderr.strip()}")


def cleanup_old_backups(bucket, prefix, older_than, endpoint_option=""):
    list_command = f"aws s3 ls {endpoint_option} s3://{bucket}/{prefix}/"
    output = run_command(list_command)
    if not output:
        logging.error("Failed to list S3 bucket contents.")
        return

    lines = output.splitlines()
    older_than_date = datetime.datetime.now() - datetime.timedelta(days=int(older_than.split()[0]))

    for line in lines:
        parts = line.split()
        if len(parts) < 4:
            continue
        last_modified = parts[0] + " " + parts[1]
        file_name = parts[3]
        last_modified_date = datetime.datetime.strptime(last_modified, "%Y-%m-%d %H:%M:%S")

        if last_modified_date < older_than_date:
            delete_command = f"aws s3 rm {endpoint_option} s3://{bucket}/{prefix}/{file_name}"
            logging.info(f"Deleting {file_name} as it is older than {older_than}")
            run_command(delete_command)


def main():
    required_env_vars = ["S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_BUCKET", "POSTGRES_HOST", "POSTGRES_USER", "POSTGRES_PASSWORD"]
    check_environment_variables(required_env_vars)

    os.environ["AWS_ACCESS_KEY_ID"] = os.getenv("S3_ACCESS_KEY_ID", "")
    os.environ["AWS_SECRET_ACCESS_KEY"] = os.getenv("S3_SECRET_ACCESS_KEY", "")
    os.environ["AWS_DEFAULT_REGION"] = os.getenv("S3_REGION", "us-west-1")
    os.environ["PGPASSWORD"] = os.getenv("POSTGRES_PASSWORD", "")

    postgres_opts = f"-h {os.getenv('POSTGRES_HOST', '')} -p {os.getenv('POSTGRES_PORT', '5432')} -U {os.getenv('POSTGRES_USER', '')}"
    version_prefix = get_postgres_version(postgres_opts)
    if version_prefix is None:
        fail("Could not determine PostgreSQL version for S3 prefixing.")

    bucket = os.getenv("S3_BUCKET")
    original_prefix = os.getenv("S3_PREFIX", "")
    full_prefix = f"{original_prefix}/{version_prefix}" if original_prefix else version_prefix
    endpoint_option = f"--endpoint-url {os.getenv('S3_ENDPOINT')}" if os.getenv("S3_ENDPOINT") else ""

    databases = list_databases(postgres_opts)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    for db in databases:
        dump_file = dump_database(db, postgres_opts, f"{db}_{timestamp}.dump")
        if dump_file and os.getenv("ENCRYPTION_PASSWORD"):
            dump_file = encrypt_dump(dump_file, os.getenv("ENCRYPTION_PASSWORD"))
        if dump_file:
            upload_to_s3(dump_file, bucket, full_prefix, endpoint_option)

    if os.getenv("DELETE_OLDER_THAN"):
        cleanup_old_backups(bucket, full_prefix, os.getenv("DELETE_OLDER_THAN"), endpoint_option)

    logging.info("SQL backup process finished.")


if __name__ == "__main__":
    main()
