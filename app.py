"""Streamlit UI: list Pokémon whose names start with a chosen letter (PokeAPI v2)."""

from __future__ import annotations

import streamlit as st

from pokemon_team_generator.pokeapi import iter_pokemon_list_entries


def _display_name(slug: str) -> str:
    """Format PokeAPI slug for display (hyphens as word breaks, title case)."""
    return slug.replace("-", " ").title()


@st.cache_data(ttl=3600, show_spinner="Loading Pokédex from PokeAPI…")
def all_pokemon_rows() -> list[dict[str, str]]:
    return sorted(iter_pokemon_list_entries(), key=lambda r: r["name"])


def main() -> None:
    st.set_page_config(
        page_title="Pokémon by letter",
        page_icon="⚡",
        layout="centered",
    )
    st.title("Pokémon by first letter")
    st.caption(
        "Data from [PokeAPI](https://pokeapi.co/). "
        "Mega and Gigantamax forms are excluded; other form variants may appear."
    )

    letter = st.selectbox(
        "First letter",
        options=[chr(c) for c in range(ord("A"), ord("Z") + 1)],
        index=0,
    )

    try:
        rows = all_pokemon_rows()
    except OSError as e:
        st.error(f"Could not reach PokeAPI: {e}")
        return

    prefix = letter.lower()
    matches = [r for r in rows if r["name"].startswith(prefix)]

    st.metric("Matching Pokémon", len(matches))

    if not matches:
        st.info("No Pokémon found for this letter.")
        return

    st.dataframe(
        {
            "sprite_url": [r["sprite_url"] for r in matches],
            "name": [_display_name(r["name"]) for r in matches],
        },
        column_config={
            "sprite_url": st.column_config.ImageColumn("", width="small"),
            "name": st.column_config.TextColumn("Name"),
        },
        use_container_width=True,
        hide_index=True,
        height=min(600, 48 + len(matches) * 72),
    )


main()
