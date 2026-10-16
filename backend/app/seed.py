"""Load seed/analytes.csv. Called from migration or startup."""
import csv
from pathlib import Path
from .models import CanonicalAnalyte

def load_analytes(db=None):
    from .database import SessionLocal
    seed_path = Path(__file__).resolve().parents[2] / "seed" / "analytes.csv"
    if not seed_path.exists():
        # fallback for test layout
        seed_path = Path("/workspace/artifacts/seed/analytes.csv")
    close = False
    if db is None:
        db = SessionLocal()
        close = True
    try:
        existing = db.query(CanonicalAnalyte).count()
        if existing > 0:
            return
        with open(seed_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                a = CanonicalAnalyte(
                    name=row["canonical"].strip(),
                    loinc=row["loinc"].strip(),
                    ucum=row["ucum"].strip(),
                    aliases=row["aliases"].strip().lower()
                )
                db.add(a)
        db.commit()
    finally:
        if close:
            db.close()
