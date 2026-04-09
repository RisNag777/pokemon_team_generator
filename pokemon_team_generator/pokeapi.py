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


def _official_artwork_url_from_list_url(list_url: str) -> str:
    """PNG on PokeAPI/sprites; ID matches the `/pokemon/{id}/` list URL."""
    segment = list_url.rstrip("/").rsplit("/", 1)[-1]
    pokemon_id = int(segment)
    return (
        "https://raw.githubusercontent.com/PokeAPI/sprites/master/"
        f"sprites/pokemon/other/official-artwork/{pokemon_id}.png"
    )


def _fetch_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=TIMEOUT_S) as resp:
        data = json.loads(resp.read().decode())
    if not isinstance(data, dict):
        raise TypeError("expected JSON object")
    return data


def iter_pokemon_list_entries() -> Iterator[dict[str, str]]:
    """Yield each list entry: {\"name\", \"url\", \"sprite_url\"} across all pages."""
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
                url = str(item["url"])
                yield {
                    "name": name,
                    "url": url,
                    "sprite_url": _official_artwork_url_from_list_url(url),
                }
        nxt = page.get("next")
        next_url = str(nxt) if nxt else None