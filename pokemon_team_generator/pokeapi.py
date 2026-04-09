"""Fetch Pokémon names from PokeAPI v2 (paginated /pokemon list)."""

import json
from typing import Iterator
from urllib.request import Request, urlopen

BASE = "https://pokeapi.co/api/v2/pokemon"
USER_AGENT = "pokemon-team-generator/1.0"
PAGE_SIZE = 1000
TIMEOUT_S = 60


def _is_mega_or_gmax_form(name: str) -> bool:
    """True if the species slug is a Mega evolution or Gigantamax form."""
    n = name.lower()
    return "-mega" in n or "-gmax" in n


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
                name = str(item["name"])
                if _is_mega_or_gmax_form(name):
                    continue
                yield {"name": name, "url": str(item["url"])}
        nxt = page.get("next")
        next_url = str(nxt) if nxt else None