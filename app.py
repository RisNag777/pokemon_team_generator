"""Streamlit UI: list Pokémon whose names start with a chosen letter (PokeAPI v2)."""

from __future__ import annotations

import html

import streamlit as st
import streamlit.components.v1 as components

from pokemon_team_generator.pokeapi import iter_pokemon_list_entries


def _display_name(slug: str) -> str:
    """Format PokeAPI slug for display (hyphens as word breaks, title case)."""
    return slug.replace("-", " ").title()


def _render_pokemon_matches(matches: list[dict[str, str]], max_height_px: int) -> None:
    """Scrollable list: hovering a row zooms artwork and name (CSS in iframe)."""
    rows: list[str] = []
    for r in matches:
        label = html.escape(_display_name(r["name"]))
        src = html.escape(r["sprite_url"], quote=True)
        rows.append(
            '<div class="poke-row">'
            '<div class="poke-img-wrap">'
            f'<img class="poke-img" src="{src}" alt="{label}" loading="lazy" />'
            "</div>"
            f'<span class="poke-name">{label}</span>'
            "</div>"
        )
    inner = "".join(rows)
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<style>
body {{
  margin: 0;
  padding: 0.35rem 0.5rem;
  font-family: system-ui, "Segoe UI", sans-serif;
  color: CanvasText;
  background: transparent;
}}
.poke-list-wrap {{
  max-height: {max_height_px}px;
  overflow-y: auto;
  overflow-x: hidden;
  border: 1px solid rgba(128, 128, 128, 0.4);
  border-radius: 0.5rem;
  padding: 0.35rem 0.5rem;
}}
.poke-row {{
  display: flex;
  align-items: center;
  gap: 0.85rem;
  padding: 0.4rem 0.45rem;
  border-radius: 0.35rem;
  cursor: zoom-in;
}}
.poke-row:hover {{
  background: rgba(128, 128, 128, 0.12);
}}
.poke-img-wrap {{
  width: 64px;
  height: 64px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: visible;
}}
.poke-img {{
  width: 56px;
  height: 56px;
  object-fit: contain;
  transition: transform 0.22s ease;
  transform-origin: center center;
  position: relative;
  z-index: 0;
}}
.poke-row:hover .poke-img {{
  transform: scale(1.65);
  z-index: 2;
}}
.poke-name {{
  font-size: 1rem;
  line-height: 1.3;
  transition: transform 0.22s ease;
  transform-origin: left center;
}}
.poke-row:hover .poke-name {{
  transform: scale(1.12);
}}
</style></head><body>
<div class="poke-list-wrap">{inner}</div>
</body></html>"""
    components.html(doc, height=min(max_height_px + 32, 720), scrolling=False)


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

    list_height = min(600, 48 + len(matches) * 72)
    _render_pokemon_matches(matches, list_height)


main()
