"""Fetch Pokémon names from PokeAPI v2 (paginated /pokemon list)."""

import json
from typing import Any, Iterator
from urllib.request import Request, urlopen

BASE = "https://pokeapi.co/api/v2/pokemon"
USER_AGENT = "pokemon-team-generator/1.0"
PAGE_SIZE = 1000
TIMEOUT_S = 60


def _is_excluded_form(name: str) -> bool:
    """True if the slug is Mega, Gigantamax, Totem, or Starter (e.g. Let's Go partner) variant."""
    n = name.lower()
    if "-mega" in n or "-gmax" in n or "-totem" in n:
        return True
    # e.g. pikachu-starter, eevee-starter — list UI would show "Pikachu (Starter)".
    return n.endswith("-starter")


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
                if _is_excluded_form(name):
                    continue
                url = str(item["url"])
                yield {
                    "name": name,
                    "url": url,
                    "sprite_url": _official_artwork_url_from_list_url(url),
                }
        nxt = page.get("next")
        next_url = str(nxt) if nxt else None


def _pretty_api_name(name: str) -> str:
    """PokeAPI lowercase hyphenated names → Title Case With Spaces."""
    return name.replace("-", " ").strip().title()


def fetch_pokemon_battle_profile(slug: str) -> dict[str, Any]:
    """
    Abilities, typings, base stats, and level-up moves for battle narration.
    ``slug`` is the PokeAPI Pokémon identifier (e.g. ``charizard``).
    """
    data = _fetch_json(f"{BASE}/{slug}/")
    types: list[str] = []
    for t in sorted(data.get("types") or [], key=lambda x: int(x.get("slot", 0))):
        tn = (t.get("type") or {}).get("name")
        if tn:
            types.append(str(tn))

    abilities: list[dict[str, Any]] = []
    for ab in data.get("abilities") or []:
        raw = (ab.get("ability") or {}).get("name")
        if raw:
            abilities.append(
                {
                    "name": str(raw),
                    "display": _pretty_api_name(str(raw)),
                    "is_hidden": bool(ab.get("is_hidden")),
                }
            )

    base_stats: dict[str, int] = {}
    for st in data.get("stats") or []:
        sn = (st.get("stat") or {}).get("name")
        if sn:
            base_stats[str(sn)] = int(st.get("base_stat") or 0)

    seen_moves: set[str] = set()
    level_moves: list[str] = []
    for entry in data.get("moves") or []:
        move = entry.get("move") or {}
        mn = move.get("name")
        if not mn or not isinstance(mn, str):
            continue
        for vgd in entry.get("version_group_details") or []:
            if (vgd.get("move_learn_method") or {}).get("name") == "level-up":
                if mn not in seen_moves:
                    seen_moves.add(mn)
                    level_moves.append(mn)
                break

    return {
        "slug": slug,
        "types": types,
        "abilities": abilities,
        "base_stats": base_stats,
        "level_up_moves": level_moves[:12],
    }