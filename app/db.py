"""SQLite storage for SiteDesk. All seed data is fictional."""
import datetime as dt
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("SITEDESK_DB", os.path.join(os.path.dirname(HERE), "data", "sitedesk.db"))

# Certificates every worker must hold to be cleared for site work
REQUIRED_CERTS = ["WHMIS", "Fall Protection"]
CERT_TYPES = ["WHMIS", "Fall Protection", "First Aid Level 1", "Forklift", "Confined Space", "Traffic Control"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, city TEXT NOT NULL, client TEXT NOT NULL,
  start_date TEXT NOT NULL, target_end TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active');
CREATE TABLE IF NOT EXISTS workers (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, trade TEXT NOT NULL, site_id INTEGER REFERENCES sites(id));
CREATE TABLE IF NOT EXISTS certs (
  id INTEGER PRIMARY KEY, worker_id INTEGER NOT NULL REFERENCES workers(id),
  cert_type TEXT NOT NULL, expires_on TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY, site_id INTEGER NOT NULL REFERENCES sites(id), date TEXT NOT NULL,
  author TEXT NOT NULL, raw_notes TEXT NOT NULL, crew_count INTEGER, weather TEXT,
  work_done TEXT, delays TEXT, delay_hours REAL DEFAULT 0, safety TEXT, materials TEXT,
  summary TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rfis (
  id INTEGER PRIMARY KEY, site_id INTEGER NOT NULL REFERENCES sites(id), number TEXT NOT NULL,
  subject TEXT NOT NULL, question TEXT NOT NULL, to_party TEXT NOT NULL,
  raised_on TEXT NOT NULL, due_on TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', answer TEXT);
"""


def conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def rows(sql, params=()):
    with conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def one(sql, params=()):
    r = rows(sql, params)
    return r[0] if r else None


def execute(sql, params=()):
    with conn() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid


def init(seed: bool = True):
    with conn() as c:
        c.executescript(SCHEMA)
        empty = c.execute("SELECT COUNT(*) FROM sites").fetchone()[0] == 0
    if seed and empty:
        _seed()


def _seed():
    """Fictional sample data, with dates relative to today so the demo always has something to show."""
    t = dt.date.today()
    d = lambda n: (t + dt.timedelta(days=n)).isoformat()
    with conn() as c:
        c.executemany("INSERT INTO sites (name, city, client, start_date, target_end) VALUES (?,?,?,?,?)", [
            ("Maple Row Townhomes (sample)", "Burnaby", "Sample Homes Ltd.", d(-120), d(150)),
            ("Cedar Point Retail Unit (sample)", "Coquitlam", "Example Retail Group", d(-45), d(60)),
            ("Harbourview Kitchen Renovation (sample)", "Vancouver", "Private client", d(-10), d(25)),
        ])
        workers = [("Alex Moreau", "Framer", 1), ("Priya Nair", "Electrician", 1), ("Daniel Okafor", "Labourer", 1),
                   ("Mina Rahimi", "Site Supervisor", 1), ("Tom Becker", "Roofer", 1), ("Lucas Ferreira", "Plumber", 2),
                   ("Sofia Kowalski", "Carpenter", 2), ("Arash Tehrani", "Labourer", 2), ("Emma Lindqvist", "Drywaller", 3),
                   ("Ravi Singh", "Carpenter", 3)]
        c.executemany("INSERT INTO workers (name, trade, site_id) VALUES (?,?,?)", workers)
        certs = []
        for wid in range(1, 11):
            certs += [(wid, "WHMIS", d(200 + wid * 20)), (wid, "Fall Protection", d(150 + wid * 25))]
        certs[4] = (3, "WHMIS", d(-12))            # Daniel: WHMIS expired
        certs[9] = (5, "Fall Protection", d(9))    # Tom (roofer): fall protection expires in 9 days
        certs[13] = (7, "Fall Protection", d(21))  # Sofia: expires in 3 weeks
        certs += [(4, "First Aid Level 1", d(300)), (6, "Confined Space", d(-40)), (8, "Forklift", d(400)),
                  (10, "First Aid Level 1", d(18))]
        c.executemany("INSERT INTO certs (worker_id, cert_type, expires_on) VALUES (?,?,?)", certs)
        c.executemany("""INSERT INTO rfis (site_id, number, subject, question, to_party, raised_on, due_on, status, answer)
                         VALUES (?,?,?,?,?,?,?,?,?)""", [
            (1, "RFI-001", "Beam size at grid C", "Drawing S-201 shows a 3-ply beam but the schedule says 4-ply. Which is correct?",
             "Structural engineer", d(-20), d(-13), "answered", "Use 4-ply per revised schedule."),
            (1, "RFI-002", "Window rough opening", "Unit 4 window supplier changed. Confirm new rough opening size.",
             "Architect", d(-9), d(-2), "open", None),
            (1, "RFI-003", "Exterior paint colour", "Client has not confirmed siding colour. Order deadline is next week.",
             "Client", d(-3), d(4), "open", None),
            (2, "RFI-001", "Sprinkler head layout", "Ceiling height changed at storefront. Does the sprinkler layout need revision?",
             "Mechanical engineer", d(-6), d(1), "open", None),
            (3, "RFI-001", "Cabinet delivery", "Cabinets arrive 3 days late. Can the countertop template date move?",
             "Private client", d(-2), d(5), "open", None),
        ])
        c.executemany("""INSERT INTO reports (site_id, date, author, raw_notes, crew_count, weather, work_done, delays,
                         delay_hours, safety, materials, summary, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            (1, d(-2), "Mina Rahimi", "8 guys today, rain in the morning. framed unit 3 walls, started sheathing. lost 2 hrs to rain. ran out of nails",
             8, "Rain (morning)", "Framed unit 3 walls\nStarted sheathing", "Rain stopped work in the morning (2 h)", 2,
             "", "Framing nails", "Unit 3 walls framed and sheathing started; 2 hours lost to rain.", d(-2)),
            (1, d(-1), "Mina Rahimi", "7 on site. sheathing unit 3 done. roof trusses delivered late at 1pm, crane waited 3 hours. saw one guy on the roof edge without harness, told him",
             7, "Cloudy", "Finished sheathing unit 3", "Late truss delivery, crane idle (3 h)", 3,
             "Worker at roof edge without a harness (corrected on the spot)", "", "Sheathing done; truss delivery 3 hours late; one fall-protection issue corrected.", d(-1)),
            (2, d(-1), "Lucas Ferreira", "3 crew. roughed in plumbing for washroom. waiting on RFI for sprinkler layout",
             3, None, "Plumbing rough-in for washroom", "Waiting on RFI-001 answer (sprinklers)", 0,
             "", "", "Washroom plumbing roughed in; sprinkler work waiting on RFI-001.", d(-1)),
        ])
