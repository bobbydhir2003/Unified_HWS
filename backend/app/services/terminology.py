"""Terminology service: versioned code-system releases, search and validation.

Loaded (legally redistributable): ICD-10-CM FY2026 from CMS/CDC (public domain), shipped compressed in
app/data/terminology/. Not loaded (licence required): CPT (AMA), SNOMED CT (UMLS affiliate licence), commercial drug
knowledge bases. Their absence is reported by `systems()` instead of being hidden.
"""

from __future__ import annotations

import gzip
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

DATA = Path(__file__).resolve().parents[1] / "data" / "terminology"
ICD10CM = "ICD-10-CM"
ICD10CM_RELEASE = {"version": "FY2026", "effective_date": date(2025, 10, 1), "file": "icd10cm_codes_2026.txt.gz",
                   "source": "CMS ICD-10-CM 2026 code descriptions (tabular order), https://www.cms.gov/medicare/coding-billing/icd-10-codes",
                   "license_note": "ICD-10-CM is in the public domain (CMS / CDC NCHS)."}
UNLICENSED = [
    {"system": "CPT", "status": "not_licensed", "note": "CPT® is licensed by the AMA. Procedure codes use a small internal list until a licence is in place."},
    {"system": "SNOMED CT", "status": "not_licensed", "note": "Requires a UMLS / SNOMED International affiliate licence."},
    {"system": "Drug knowledge base", "status": "not_licensed", "note": "Interaction and contraindication screening needs a commercial, clinically validated source."},
]


def dotted(code: str) -> str:
    c = code.strip().upper().replace(".", "")
    return c if len(c) <= 3 else f"{c[:3]}.{c[3:]}"


def load_release(conn, system: str, version: str, effective_date: date, source: str, license_note: str, rows) -> int:
    """Idempotent, versioned load through COPY. Codes missing from the new release are marked retired, never deleted.
    `conn` is a SQLAlchemy Connection (works inside Alembic migrations and normal sessions)."""
    if conn.execute(text("SELECT 1 FROM terminology_releases WHERE system = :s AND version = :v"), {"s": system, "v": version}).first():
        return 0
    conn.execute(text("CREATE TEMP TABLE IF NOT EXISTS tmp_terms (code text, display text) ON COMMIT DROP"))
    conn.execute(text("TRUNCATE tmp_terms"))
    raw = conn.connection.dbapi_connection
    n = 0
    with raw.cursor() as cur, cur.copy("COPY tmp_terms (code, display) FROM STDIN") as cp:
        for code, display in rows:
            cp.write_row((code, display[:400]))
            n += 1
    conn.execute(text("""
        INSERT INTO terminology_concepts (id, system, code, display, version, status)
        SELECT gen_random_uuid(), :s, code, display, :v, 'active' FROM tmp_terms
        ON CONFLICT (system, code) DO UPDATE SET display = EXCLUDED.display, version = EXCLUDED.version, status = 'active'"""),
                 {"s": system, "v": version})
    conn.execute(text("UPDATE terminology_concepts SET status = 'retired' WHERE system = :s AND version <> :v"), {"s": system, "v": version})
    conn.execute(text("""INSERT INTO terminology_releases (id, system, version, effective_date, source, license_note, concept_count)
                         VALUES (gen_random_uuid(), :s, :v, :d, :src, :lic, :n)"""),
                 {"s": system, "v": version, "d": effective_date, "src": source, "lic": license_note, "n": n})
    return n


def icd10cm_rows(path: Path | None = None):
    with gzip.open(path or DATA / ICD10CM_RELEASE["file"], "rt", encoding="utf-8") as f:
        for line in f:
            code, _, display = line.rstrip("\n").partition(" ")
            if code:
                yield dotted(code), display.strip()


def load_icd10cm(conn) -> int:
    r = ICD10CM_RELEASE
    return load_release(conn, ICD10CM, r["version"], r["effective_date"], r["source"], r["license_note"], icd10cm_rows())


def search(db: Session, system: str, q: str, limit: int = 20, include_retired: bool = False) -> list[dict]:
    words = [w for w in q.lower().replace(",", " ").split() if w]
    if not words:
        return []
    code_q = dotted(q) if len(words) == 1 else None
    params: dict = {"s": system, "lim": limit}
    conds = []
    for i, w in enumerate(words):
        params[f"w{i}"] = f"%{w}%"
        conds.append(f"lower(display) LIKE :w{i}")
    where = " AND ".join(conds)
    if code_q:
        params["cq"] = f"{code_q}%"
        where = f"(code LIKE :cq OR ({where}))"
    status = "" if include_retired else "AND status = 'active'"
    rows = db.execute(text(f"""SELECT code, display, version, status FROM terminology_concepts
                               WHERE system = :s {status} AND {where}
                               ORDER BY (code LIKE :cq) DESC, length(code), code LIMIT :lim""" if code_q else
                           f"""SELECT code, display, version, status FROM terminology_concepts
                               WHERE system = :s {status} AND {where} ORDER BY length(code), code LIMIT :lim"""), params).all()
    return [{"code": c, "description": d, "version": v, "status": s} for c, d, v, s in rows]


def lookup(db: Session, system: str, code: str) -> dict | None:
    r = db.execute(text("SELECT code, display, version, status FROM terminology_concepts WHERE system = :s AND code = :c"),
                   {"s": system, "c": dotted(code)}).first()
    return {"code": r[0], "description": r[1], "version": r[2], "status": r[3]} if r else None


def loaded(db: Session, system: str) -> bool:
    return bool(db.execute(text("SELECT 1 FROM terminology_releases WHERE system = :s LIMIT 1"), {"s": system}).first())


def systems(db: Session) -> list[dict]:
    rows = db.execute(text("SELECT system, version, effective_date, source, license_note, concept_count, loaded_at FROM terminology_releases "
                           "ORDER BY system, effective_date DESC")).all()
    out = [{"system": r[0], "version": r[1], "effective_date": r[2], "source": r[3], "license_note": r[4], "concepts": r[5],
            "loaded_at": r[6], "status": "loaded"} for r in rows]
    return out + UNLICENSED
