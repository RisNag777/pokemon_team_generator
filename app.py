"""Streamlit UI: browse Pokémon by letter or build a name-based team (PokeAPI v2)."""

from __future__ import annotations

import html
import json
import string

import streamlit as st
import streamlit.components.v1 as components

from pokemon_team_generator.pokeapi import iter_pokemon_list_entries

MENU_BROWSE = "Browse by letter"
MENU_TEAM = "Create a Pokémon team for your name"


def _display_name(slug: str) -> str:
    """Format PokeAPI slug for display (hyphens as word breaks, title case)."""
    return slug.replace("-", " ").title()


def _letters_a_to_z(raw: str) -> list[str]:
    """Uppercase A–Z letters only (English Pokédex slugs)."""
    return [c.upper() for c in raw if c.upper() in string.ascii_uppercase]


def _pokemon_list_css_block(max_height_px: int, *, team_picker: bool) -> str:
    """Shared iframe styles for browse list and team picker (hover zoom on rows)."""
    team_extra = ""
    if team_picker:
        team_extra = """
.poke-row.poke-pick { cursor: pointer; }
.poke-row.poke-pick.selected {
  outline: 2px solid rgba(100, 149, 237, 0.95);
  background: rgba(100, 149, 237, 0.14);
}
"""
    return f"""
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
{team_extra}"""


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
    css = _pokemon_list_css_block(max_height_px, team_picker=False)
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<style>{css}</style></head><body>
<div class="poke-list-wrap">{inner}</div>
</body></html>"""
    components.html(doc, height=min(max_height_px + 32, 720), scrolling=False)


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
        sel = " selected" if slug == selected_slug else ""
        slug_js = json.dumps(slug)
        rows.append(
            f'<div class="poke-row poke-pick{sel}" role="button" tabindex="0" '
            f"onclick='teamPick({slug_js})'>"
            '<div class="poke-img-wrap">'
            f'<img class="poke-img" src="{src}" alt="{label}" loading="lazy" />'
            "</div>"
            f'<span class="poke-name">{label}</span>'
            "</div>"
        )
    inner = "".join(rows)
    css = _pokemon_list_css_block(max_height_px, team_picker=True)
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<style>{css}</style></head><body>
<script>
function teamPick(slug) {{
  try {{
    var u = new URL(window.parent.location.href);
    u.searchParams.set("pteam", {json.dumps(normalized)} + "|" + {json.dumps(str(int(slot_i)))} + "|" + slug);
    window.parent.location.href = u.toString();
  }} catch (e) {{}}
}}
</script>
<div class="poke-list-wrap">{inner}</div>
</body></html>"""
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


def page_browse_by_letter(rows: list[dict[str, str]]) -> None:
    st.header("Pokémon by first letter")
    letter = st.selectbox(
        "First letter",
        options=[chr(c) for c in range(ord("A"), ord("Z") + 1)],
        index=0,
    )

    prefix = letter.lower()
    matches = [r for r in rows if r["name"].startswith(prefix)]

    st.metric("Matching Pokémon", len(matches))

    if not matches:
        st.info("No Pokémon found for this letter.")
        return

    list_height = min(600, 48 + len(matches) * 72)
    _render_pokemon_matches(matches, list_height)


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

    menu = st.sidebar.radio(
        "Menu",
        [MENU_BROWSE, MENU_TEAM],
    )

    try:
        rows = all_pokemon_rows()
    except OSError as e:
        st.error(f"Could not reach PokeAPI: {e}")
        return

    if menu == MENU_BROWSE:
        page_browse_by_letter(rows)
    else:
        page_team_for_name(rows)


main()
