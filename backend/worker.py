#!/usr/bin/env python3
"""Postgres job queue worker. One process. FOR UPDATE SKIP LOCKED."""
import time
import os
import sys
sys.path.insert(0, "/app")

from app.database import SessionLocal
from app.processor import claim_next_job, process_job

def main():
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
