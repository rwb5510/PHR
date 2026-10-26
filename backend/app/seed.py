"""Load seed/analytes.csv. Called from migration or startup."""
import csv
from pathlib import Path
from .models import CanonicalAnalyte

def load_analytes(db=None):
    from .database import SessionLocal
    candidates = [
        Path("/seed/analytes.csv"),
        Path(__file__).resolve().parents[1] / "seed" / "analytes.csv",
        Path(__file__).resolve().parents[2] / "seed" / "analytes.csv",
        Path("/workspace/artifacts/seed/analytes.csv"),
    ]
    seed_path = next((p for p in candidates if p.exists()), candidates[0])
    close = False
    if db is None:
        db = SessionLocal()
        close = True
    try:
        with open(seed_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row["canonical"].strip()
                aliases = row["aliases"].strip().lower()
                ucum = row["ucum"].strip()
                loinc = row["loinc"].strip()
                existing_row = db.query(CanonicalAnalyte).filter(CanonicalAnalyte.name == name).first()
                if existing_row:
                    existing_row.aliases = aliases
                    existing_row.ucum = ucum
                else:
                    db.add(CanonicalAnalyte(name=name, loinc=loinc, ucum=ucum, aliases=aliases))
        db.commit()
    finally:
        if close:
            db.close()
