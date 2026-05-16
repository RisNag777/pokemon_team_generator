"""OpenAI GPT Image: multi-reference unified trainer + team scene."""

from __future__ import annotations

import base64
import time
from io import BytesIO
from urllib.error import URLError
from urllib.request import urlopen

# Long timeout: image edit uploads many bytes and generation can be slow.
_OPENAI_TIMEOUT_S = 300.0
_OPENAI_MAX_RETRIES = 3
_EDIT_ATTEMPTS_PER_MODEL = 3

# GPT Image models accept multiple reference images via images.edit (see OpenAI docs).
# Order: newest / best first; fall through on failure.
_UNIFIED_SCENE_MODELS = (
    "gpt-image-2",
    "gpt-image-1.5",
    "gpt-image-1",
    "gpt-image-1-mini",
    "chatgpt-image-latest",
)
# input_fidelity is unsupported on these models (gpt-image-2 is always high-fidelity).
_NO_INPUT_FIDELITY_MODELS = frozenset({"gpt-image-1-mini", "gpt-image-2"})


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


def _is_moderation_blocked(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "moderation_blocked" in msg or "rejected by the safety system" in msg


def _is_client_kwarg_error(exc: BaseException) -> bool:
    """SDK/client mismatch — retrying other models won't help."""
    return isinstance(exc, TypeError) and "unexpected keyword argument" in str(exc)


def _is_invalid_model_error(exc: BaseException) -> bool:
    """Skip to the next model when this one isn't available on the account."""
    msg = str(exc).lower()
    return any(
        x in msg
        for x in (
            "does not exist",
            "model_not_found",
            "is not supported",
            "unknown model",
            "invalid model",
        )
    )


def _is_transient_network_error(exc: BaseException) -> bool:
    """True for likely retryable connection / timeout failures."""
    try:
        from openai import APIConnectionError, APITimeoutError

        if isinstance(exc, (APIConnectionError, APITimeoutError)):
            return True
    except ImportError:
        pass
    name = type(exc).__name__
    if "Connection" in name or "Timeout" in name or "ConnectError" in name:
        return True
    msg = str(exc).lower()
    return any(
        x in msg
        for x in (
            "connection error",
            "connection reset",
            "connection aborted",
            "timed out",
            "timeout",
            "network is unreachable",
            "temporary failure",
            "ssl",
            "remote end closed",
        )
    )


def _images_edit_once(
    client: object,
    model: str,
    prompt: str,
    size: str,
    user_photo_bytes: bytes,
    user_suffix: str,
    sprite_bytes_list: list[bytes],
) -> bytes:
    """Single images.edit call; closes stream handles in finally."""
    streams: list[BytesIO] = [_bytesio_upload(user_photo_bytes, f"user{user_suffix}")]
    for i, raw in enumerate(sprite_bytes_list):
        streams.append(_bytesio_upload(raw, f"creature_{i + 1}.png"))
    try:
        edit_kw: dict = {
            "model": model,
            "image": streams,
            "prompt": prompt,
            "size": size,
            "quality": "high",
        }
        if model not in _NO_INPUT_FIDELITY_MODELS:
            edit_kw["input_fidelity"] = "high"
        result = client.images.edit(**edit_kw)
        b64 = result.data[0].b64_json if result.data else None
        if not b64:
            raise RuntimeError("GPT Image returned no image data")
        return base64.standard_b64decode(b64)
    finally:
        for b in streams:
            try:
                b.close()
            except Exception:
                pass


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
    client = OpenAI(
        api_key=api_key,
        timeout=_OPENAI_TIMEOUT_S,
        max_retries=_OPENAI_MAX_RETRIES,
    )
    last_err: Exception | None = None

    for model in _UNIFIED_SCENE_MODELS:
        for attempt in range(_EDIT_ATTEMPTS_PER_MODEL):
            try:
                return _images_edit_once(
                    client,
                    model,
                    prompt,
                    size,
                    user_photo_bytes,
                    user_suffix,
                    sprite_bytes_list,
                )
            except Exception as e:
                last_err = e
                if _is_client_kwarg_error(e):
                    raise RuntimeError(
                        f"OpenAI client call failed before reaching the API: {e}"
                    ) from e
                if _is_invalid_model_error(e):
                    break
                if attempt < _EDIT_ATTEMPTS_PER_MODEL - 1 and _is_transient_network_error(e):
                    time.sleep(1.5 * (2**attempt))
                    continue
                break

    if last_err is not None and _is_moderation_blocked(last_err):
        raise RuntimeError(
            f"Could not generate a unified scene with any of {list(_UNIFIED_SCENE_MODELS)}. "
            f"Last error: {last_err!s}. "
            "OpenAI's safety filter blocked the request — try a different photo, fewer Pokémon, "
            "or contact help.openai.com with the request ID from the error."
        ) from last_err

    hint = (
        " If this was a connection error, check your network, VPN, firewall, and "
        "https://status.openai.com/ — then try again."
    )
    raise RuntimeError(
        f"Could not generate a unified scene with any of {list(_UNIFIED_SCENE_MODELS)}. "
        f"Last error: {last_err!s}.{hint}"
    ) from last_err
