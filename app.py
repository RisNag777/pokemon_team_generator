"""Streamlit UI: build a Pokémon team from your name (PokeAPI v2)."""

from __future__ import annotations
from dotenv import load_dotenv
from pathlib import Path

from pokemon_team_generator.openai_trainer_image import generate_unified_group_scene_png
from pokemon_team_generator.pokeapi import iter_pokemon_list_entries
from pokemon_team_generator.trainer_db import (
    db_path,
    delete_trainer,
    get_trainer,
    init_db,
    insert_draft_trainer,
    list_saved_teams,
    save_trainer_team,
    update_trainer_fields,
)

import os
import sqlite3
import streamlit as st
import string

load_dotenv(Path(__file__).with_name(".env"))

def _openai_api_key() -> str | None:
    k = (os.environ.get("OPENAI_API_KEY") or "").strip()
    return k or None

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
        "tapu-koko",
        "tapu-lele",
        "tapu-bulu",
        "tapu-fini",
    }
)

def _display_name(slug: str) -> str:
    """Format PokeAPI slug for display."""
    if slug in _EXACT_DISPLAY_NAMES:
        return _EXACT_DISPLAY_NAMES[slug]
    s = slug.replace("-", " ").title()
    if " " not in s or slug in _NO_PAREN_MULTIWORD_SLUGS:
        return s
    first, rest = s.split(" ", 1)
    return f"{first} ({rest})"

def _team_widget_key(widget: str, prefix: str, slot_i: int, slug: str | None = None) -> str:
    """Streamlit session key: ``widget`` is ``cb`` (checkbox; pass ``slug``), ``dd``, or ``revealed``."""
    base = f"team_{widget}_{prefix}_{slot_i}"
    return f"{base}_{slug}" if slug is not None else base

# Not a valid Pokédex slug — used as the selectbox default / reset value.
_DROPDOWN_PLACEHOLDER = "— Choose a Pokémon —"

@st.cache_data(ttl=3600, show_spinner="Loading Pokédex from PokeAPI…")
def all_pokemon_rows() -> list[dict[str, str]]:
    return sorted(iter_pokemon_list_entries(), key=lambda r: r["name"])

def _persist_trainer_to_db(
    editing_id: int | None,
    trainer_name: str,
    team_slots: list[list[str]],
    *,
    team_image_png: bytes | None = None,
) -> int:
    """
    Insert or update the trainer row (edit id, else session draft, else new insert).
    Pass ``team_image_png`` to set the generated scene; omit it on team-only confirm so the
    image column is left unchanged on UPDATE. User camera bytes are never stored.
    """
    draft = st.session_state.get("draft_row_id")
    row_id = editing_id if editing_id is not None else (int(draft) if draft is not None else None)
    if row_id is not None:
        if team_image_png is not None:
            update_trainer_fields(
                row_id,
                trainer_name=trainer_name,
                team_slots=team_slots,
                team_image_png=team_image_png,
            )
        else:
            update_trainer_fields(row_id, trainer_name=trainer_name, team_slots=team_slots)
        return int(row_id)
    if team_image_png is not None:
        rid = save_trainer_team(trainer_name, team_slots, team_image_png)
    else:
        rid = insert_draft_trainer(trainer_name, team_slots)
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
            letters_load = [c.upper() for c in name if c.upper() in string.ascii_uppercase]
            slots: list[list[str]] = [list(s) for s in (rec["team_slots"] or [])]
            while len(slots) < len(letters_load):
                slots.append([])
            for i in range(len(letters_load)):
                rv = _team_widget_key("revealed", pfx, i)
                sl = slots[i] if i < len(slots) else []
                st.session_state[rv] = list(sl)
                for slug in sl:
                    st.session_state[_team_widget_key("cb", pfx, i, slug)] = True
                dd_reroll = f"{_team_widget_key('dd', pfx, i)}_reroll"
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
    letters = [c.upper() for c in raw_name if c.upper() in string.ascii_uppercase]
    normalized = "".join(c.lower() for c in letters)
    prefix = f"edit_{editing_id}" if editing_id is not None else normalized

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
        matches = [r for r in rows if r["name"].startswith(letter.lower())]
        if not matches:
            st.warning(f"No Pokémon found for letter {letter} (position {i + 1}).")
            continue

        slugs = [r["name"] for r in matches]

        st.markdown(f"**Letter {letter}** — pick {i + 1} of {len(letters)}")

        revealed_key = _team_widget_key("revealed", prefix, i)
        if revealed_key not in st.session_state:
            st.session_state[revealed_key] = []
        st.session_state[revealed_key] = [s for s in st.session_state[revealed_key] if s in slugs]
        st.session_state[revealed_key] = [
            s
            for s in st.session_state[revealed_key]
            if st.session_state.get(_team_widget_key("cb", prefix, i, s), False)
        ]

        dd_key = _team_widget_key("dd", prefix, i)
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
                ck = _team_widget_key("cb", pfx, slot, picked)
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
                ck = _team_widget_key("cb", prefix, i, slug)
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
        "Your photo (camera or file upload) and **each team sprite** are sent to **OpenAI GPT Image** so one model pass can "
        "pose you and your companions in a single illustration. Paid API usage applies."
    )
    if not openai_key:
        st.info("Set **OPENAI_API_KEY** in `.env` or Streamlit secrets to generate a team image.")

    poster_ok = st.checkbox("I confirm this team.", key=f"poster_confirm_{prefix}")

    team_slots_live = [
        list(st.session_state.get(_team_widget_key("revealed", prefix, i), []))
        for i in range(len(letters))
    ]
    if poster_ok:
        try:
            _persist_trainer_to_db(editing_id, raw_name.strip(), team_slots_live)
        except Exception as save_err:
            st.warning(f"Could not save team to database: {save_err}")

    if poster_ok:
        photo_mode = st.radio(
            "Your photo",
            ["Take a photo", "Upload a photo"],
            horizontal=True,
            key=f"poster_photo_mode_{prefix}",
        )
        saved_photo = (
            st.session_state.get(f"_edit_photo_bytes_{editing_id}") if editing_id is not None else None
        )
        cam_bytes: bytes | None = None
        upload_bytes: bytes | None = None

        if photo_mode == "Take a photo":
            cam = st.camera_input(
                "Camera",
                key=f"poster_cam_{prefix}",
                help="Sent to OpenAI for image generation only — not saved to the database.",
            )
            if cam is not None:
                cam_bytes = cam.getvalue()
                if editing_id is not None:
                    st.session_state[f"_edit_photo_bytes_{editing_id}"] = cam_bytes
        else:
            up = st.file_uploader(
                "Image file",
                type=["png", "jpg", "jpeg", "webp"],
                key=f"poster_upload_{prefix}",
                help="Sent to OpenAI for image generation only — not saved to the database.",
            )
            if up is not None:
                upload_bytes = up.getvalue()
                if editing_id is not None:
                    st.session_state[f"_edit_photo_bytes_{editing_id}"] = upload_bytes

        if photo_mode == "Take a photo":
            photo_for_api = cam_bytes if cam_bytes is not None else (saved_photo or b"")
        else:
            photo_for_api = upload_bytes if upload_bytes is not None else (saved_photo or b"")

        can_generate = openai_key and photo_for_api and len(photo_for_api) > 0

        if can_generate:
            if st.button("Generate team image", key=f"unified_{prefix}"):
                with st.spinner("Sending photo + sprites to GPT Image for one scene…"):
                    try:
                        png = generate_unified_group_scene_png(openai_key, photo_for_api, all_picks)
                    except Exception as e:
                        st.error(f"Image generation failed: {e}")
                    else:
                        try:
                            row_id = _persist_trainer_to_db(
                                editing_id,
                                raw_name.strip(),
                                team_slots_live,
                                team_image_png=png,
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
            st.warning(
                "Add a photo with the camera or upload (or open a saved team that already has a photo in this session)."
            )


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
    """View trainer_teams rows, images, and optional delete."""
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

            st.divider()
            del_confirm_key = f"db_delete_confirm_{tid}"
            if st.button("Delete this trainer", type="secondary", key=f"db_delete_{tid}"):
                st.session_state[del_confirm_key] = True
            if st.session_state.get(del_confirm_key):
                st.warning(
                    f"Permanently delete **#{tid}** — **{rec['trainer_name']}**? This cannot be undone."
                )
                c_yes, c_no = st.columns(2)
                with c_yes:
                    if st.button("Yes, delete", type="primary", key=f"db_delete_yes_{tid}"):
                        try:
                            delete_trainer(tid)
                        except KeyError:
                            st.error("That row no longer exists.")
                        else:
                            st.session_state.pop(del_confirm_key, None)
                            st.session_state.pop(f"_loaded_edit_{tid}", None)
                            st.session_state.pop(f"_edit_photo_bytes_{tid}", None)
                            if st.session_state.get("editing_id") == tid:
                                st.session_state["editing_id"] = None
                            if st.session_state.get("draft_row_id") == tid:
                                st.session_state.pop("draft_row_id", None)
                            st.rerun()
                with c_no:
                    if st.button("Cancel", key=f"db_delete_no_{tid}"):
                        st.session_state.pop(del_confirm_key, None)
                        st.rerun()


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
    if st.session_state.get("nav_page") == "battles":
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
