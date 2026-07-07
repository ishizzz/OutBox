"""Job outreach automator: draft with AI, verify claims, review, send.

Run:  python app.py   then open http://127.0.0.1:5000
"""

import csv
import io

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, flash, redirect, render_template, request, url_for

from outreach import db
from outreach.drafter import DRAFT_MODEL, generate
from outreach.mailer import send_email
from outreach.research import fetch_posting
from outreach.resume import load_resume_text

app = Flask(__name__)
app.secret_key = "local-only-tool"

db.init_db()


@app.route("/")
def index():
    targets = db.list_targets()
    counts = {}
    for t in targets:
        counts[t["status"]] = counts.get(t["status"], 0) + 1
    follow_ups = sum(1 for t in targets if t["needs_follow_up"])
    return render_template("index.html", targets=targets, counts=counts,
                           follow_ups=follow_ups)


@app.route("/targets/new", methods=["GET", "POST"])
def new_target():
    if request.method == "POST":
        company = request.form.get("company", "").strip()
        role = request.form.get("role", "").strip()
        contact_email = request.form.get("contact_email", "").strip()
        if not (company and role and contact_email):
            flash("Company, role, and contact email are required.", "error")
            return render_template("target_form.html", form=request.form)
        target_id = db.add_target(
            company=company,
            role=role,
            contact_name=request.form.get("contact_name", ""),
            contact_title=request.form.get("contact_title", ""),
            contact_email=contact_email,
            posting_url=request.form.get("posting_url", ""),
            posting_text=request.form.get("posting_text", ""),
        )
        flash(f"Added {company}.", "ok")
        return redirect(url_for("index", _anchor=f"t{target_id}"))
    return render_template("target_form.html", form={})


@app.route("/targets/import", methods=["POST"])
def import_csv():
    file = request.files.get("csv_file")
    if not file:
        flash("No CSV file selected.", "error")
        return redirect(url_for("index"))
    added, skipped = 0, 0
    reader = csv.DictReader(io.StringIO(file.read().decode("utf-8-sig")))
    for row in reader:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        if row.get("company") and row.get("role") and row.get("contact_email"):
            db.add_target(
                company=row["company"], role=row["role"],
                contact_name=row.get("contact_name", ""),
                contact_title=row.get("contact_title", ""),
                contact_email=row["contact_email"],
                posting_url=row.get("posting_url", ""),
                posting_text=row.get("posting_text", ""),
            )
            added += 1
        else:
            skipped += 1
    flash(f"Imported {added} target(s)." + (f" Skipped {skipped} incomplete row(s)." if skipped else ""),
          "ok" if added else "error")
    return redirect(url_for("index"))


@app.route("/targets/<int:target_id>/draft", methods=["POST"])
def create_draft(target_id):
    target = db.get_target(target_id)
    if not target:
        flash("Target not found.", "error")
        return redirect(url_for("index"))
    try:
        resume_text = load_resume_text()
    except RuntimeError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))

    if not target["posting_text"] and target["posting_url"]:
        posting = fetch_posting(target["posting_url"])
        if posting:
            db.update_posting_text(target_id, posting)
            target["posting_text"] = posting
        else:
            flash("Could not fetch the posting URL (some job boards block scripts). "
                  "Drafting from company and role only; paste the posting text for a "
                  "stronger draft.", "error")

    try:
        subject, body, report = generate(resume_text, target)
    except Exception as exc:
        flash(f"Draft failed: {exc}", "error")
        return redirect(url_for("index"))

    db.save_draft(target_id, subject, body, DRAFT_MODEL, report)
    db.set_status(target_id, "drafted")
    return redirect(url_for("review", target_id=target_id))


@app.route("/targets/<int:target_id>/review")
def review(target_id):
    target = db.get_target(target_id)
    draft = db.latest_draft(target_id)
    if not target or not draft:
        flash("Nothing to review yet. Generate a draft first.", "error")
        return redirect(url_for("index"))
    return render_template("review.html", target=target, draft=draft)


@app.route("/targets/<int:target_id>/save", methods=["POST"])
def save_edits(target_id):
    draft = db.latest_draft(target_id)
    if draft:
        db.update_draft(draft["id"], request.form["subject"], request.form["body"])
        flash("Edits saved.", "ok")
    return redirect(url_for("review", target_id=target_id))


@app.route("/targets/<int:target_id>/send", methods=["POST"])
def approve_and_send(target_id):
    target = db.get_target(target_id)
    draft = db.latest_draft(target_id)
    if not (target and draft):
        flash("Nothing to send.", "error")
        return redirect(url_for("index"))
    # Persist any last-minute edits from the review form before sending
    subject = request.form.get("subject", draft["subject"])
    body = request.form.get("body", draft["body"])
    db.update_draft(draft["id"], subject, body)
    try:
        send_email(target["contact_email"], subject, body)
    except Exception as exc:
        flash(f"Send failed: {exc}", "error")
        return redirect(url_for("review", target_id=target_id))
    db.set_status(target_id, "sent", sent_at=db.now())
    flash(f"Sent to {target['contact_email']}.", "ok")
    return redirect(url_for("index"))


@app.route("/targets/process-all", methods=["POST"])
def process_all():
    pending = [t for t in db.list_targets() if t["status"] == "new"]
    if not pending:
        flash("No pending targets to process.", "error")
        return redirect(url_for("index"))
    try:
        resume_text = load_resume_text()
    except RuntimeError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))

    sent, held, failed = [], [], []
    for t in pending:
        target_id = t["id"]
        target = db.get_target(target_id)
        if not target:
            continue

        if not target["posting_text"] and target["posting_url"]:
            posting = fetch_posting(target["posting_url"])
            if posting:
                db.update_posting_text(target_id, posting)
                target["posting_text"] = posting

        try:
            subject, body, report = generate(resume_text, target)
        except Exception as exc:
            failed.append(f"{target['company']} (draft failed: {exc})")
            continue

        db.save_draft(target_id, subject, body, DRAFT_MODEL, report)
        db.set_status(target_id, "drafted")

        if report and report.get("unsupported_count"):
            held.append(target["company"])
            continue

        try:
            send_email(target["contact_email"], subject, body)
        except Exception as exc:
            failed.append(f"{target['company']} (send failed: {exc})")
            continue
        db.set_status(target_id, "sent", sent_at=db.now())
        sent.append(target["company"])

    if sent:
        flash(f"Sent {len(sent)} email(s) automatically: {', '.join(sent)}.", "ok")
    if held:
        flash(f"Drafted {len(held)} but held for review (unverified claims found): "
              f"{', '.join(held)}. Review and send them from the pipeline.", "error")
    if failed:
        flash(f"Failed to process {len(failed)}: {', '.join(failed)}.", "error")
    if not (sent or held or failed):
        flash("Nothing processed.", "error")
    return redirect(url_for("index"))


@app.route("/targets/send-bulk", methods=["POST"])
def send_bulk():
    ids = [int(i) for i in request.form.getlist("target_ids") if i.isdigit()]
    if not ids:
        flash("No drafts selected to send.", "error")
        return redirect(url_for("index"))

    sent, failed = [], []
    for target_id in ids:
        target = db.get_target(target_id)
        draft = db.latest_draft(target_id)
        if not target or not draft or target["status"] != "drafted":
            continue
        try:
            send_email(target["contact_email"], draft["subject"], draft["body"])
        except Exception as exc:
            failed.append(f"{target['company']} ({exc})")
            continue
        db.set_status(target_id, "sent", sent_at=db.now())
        sent.append(target["company"])

    if sent:
        flash(f"Sent {len(sent)} email(s): {', '.join(sent)}.", "ok")
    if failed:
        flash(f"Failed to send {len(failed)}: {', '.join(failed)}.", "error")
    if not sent and not failed:
        flash("Nothing eligible to send (drafts may be stale, refresh and retry).", "error")
    return redirect(url_for("index"))


@app.route("/targets/<int:target_id>/skip", methods=["POST"])
def skip(target_id):
    db.set_status(target_id, "skipped")
    return redirect(url_for("index"))


@app.route("/targets/<int:target_id>/replied", methods=["POST"])
def mark_replied(target_id):
    db.set_status(target_id, "replied", replied_at=db.now())
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
