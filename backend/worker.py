#!/usr/bin/env python3
"""Postgres job queue worker. One process. FOR UPDATE SKIP LOCKED."""
import time
import os
import sys
sys.path.insert(0, "/app")

from sqlalchemy import text
from app.database import SessionLocal
from app.processor import claim_next_job, process_job

def wait_for_db():
    for attempt in range(60):
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            return
        except Exception as exc:
            print(f"waiting for database ({attempt + 1}/60): {exc}", flush=True)
            time.sleep(1)
        finally:
            db.close()
    raise RuntimeError("database never became ready")

def main():
    wait_for_db()
    print("Worker started", flush=True)
    while True:
        db = SessionLocal()
        try:
            job_id = claim_next_job(db)
            if job_id:
                print(f"Processing job {job_id}", flush=True)
                try:
                    process_job(db, job_id)
                except Exception as e:
                    print(f"Job {job_id} failed: {e}", flush=True)
            else:
                time.sleep(2)
        finally:
            db.close()

if __name__ == "__main__":
    main()
