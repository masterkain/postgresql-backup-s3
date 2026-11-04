#!/usr/bin/env bash
# Real PostgreSQL regression: clean dumps must restore into an empty database.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
trial="backup-restore-$(date +%s)-$$"
private=$(mktemp -d)
backup_image=${BACKUP_TEST_IMAGE:-masterkain/postgresql-backup-s3:18.3.2}
postgres_image=${POSTGRES_TEST_IMAGE:-postgres:18.6-bookworm}
cleanup() {
  docker rm -f -v "$trial-client" "$trial-db" >/dev/null 2>&1 || true
  docker network rm "$trial" >/dev/null 2>&1 || true
  rm -rf "$private"
}
trap cleanup EXIT
docker network create "$trial" >/dev/null
docker run -d --name "$trial-db" --network "$trial" --network-alias database \
  --cpus 1 --memory 1g -e POSTGRES_HOST_AUTH_METHOD=trust "$postgres_image" >/dev/null
for _attempt in {1..30}; do
  if docker exec "$trial-db" pg_isready -U postgres >/dev/null 2>&1; then break; fi
  sleep 1
done
docker exec "$trial-db" psql -U postgres -v ON_ERROR_STOP=1 \
  -c 'CREATE DATABASE source_data' -c 'CREATE DATABASE restored_data'
docker exec -i "$trial-db" psql -U postgres -d source_data -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE categories (id serial PRIMARY KEY, name text UNIQUE NOT NULL);
CREATE TABLE entries (id serial PRIMARY KEY, category_id integer REFERENCES categories(id), content text NOT NULL);
CREATE INDEX entries_content ON entries(content);
CREATE VIEW catalogue AS SELECT entries.id, categories.name, entries.content FROM entries JOIN categories ON categories.id = entries.category_id;
INSERT INTO categories(name) VALUES ('sample');
INSERT INTO entries(category_id, content) VALUES (1, 'first'), (1, 'second');
SQL
docker run --rm --name "$trial-client" --network "$trial" --cpus 1 --memory 1g \
  -v "$repo:/source:ro" -w /tmp -e PYTHONPATH=/source --entrypoint python3 "$backup_image" -c '
import backup
import pathlib
import sys
path = backup.dump_database("source_data", "-h database -U postgres", "/tmp/dump.sql.gz")
if path is None:
    sys.exit(1)
sys.stdout.buffer.write(pathlib.Path(path).read_bytes())
' > "$private/dump.sql.gz"
gzip -dc "$private/dump.sql.gz" | docker exec -i "$trial-db" \
  psql -U postgres -d restored_data --single-transaction -v ON_ERROR_STOP=1
actual=$(docker exec "$trial-db" psql -U postgres -d restored_data -At -v ON_ERROR_STOP=1 \
  -c "SELECT string_agg(name || ':' || content, ',' ORDER BY id) FROM catalogue")
test "$actual" = 'sample:first,sample:second'
next_id=$(docker exec "$trial-db" psql -U postgres -d restored_data -At -v ON_ERROR_STOP=1 \
  -c "INSERT INTO entries(category_id, content) VALUES (1, 'third') RETURNING id" | head -1)
test "$next_id" = 3
printf 'PASS: empty-database atomic restore preserves table data, view, foreign key and sequence\n'
