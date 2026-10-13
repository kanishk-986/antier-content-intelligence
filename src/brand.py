"""The persona registry, discovered from `config/brand/`.

The list of personas was duplicated in three places -- the QA schema, the brief
router and the QA prompt -- so adding one meant the QA validator rejecting a
recommendation the brief could route perfectly well. The configuration directory is
the single source of truth instead: a new persona is a new YAML file.

Section 4 names four (company, ceo, cto, sme). An owner may add more; a file that
does so says it in a comment, and `coo.yaml` does.
"""

from __future__ import annotations

import functools
import glob
import os
from typing import Any

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(REPO, "config", "brand")

# Not a persona file: the company brand brain and the service/ICP matrix.
_NOT_PERSONAS = {"antier.yaml", "services.yaml", "recipients.yaml"}

# `company` reads as the catch-all channel, so it is listed last and a tie never
# goes to it. The rest follow the order a reader expects in the brief.
_ORDER = ("ceo", "coo", "cto", "sme", "company")
FALLBACK = "company"


@functools.lru_cache(maxsize=4)
def load_personas(brand_dir: str = BRAND) -> dict[str, dict[str, Any]]:
    """Every persona config, keyed by its own `persona:` field.

    Keyed by the field rather than the filename so a renamed file cannot silently
    become a new persona.
    """
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(glob.glob(os.path.join(brand_dir, "*.yaml"))):
        if os.path.basename(path) in _NOT_PERSONAS:
            continue
        with open(path) as fh:
            config = yaml.safe_load(fh) or {}
        name = config.get("persona")
        if name:
            out[str(name)] = config
    return {k: out[k] for k in _ORDER if k in out} | {
        k: v for k, v in out.items() if k not in _ORDER}


def persona_names(brand_dir: str = BRAND) -> tuple[str, ...]:
    return tuple(load_personas(brand_dir))
