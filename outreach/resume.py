"""Load resume text once from PDF or plain text."""

import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_resume_text():
    path = os.environ.get("RESUME_PATH", "")
    if not path:
        raise RuntimeError("RESUME_PATH is not set in your .env file.")
    p = Path(path).expanduser()
    if not p.exists():
        raise RuntimeError(f"Resume not found at {p}. Check RESUME_PATH in .env.")

    if p.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(p))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    else:
        text = p.read_text(encoding="utf-8", errors="ignore")

    text = text.strip()
    if len(text) < 200:
        raise RuntimeError(
            "Extracted resume text is suspiciously short. If your PDF is a scan, "
            "export a text-based PDF or point RESUME_PATH at a .txt version."
        )
    return text


def resume_attachment_path():
    return str(Path(os.environ.get("RESUME_PATH", "")).expanduser())
