"""OpenAI GPT Image: multi-reference unified trainer + team scene."""

from __future__ import annotations

import base64
from io import BytesIO
from urllib.error import URLError
from urllib.request import urlopen

# GPT Image models accept multiple reference images via images.edit (see OpenAI docs).
_UNIFIED_SCENE_MODELS = ("gpt-image-1.5", "gpt-image-1", "gpt-image-1-mini")


def _bytesio_upload(data: bytes, filename: str) -> BytesIO:
    """File-like object with a name so the multipart upload gets a correct content-type."""
    buf = BytesIO(data)
    buf.name = filename  # type: ignore[attr-defined]
    return buf


def _build_unified_group_prompt(num_creatures: int) -> str:
    n = max(0, num_creatures)
    creature_line = (
        f"The next {n} reference images are fantasy creature companions — include each as a full-body character, "
        "matching their colors, silhouette, and proportions from those references."
        if n
        else "No creature references were provided; show only the person in the environment."
    )
    return (
        "Create one cohesive Japanese anime-style illustration. "
        "The FIRST reference image is a real person — preserve their recognizable likeness (face, hair, skin tone) "
        "as the main trainer figure in stylish but practical travel clothes. "
        f"{creature_line} "
        "Pose everyone together in one outdoor scene (peaceful park path or meadow at golden hour): "
        "the person slightly off-center, companions arranged around them at varied depths like a team photo. "
        "Consistent warm lighting and soft shadows on all figures. Wholesome, non-violent adventure mood. "
        "No text, no watermarks, no logos, no real celebrity names."
    )[:8000]


def generate_unified_group_scene_png(
    api_key: str,
    user_photo_bytes: bytes,
    picks: list[tuple[str, dict[str, str]]],
    *,
    size: str = "1536x1024",
) -> bytes:
    """
    Single generated image: user photo + official artwork URLs as references.
    Uses OpenAI ``images.edit`` (GPT Image family).
    """
    from openai import OpenAI

    user_suffix = ".png" if user_photo_bytes[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
    sprite_bytes_list: list[bytes] = []
    for _slug, row in picks:
        try:
            with urlopen(row["sprite_url"], timeout=30.0) as resp:
                sprite_bytes_list.append(resp.read())
        except (URLError, OSError) as e:
            raise RuntimeError(f"Could not load sprite: {e}") from e

    prompt = _build_unified_group_prompt(len(picks))
    client = OpenAI(api_key=api_key)
    last_err: Exception | None = None

    for model in _UNIFIED_SCENE_MODELS:
        streams: list[BytesIO] = [_bytesio_upload(user_photo_bytes, f"user{user_suffix}")]
        for i, raw in enumerate(sprite_bytes_list):
            streams.append(_bytesio_upload(raw, f"creature_{i + 1}.png"))
        try:
            result = client.images.edit(
                model=model,
                image=streams,
                prompt=prompt,
                input_fidelity="high",
                size=size,
                quality="high",
            )
            b64 = result.data[0].b64_json if result.data else None
            if not b64:
                raise RuntimeError("GPT Image returned no image data")
            return base64.standard_b64decode(b64)
        except Exception as e:
            last_err = e
        finally:
            for b in streams:
                try:
                    b.close()
                except Exception:
                    pass

    raise RuntimeError(
        f"Could not generate a unified scene with any of {list(_UNIFIED_SCENE_MODELS)}. Last error: {last_err}"
    )
