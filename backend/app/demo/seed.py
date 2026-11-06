"""Seed the local database with SYNTHETIC demo data.

    python -m app.demo.seed            # import CVs + jobs, process with the local AI
    python -m app.demo.seed --no-ai    # import only (processing can be started from the UI)

The backend server does not need to be running; if it is, the worker will
pick up pending candidates.
"""
from __future__ import annotations

import argparse

from sqlalchemy import select

from app.config import get_settings
from app.db import init_engine, new_session
from app.demo.synthetic import CVS, JOBS, make_docx, make_pdf
from app.models import JobDescription
from app.services.candidates import import_file, mark_pending, process_candidate
from app.models import Candidate


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ai", action="store_true", help="do not run the AI extraction now")
    args = ap.parse_args()
    s = get_settings()
    init_engine(f"sqlite:///{s.db_path.as_posix()}")
    with new_session() as db:
        for j in JOBS:
            if not db.execute(select(JobDescription).where(JobDescription.title == j["title"])).scalars().first():
                db.add(JobDescription(**j))
        db.commit()
        ids = []
        for i, cv in enumerate(CVS):
            content, name = (make_docx(cv.text), f"{cv.key}.docx") if i == 1 else (make_pdf(cv.text), f"{cv.key}.pdf")
            res = import_file(db, name, content)
            print(f"{name}: {res['status']}")
            if res["status"] == "imported":
                cand = db.get(Candidate, res["candidate_id"])
                mark_pending(db, cand)
                ids.append(cand.id)
        if not args.no_ai:
            for cid in ids:
                print(f"processing {cid} ...", flush=True)
                process_candidate(db, cid)
                c = db.get(Candidate, cid)
                print(f"  -> {c.status} {c.error_message or ''}")
    print("Done. Synthetic demo data only.")


if __name__ == "__main__":
    main()
