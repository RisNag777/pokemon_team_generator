"""Streamlit UI: build a Pokémon team from your name (PokeAPI v2)."""

from __future__ import annotations

import os
import string
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from pokemon_team_generator.openai_trainer_image import generate_unified_group_scene_png
from pokemon_team_generator.pokeapi import iter_pokemon_list_entries
import sqlite3

from pokemon_team_generator.trainer_db import (
    db_path,
    get_trainer,
    init_db,
    insert_draft_trainer,
    list_saved_teams,
    save_trainer_team,
    update_trainer_fields,
)

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

# Slugs with multiple words in the official name but no form suffix in parentheses (e.g. paradox Pokémon).
_NO_PAREN_MULTIWORD_SLUGS: frozenset[str] = frozenset(
    {
        "great-tusk",
        "scream-tail",
        "brute-bonnet",
        "flutter-mane",
        "slither-wing",
        "sandy-shocks",
        "roaring-moon",
        "walking-wake",
        "gouging-fire",
        "raging-bolt",
        "iron-treads",
        "iron-bundle",
        "iron-hands",
        "iron-jugulis",
        "iron-moth",
        "iron-thorns",
        "iron-valiant",
        "iron-leaves",
        "iron-boulder",
        "iron-crown",
    }
)


def _default_display_name(slug: str) -> str:
    """Title-case hyphen → spaces; put all text after the first word in parentheses."""
    s = slug.replace("-", " ").title()
    if " " not in s:
        return s
    if slug in _NO_PAREN_MULTIWORD_SLUGS:
        return s
    first, rest = s.split(" ", 1)
    return f"{first} ({rest})"


def _display_name(slug: str) -> str:
    """Format PokeAPI slug for display."""
    if slug in _EXACT_DISPLAY_NAMES:
        return _EXACT_DISPLAY_NAMES[slug]
    return _default_display_name(slug)


def _letters_a_to_z(raw: str) -> list[str]:
    """Uppercase A–Z letters only (English Pokédex slugs)."""
    return [c.upper() for c in raw if c.upper() in string.ascii_uppercase]


def _team_state_prefix(editing_id: int | None, normalized: str) -> str:
    """Session prefix: stable while editing a saved row; otherwise tied to the current name letters."""
    if editing_id is not None:
        return f"edit_{editing_id}"
    return normalized


def _checkbox_key(prefix: str, slot_i: int, slug: str) -> str:
    """Session-state key for one Pokémon checkbox (slot = letter index in name)."""
    return f"team_cb_{prefix}_{slot_i}_{slug}"


def _dropdown_key(prefix: str, slot_i: int) -> str:
    """Session-state key for the per-letter selectbox."""
    return f"team_dd_{prefix}_{slot_i}"


def _revealed_key(prefix: str, slot_i: int) -> str:
    """Session-state key for slugs added via dropdown (shown in checkbox section)."""
    return f"team_revealed_{prefix}_{slot_i}"


# Not a valid Pokédex slug — used as the selectbox default / reset value.
_DROPDOWN_PLACEHOLDER = "— Choose a Pokémon —"


@st.cache_data(ttl=3600, show_spinner="Loading Pokédex from PokeAPI…")
def all_pokemon_rows() -> list[dict[str, str]]:
    return sorted(iter_pokemon_list_entries(), key=lambda r: r["name"])


def _matches_for_letter(rows: list[dict[str, str]], letter: str) -> list[dict[str, str]]:
    prefix = letter.lower()
    return [r for r in rows if r["name"].startswith(prefix)]


def _collect_team_slots(prefix: str, n_letters: int) -> list[list[str]]:
    return [list(st.session_state.get(_revealed_key(prefix, i), [])) for i in range(n_letters)]


def _persist_team_confirm_to_db(
    editing_id: int | None,
    trainer_name: str,
    team_slots: list[list[str]],
) -> None:
    """Insert or update DB row when the user confirms their team."""
    if editing_id is not None:
        update_trainer_fields(editing_id, trainer_name=trainer_name, team_slots=team_slots)
        return
    draft = st.session_state.get("draft_row_id")
    if draft is not None:
        update_trainer_fields(int(draft), trainer_name=trainer_name, team_slots=team_slots)
        return
    rid = insert_draft_trainer(trainer_name, team_slots)
    st.session_state["draft_row_id"] = int(rid)


def _persist_generated_image_to_db(
    editing_id: int | None,
    trainer_name: str,
    team_slots: list[list[str]],
    png: bytes,
) -> int:
    """
    Write the generated PNG to team_image_blob (user camera image is not stored).
    Creates a full row if none exists yet for this session.
    """
    if editing_id is not None:
        update_trainer_fields(
            editing_id,
            trainer_name=trainer_name,
            team_slots=team_slots,
            team_image_png=png,
        )
        return int(editing_id)
    draft = st.session_state.get("draft_row_id")
    if draft is not None:
        rid = int(draft)
        update_trainer_fields(
            rid,
            trainer_name=trainer_name,
            team_slots=team_slots,
            team_image_png=png,
        )
        return rid
    rid = save_trainer_team(trainer_name, team_slots, png)
    st.session_state["draft_row_id"] = int(rid)
    return int(rid)


def render_team_page(rows: list[dict[str, str]]) -> None:
    editing_id: int | None = st.session_state.get("editing_id")

    if editing_id is not None:
        load_flag = f"_loaded_edit_{editing_id}"
        if load_flag not in st.session_state:
            try:
                rec = get_trainer(editing_id)
            except KeyError:
                st.error("That saved team no longer exists.")
                st.session_state["editing_id"] = None
                return
            pfx = f"edit_{editing_id}"
            name = str(rec["trainer_name"])
            letters_load = _letters_a_to_z(name)
            slots: list[list[str]] = [list(s) for s in (rec["team_slots"] or [])]
            while len(slots) < len(letters_load):
                slots.append([])
            for i in range(len(letters_load)):
                rv = _revealed_key(pfx, i)
                sl = slots[i] if i < len(slots) else []
                st.session_state[rv] = list(sl)
                for slug in sl:
                    st.session_state[_checkbox_key(pfx, i, slug)] = True
                dd_reroll = f"{_dropdown_key(pfx, i)}_reroll"
                st.session_state[dd_reroll] = st.session_state.get(dd_reroll, 0) + 1
            st.session_state["trainer_name_input"] = name
            st.session_state.pop(f"_edit_photo_bytes_{editing_id}", None)
            st.session_state[load_flag] = True

    if editing_id is not None:
        st.header("Edit saved team")
        st.caption(
            "Change your name, Pokémon, or photo, then generate again to **overwrite** this row in the database."
        )
    else:
        st.header("Create a Pokémon team for your name")
        st.caption(
            "For each letter, pick from the **dropdown** to add Pokémon under **Added here**. "
            "Pick the same Pokémon again to remove it, or **uncheck** a row."
        )

    raw_name = st.text_input(
        "Your name",
        placeholder="e.g. Ash",
        max_chars=64,
        key="trainer_name_input",
    )
    letters = _letters_a_to_z(raw_name)
    normalized = "".join(c.lower() for c in letters)
    prefix = _team_state_prefix(editing_id, normalized)

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

        revealed_key = _revealed_key(prefix, i)
        if revealed_key not in st.session_state:
            st.session_state[revealed_key] = []
        st.session_state[revealed_key] = [s for s in st.session_state[revealed_key] if s in slugs]
        st.session_state[revealed_key] = [
            s
            for s in st.session_state[revealed_key]
            if st.session_state.get(_checkbox_key(prefix, i, s), False)
        ]

        dd_key = _dropdown_key(prefix, i)
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
            pfx: str,
            slug_list: list[str],
            rv_key: str,
        ):
            def _sync() -> None:
                picked = st.session_state.get(wk, _DROPDOWN_PLACEHOLDER)
                if picked == _DROPDOWN_PLACEHOLDER or picked not in slug_list:
                    return
                ck = _checkbox_key(pfx, slot, picked)
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
                dd_widget_key, dd_reroll_key, i, prefix, slugs, revealed_key
            ),
        )

        st.caption("**Added here** (after you pick from the dropdown above)")
        revealed_slugs: list[str] = st.session_state[revealed_key]
        if not revealed_slugs:
            st.info("Nothing here yet — choose a Pokémon from the dropdown to add it to this list.")
        else:
            for slug in revealed_slugs:
                r = slug_to_row[slug]
                ck = _checkbox_key(prefix, i, slug)
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

    poster_ok = st.checkbox("I confirm this team.", key=f"poster_confirm_{prefix}")

    team_slots_live = _collect_team_slots(prefix, len(letters))
    if poster_ok:
        try:
            _persist_team_confirm_to_db(editing_id, raw_name.strip(), team_slots_live)
        except Exception as save_err:
            st.warning(f"Could not save team to database: {save_err}")

    if poster_ok:
        cam = st.camera_input(
            "Your photo",
            key=f"poster_cam_{prefix}",
            help="Sent to OpenAI for image generation only — not saved to the database.",
        )
        saved_photo = (
            st.session_state.get(f"_edit_photo_bytes_{editing_id}") if editing_id is not None else None
        )
        if cam is not None and editing_id is not None:
            st.session_state[f"_edit_photo_bytes_{editing_id}"] = cam.getvalue()
        photo_for_api = cam.getvalue() if cam is not None else (saved_photo or b"")
        can_generate = openai_key and photo_for_api and len(photo_for_api) > 0

        if can_generate:
            if st.button("Generate team image", key=f"unified_{prefix}"):
                with st.spinner("Sending photo + sprites to GPT Image for one scene…"):
                    try:
                        png = generate_unified_group_scene_png(openai_key, photo_for_api, all_picks)
                    except Exception as e:
                        st.error(f"Image generation failed: {e}")
                    else:
                        team_slots = _collect_team_slots(prefix, len(letters))
                        try:
                            row_id = _persist_generated_image_to_db(
                                editing_id,
                                raw_name.strip(),
                                team_slots,
                                png,
                            )
                            st.success(f"Generated image saved to database (row **{row_id}**).")
                        except Exception as save_err:
                            st.warning(f"Image was generated but could not be saved to the database: {save_err}")
                        st.image(png, caption="Generated scene (references: you + official artwork)")
                        st.download_button(
                            "Download PNG",
                            data=png,
                            file_name="team_unified_scene.png",
                            mime="image/png",
                            key=f"unified_dl_{prefix}",
                        )
        elif openai_key and not photo_for_api:
            st.warning("Add a camera photo (or open a saved team that includes one).")


def _trainer_summaries_for_view() -> list[dict[str, int | str]]:
    """Lightweight rows for the database page (same table as trainer_db, avoids import mismatch)."""
    init_db()
    with sqlite3.connect(db_path()) as conn:
        rows = conn.execute(
            """
            SELECT id, trainer_name, created_at,
                   COALESCE(LENGTH(team_image_blob), 0)
            FROM trainer_teams ORDER BY id DESC
            """
        ).fetchall()
    return [
        {
            "id": int(r[0]),
            "trainer_name": str(r[1]),
            "created_at": str(r[2]),
            "image_bytes": int(r[3]),
        }
        for r in rows
    ]


def render_database_page() -> None:
    """Read-only view of trainer_teams rows and stored blobs."""
    st.header("Trainer database")
    st.caption(f"SQLite file: `{db_path()}`")

    try:
        summaries = _trainer_summaries_for_view()
    except OSError as e:
        st.error(f"Could not read database: {e}")
        return

    if not summaries:
        st.info("No rows in **trainer_teams** yet.")
        return

    try:
        import pandas as pd

        df = pd.DataFrame(summaries)
        df = df.rename(
            columns={
                "trainer_name": "Trainer",
                "created_at": "Created (UTC)",
                "image_bytes": "Generated image size (B)",
            }
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception:
        st.table(summaries)

    st.subheader("Row details")
    for s in summaries:
        tid = int(s["id"])
        with st.expander(f"#{tid} — {s['trainer_name']}", expanded=False):
            try:
                rec = get_trainer(tid)
            except KeyError:
                st.warning("Row was deleted.")
                continue
            st.json(
                {
                    "id": rec["id"],
                    "trainer_name": rec["trainer_name"],
                    "created_at": rec["created_at"],
                    "team_slots": rec["team_slots"],
                }
            )
            st.caption("User photos are not stored in the database.")
            img = rec["team_image_png"]
            if img:
                st.caption("Generated team image")
                st.image(img, width=480)
            else:
                st.caption("No generated image stored.")


def main() -> None:
    st.set_page_config(
        page_title="Pokémon team generator",
        page_icon="⚡",
        layout="wide",
    )

    if "editing_id" not in st.session_state:
        st.session_state["editing_id"] = None
    if "nav_page" not in st.session_state:
        st.session_state["nav_page"] = "team"

    with st.sidebar:
        st.subheader("Navigation")
        if st.button("Home", use_container_width=True):
            st.session_state["nav_page"] = "team"
            st.session_state["editing_id"] = None
            st.session_state.pop("draft_row_id", None)
            st.session_state.pop("trainer_name_input", None)
            st.rerun()

        if st.button("View database", use_container_width=True):
            st.session_state["nav_page"] = "database"
            st.session_state["editing_id"] = None
            st.session_state.pop("draft_row_id", None)
            st.rerun()

        st.divider()
        st.subheader("Generated teams")
        teams = list_saved_teams()
        if not teams:
            st.caption("No saved teams yet.")
        else:
            with st.expander("Open a team", expanded=True):
                for t in teams:
                    tid = int(t["id"])
                    label = f"{t['trainer_name']} (#{tid})"
                    if st.button(label, key=f"sb_open_team_{tid}", use_container_width=True):
                        st.session_state["nav_page"] = "team"
                        st.session_state.pop(f"_loaded_edit_{tid}", None)
                        st.session_state.pop("draft_row_id", None)
                        st.session_state["editing_id"] = tid
                        st.rerun()

    if st.session_state.get("nav_page") == "database":
        st.title("Pokémon team generator")
        render_database_page()
        return

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

    render_team_page(rows)


main()
