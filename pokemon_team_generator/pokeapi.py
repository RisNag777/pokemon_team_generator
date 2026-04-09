"""Fetch Pokémon names from PokeAPI v2 (paginated /pokemon list)."""

from __future__ import annotations

import json
from typing import Iterator
from urllib.request import Request, urlopen

BASE = "https://pokeapi.co/api/v2/pokemon"
USER_AGENT = "pokemon-team-generator/1.0"
PAGE_SIZE = 1000
TIMEOUT_S = 60

__all__ = ["iter_pokemon_list_entries", "names_starting_with"]


def _fetch_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=TIMEOUT_S) as resp:
        data = json.loads(resp.read().decode())
    if not isinstance(data, dict):
        raise TypeError("expected JSON object")
    return data


def iter_pokemon_list_entries() -> Iterator[dict[str, str]]:
    """Yield each list entry: {\"name\", \"url\"} across all pages."""
    next_url: str | None = f"{BASE}?limit={PAGE_SIZE}&offset=0"
    while next_url:
        page = _fetch_json(next_url)
        results = page.get("results") or []
        if not isinstance(results, list):
            raise TypeError("invalid results")
        for item in results:
            if isinstance(item, dict) and "name" in item and "url" in item:
                yield {"name": str(item["name"]), "url": str(item["url"])}
        nxt = page.get("next")
        next_url = str(nxt) if nxt else None


def names_starting_with(letter: str) -> list[str]:
    letter = letter.strip().lower()
    if len(letter) != 1 or not letter.isalpha():
        raise ValueError("expected a single A–Z letter")
    prefix = letter
    out: list[str] = []
    for row in iter_pokemon_list_entries():
        name = row["name"]
        if name.startswith(prefix):
            out.append(name)
    out.sort()
    return out
