"""Streamlit UI: build a Pokémon team from your name (PokeAPI v2)."""

from __future__ import annotations

import string

import streamlit as st

from pokemon_team_generator.pokeapi import iter_pokemon_list_entries


def _display_name(slug: str) -> str:
    """Format PokeAPI slug for display (hyphens as word breaks, title case)."""
    return slug.replace("-", " ").title()


def _letters_a_to_z(raw: str) -> list[str]:
    """Uppercase A–Z letters only (English Pokédex slugs)."""
    return [c.upper() for c in raw if c.upper() in string.ascii_uppercase]


@st.cache_data(ttl=3600, show_spinner="Loading Pokédex from PokeAPI…")
def all_pokemon_rows() -> list[dict[str, str]]:
    return sorted(iter_pokemon_list_entries(), key=lambda r: r["name"])


def _matches_for_letter(rows: list[dict[str, str]], letter: str) -> list[dict[str, str]]:
    prefix = letter.lower()
    return [r for r in rows if r["name"].startswith(prefix)]


def page_team_for_name(rows: list[dict[str, str]]) -> None:
    st.header("Create a Pokémon team for your name")
    st.caption(
        "For each letter in your name (A–Z), choose one Pokémon from the dropdown "
        "(English names). Your team appears at the bottom."
    )

    raw_name = st.text_input(
        "Your name",
        placeholder="e.g. Ash",
        max_chars=64,
    )
    letters = _letters_a_to_z(raw_name)
    normalized = "".join(c.lower() for c in letters)

    if not raw_name.strip():
        st.info("Enter a name to build your team.")
        return

    if not letters:
        st.warning("Use letters A–Z in your name. Spaces and punctuation are ignored.")
        return

    st.write(f"**Letters:** {' '.join(letters)}")

    slug_to_row = {r["name"]: r for r in rows}
    picks: list[tuple[str, dict[str, str]]] = []

    for i, letter in enumerate(letters):
        matches = _matches_for_letter(rows, letter)
        if not matches:
            st.warning(f"No Pokémon found for letter {letter} (position {i + 1}).")
            continue

        slugs = [r["name"] for r in matches]
        key = f"team_pick_{normalized}_{i}"

        if key not in st.session_state:
            st.session_state[key] = slugs[0]
        elif st.session_state[key] not in slugs:
            st.session_state[key] = slugs[0]

        st.markdown(f"**Letter {letter}** — pick {i + 1} of {len(letters)}")
        choice = st.selectbox(
            f"Pokémon for “{letter}”",
            options=slugs,
            format_func=_display_name,
            key=key,
        )
        row = slug_to_row[choice]
        st.image(row["sprite_url"], width=120)
        picks.append((choice, row))

    if not picks:
        return

    st.divider()
    st.subheader("Your team")
    per_row = 6
    for start in range(0, len(picks), per_row):
        chunk = picks[start : start + per_row]
        cols = st.columns(len(chunk))
        for col, (slug, row) in zip(cols, chunk):
            with col:
                st.image(row["sprite_url"], width=96)
                st.caption(_display_name(slug))


def main() -> None:
    st.set_page_config(
        page_title="Pokémon team generator",
        page_icon="⚡",
        layout="wide",
    )

    st.title("Pokémon team generator")
    st.caption(
        "Data from [PokeAPI](https://pokeapi.co/). "
        "Mega and Gigantamax forms are excluded; other form variants may appear."
    )

    try:
        rows = all_pokemon_rows()
    except OSError as e:
        st.error(f"Could not reach PokeAPI: {e}")
        return

    page_team_for_name(rows)


main()
