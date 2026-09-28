# 🏗️ SiteDesk — field-to-office system for small contractors

> **All data is synthetic.** Sites, clients and workers are fictional sample data created by the app. Any resemblance to real businesses or people is coincidental.

Small construction companies still run the site on paper, texts and memory. SiteDesk puts the three things that cause the most trouble in one place:

| Module | Problem it solves |
|---|---|
| 📝 **Daily reports** | Foremen type rough notes on their phone → **AI turns them into a clean report** (crew, weather, work done, delays, materials, safety). The foreman reviews and edits before saving. |
| 🦺 **Certificates** | Tracks worker safety certificates (WHMIS, Fall Protection, First Aid…) and shows who is **not cleared** for site work and what expires in the next 30 days. |
| ❓ **RFIs** | Requests for information to architects, engineers and clients, with due dates. **Overdue RFIs are flagged**, because a late answer can stop a crew. |
| 📊 **Dashboard** | Everything that needs attention today, across all sites. |

## Design choices
- **AI drafts, people decide.** The AI output is an editable form; nothing is saved until the foreman clicks Save.
- **Safety never depends on the AI alone.** A rule-based keyword check (no harness, near miss, injury, spill, open edge…) **always** runs, so a safety issue is flagged even if the AI misses it or Ollama is offline.
- **Works without AI.** If the model isn't available, the app says so and the foreman fills the form in manually.
- **Phone-first.** Big touch targets, and tables scroll instead of breaking the layout.

## Tech
**FastAPI + HTMX** (server-rendered HTML, no JavaScript framework) · Jinja2 · SQLite · Ollama (Qwen 2.5, local) · pytest

HTMX is bundled in `app/static/`, so the app works offline.

## Run it
```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```
Open **http://127.0.0.1:8000**. The database and sample data are created on first run in `data/`.

For AI report drafting, install [Ollama](https://ollama.com) and run `ollama pull qwen2.5:7b` (or set `CHAT_MODEL=llama3.2`).

## Tests
```bash
pytest -q
```
6 tests: all pages load, dashboard flags the planted problems, the safety rule check works with the AI **offline**, AI preview → save flow, RFI create/answer, and renewing a certificate clears a worker.

## Files
| Path | Purpose |
|---|---|
| `app/main.py` | Routes (dashboard, reports, certificates, RFIs) |
| `app/ai.py` | AI report structuring + rule-based safety check |
| `app/db.py` | SQLite schema and fictional sample data (dates relative to today) |
| `app/templates/` | HTML pages and HTMX partials |
| `tests/` | Tests with a fake AI |
