#!/bin/bash
# Phase 8 restore into a fresh Compose project
set -e
if [ -z "$1" ]; then echo "Usage: $0 <backup_dir>"; exit 1; fi
DIR="$1"
echo "Restoring Postgres..."
docker compose exec -T db psql -U phr phr < "$DIR/postgres.sql"
echo "Restoring documents..."
docker compose exec -T api tar xzf - -C / < "$DIR/documents.tar.gz" || true
echo "Restoring Orthanc..."
docker compose exec -T orthanc tar xzf - -C / < "$DIR/orthanc.tar.gz" || true
echo "Restore complete. Verify medication and sodium result."
