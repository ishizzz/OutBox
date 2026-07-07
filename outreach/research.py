"""Fetch and clean job posting text from a URL."""

import requests
from bs4 import BeautifulSoup

MAX_CHARS = 6000
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}


def fetch_posting(url):
    """Return cleaned text from a job posting URL, or None on failure.

    Many job boards (Greenhouse, Lever, Ashby) serve readable HTML.
    Some (LinkedIn, Workday) block scripted fetches; for those, paste
    the posting text directly into the target form instead.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    text = " ".join(soup.get_text(separator=" ").split())
    if len(text) < 300:
        return None
    return text[:MAX_CHARS]
