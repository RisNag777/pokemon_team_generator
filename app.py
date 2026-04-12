"""Streamlit UI: build a Pokémon team from your name (PokeAPI v2)."""

from __future__ import annotations

import os
import string
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from pokemon_team_generator.openai_trainer_image import generate_unified_group_scene_png
from pokemon_team_generator.pokeapi import iter_pokemon_list_entries

load_dotenv(Path(__file__).resolve().parent / ".env")


def _openai_api_key() -> str | None:
    k = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if k:
        return k
    try:
        return str(st.secrets["OPENAI_API_KEY"]).strip()
    except Exception:
        return None


# Exact UI strings where plain title-case is wrong: hyphens, accents, apostrophes, Mr./Jr., or Nidoran symbols.
_EXACT_DISPLAY_NAMES: dict[str, str] = {
    "nidoran-f": "Nidoran♀",
    "nidoran-m": "Nidoran♂",
    "farfetchd": "Farfetch'd",
    "farfetchd-galar": "Farfetch'd Galar",
    "sirfetchd": "Sirfetch'd",
    "flabebe": "Flabébé",
    "type-null": "Type: Null",
    "ho-oh": "Ho-Oh",
    "porygon-z": "Porygon-Z",
    "jangmo-o": "Jangmo-o",
    "hakamo-o": "Hakamo-o",
    "kommo-o": "Kommo-o",
    "ting-lu": "Ting-Lu",
    "chien-pao": "Chien-Pao",
    "wo-chien": "Wo-Chien",
    "chi-yu": "Chi-Yu",
    "mr-mime": "Mr. Mime",
    "mr-mime-galar": "Mr. Mime Galar",
    "mime-jr": "Mime Jr.",
    "mr-rime": "Mr. Rime",
}


def _display_name(slug: str) -> str:
    """Format PokeAPI slug for display."""
    if slug in _EXACT_DISPLAY_NAMES:
        return _EXACT_DISPLAY_NAMES[slug]
    return slug.replace("-", " ").title()


def _letters_a_to_z(raw: str) -> list[str]:
    """Uppercase A–Z letters only (English Pokédex slugs)."""
    return [c.upper() for c in raw if c.upper() in string.ascii_uppercase]


def _checkbox_key(normalized: str, slot_i: int, slug: str) -> str:
    """Session-state key for one Pokémon checkbox (slot = letter index in name)."""
    return f"team_cb_{normalized}_{slot_i}_{slug}"


def _dropdown_key(normalized: str, slot_i: int) -> str:
    """Session-state key for the per-letter selectbox."""
    return f"team_dd_{normalized}_{slot_i}"


def _revealed_key(normalized: str, slot_i: int) -> str:
    """Session-state key for slugs added via dropdown (shown in checkbox section)."""
    return f"team_revealed_{normalized}_{slot_i}"


# Not a valid Pokédex slug — used as the selectbox default / reset value.
_DROPDOWN_PLACEHOLDER = "— Choose a Pokémon —"


@st.cache_data(ttl=3600, show_spinner="Loading Pokédex from PokeAPI…")
def all_pokemon_rows() -> list[dict[str, str]]:
    return sorted(iter_pokemon_list_entries(), key=lambda r: r["name"])


def _matches_for_letter(rows: list[dict[str, str]], letter: str) -> list[dict[str, str]]:
    prefix = letter.lower()
    return [r for r in rows if r["name"].startswith(prefix)]


def page_team_for_name(rows: list[dict[str, str]]) -> None:
    st.header("Create a Pokémon team for your name")
    st.caption(
        "For each letter, pick from the **dropdown** to add Pokémon under **Added here**. "
        "Pick the same Pokémon again to remove it, or **uncheck** a row."
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
    all_picks: list[tuple[str, dict[str, str]]] = []

    for i, letter in enumerate(letters):
        matches = _matches_for_letter(rows, letter)
        if not matches:
            st.warning(f"No Pokémon found for letter {letter} (position {i + 1}).")
            continue

        slugs = [r["name"] for r in matches]

        st.markdown(f"**Letter {letter}** — pick {i + 1} of {len(letters)}")

        revealed_key = _revealed_key(normalized, i)
        if revealed_key not in st.session_state:
            st.session_state[revealed_key] = []
        st.session_state[revealed_key] = [s for s in st.session_state[revealed_key] if s in slugs]
        st.session_state[revealed_key] = [
            s
            for s in st.session_state[revealed_key]
            if st.session_state.get(_checkbox_key(normalized, i, s), False)
        ]

        dd_key = _dropdown_key(normalized, i)
        dd_reroll_key = f"{dd_key}_reroll"
        dd_widget_key = f"{dd_key}__{st.session_state.get(dd_reroll_key, 0)}"
        dd_options = [_DROPDOWN_PLACEHOLDER] + slugs

        def _format_dd_option(x: str) -> str:
            if x == _DROPDOWN_PLACEHOLDER:
                return _DROPDOWN_PLACEHOLDER
            return _display_name(x)

        def _make_dropdown_sync(
            wk: str,
            reroll_k: str,
            slot: int,
            norm: str,
            slug_list: list[str],
            rv_key: str,
        ):
            def _sync() -> None:
                picked = st.session_state.get(wk, _DROPDOWN_PLACEHOLDER)
                if picked == _DROPDOWN_PLACEHOLDER or picked not in slug_list:
                    return
                ck = _checkbox_key(norm, slot, picked)
                revealed: list[str] = list(st.session_state.get(rv_key, []))
                already_added = picked in revealed and st.session_state.get(ck, False)
                if already_added:
                    st.session_state[rv_key] = [s for s in revealed if s != picked]
                    st.session_state[ck] = False
                else:
                    if picked not in revealed:
                        st.session_state[rv_key] = [*revealed, picked]
                    st.session_state[ck] = True
                st.session_state[reroll_k] = st.session_state.get(reroll_k, 0) + 1

            return _sync

        st.selectbox(
            f"All Pokémon for letter {letter}",
            options=dd_options,
            format_func=_format_dd_option,
            key=dd_widget_key,
            on_change=_make_dropdown_sync(
                dd_widget_key, dd_reroll_key, i, normalized, slugs, revealed_key
            ),
        )

        st.caption("**Added here** (after you pick from the dropdown above)")
        revealed_slugs: list[str] = st.session_state[revealed_key]
        if not revealed_slugs:
            st.info("Nothing here yet — choose a Pokémon from the dropdown to add it to this list.")
        else:
            for slug in revealed_slugs:
                r = slug_to_row[slug]
                ck = _checkbox_key(normalized, i, slug)
                img_col, box_col = st.columns([0.11, 0.89])
                with img_col:
                    st.image(r["sprite_url"], width=48)
                with box_col:
                    st.checkbox(
                        _display_name(slug),
                        key=ck,
                    )

        for slug in revealed_slugs:
            all_picks.append((slug, slug_to_row[slug]))

    if not all_picks:
        st.info("Select at least one Pokémon above to see your team below.")
        return

    st.divider()
    st.subheader("Your team")
    per_row = 6
    for start in range(0, len(all_picks), per_row):
        chunk = all_picks[start : start + per_row]
        cols = st.columns(len(chunk))
        for col, (slug, row) in zip(cols, chunk):
            with col:
                st.image(row["sprite_url"], width=96)
                st.caption(_display_name(slug))

    st.divider()
    st.subheader("Team image")
    openai_key = _openai_api_key()
    st.caption(
        "Your camera photo and **each team sprite** are sent to **OpenAI GPT Image** so one model pass can "
        "pose you and your companions in a single illustration. Paid API usage applies."
    )
    if not openai_key:
        st.info("Set **OPENAI_API_KEY** in `.env` or Streamlit secrets to generate a team image.")

    poster_ok = st.checkbox("I confirm this team.", key=f"poster_confirm_{normalized}")

    if poster_ok:
        cam = st.camera_input(
            "Your photo",
            key=f"poster_cam_{normalized}",
            help="Sent to OpenAI with your team’s official artwork for image generation.",
        )
        if cam is not None and openai_key:
            if st.button("Generate team image", key=f"unified_{normalized}"):
                with st.spinner("Sending photo + sprites to GPT Image for one scene…"):
                    try:
                        png = generate_unified_group_scene_png(openai_key, cam.getvalue(), all_picks)
                    except Exception as e:
                        st.error(f"Image generation failed: {e}")
                    else:
                        st.image(png, caption="Generated scene (references: you + official artwork)")
                        st.download_button(
                            "Download PNG",
                            data=png,
                            file_name="team_unified_scene.png",
                            mime="image/png",
                            key=f"unified_dl_{normalized}",
                        )


def main() -> None:
    st.set_page_config(
        page_title="Pokémon team generator",
        page_icon="⚡",
        layout="wide",
    )

    st.title("Pokémon team generator")
    st.caption(
        "Data from [PokeAPI](https://pokeapi.co/). "
        "Mega, Gigantamax, and Totem forms are excluded; other form variants may appear."
    )

    try:
        rows = all_pokemon_rows()
    except OSError as e:
        st.error(f"Could not reach PokeAPI: {e}")
        return

    page_team_for_name(rows)


main()
