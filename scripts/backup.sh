#!/bin/bash
# Phase 8 backup: Postgres + document volume + Orthanc volume
set -e
STAMP=$(date +%Y%m%d_%H%M%S)
OUT="backup_${STAMP}"
mkdir -p "$OUT"
echo "Dumping Postgres..."
docker compose exec -T db pg_dump -U phr phr > "$OUT/postgres.sql"
echo "Copying document volume..."
docker compose exec -T backend tar czf - /data/documents > "$OUT/documents.tar.gz" || true
echo "Copying Orthanc volume..."
docker compose exec -T orthanc tar czf - /var/lib/orthanc/db > "$OUT/orthanc.tar.gz" || true
echo "Backup written to $OUT"
echo "Restore drill command: ./scripts/restore.sh $OUT"
