#!/usr/bin/env ruby

require "open3"
require "date"

def fail(message)
  warn "ERROR: #{message}"
  exit 1
end

# Check environment variables
fail("You need to set the S3_ACCESS_KEY_ID environment variable.") if ENV["S3_ACCESS_KEY_ID"].nil?
fail("You need to set the S3_SECRET_ACCESS_KEY environment variable.") if ENV["S3_SECRET_ACCESS_KEY"].nil?
fail("You need to set the S3_BUCKET environment variable.") if ENV["S3_BUCKET"].nil?
fail("You need to set the POSTGRES_HOST environment variable.") if ENV["POSTGRES_HOST"].nil?
fail("You need to set the POSTGRES_USER environment variable.") if ENV["POSTGRES_USER"].nil?
fail("You need to set the POSTGRES_PASSWORD environment variable or link to a container named POSTGRES.") if ENV["POSTGRES_PASSWORD"].nil?

# Set AWS environment variables
ENV["AWS_ACCESS_KEY_ID"] = ENV["S3_ACCESS_KEY_ID"]
ENV["AWS_SECRET_ACCESS_KEY"] = ENV["S3_SECRET_ACCESS_KEY"]
ENV["AWS_DEFAULT_REGION"] = ENV["S3_REGION"] || "us-west-1"

# Set PostgreSQL environment variables
ENV["PGPASSWORD"] = ENV["POSTGRES_PASSWORD"]
postgres_host = ENV["POSTGRES_HOST"]
postgres_port = ENV["POSTGRES_PORT"] || "5432"
postgres_user = ENV["POSTGRES_USER"]
postgres_extra_opts = ENV["POSTGRES_EXTRA_OPTS"] || ""
postgres_host_opts = "-h #{postgres_host} -p #{postgres_port} -U #{postgres_user} #{postgres_extra_opts}"

# List databases
cmd = "psql #{postgres_host_opts} -t -A -c 'SELECT datname FROM pg_database WHERE datistemplate = false'"
stdout, stderr, status = Open3.capture3(cmd)
fail("Failed to list databases: #{stderr}") unless status.success?
databases = stdout.split("\n").map(&:strip)

# Create database dumps
databases.each do |database|
  src_file = "#{database}.sql.gz"
  dest_file = "#{database}_#{DateTime.now.strftime("%Y-%m-%dT%H:%M:%SZ")}.sql.gz"
  cmd = "pg_dump #{postgres_host_opts} #{database} -Fc -O -x > #{src_file}"
  stdout, stderr, status = Open3.capture3(cmd)
  fail("Failed to create database dump for #{database}: #{stderr}") unless status.success?
  # Encrypt database dump if encryption password is set
  if ENV["ENCRYPTION_PASSWORD"]
    cmd = "openssl enc -aes-256-cbc -in #{src_file} -out #{src_file}.enc -k #{ENV["ENCRYPTION_PASSWORD"]}"
    stdout, stderr, status = Open3.capture3(cmd)
    fail("Failed to encrypt database dump for #{database}: #{stderr}") unless status.success?
    File.delete(src_file)
    src_file += ".enc"
    dest_file += ".enc"
  end
  # Upload database dump to S3
  cmd = "aws s3 cp #{src_file} s3://#{ENV["S3_BUCKET"]}/#{ENV["S3_PREFIX"]}/#{dest_file}"
  stdout, stderr, status = Open3.capture3(cmd)
  fail("Failed to upload database dump for #{database} to S3: #{stderr}") unless status.success?
end

# Delete old backups if DELETE_OLDER_THAN is set
if ENV["DELETE_OLDER_THAN"]
  cmd = "aws s3 ls s3://#{ENV["S3_BUCKET"]}/#{ENV["S3_PREFIX"]}/ | grep -v ' PRE ' | while read -r line; do fileName=$(echo $line | awk '{print $4}'); created=$(echo $line | awk '{print $1 " " $2}'); created=$(date -d \"$created\" +%s); older_than=$(date -d \"#{ENV["DELETE_OLDER_THAN"]}\" +%s); if [ $created -lt $older_than ]; then if [ $fileName != '' ]; then echo \"DELETING ${fileName}\"; aws s3 rm s3://#{ENV["S3_BUCKET"]}/#{ENV["S3_PREFIX"]}/$fileName; fi; else echo \"${fileName} not older than #{ENV["DELETE_OLDER_THAN"]}\"; fi; done"
  stdout, stderr, status = Open3.capture3(cmd)
  fail("Failed to delete old backups: #{stderr}") unless status.success?
end

puts "SQL backup finished"
