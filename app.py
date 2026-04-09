"""Streamlit UI: list Pokémon whose names start with a chosen letter (PokeAPI v2)."""

from __future__ import annotations

import streamlit as st

from pokemon_team_generator.pokeapi import iter_pokemon_list_entries


@st.cache_data(ttl=3600, show_spinner="Loading Pokédex from PokeAPI…")
def all_pokemon_names() -> list[str]:
    return sorted(row["name"] for row in iter_pokemon_list_entries())


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
        names = all_pokemon_names()
    except OSError as e:
        st.error(f"Could not reach PokeAPI: {e}")
        return

    prefix = letter.lower()
    matches = [n for n in names if n.startswith(prefix)]

    st.metric("Matching Pokémon", len(matches))

    if not matches:
        st.info("No Pokémon found for this letter.")
        return

    st.dataframe(
        {"name": matches},
        use_container_width=True,
        hide_index=True,
        height=min(520, 36 + len(matches) * 35),
    )


main()
