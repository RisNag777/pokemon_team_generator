"""Command-line entry for ``python -m pokemon_team_generator``."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError

from .pokeapi import names_starting_with


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="List Pokémon whose names start with a given letter.",
    )
    p.add_argument(
        "letter",
        help="First letter of the Pokémon name (A–Z), case-insensitive.",
    )
    args = p.parse_args(argv)
    try:
        names = names_starting_with(args.letter)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except (HTTPError, URLError, OSError, TypeError, json.JSONDecodeError) as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return 1
    for n in names:
        print(n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
