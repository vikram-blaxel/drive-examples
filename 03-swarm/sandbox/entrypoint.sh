#!/bin/sh

/usr/local/bin/sandbox-api &

echo "Waiting for sandbox API..."
while ! nc -z 127.0.0.1 8080; do
  sleep 0.1
done
echo "Sandbox API ready"

# Resolve PostgreSQL bin directory
PG_BIN=$(find /usr/lib/postgresql/*/bin -maxdepth 0 -type d 2>/dev/null | sort -V | tail -1)
export PATH="$PG_BIN:$PATH"

# Initialize and start PostgreSQL
echo "Starting PostgreSQL..."
mkdir -p /var/run/postgresql /var/lib/postgresql/data
chown -R postgres:postgres /var/run/postgresql /var/lib/postgresql/data

if [ ! -f /var/lib/postgresql/data/PG_VERSION ]; then
  echo "Initializing PostgreSQL data directory..."
  su postgres -c "$PG_BIN/initdb -D /var/lib/postgresql/data"
fi

su postgres -c "$PG_BIN/pg_ctl start -D /var/lib/postgresql/data -l /var/lib/postgresql/data/postgresql.log -w"

echo "Waiting for PostgreSQL to accept connections..."
until su postgres -c "$PG_BIN/pg_isready -q"; do
  sleep 0.1
done
echo "PostgreSQL ready"

wait
