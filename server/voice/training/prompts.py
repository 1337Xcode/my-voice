"""Teach prompt lists (spec 9.5, 11.9): the 72 Harvard lists fetched from the source page, and the default phrases."""

import html
import json
import re

import httpx

from voice.config import ASSETS_ROOT
from voice.storage import shared_dir, write_json

HARVARD_URL = "https://www.cs.columbia.edu/~hgs/audio/harvard.html"
HARVARD_LISTS = 72
SENTENCES_PER_LIST = 10
FETCH_TIMEOUT_S = 30
# Each list on the page is "<h2>List N</h2>" followed by an <ol> of <li> sentences.
LIST_PATTERN = re.compile(r"<h2>\s*List\s+(\d+)\s*</h2>\s*<ol>(.*?)</ol>", re.IGNORECASE | re.DOTALL)
ITEM_PATTERN = re.compile(r"<li>(.*?)(?=<li>|</li>|$)", re.IGNORECASE | re.DOTALL)
TAG_PATTERN = re.compile(r"<[^>]+>")


def parse_harvard(page: str) -> list[list[str]]:
    """Every list on the Harvard sentences page, in order, each a list of 10 sentences."""
    lists: list[list[str]] = []
    for number, body in LIST_PATTERN.findall(page):
        sentences = [" ".join(html.unescape(TAG_PATTERN.sub("", item)).split()) for item in ITEM_PATTERN.findall(body)]
        sentences = [sentence for sentence in sentences if sentence]
        if int(number) != len(lists) + 1 or len(sentences) != SENTENCES_PER_LIST:
            raise ValueError(f"Harvard list {number} has {len(sentences)} sentences or is out of order.")
        lists.append(sentences)
    if len(lists) != HARVARD_LISTS:
        raise ValueError(f"Expected {HARVARD_LISTS} Harvard lists, found {len(lists)}.")
    return lists


def fetch_harvard() -> list[list[str]]:
    """Downloads and parses the Harvard sentences page."""
    response = httpx.get(HARVARD_URL, timeout=FETCH_TIMEOUT_S, follow_redirects=True)
    response.raise_for_status()
    return parse_harvard(response.text)


def harvard_prompts(lists: list[list[str]]) -> dict:
    """The stored form: list 1 is the onboarding test set (ta01..ta10); lists 2+ are Teach prompts."""
    test = [{"id": f"ta{index:02d}", "text": text} for index, text in enumerate(lists[0], start=1)]
    teach = [
        {"id": f"h{number:02d}-{index:02d}", "list": number, "text": text}
        for number, sentences in enumerate(lists[1:], start=2)
        for index, text in enumerate(sentences, start=1)
    ]
    return {"source": HARVARD_URL, "lists": lists, "test": test, "teach": teach}


def build_prompts() -> dict:
    """Writes `_shared/prompts/harvard.json` and `default_phrases.json`; returns counts."""
    prompts = harvard_prompts(fetch_harvard())
    write_json(shared_dir("prompts") / "harvard.json", prompts)
    defaults = json.loads((ASSETS_ROOT / "default_phrases.json").read_text(encoding="utf-8"))
    write_json(shared_dir("prompts") / "default_phrases.json", defaults)
    return {"harvard_lists": len(prompts["lists"]), "teach_prompts": len(prompts["teach"]), "default_phrases": sum(map(len, defaults.values()))}
