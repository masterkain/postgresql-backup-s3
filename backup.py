#!/usr/bin/env python3

import datetime
import logging
import os
import re
import subprocess
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def fail(message):
    """Logs an error message and exits the script with status 1."""
    logging.error(message)
    sys.exit(1)


def check_environment_variables(required_vars):
    """Checks if all required environment variables are set."""
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
        else:
            # Avoid logging sensitive variables like passwords directly
            if "PASSWORD" not in var.upper() and "KEY" not in var.upper() and "SECRET" not in var.upper():
                logging.info(f"{var} is set.")
            else:
                logging.info(f"{var} is set (value hidden).")

    if missing_vars:
        fail(f"Missing required environment variables: {', '.join(missing_vars)}")


def run_command(command, sensitive=False):
    """
    Runs a shell command, logs the command and its output/error.
    Returns stdout on success, None on failure.
    If sensitive is True, the command itself won't be logged fully.
    """
    log_command = command
    if sensitive:
        # Basic masking for sensitive commands (like encryption)
        parts = command.split()
        log_command = parts[0] + " ..." if parts else command

    logging.info(f"Running command: {log_command}")
    try:
        # Use list format for subprocess.run when not using shell=True for better security
        # But stick with shell=True here as the original script uses pipes and complex commands
        result = subprocess.run(command, shell=True, text=True, capture_output=True, check=True)
        stdout_stripped = result.stdout.strip()
        if stdout_stripped:
            logging.info(f"Command successful. Output: {stdout_stripped}")
        else:
            logging.info("Command successful with no output.")
        return stdout_stripped
    except subprocess.CalledProcessError as e:
        stderr_stripped = e.stderr.strip() if e.stderr else "No stderr output"
        stdout_stripped = e.stdout.strip() if e.stdout else "No stdout output"
        log_message = f"Command failed: {log_command}\nExit Code: {e.returncode}"
        log_message += f"\nStandard Error: {stderr_stripped}"
        # Include stdout on failure only if it contains something, might be useful
        if stdout_stripped != "No stdout output":
            log_message += f"\nStandard Output: {stdout_stripped}"
        logging.error(log_message)
        return None  # Indicate failure
    except Exception as e:
        # Catch other potential exceptions like file not found for the command itself
        logging.error(f"Failed to execute command '{log_command}': {e}")
        return None


def get_postgres_version(postgres_opts):
    """Determines the PostgreSQL major version (e.g., 'pg13')."""
    logging.info("Determining PostgreSQL server version...")
    command = f"psql {postgres_opts} -d postgres -t -c 'SHOW server_version;'"
    version_output = run_command(command)
    if version_output:
        try:
            # Extract major version part (e.g., '13' from '13.3' or '14' from '14.1 (Debian 14.1-1.pgdg110+1)')
            major_version = version_output.split()[0].split(".")[0]
            if major_version.isdigit():
                version_prefix = f"pg{major_version}"
                logging.info(f"PostgreSQL server version determined: {version_prefix}")
                return version_prefix
            else:
                logging.error(f"Could not parse major version number from output: '{version_output}'")
                return None
        except IndexError:
            logging.error(f"Unexpected format for PostgreSQL version output: '{version_output}'")
            return None
    else:
        logging.error("Failed to execute psql command to get server version.")
        return None


def list_databases(postgres_opts):
    """Lists databases to be backed up."""
    specific_db = os.getenv("POSTGRES_DATABASE")
    if specific_db:
        logging.info(f"Backing up specific database: {specific_db}")
        return [specific_db]
    else:
        logging.info("Listing all non-template databases...")
        # Exclude common system/template databases explicitly
        command = f"psql {postgres_opts} -d postgres -t -A -c \"SELECT datname FROM pg_database WHERE datistemplate = false AND datname NOT IN ('postgres', 'template0', 'template1');\""
        output = run_command(command)
        databases = output.split() if output else []
        if databases:
            logging.info(f"Databases found for backup: {databases}")
        else:
            logging.warning("No user databases found to back up (excluding postgres, template0, template1).")
        return databases


def dump_database(db_name, postgres_opts, dest_file):
    """Dumps a specific database to a gzipped file."""
    logging.info(f"Attempting to dump database: {db_name} to {dest_file}")
    # Use --no-password option as PGPASSWORD env var is set
    # Use plain format for better diffability and simplicity, compressed with gzip
    command = f"pg_dump {postgres_opts} --no-password --dbname={db_name} " f"--format=plain --no-owner --clean --no-acl " f"| gzip > {dest_file}"
    # Log a less verbose version of the command for security/clarity
    logging.debug(f"Full dump command: {command}")

    # Use subprocess.run directly for piping, check for errors
    try:
        # Running with shell=True because of the pipe and redirection
        process = subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
        # Check if the destination file was created and has size > 0
        if os.path.exists(dest_file) and os.path.getsize(dest_file) > 0:
            file_size = os.path.getsize(dest_file)
            logging.info(f"Database '{db_name}' dumped successfully to '{dest_file}' ({file_size} bytes).")
            return dest_file
        else:
            # This case might happen if gzip failed or produced an empty file
            stderr_info = process.stderr.strip() if process.stderr else "No stderr."
            logging.error(f"Dump command ran but '{dest_file}' is missing or empty. Stderr: {stderr_info}")
            # Clean up potentially empty file
            if os.path.exists(dest_file):
                os.remove(dest_file)
            return None
    except subprocess.CalledProcessError as e:
        stderr_stripped = e.stderr.strip() if e.stderr else "No stderr output"
        stdout_stripped = e.stdout.strip() if e.stdout else "No stdout output"  # gzip might output to stdout on error
        log_message = f"Failed to dump database '{db_name}'. Exit Code: {e.returncode}"
        log_message += f"\nStandard Error: {stderr_stripped}"
        if stdout_stripped != "No stdout output":
            log_message += f"\nStandard Output: {stdout_stripped}"
        logging.error(log_message)
        # Ensure partial/failed dump file is removed
        if os.path.exists(dest_file):
            logging.info(f"Removing potentially incomplete dump file: {dest_file}")
            try:
                os.remove(dest_file)
            except OSError as remove_err:
                logging.error(f"Error removing incomplete dump file '{dest_file}': {remove_err}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during dump of '{db_name}': {e}")
        if os.path.exists(dest_file):
            os.remove(dest_file)  # Cleanup
        return None


def encrypt_dump(src_file, password):
    """Encrypts the dump file using OpenSSL AES-256-CBC."""
    if not src_file or not os.path.exists(src_file):
        logging.error(f"Encryption source file '{src_file}' not found or invalid.")
        return None

    logging.info(f"Encrypting dump file: {src_file}")
    enc_file = f"{src_file}.enc"
    # Using -pbkdf2 for better key derivation (requires OpenSSL 1.1.1+)
    # Pass password via env var or stdin for better security than -k, but -k is simpler for this script
    # WARNING: Using -k is less secure as the key is visible in process list. Consider alternatives for high security.
    command = f"openssl enc -aes-256-cbc -pbkdf2 -salt -in {src_file} -out {enc_file} -k {password}"

    # Run command, mark as sensitive to avoid logging the key
    if run_command(command, sensitive=True) is not None:
        try:
            os.remove(src_file)  # Remove original unencrypted file
            logging.info(f"Encryption successful. Encrypted file: {enc_file}. Original removed: {src_file}")
            return enc_file
        except OSError as e:
            logging.error(f"Encryption seemed successful, but failed to remove original file '{src_file}': {e}")
            # We still return the encrypted file path, but warn about the original
            return enc_file
    else:
        logging.error(f"Failed to encrypt file {src_file}.")
        # Clean up potentially incomplete encrypted file
        if os.path.exists(enc_file):
            logging.info(f"Removing potentially incomplete encrypted file: {enc_file}")
            try:
                os.remove(enc_file)
            except OSError as remove_err:
                logging.error(f"Error removing incomplete encrypted file '{enc_file}': {remove_err}")
        return None


def upload_to_s3(local_file, bucket, s3_key, endpoint_option=""):
    """Uploads a file to S3 using AWS CLI."""
    if not local_file or not os.path.exists(local_file):
        logging.error(f"Cannot upload: Local file '{local_file}' not found.")
        return False  # Indicate failure

    s3_path = f"s3://{bucket}/{s3_key}"
    logging.info(f"Uploading '{local_file}' to '{s3_path}'")
    command = f"aws s3 cp {endpoint_option} {local_file} {s3_path}"

    if run_command(command) is not None:
        logging.info(f"File '{local_file}' uploaded successfully to '{s3_path}'")
        return True  # Indicate success
    else:
        logging.error(f"Failed to upload '{local_file}' to S3.")
        return False  # Indicate failure


def cleanup_old_backups(bucket, prefix, older_than_str, active_databases, endpoint_option=""):
    """Removes backups older than the specified period from S3."""
    logging.info(f"Starting cleanup of backups older than '{older_than_str}' in s3://{bucket}/{prefix}/")

    # Regex to match the timestamp and suffixes at the end of the filename
    # Matches _YYYY-MM-DDTHHMMSSZ.sql.gz(.enc)? - Corrected Timestamp format
    # Captures the part *before* this pattern as group 1 (the database name)
    filename_pattern = re.compile(r"^(.*)_(\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}Z|T\d{6}Z))\.sql\.gz(?:\.enc)?$")

    list_command = f"aws s3 ls {endpoint_option} s3://{bucket}/{prefix}/"
    output = run_command(list_command)

    if output is None:  # Check for explicit failure from run_command
        logging.error("Failed to list S3 bucket contents for cleanup.")
        return
    if not output:  # Handle empty output (bucket/prefix exists but is empty)
        logging.info(f"No files found in s3://{bucket}/{prefix}/. No cleanup needed.")
        return

    lines = output.splitlines()
    if not lines:
        logging.info(f"No files listed in s3://{bucket}/{prefix}/. No cleanup needed.")
        return

    # Calculate the cutoff date
    try:
        # Expect format like "30 days"
        parts = older_than_str.split()
        if len(parts) != 2 or not parts[0].isdigit() or parts[1].lower() not in ["day", "days"]:
            raise ValueError("Invalid format")
        days_to_subtract = int(parts[0])
        # Use UTC timezone for comparison
        cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_to_subtract)
        logging.info(f"Cleanup cutoff date (UTC): {cutoff_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    except (ValueError, IndexError):
        logging.error(f"Invalid format for DELETE_OLDER_THAN: '{older_than_str}'. Expected format like '30 days'. Aborting cleanup.")
        return

    deleted_count = 0
    kept_count = 0
    skipped_db_count = 0
    skipped_pattern_count = 0
    error_count = 0

    for line in lines:
        parts = line.split()
        # Expected format: YYYY-MM-DD HH:MM:SS SIZE FILENAME
        if len(parts) < 4:
            logging.warning(f"Skipping malformed S3 ls line: '{line}'")
            error_count += 1
            continue

        date_str = parts[0]
        time_str = parts[1]
        # Size is parts[2]
        file_name = parts[3]

        try:
            # Parse the S3 timestamp string. Assume it's UTC.
            last_modified_str = f"{date_str} {time_str}"
            last_modified_date = datetime.datetime.strptime(last_modified_str, "%Y-%m-%d %H:%M:%S")
            # Make the timestamp offset-aware (UTC) for correct comparison
            last_modified_date = last_modified_date.replace(tzinfo=datetime.timezone.utc)
        except ValueError as ve:
            logging.error(f"Could not parse date/time '{last_modified_str}' from S3 listing for file '{file_name}': {ve}")
            error_count += 1
            continue

        # --- Extract Database Name using Regex ---
        match = filename_pattern.match(file_name)
        if not match:
            logging.warning(f"Skipping file '{file_name}': does not match expected naming pattern 'dbname_YYYY-MM-DDTHHMMSSZ.sql.gz[.enc]'.")
            skipped_pattern_count += 1
            continue

        db_name = match.group(1)  # Extracted database name

        # --- Check if DB is still active ---
        if db_name not in active_databases:
            logging.info(f"Skipping deletion of '{file_name}': Extracted database name '{db_name}' is not in the current active list: {active_databases}")
            skipped_db_count += 1
            continue

        # --- Compare dates for deletion ---
        if last_modified_date < cutoff_date:
            delete_command = f"aws s3 rm {endpoint_option} s3://{bucket}/{prefix}/{file_name}"
            logging.info(f"Deleting '{file_name}' (Last Modified: {last_modified_date.strftime('%Y-%m-%d %H:%M:%S %Z')}, older than cutoff)")
            if run_command(delete_command) is not None:
                deleted_count += 1
            else:
                logging.error(f"Failed to delete '{file_name}'.")
                error_count += 1
        else:
            logging.debug(f"Keeping '{file_name}' (Last Modified: {last_modified_date.strftime('%Y-%m-%d %H:%M:%S %Z')}) as it is not older than cutoff")
            kept_count += 1

    logging.info(f"Cleanup finished for s3://{bucket}/{prefix}/.")
    logging.info(f"Summary: Deleted={deleted_count}, Kept={kept_count}, Skipped (Inactive DB)={skipped_db_count}, Skipped (Pattern Mismatch)={skipped_pattern_count}, Errors={error_count}")


def main():
    """Main execution function."""
    # Configure logging level from environment variable, default to INFO
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    # Reconfigure logging with the potentially updated level
    # Use force=True if running in an environment where basicConfig might have been called before (like AWS Lambda)
    logging.basicConfig(level=log_level, format="%(asctime)s - %(levelname)s - %(message)s", force=True)

    logging.info("Starting PostgreSQL backup script...")

    # Define required env vars
    required_env_vars = ["S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_BUCKET", "POSTGRES_HOST", "POSTGRES_USER", "POSTGRES_PASSWORD"]
    # Add optional ones if they influence required settings (none in this case)
    check_environment_variables(required_env_vars)

    # Set AWS credentials for the aws cli commands
    # Note: It's generally better to use IAM roles if running on EC2/ECS/EKS
    # or configure AWS credentials via ~/.aws/credentials or instance profile.
    # Setting env vars like this is simple but less secure if logs are exposed.
    os.environ["AWS_ACCESS_KEY_ID"] = os.getenv("S3_ACCESS_KEY_ID", "")
    os.environ["AWS_SECRET_ACCESS_KEY"] = os.getenv("S3_SECRET_ACCESS_KEY", "")
    # Set region, important for AWS CLI operations
    aws_region = os.getenv("S3_REGION")
    if aws_region:
        os.environ["AWS_DEFAULT_REGION"] = aws_region
        logging.info(f"Using AWS Region: {aws_region}")
    else:
        # Defaulting region if not set, AWS CLI might require it depending on config
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
        logging.warning("S3_REGION not set, defaulting to us-east-1. Consider setting S3_REGION.")

    # Set PGPASSWORD for psql and pg_dump
    os.environ["PGPASSWORD"] = os.getenv("POSTGRES_PASSWORD", "")

    # Construct PostgreSQL connection options string
    postgres_host = os.getenv("POSTGRES_HOST")
    postgres_port = os.getenv("POSTGRES_PORT", "5432")
    postgres_user = os.getenv("POSTGRES_USER")
    postgres_opts = f"-h {postgres_host} -p {postgres_port} -U {postgres_user}"  # --no-password added in dump/psql commands

    # Determine PG version for S3 prefix
    version_prefix = get_postgres_version(postgres_opts)
    if version_prefix is None:
        fail("Could not determine PostgreSQL version. Cannot proceed.")

    # Configure S3 bucket, prefix, and endpoint
    bucket = os.getenv("S3_BUCKET")
    original_prefix = os.getenv("S3_PREFIX", "").strip("/")  # Remove leading/trailing slashes
    # Combine original prefix and version prefix correctly
    full_prefix_parts = [p for p in [original_prefix, version_prefix] if p]  # Filter out empty parts
    full_prefix = "/".join(full_prefix_parts)
    logging.info(f"Using S3 bucket: '{bucket}', Full prefix: '{full_prefix}'")

    s3_endpoint_url = os.getenv("S3_ENDPOINT")
    endpoint_option = f"--endpoint-url {s3_endpoint_url}" if s3_endpoint_url else ""
    if endpoint_option:
        logging.info(f"Using S3 endpoint URL: {s3_endpoint_url}")

    # --- Backup Process ---
    databases = list_databases(postgres_opts)
    if not databases:
        logging.warning("No databases found or specified to back up. Skipping dump and upload steps.")
    else:
        # Use UTC timestamp for consistency, format without colons for wider filename compatibility
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")

        encryption_password = os.getenv("ENCRYPTION_PASSWORD")
        if encryption_password:
            logging.info("ENCRYPTION_PASSWORD is set. Backups will be encrypted.")
        else:
            logging.info("ENCRYPTION_PASSWORD is not set. Backups will not be encrypted.")

        successful_uploads = 0
        failed_dumps = 0

        for db in databases:
            base_filename = f"{db}_{timestamp}.sql.gz"
            # Dumps are created in the current working directory
            local_dump_path = os.path.abspath(base_filename)

            logging.info(f"--- Processing database: {db} ---")
            dumped_file_path = dump_database(db, postgres_opts, local_dump_path)

            if not dumped_file_path:
                logging.error(f"Dump failed for database '{db}'. Skipping upload and encryption.")
                failed_dumps += 1
                continue  # Skip to the next database

            # Encryption Step (if password provided)
            file_to_upload = dumped_file_path
            is_encrypted = False
            if encryption_password:
                encrypted_file_path = encrypt_dump(dumped_file_path, encryption_password)
                if encrypted_file_path:
                    file_to_upload = encrypted_file_path  # Upload the encrypted file
                    is_encrypted = True
                else:
                    logging.error(f"Encryption failed for '{dumped_file_path}'. Will attempt to upload unencrypted file.")
                    # If encryption failed, we might still have the original dump file_to_upload remains dumped_file_path
                    # Or if encrypt_dump cleaned up the source, file_to_upload might be invalid now. Check existence.
                    if not os.path.exists(file_to_upload):
                        logging.error(f"Original dump file '{file_to_upload}' also missing after failed encryption attempt. Cannot upload.")
                        failed_dumps += 1  # Count as failure as nothing can be uploaded
                        continue  # Skip upload for this DB

            # Upload Step
            s3_filename = os.path.basename(file_to_upload)  # e.g., db_ts.sql.gz or db_ts.sql.gz.enc
            s3_key = f"{full_prefix}/{s3_filename}"
            if upload_to_s3(file_to_upload, bucket, s3_key, endpoint_option):
                successful_uploads += 1
            else:
                logging.error(f"Upload failed for {s3_filename}")
                # Decide if this counts as a total failure. Let's count it separately.
                # If dump worked but upload failed, it's not a dump failure.

            # --- Local Cleanup ---
            logging.debug(f"Attempting to clean up local file: {file_to_upload}")
            try:
                os.remove(file_to_upload)
                logging.info(f"Successfully cleaned up local file: {file_to_upload}")
            except OSError as e:
                logging.warning(f"Could not remove local backup file '{file_to_upload}': {e}")
            # If encryption failed but we uploaded the original, the original might have been removed by encrypt_dump already
            # or if encryption succeeded the original is removed by encrypt_dump. This handles the final file.

        logging.info(f"Backup uploads finished. Successful uploads: {successful_uploads}, Failed dumps/encryption: {failed_dumps}")

    # --- Cleanup Old Backups Step ---
    delete_older_than = os.getenv("DELETE_OLDER_THAN")
    if delete_older_than:
        if not databases:
            logging.warning("Skipping cleanup because no active databases were determined in this run.")
        else:
            # Pass the list of databases found *in this run* to the cleanup function
            cleanup_old_backups(bucket, full_prefix, delete_older_than, databases, endpoint_option)
    else:
        logging.info("DELETE_OLDER_THAN not set, skipping cleanup of old backups.")

    logging.info("PostgreSQL backup script finished.")


if __name__ == "__main__":
    main()
