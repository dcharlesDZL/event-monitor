"""Collect news / policy items from RSS feeds + US Federal Register API."""
from __future__ import annotations

import hashlib
import re
import time
from calendar import timegm
from typing import Dict, List

import feedparser
import requests

from config import NEWS_FEEDS, URGENT_KEYWORDS

_HTML = re.compile(r"<[^>]+>")
_UA = {"User-Agent": "Mozilla/5.0 (event-monitor)"}

# In-memory translation cache: original text -> Chinese. Bounded to avoid growth.
_TR_CACHE: Dict[str, str] = {}
_TR_MAX = 5000


def _clean(text: str, limit: int = 280) -> str:
    text = _HTML.sub("", text or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def translate(text: str, tl: str = "zh-CN") -> str:
    """Translate via the free Google Translate endpoint (no key). Cached;
    returns the original text on any failure so the feed never breaks."""
    text = (text or "").strip()
    if not text:
        return text
    if text in _TR_CACHE:
        return _TR_CACHE[text]
    try:
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "auto", "tl": tl, "dt": "t", "q": text},
            headers=_UA, timeout=10,
        )
        data = r.json()
        out = "".join(seg[0] for seg in data[0] if seg and seg[0]).strip()
        result = out or text
    except Exception as e:  # noqa: BLE001
        print(f"[news] translate error: {e}")
        result = text
    if len(_TR_CACHE) < _TR_MAX:
        _TR_CACHE[text] = result
    return result


def _is_urgent(title: str, summary: str) -> bool:
    blob = ((title or "") + " " + (summary or "")).lower()
    return any(k.lower() in blob for k in URGENT_KEYWORDS)


def _mkitem(feed: Dict, title: str, link: str, summary: str, published: int) -> Dict:
    return {
        "id": hashlib.sha1(link.encode("utf-8")).hexdigest(),
        "category": feed["category"],
        "country": feed["country"],
        "source": feed["name"],
        "title": _clean(title, 200),
        "link": link,
        "summary": _clean(summary, 280),
        "urgent": _is_urgent(title, summary),
        "published": published,
        "fetched": int(time.time()),
    }


def _fetch_rss(feed: Dict) -> List[Dict]:
    items: List[Dict] = []
    try:
        resp = requests.get(feed["url"], headers=_UA, timeout=15)
        parsed = feedparser.parse(resp.content)
    except Exception as e:  # noqa: BLE001
        print(f"[news] RSS error {feed['name']}: {e}")
        return items
    for e in parsed.entries[:30]:
        link = e.get("link", "")
        if not link:
            continue
        pub = 0
        if e.get("published_parsed"):
            pub = timegm(e.published_parsed)
        elif e.get("updated_parsed"):
            pub = timegm(e.updated_parsed)
        raw_title = e.get("title", "")
        summary = e.get("summary", "")
        if feed.get("translate"):
            zh = translate(raw_title)
            if zh and zh != raw_title:
                # show Chinese title; keep the original underneath for reference
                summary = "原文: " + _clean(raw_title, 200)
                raw_title = zh
        items.append(_mkitem(feed, raw_title, link, summary, pub))
    return items


def _fetch_federal_register(feed: Dict) -> List[Dict]:
    """US presidential / policy documents via the Federal Register API (free)."""
    items: List[Dict] = []
    url = (
        "https://www.federalregister.gov/api/v1/documents.json"
        "?per_page=25&order=newest"
        "&fields[]=title&fields[]=html_url&fields[]=abstract"
        "&fields[]=publication_date&fields[]=type"
    )
    try:
        data = requests.get(url, headers=_UA, timeout=15).json()
    except Exception as e:  # noqa: BLE001
        print(f"[news] FederalRegister error: {e}")
        return items
    for d in data.get("results", []):
        link = d.get("html_url", "")
        if not link:
            continue
        pub = 0
        if d.get("publication_date"):
            try:
                pub = timegm(time.strptime(d["publication_date"], "%Y-%m-%d"))
            except ValueError:
                pub = 0
        title = f"[{d.get('type','')}] {d.get('title','')}"
        items.append(_mkitem(feed, title, link, d.get("abstract", ""), pub))
    return items


def collect_all() -> List[Dict]:
    out: List[Dict] = []
    for feed in NEWS_FEEDS:
        if feed["url"] == "FEDERAL_REGISTER":
            out.extend(_fetch_federal_register(feed))
        else:
            out.extend(_fetch_rss(feed))
    return out
