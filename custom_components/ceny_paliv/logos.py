"""Optional station logos: downloaded on request into the Home Assistant config folder.

The logo pack lives in the GitHub repository (folder `logos/`, outside `custom_components/`, so HACS never installs
it). The integration only downloads the chains the user ticked, stores them in `<config>/ceny_paliv_logos/` and
serves them itself. Files that the user drops into that folder are used too and never deleted.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

from aiohttp import ClientError, ClientSession

from homeassistant.core import HomeAssistant

from .const import LOGO_DIR_NAME, LOGO_INDEX_URL, LOGO_RAW_URL, USER_AGENT

_LOGGER = logging.getLogger(__name__)

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_BYTES = 150_000
MANIFEST = "installed.json"  # {id: {"label": ..., "match": [...]}} for the logos this integration downloaded


def normalize(text: str) -> str:
    """Lower case, no diacritics, single spaces: 'Čerpací  Stanice' -> 'cerpaci stanice'."""
    decomposed = unicodedata.normalize("NFD", text or "")
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(plain.lower().split())


def logo_dir(hass: HomeAssistant) -> Path:
    return Path(hass.config.path(LOGO_DIR_NAME))


def _read_manifest(folder: Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def scan_logos(folder: Path) -> list[dict[str, Any]]:
    """Logos available on disk: [{"id": "orlen", "match": ["orlen"]}]. Blocking, run it in the executor."""
    if not folder.is_dir():
        return []
    manifest = _read_manifest(folder)
    out = []
    for path in sorted(folder.glob("*.png")):
        logo_id = path.stem
        if not ID_RE.match(logo_id):
            continue
        # a file dropped by hand matches its own name, with dashes and underscores read as spaces ("robin-oil" = "robin oil")
        match = manifest.get(logo_id, {}).get("match") or [logo_id, logo_id.replace("-", " ").replace("_", " ")]
        out.append({"id": logo_id, "match": list(dict.fromkeys(normalize(m) for m in match if m))})
    return out


def installed_ids(folder: Path) -> list[str]:
    """Ids downloaded by this integration (the ones the options step may uninstall). Blocking."""
    if not folder.is_dir():
        return []
    return sorted(i for i in _read_manifest(folder) if (folder / f"{i}.png").is_file())


async def async_fetch_index(session: ClientSession) -> list[dict[str, Any]] | None:
    """The list of logos offered in the pack, or None when GitHub cannot be reached."""
    try:
        async with session.get(LOGO_INDEX_URL, headers={"User-Agent": USER_AGENT}, timeout=20) as resp:
            if resp.status != 200:
                return None
            data = json.loads(await resp.text())
    except (ClientError, TimeoutError, ValueError) as err:
        _LOGGER.warning("Ceny paliv: cannot read the logo index: %s", err)
        return None
    out = []
    for item in data.get("logos", []) if isinstance(data, dict) else []:
        logo_id = str(item.get("id", ""))
        if ID_RE.match(logo_id):
            out.append({"id": logo_id, "label": str(item.get("label") or logo_id), "match": list(item.get("match") or [logo_id])})
    return out


def chains_in(names: list[str], index: list[dict[str, Any]]) -> set[str]:
    """Ids of the pack logos that match one of the given chain names (to preselect the ones a city needs)."""
    found = set()
    for name in names:
        key = normalize(name)
        for item in index:
            if any(key == normalize(m) or key.startswith(normalize(m) + " ") for m in item["match"]):
                found.add(item["id"])
    return found


async def async_sync(hass: HomeAssistant, session: ClientSession, index: list[dict[str, Any]], wanted: set[str]) -> None:
    """Download the wanted logos that are missing and remove the downloaded ones that are no longer wanted."""
    folder = logo_dir(hass)
    by_id = {i["id"]: i for i in index}
    manifest = await hass.async_add_executor_job(_read_manifest, folder)

    for logo_id in sorted(wanted & set(by_id)):
        if (folder / f"{logo_id}.png").is_file() and logo_id in manifest:
            continue
        try:
            async with session.get(LOGO_RAW_URL.format(id=logo_id), headers={"User-Agent": USER_AGENT}, timeout=20) as resp:
                body = await resp.read() if resp.status == 200 else b""
        except (ClientError, TimeoutError) as err:
            _LOGGER.warning("Ceny paliv: cannot download the logo %s: %s", logo_id, err)
            continue
        if not body.startswith(PNG_MAGIC) or len(body) > MAX_BYTES:
            _LOGGER.warning("Ceny paliv: the logo %s was refused (not a PNG or too big)", logo_id)
            continue
        item = by_id[logo_id]
        await hass.async_add_executor_job(_write, folder, logo_id, body)
        manifest[logo_id] = {"label": item["label"], "match": item["match"]}

    removable = [i for i in manifest if i not in wanted]
    for logo_id in removable:
        manifest.pop(logo_id, None)
    await hass.async_add_executor_job(_finish, folder, manifest, removable)


def _write(folder: Path, logo_id: str, body: bytes) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{logo_id}.png").write_bytes(body)


def _finish(folder: Path, manifest: dict[str, Any], removed: list[str]) -> None:
    for logo_id in removed:
        (folder / f"{logo_id}.png").unlink(missing_ok=True)
    if manifest or (folder / MANIFEST).exists():
        folder.mkdir(parents=True, exist_ok=True)
        (folder / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
