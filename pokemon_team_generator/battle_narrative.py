"""Generate a written Pokémon battle script from two saved teams (OpenAI + PokeAPI data)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pokemon_team_generator.pokeapi import fetch_pokemon_battle_profile

BATTLE_TEMPERATURE = 0.5
_DEFAULT_MODEL = "gpt-4o-mini"


def ordered_team_slugs(team_slots: list[list[str]], *, max_size: int = 6) -> list[str]:
    """Flatten per-letter slots in order; cap at six Pokémon like a standard battle team."""
    out: list[str] = []
    for slot in team_slots:
        for raw in slot:
            s = (raw or "").strip()
            if s:
                out.append(s)
    return out[:max_size]


def _pretty_move(name: str) -> str:
    return name.replace("-", " ").strip().title()


def load_roster_profiles(
    slugs: list[str],
    label_for_slug: Callable[[str], str],
) -> list[dict[str, Any]]:
    """Fetch PokeAPI data for each slug and attach a display ``label``."""
    out: list[dict[str, Any]] = []
    for s in slugs:
        p = fetch_pokemon_battle_profile(s)
        p["label"] = label_for_slug(s)
        out.append(p)
    return out


def _format_pokemon_block(p: dict[str, Any]) -> str:
    st = p["base_stats"]
    ab_lines = []
    for a in p["abilities"]:
        tag = " (hidden ability)" if a["is_hidden"] else ""
        ab_lines.append(f"{a['display']}{tag}")
    moves = [_pretty_move(m) for m in p["level_up_moves"][:10]]
    types = [_pretty_move(t) for t in p["types"]]
    return (
        f"  • {p['label']} [{p['slug']}]\n"
        f"      Types: {', '.join(types)}\n"
        f"      Abilities: {', '.join(ab_lines)}\n"
        f"      Base stats — HP {st.get('hp', 0)}, Atk {st.get('attack', 0)}, "
        f"Def {st.get('defense', 0)}, SpA {st.get('special-attack', 0)}, "
        f"SpD {st.get('special-defense', 0)}, Spe {st.get('speed', 0)}\n"
        f"      Level-up moves (sample): {', '.join(moves) if moves else '(none listed)'}"
    )


def _build_user_prompt(
    trainer_a: str,
    trainer_b: str,
    roster_a: list[dict[str, Any]],
    roster_b: list[dict[str, Any]],
) -> str:
    block_a = "\n".join(_format_pokemon_block(p) for p in roster_a) or "  (no Pokémon)"
    block_b = "\n".join(_format_pokemon_block(p) for p in roster_b) or "  (no Pokémon)"
    return (
        f"Trainer A — {trainer_a}\n{block_a}\n\n"
        f"Trainer B — {trainer_b}\n{block_b}\n\n"
        "Write the battle using this data. Assign each Pokémon a plausible held item "
        "(name items explicitly) that fits its stats and typings. Use abilities, moves, "
        "stats, typings, and items in the narration; reference type effectiveness where it matters."
    )


_SYSTEM = """You write turn-by-turn Pokémon battle scripts for entertainment.

Rules:
- Use ONLY the Pokémon data given (species names, typings, base stats, abilities, and the listed moves). You may assign held items that are plausible for each Pokémon; name each item when it matters.
- Simulate a singles match: lead Pokémon sent out first unless you briefly explain a switch. Include multiple turns, switches when appropriate, ability triggers, item effects, and move choices from the listed level-up moves (you may omit some moves; do not invent moves not listed unless you clearly mark them as Struggle or as last-resort after PP exhaustion—prefer listed moves).
- Base outcomes on typings, relative stats, and plausible damage—keep tension; avoid a one-shot wipe unless the data supports it.
- Temperature is already applied; allow some unpredictability (crits, surprising switches, clutches) without breaking type logic.
- Format as a readable script: optional short scene setup, then numbered turns or labeled exchanges (Trainer A / Trainer B). End with a clear result.
- Do not repeat raw stat tables; weave numbers into the narrative sparingly."""


def generate_battle_script(
    *,
    api_key: str,
    trainer_a_name: str,
    trainer_b_name: str,
    roster_a: list[dict[str, Any]],
    roster_b: list[dict[str, Any]],
    model: str = _DEFAULT_MODEL,
) -> str:
    """Call OpenAI Chat Completions to produce the battle narrative."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=180.0, max_retries=2)
    user_content = _build_user_prompt(trainer_a_name, trainer_b_name, roster_a, roster_b)
    resp = client.chat.completions.create(
        model=model,
        temperature=BATTLE_TEMPERATURE,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ],
    )
    choice = resp.choices[0].message
    text = (choice.content or "").strip()
    if not text:
        raise RuntimeError("OpenAI returned an empty battle script")
    return text
