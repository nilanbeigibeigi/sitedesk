"""SiteDesk — field-to-office system for small construction contractors.

Run:  python -m uvicorn app.main:app --reload     then open http://127.0.0.1:8000
"""
import datetime as dt
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import ai, db

HERE = os.path.dirname(os.path.abspath(__file__))


@asynccontextmanager
async def lifespan(app):
    db.init()
    yield


app = FastAPI(title="SiteDesk", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(HERE, "templates"))


def today():
    return dt.date.today()


def cert_status(expires_on: str) -> str:
    days = (dt.date.fromisoformat(expires_on) - today()).days
    return "expired" if days < 0 else "expiring" if days <= 30 else "ok"


def days_left(date_str: str) -> int:
    return (dt.date.fromisoformat(date_str) - today()).days


templates.env.globals.update(cert_status=cert_status, days_left=days_left)


def workers_with_certs():
    workers = db.rows("""SELECT w.*, s.name AS site FROM workers w LEFT JOIN sites s ON s.id = w.site_id
                         ORDER BY s.id, w.name""")
    certs = db.rows("SELECT * FROM certs ORDER BY expires_on")
    for w in workers:
        w["certs"] = [c for c in certs if c["worker_id"] == w["id"]]
        valid = {c["cert_type"] for c in w["certs"] if cert_status(c["expires_on"]) != "expired"}
        w["missing"] = [r for r in db.REQUIRED_CERTS if r not in valid]
        w["cleared"] = not w["missing"]
    return workers


def open_rfis():
    rfis = db.rows("""SELECT r.*, s.name AS site FROM rfis r JOIN sites s ON s.id = r.site_id
                      WHERE r.status = 'open' ORDER BY r.due_on""")
    for r in rfis:
        r["overdue"] = days_left(r["due_on"]) < 0
    return rfis


# ------------------------------------------------------------------ dashboard
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    workers = workers_with_certs()
    expiring = sorted(({**c, "worker": w["name"], "site": w["site"]} for w in workers for c in w["certs"]
                       if cert_status(c["expires_on"]) != "ok"), key=lambda c: c["expires_on"])
    rfis = open_rfis()
    week_ago = (today() - dt.timedelta(days=7)).isoformat()
    delay = db.one("SELECT COALESCE(SUM(delay_hours),0) AS h FROM reports WHERE date >= ?", (week_ago,))["h"]
    sites = db.rows("""SELECT s.*, (SELECT MAX(date) FROM reports r WHERE r.site_id = s.id) AS last_report,
                              (SELECT COUNT(*) FROM workers w WHERE w.site_id = s.id) AS crew
                       FROM sites s WHERE status = 'active' ORDER BY s.id""")
    safety = db.rows("""SELECT r.id, r.date, r.safety, s.name AS site FROM reports r JOIN sites s ON s.id = r.site_id
                        WHERE r.safety != '' AND r.date >= ? ORDER BY r.date DESC""", (week_ago,))
    return templates.TemplateResponse(request, "dashboard.html", {
        "sites": sites, "expiring": expiring, "rfis": rfis, "delay_hours": delay, "safety": safety,
        "not_cleared": [w for w in workers if not w["cleared"]], "page": "dash"})


# ------------------------------------------------------------------ daily reports
@app.get("/reports", response_class=HTMLResponse)
def reports(request: Request):
    return templates.TemplateResponse(request, "reports.html", {
        "reports": db.rows("""SELECT r.*, s.name AS site FROM reports r JOIN sites s ON s.id = r.site_id
                              ORDER BY r.date DESC, r.id DESC LIMIT 50"""),
        "sites": db.rows("SELECT id, name FROM sites WHERE status='active'"),
        "today": today().isoformat(), "page": "reports"})


@app.post("/reports/preview", response_class=HTMLResponse)
def report_preview(request: Request, site_id: int = Form(...), date: str = Form(...),
                   author: str = Form(...), raw_notes: str = Form(...)):
    """AI structures the notes; the foreman reviews and edits before anything is saved."""
    if not raw_notes.strip():
        return HTMLResponse('<p class="msg bad">Write a few notes about today first.</p>')
    draft = ai.structure_report(raw_notes)
    return templates.TemplateResponse(request, "partials/report_preview.html", {
        "d": draft, "site_id": site_id, "date": date, "author": author, "raw_notes": raw_notes,
        "site": db.one("SELECT name FROM sites WHERE id=?", (site_id,))})


@app.post("/reports")
def save_report(site_id: int = Form(...), date: str = Form(...), author: str = Form(...),
                raw_notes: str = Form(...), crew_count: str = Form(""), weather: str = Form(""),
                work_done: str = Form(""), delays: str = Form(""), delay_hours: float = Form(0),
                safety: str = Form(""), materials: str = Form(""), summary: str = Form("")):
    rid = db.execute("""INSERT INTO reports (site_id, date, author, raw_notes, crew_count, weather, work_done, delays,
                        delay_hours, safety, materials, summary, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (site_id, date, author.strip(), raw_notes, int(crew_count) if crew_count.strip().isdigit() else None,
                      weather.strip(), work_done.strip(), delays.strip(), delay_hours, safety.strip(), materials.strip(),
                      summary.strip(), dt.datetime.now().isoformat(timespec="minutes")))
    return Response(status_code=204, headers={"HX-Redirect": f"/reports/{rid}"})


@app.get("/reports/{rid}", response_class=HTMLResponse)
def report_detail(request: Request, rid: int):
    r = db.one("SELECT r.*, s.name AS site FROM reports r JOIN sites s ON s.id=r.site_id WHERE r.id=?", (rid,))
    if not r:
        raise HTTPException(404, "Report not found")
    return templates.TemplateResponse(request, "report_detail.html", {"r": r, "page": "reports"})


# ------------------------------------------------------------------ certificates
@app.get("/certs", response_class=HTMLResponse)
def certs(request: Request):
    return templates.TemplateResponse(request, "certs.html", {
        "workers": workers_with_certs(), "cert_types": db.CERT_TYPES, "required": db.REQUIRED_CERTS, "page": "certs"})


@app.post("/certs")
def add_cert(worker_id: int = Form(...), cert_type: str = Form(...), expires_on: str = Form(...)):
    if cert_type not in db.CERT_TYPES:
        raise HTTPException(400, "Unknown certificate type")
    dt.date.fromisoformat(expires_on)
    db.execute("INSERT INTO certs (worker_id, cert_type, expires_on) VALUES (?,?,?)", (worker_id, cert_type, expires_on))
    return RedirectResponse("/certs", status_code=303)


# ------------------------------------------------------------------ RFIs
@app.get("/rfis", response_class=HTMLResponse)
def rfis(request: Request):
    all_rfis = db.rows("""SELECT r.*, s.name AS site FROM rfis r JOIN sites s ON s.id=r.site_id
                          ORDER BY CASE r.status WHEN 'open' THEN 0 ELSE 1 END, r.due_on""")
    for r in all_rfis:
        r["overdue"] = r["status"] == "open" and days_left(r["due_on"]) < 0
    return templates.TemplateResponse(request, "rfis.html", {
        "rfis": all_rfis, "sites": db.rows("SELECT id, name FROM sites WHERE status='active'"),
        "due_default": (today() + dt.timedelta(days=7)).isoformat(), "page": "rfis"})


@app.post("/rfis")
def add_rfi(site_id: int = Form(...), subject: str = Form(...), question: str = Form(...),
            to_party: str = Form(...), due_on: str = Form(...)):
    n = db.one("SELECT COUNT(*) AS n FROM rfis WHERE site_id=?", (site_id,))["n"] + 1
    db.execute("""INSERT INTO rfis (site_id, number, subject, question, to_party, raised_on, due_on)
                  VALUES (?,?,?,?,?,?,?)""", (site_id, f"RFI-{n:03d}", subject.strip(), question.strip(),
                                              to_party.strip(), today().isoformat(), due_on))
    return RedirectResponse("/rfis", status_code=303)


@app.post("/rfis/{rid}/answer", response_class=HTMLResponse)
def answer_rfi(request: Request, rid: int, answer: str = Form(...)):
    if not answer.strip():
        raise HTTPException(400, "Answer is empty")
    db.execute("UPDATE rfis SET status='answered', answer=? WHERE id=?", (answer.strip(), rid))
    r = db.one("SELECT r.*, s.name AS site FROM rfis r JOIN sites s ON s.id=r.site_id WHERE r.id=?", (rid,))
    r["overdue"] = False
    return templates.TemplateResponse(request, "partials/rfi_row.html", {"r": r})
