from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from evals import db
from evals.compare import compare, get_results, summarize
from evals.runner import load_cases

app = FastAPI(title="Release Gate Dashboard")
HERE = Path(__file__).parent


@app.get("/")
def index():
    return FileResponse(HERE / "index.html")


@app.get("/api/runs")
def runs():
    conn = db.connect()
    rows = conn.execute(
        """SELECT r.*, (SELECT COUNT(*) FROM results x
                        WHERE x.run_id = r.id AND x.error IS NOT NULL) AS errors
           FROM runs r ORDER BY id DESC""").fetchall()
    return [dict(r) for r in rows]


@app.get("/api/runs/{run_id}")
def run_detail(run_id: int):
    conn = db.connect()
    run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "Run not found")
    res = [dict(r) for r in conn.execute(
        "SELECT * FROM results WHERE run_id=? ORDER BY case_id", (run_id,))]
    return {"run": dict(run), "results": res}


@app.get("/api/compare")
def api_compare(base: int, cand: int):
    conn = db.connect()
    runs = {}
    for name, rid in (("base", base), ("cand", cand)):
        row = conn.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
        if not row:
            raise HTTPException(404, f"Run {rid} not found")
        runs[name] = dict(row)
    b_res, c_res = get_results(conn, base), get_results(conn, cand)
    cases = {c["id"]: c for c in load_cases()}
    return {"baseline": summarize(runs["base"], b_res),
            "candidate": summarize(runs["cand"], c_res),
            **compare(b_res, c_res, cases)}