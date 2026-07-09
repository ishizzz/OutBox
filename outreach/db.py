"""SQLite persistence for targets and drafts."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "outreach.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    role TEXT NOT NULL,
    contact_name TEXT,
    contact_title TEXT,
    contact_email TEXT NOT NULL,
    posting_url TEXT,
    posting_text TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL,
    sent_at TEXT,
    replied_at TEXT
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id INTEGER NOT NULL REFERENCES targets(id),
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    model TEXT,
    claims_report TEXT,
    created_at TEXT NOT NULL
);
"""

FOLLOW_UP_DAYS = 7


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Migrate databases created before contact_title existed
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(targets)")]
        if "contact_title" not in cols:
            conn.execute("ALTER TABLE targets ADD COLUMN contact_title TEXT")


def now():
    return datetime.utcnow().isoformat(timespec="seconds")


# ---------- targets ----------

def add_target(company, role, contact_name, contact_email, posting_url,
               posting_text, contact_title=""):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO targets (company, role, contact_name, contact_title, "
            "contact_email, posting_url, posting_text, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?)",
            (company.strip(), role.strip(), (contact_name or "").strip(),
             (contact_title or "").strip(), contact_email.strip(),
             (posting_url or "").strip(), (posting_text or "").strip(), now()),
        )
        return cur.lastrowid


def get_target(target_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM targets WHERE id = ?", (target_id,)).fetchone()
        return dict(row) if row else None


def prior_sends(email, exclude_id=None):
    """Targets already emailed (sent/replied) at this address, case-insensitive.

    Used to warn before emailing the same person twice. `exclude_id` skips the
    target being acted on so it never counts itself.
    """
    email = (email or "").strip().lower()
    if not email:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, company, role, sent_at FROM targets "
            "WHERE status IN ('sent', 'replied') "
            "AND lower(trim(contact_email)) = ? ORDER BY id DESC",
            (email,),
        ).fetchall()
    return [dict(r) for r in rows if r["id"] != exclude_id]


def list_targets():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT t.*, d.subject AS draft_subject, d.claims_report AS draft_claims_report "
            "FROM targets t LEFT JOIN drafts d ON d.id = ("
            "  SELECT id FROM drafts WHERE target_id = t.id ORDER BY id DESC LIMIT 1"
            ") "
            "ORDER BY CASE t.status WHEN 'drafted' THEN 0 WHEN 'new' THEN 1 "
            "WHEN 'sent' THEN 2 WHEN 'replied' THEN 3 ELSE 4 END, t.id DESC"
        ).fetchall()
        targets = [dict(r) for r in rows]
    # Map each email we've already emailed (sent/replied) to those targets, so
    # we can flag any OTHER target that reuses the same contact address.
    emailed = {}
    for t in targets:
        email = (t.get("contact_email") or "").strip().lower()
        if email and t["status"] in ("sent", "replied"):
            emailed.setdefault(email, []).append(t)

    cutoff = datetime.utcnow() - timedelta(days=FOLLOW_UP_DAYS)
    for t in targets:
        t["needs_follow_up"] = (
            t["status"] == "sent"
            and t["sent_at"]
            and datetime.fromisoformat(t["sent_at"]) < cutoff
        )
        t["unsupported_count"] = 0
        if t.get("draft_claims_report"):
            try:
                t["unsupported_count"] = json.loads(t["draft_claims_report"]).get("unsupported_count", 0)
            except (TypeError, json.JSONDecodeError):
                pass

        email = (t.get("contact_email") or "").strip().lower()
        priors = [o for o in emailed.get(email, []) if o["id"] != t["id"]]
        t["contacted_before"] = bool(priors)
        t["contacted_before_count"] = len(priors)
        t["contacted_before_where"] = [
            o["company"] + (" (" + o["role"] + ")" if o.get("role") else "")
            for o in priors
        ]
    return targets


def sent_activity(days=7):
    """Daily counts of emails sent over the last `days` days, in LOCAL time.

    sent_at is stored as naive UTC (see now()); convert each to the machine's
    local timezone before bucketing so 'today' lines up with the wall clock.
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT sent_at FROM targets WHERE sent_at IS NOT NULL AND sent_at != ''"
        ).fetchall()
    counts = {}
    for r in rows:
        try:
            dt = datetime.fromisoformat(r["sent_at"]).replace(tzinfo=timezone.utc).astimezone()
        except (TypeError, ValueError):
            continue
        d = dt.date()
        counts[d] = counts.get(d, 0) + 1
    today = datetime.now().date()
    series = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        series.append({
            "date": d.isoformat(),
            "weekday": d.strftime("%a"),
            "label": d.strftime("%b ") + str(d.day),
            "count": counts.get(d, 0),
            "is_today": d == today,
        })
    return {
        "series": series,
        "week_total": sum(s["count"] for s in series),
        "today": counts.get(today, 0),
        "max": max((s["count"] for s in series), default=0),
    }


def set_status(target_id, status, **stamps):
    fields = ["status = ?"]
    values = [status]
    for col, val in stamps.items():
        fields.append(f"{col} = ?")
        values.append(val)
    values.append(target_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE targets SET {', '.join(fields)} WHERE id = ?", values)


def update_posting_text(target_id, posting_text):
    with get_conn() as conn:
        conn.execute("UPDATE targets SET posting_text = ? WHERE id = ?",
                     (posting_text, target_id))


# ---------- drafts ----------

def save_draft(target_id, subject, body, model, claims_report):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO drafts (target_id, subject, body, model, claims_report, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (target_id, subject, body, model,
             json.dumps(claims_report) if claims_report else None, now()),
        )
        return cur.lastrowid


def latest_draft(target_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM drafts WHERE target_id = ? ORDER BY id DESC LIMIT 1",
            (target_id,),
        ).fetchone()
    if not row:
        return None
    draft = dict(row)
    if draft.get("claims_report"):
        try:
            draft["claims_report"] = json.loads(draft["claims_report"])
        except (TypeError, json.JSONDecodeError):
            draft["claims_report"] = None
    return draft


def update_draft(draft_id, subject, body):
    with get_conn() as conn:
        conn.execute("UPDATE drafts SET subject = ?, body = ? WHERE id = ?",
                     (subject, body, draft_id))
