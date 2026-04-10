"""Streamlit UI: build a Pokémon team from your name (PokeAPI v2)."""

from __future__ import annotations

import html
import json
import string

import streamlit as st
import streamlit.components.v1 as components

from pokemon_team_generator.format import (
    pokemon_list_css_block,
    pokemon_list_iframe_document,
    pokemon_team_picker_row_html,
    team_picker_iframe_script,
)
from pokemon_team_generator.pokeapi import iter_pokemon_list_entries


def _display_name(slug: str) -> str:
    """Format PokeAPI slug for display (hyphens as word breaks, title case)."""
    return slug.replace("-", " ").title()


def _letters_a_to_z(raw: str) -> list[str]:
    """Uppercase A–Z letters only (English Pokédex slugs)."""
    return [c.upper() for c in raw if c.upper() in string.ascii_uppercase]


def _render_pokemon_team_picker(
    matches: list[dict[str, str]],
    max_height_px: int,
    normalized: str,
    slot_i: int,
    selected_slug: str,
) -> None:
    """Clickable scrollable list with images, hover zoom, and selection highlight."""
    rows: list[str] = []
    for r in matches:
        slug = r["name"]
        label = html.escape(_display_name(slug))
        src = html.escape(r["sprite_url"], quote=True)
        slug_js = json.dumps(slug)
        rows.append(
            pokemon_team_picker_row_html(
                label,
                src,
                selected=slug == selected_slug,
                slug_js=slug_js,
            )
        )
    inner = "".join(rows)
    css = pokemon_list_css_block(max_height_px)
    doc = pokemon_list_iframe_document(
        css,
        inner,
        body_prefix=team_picker_iframe_script(normalized, slot_i),
    )
    components.html(doc, height=min(max_height_px + 32, 720), scrolling=False)


def _apply_team_pick_from_query() -> None:
    """Apply ?pteam=norm|slot|slug from the team picker iframe (parent navigation)."""
    qp = st.query_params
    if "pteam" not in qp:
        return
    raw = qp["pteam"]
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    try:
        parts = str(raw).split("|", 2)
        if len(parts) != 3:
            return
        norm, idx_s, slug = parts
        st.session_state[f"team_pick_{norm}_{int(idx_s)}"] = slug
    except (ValueError, TypeError):
        pass
    try:
        del st.query_params["pteam"]
    except KeyError:
        pass


@st.cache_data(ttl=3600, show_spinner="Loading Pokédex from PokeAPI…")
def all_pokemon_rows() -> list[dict[str, str]]:
    return sorted(iter_pokemon_list_entries(), key=lambda r: r["name"])


def _matches_for_letter(rows: list[dict[str, str]], letter: str) -> list[dict[str, str]]:
    prefix = letter.lower()
    return [r for r in rows if r["name"].startswith(prefix)]


def page_team_for_name(rows: list[dict[str, str]]) -> None:
    st.header("Create a Pokémon team for your name")
    st.caption(
        "For each letter in your name (A–Z), choose one Pokémon whose English name "
        "starts with that letter. Scroll the gallery, hover to zoom, click a row to select."
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

    _apply_team_pick_from_query()

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

        choice = st.session_state[key]
        row = slug_to_row[choice]

        st.markdown(
            f"**Letter {letter}** — pick {i + 1} of {len(letters)} · "
            f"selected: **{_display_name(choice)}**"
        )
        list_height = min(420, 48 + len(matches) * 72)
        _render_pokemon_team_picker(matches, list_height, normalized, i, choice)
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
