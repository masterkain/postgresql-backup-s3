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
        print(f"Command failed: {e.stderr.strip()}")
        return None


def list_databases(postgres_opts):
    if os.getenv("POSTGRES_DATABASE"):
        logging.info(f"Backing up specific database: {os.getenv('POSTGRES_DATABASE')}")
        return [os.getenv("POSTGRES_DATABASE")]
    else:
        logging.info("Listing all databases...")
        command = f"psql {postgres_opts} -t -A -c 'SELECT datname FROM pg_database WHERE datistemplate = false'"
        output = run_command(command)
        databases = output.split() if output else []
        logging.info(f"Databases found: {databases}")
        return databases


def dump_database(db_name, postgres_opts, dest_file):
    logging.info(f"Dumping database: {db_name}")
    command = f"pg_dump {postgres_opts} {db_name} -Fc -O -x > {dest_file}"
    run_command(command)
    return dest_file


def encrypt_dump(src_file, password):
    logging.info(f"Encrypting dump file: {src_file}")
    enc_file = f"{src_file}.enc"
    command = f"openssl enc -aes-256-cbc -in {src_file} -out {enc_file} -k {password}"
    run_command(command)
    os.remove(src_file)
    logging.info(f"Encrypted file created: {enc_file}")
    return enc_file


def upload_to_s3(src_file, bucket, prefix, endpoint_option=""):
    logging.info(f"Uploading {src_file} to S3: s3://{bucket}/{prefix}/{src_file}")
    command = f"aws s3 cp {endpoint_option} {src_file} s3://{bucket}/{prefix}/{src_file}"
    run_command(command)


def cleanup_old_backups(bucket, prefix, older_than, endpoint_option=""):
    list_command = f"aws s3 ls {endpoint_option} s3://{bucket}/{prefix}/"
    output = run_command(list_command)
    if not output:
        print("Failed to list S3 bucket contents.")
        return

    lines = output.splitlines()
    older_than_date = datetime.datetime.now() - datetime.timedelta(days=int(older_than.split()[0]))

    for line in lines:
        parts = line.split()
        if len(parts) < 4:
            continue
        last_modified = " ".join(parts[:2])
        file_name = parts[3]
        last_modified_date = datetime.datetime.strptime(last_modified, "%Y-%m-%d %H:%M:%S")

        if last_modified_date < older_than_date:
            delete_command = f"aws s3 rm {endpoint_option} s3://{bucket}/{prefix}/{file_name}"
            print(f"Deleting {file_name} as it is older than {older_than}")
            delete_output = run_command(delete_command)
            print(delete_output)


def main():
    required_env_vars = ["S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_BUCKET", "POSTGRES_HOST", "POSTGRES_USER", "POSTGRES_PASSWORD"]
    check_environment_variables(required_env_vars)

    os.environ["AWS_ACCESS_KEY_ID"] = os.getenv("S3_ACCESS_KEY_ID", "")
    os.environ["AWS_SECRET_ACCESS_KEY"] = os.getenv("S3_SECRET_ACCESS_KEY", "")
    os.environ["AWS_DEFAULT_REGION"] = os.getenv("S3_REGION", "us-west-1")
    os.environ["PGPASSWORD"] = os.getenv("POSTGRES_PASSWORD", "")

    postgres_opts = f"-h {os.getenv('POSTGRES_HOST', '')} -p {os.getenv('POSTGRES_PORT', '5432')} -U {os.getenv('POSTGRES_USER', '')}"

    databases = list_databases(postgres_opts)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    bucket = os.getenv("S3_BUCKET")
    prefix = os.getenv("S3_PREFIX", "")
    endpoint_option = f"--endpoint-url {os.getenv('S3_ENDPOINT')}" if os.getenv("S3_ENDPOINT") else ""

    for db in databases:
        dump_file = dump_database(db, postgres_opts, f"{db}_{timestamp}.dump")
        if os.getenv("ENCRYPTION_PASSWORD"):
            dump_file = encrypt_dump(dump_file, os.getenv("ENCRYPTION_PASSWORD"))
        upload_to_s3(dump_file, bucket, prefix, endpoint_option)

    if os.getenv("DELETE_OLDER_THAN"):
        cleanup_old_backups(bucket, prefix, os.getenv("DELETE_OLDER_THAN"), endpoint_option)

    logging.info("SQL backup process finished.")


if __name__ == "__main__":
    main()
