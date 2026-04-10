"""Formatting helpers for iframe CSS and HTML (Pokémon lists, team picker)."""

from __future__ import annotations

import json

# Styles for clickable rows + selection highlight in the name-based team builder.
TEAM_PICKER_EXTRA_CSS = """
.poke-row.poke-pick { cursor: pointer; }
.poke-row.poke-pick.selected {
  outline: 2px solid rgba(100, 149, 237, 0.95);
  background: rgba(100, 149, 237, 0.14);
}
"""


def pokemon_list_css_block(max_height_px: int) -> str:
    """Iframe styles for the team picker list (hover zoom on rows)."""
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
{TEAM_PICKER_EXTRA_CSS}"""


def pokemon_row_body_html(label_escaped: str, src_escaped_attr: str) -> str:
    """Image cell + name span. ``label_escaped`` / ``src_escaped_attr`` must be HTML-safe."""
    return (
        '<div class="poke-img-wrap">'
        f'<img class="poke-img" src="{src_escaped_attr}" alt="{label_escaped}" loading="lazy" />'
        "</div>"
        f'<span class="poke-name">{label_escaped}</span>'
    )


def pokemon_list_iframe_document(css: str, inner: str, *, body_prefix: str = "") -> str:
    """HTML5 shell for embedded list iframes: CSS in head, optional markup before ``poke-list-wrap``."""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<style>{css}</style></head><body>
{body_prefix}<div class="poke-list-wrap">{inner}</div>
</body></html>"""


def team_picker_iframe_script(normalized: str, slot_i: int) -> str:
    """Sets ``?pteam=norm|slot|slug`` on the parent page when ``teamPick(slug)`` runs."""
    return f"""<script>
function teamPick(slug) {{
  try {{
    var u = new URL(window.parent.location.href);
    u.searchParams.set("pteam", {json.dumps(normalized)} + "|" + {json.dumps(str(int(slot_i)))} + "|" + slug);
    window.parent.location.href = u.toString();
  }} catch (e) {{}}
}}
</script>
"""


def pokemon_team_picker_row_html(
    label_escaped: str,
    src_escaped_attr: str,
    *,
    selected: bool,
    slug_js: str,
) -> str:
    """One clickable row for the name-based team picker iframe."""
    sel = " selected" if selected else ""
    return (
        f'<div class="poke-row poke-pick{sel}" role="button" tabindex="0" '
        f"onclick='teamPick({slug_js})'>"
        f"{pokemon_row_body_html(label_escaped, src_escaped_attr)}"
        "</div>"
    )
