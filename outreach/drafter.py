"""Draft outreach emails with OpenAI, then verify every claim against the resume.

Two passes:
1. Draft: writes a short, specific email grounded ONLY in the resume text.
2. Validate: a separate call lists each factual claim about the candidate
   in the draft and checks whether the resume supports it. Unsupported
   claims are flagged in the review UI so nothing embellished goes out.
"""

import json
import os

from openai import OpenAI

DRAFT_MODEL = os.environ.get("DRAFT_MODEL", "gpt-4o")
VALIDATE_MODEL = os.environ.get("VALIDATE_MODEL", "gpt-4o-mini")

DRAFT_SYSTEM = """You write short cold outreach emails for a job seeker.

Hard rules, in priority order:
1. NEVER state anything about the candidate that is not literally supported by
   the resume text provided. Do not infer skills, inflate titles, add tools,
   or round up numbers. If the posting asks for something the resume does not
   show, do not claim it.
2. 110 to 160 words in the body. Recruiters skim.
3. Reference 2 or 3 SPECIFIC things from the resume that map to SPECIFIC
   needs in the posting or company description. No generic praise of the
   company, no "I am passionate about" filler.
4. Plain, direct, warm-professional tone. No emojis. No em dashes anywhere;
   use commas, periods, or parentheses instead.
5. End with one clear, low-friction ask (a short call, or consideration for
   the role) and mention the resume is attached.
7. Tailor the angle to the recipient's designation when one is given:
   - Recruiter / HR / talent: lead with clean role fit. Mirror the posting's
     key requirement language where the resume genuinely matches, state
     degree and graduation plainly, keep it easy to forward internally.
   - Hiring manager / engineering manager / team lead: lead with technical
     substance. Pick the 1 or 2 resume projects closest to their stack and
     describe what was built and its outcome. Less positioning, more depth.
   - Founder / co-founder / CEO / executive: lead with ownership and impact.
     Emphasize shipping end to end, speed, and how the candidate's work
     connects to what the company is building. Keep it especially short.
   - Unknown designation: default to the hiring manager register.
6. The candidate has already graduated (MS in Computer Science, May 2026).
   Never describe them as a current student.

Respond ONLY with JSON, no markdown fences, in this exact shape:
{"subject": "...", "body": "..."}
The body should use \\n\\n between paragraphs and end with a sign-off using
the candidate's name."""

VALIDATE_SYSTEM = """You are a strict fact checker. You receive a resume and a
draft email written on behalf of the candidate. Extract every factual claim
the email makes about the candidate (skills, projects, tools, titles,
education, metrics). For each claim decide if the resume text literally
supports it. Be strict: an inferred or exaggerated claim is unsupported.
Claims about the company or the role itself are out of scope; skip them.

Respond ONLY with JSON, no markdown fences:
{"claims": [{"claim": "...", "supported": true, "evidence": "short quote or explanation"}]}"""


def _client():
    return OpenAI()  # reads OPENAI_API_KEY from environment


def _parse_json(raw):
    clean = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(clean)


def draft_email(resume_text, target):
    posting = target.get("posting_text") or "(no posting text available; write based on company and role title only, and keep claims conservative)"
    contact = target.get("contact_name") or "the hiring team"
    title = target.get("contact_title") or "unknown"
    candidate = os.environ.get("YOUR_NAME", "the candidate")

    user_prompt = (
        f"CANDIDATE NAME: {candidate}\n\n"
        f"RESUME (the only permitted source of claims about the candidate):\n"
        f"{resume_text}\n\n"
        f"TARGET COMPANY: {target['company']}\n"
        f"TARGET ROLE: {target['role']}\n"
        f"RECIPIENT: {contact}\n"
        f"RECIPIENT DESIGNATION: {title}\n\n"
        f"JOB POSTING / COMPANY CONTEXT:\n{posting}\n\n"
        f"Write the outreach email now."
    )

    resp = _client().chat.completions.create(
        model=DRAFT_MODEL,
        messages=[
            {"role": "system", "content": DRAFT_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
    )
    data = _parse_json(resp.choices[0].message.content)
    return data["subject"], data["body"]


def validate_claims(resume_text, subject, body):
    user_prompt = (
        f"RESUME:\n{resume_text}\n\n"
        f"DRAFT EMAIL:\nSubject: {subject}\n\n{body}"
    )
    try:
        resp = _client().chat.completions.create(
            model=VALIDATE_MODEL,
            messages=[
                {"role": "system", "content": VALIDATE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        report = _parse_json(resp.choices[0].message.content)
        claims = report.get("claims", [])
        report["unsupported_count"] = sum(1 for c in claims if not c.get("supported"))
        return report
    except Exception as exc:  # validation failing should not block drafting
        return {"claims": [], "unsupported_count": 0, "error": str(exc)}


def generate(resume_text, target):
    subject, body = draft_email(resume_text, target)
    report = validate_claims(resume_text, subject, body)
    return subject, body, report
