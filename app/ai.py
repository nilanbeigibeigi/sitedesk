"""AI + rules for daily reports.

The AI turns a foreman's rough notes into a structured report. A deterministic keyword check for
safety issues ALWAYS runs as well, so a safety problem is flagged even if the AI misses it or is offline.
"""
import json
import os
import re
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "qwen2.5:7b")

SYSTEM = """You turn a construction foreman's rough daily notes into a structured site report.
Return ONLY JSON with these keys:
{"crew_count": integer or null, "weather": string or null,
 "work_done": [short strings], "delays": [{"reason": string, "hours": number}],
 "safety_issues": [short strings], "materials_needed": [short strings],
 "summary": "one sentence for the project manager"}
Use only what the notes say. Do not invent numbers. If something isn't mentioned, use null or []."""

SAFETY_WORDS = {
    r"without (a )?harness|no harness|no tie.?off": "Fall protection not used",
    r"near.?miss": "Near miss reported",
    r"injur|hurt|cut (his|her|their)|first aid": "Possible injury",
    r"no hard ?hat|without (a )?hard ?hat": "Hard hat not worn",
    r"spill|leak(ed|ing)? (fuel|oil|diesel)": "Spill",
    r"fell|fall(ing)? from": "Fall incident",
    r"guard ?rail (missing|down|removed)|open (edge|hole)": "Unprotected edge or opening",
}


def rule_flags(notes: str) -> list[str]:
    text = notes.lower()
    return [label for pattern, label in SAFETY_WORDS.items() if re.search(pattern, text)]


def _chat(system: str, user: str) -> str:
    payload = {"model": CHAT_MODEL, "stream": False, "format": "json", "options": {"temperature": 0},
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(OLLAMA_URL + "/api/chat", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())["message"]["content"]


def _parse(text: str) -> dict:
    text = re.sub(r"```(json)?", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else {}


def structure_report(notes: str, chat=None) -> dict:
    """Returns a report dict + 'ai_ok' flag. Falls back to rules-only if the AI is unavailable."""
    chat = chat or _chat
    flags = rule_flags(notes)
    try:
        data = _parse(chat(SYSTEM, f"FOREMAN NOTES:\n{notes}"))
        ai_ok = True
    except Exception as e:  # Ollama not running, model missing, bad JSON...
        data, ai_ok = {}, False
        error = str(e)
    delays = [d for d in (data.get("delays") or []) if isinstance(d, dict)]
    safety = list(dict.fromkeys([*(data.get("safety_issues") or []), *[f"⚑ {f} (rule check)" for f in flags]]))
    hours = 0.0
    for d in delays:
        try:
            hours += float(d.get("hours") or 0)
        except (TypeError, ValueError):
            pass
    crew = data.get("crew_count")
    return {
        "ai_ok": ai_ok,
        "error": None if ai_ok else error,
        "crew_count": crew if isinstance(crew, int) else None,
        "weather": data.get("weather") or "",
        "work_done": "\n".join(data.get("work_done") or []),
        "delays": "\n".join(f"{d.get('reason', '')} ({d.get('hours', 0)} h)" for d in delays),
        "delay_hours": round(hours, 1),
        "safety": "\n".join(safety),
        "materials": "\n".join(data.get("materials_needed") or []),
        "summary": data.get("summary") or "",
    }
