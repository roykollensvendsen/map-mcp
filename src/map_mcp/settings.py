"""The plugin's own settings, read from its own config folder.

`claude-voice plugins install` writes `config.default.toml` there the first time, so the file
holds exactly the keys that file has. A key it does not know is refused by name, so a typo
never passes as a default silently.
"""

from __future__ import annotations

import os
import pathlib
import tomllib
from dataclasses import dataclass

from map_mcp import platform

#: The folder under the config home, as the manifest's `config.dir` names it.
CONFIG_DIR = "map-mcp"
#: Points at another config file, for a test or a second source.
CONFIG_ENV = "MAP_MCP_CONFIG"


class SettingsError(ValueError):
    """The config file cannot be used; the message names the fix."""


@dataclass(frozen=True)
class Settings:
    """What the plugin reads from its config file."""

    #: Answer from the made-up places instead of Kartverket. Off unless asked for, since
    #: Kartverket needs no key and no device.
    simulate: bool = False


def config_file() -> pathlib.Path:
    """Where the config is: `$MAP_MCP_CONFIG`, or the plugin's folder in the config home."""
    named = os.environ.get(CONFIG_ENV)
    return pathlib.Path(named) if named else platform.current().config_home() / CONFIG_DIR / "config.toml"


def load(path: pathlib.Path | None = None) -> Settings:
    """The settings in `path`, or the defaults when there is no file."""
    path = config_file() if path is None else path
    if not path.is_file():
        return Settings()
    data = _known_keys(path)
    return Settings(simulate=_true_or_false(path, data.get("simulate", Settings.simulate)))


def _known_keys(path: pathlib.Path) -> dict[str, object]:
    """The TOML in `path`, refused with the fix if it is broken or holds a key map-mcp does not know."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as broken:
        msg = f"{path} is not valid TOML ({broken}); fix it, or delete it to use the defaults"
        raise SettingsError(msg) from broken
    unknown = sorted(key for key in data if key != "simulate")
    if unknown:
        msg = f"{path} has keys map-mcp does not know: {', '.join(unknown)}; remove them or fix their spelling"
        raise SettingsError(msg)
    return data


def _true_or_false(path: pathlib.Path, simulate: object) -> bool:
    """`simulate` itself; a quoted "false" would read as true, so anything but a bool is refused."""
    if not isinstance(simulate, bool):
        msg = f"{path}: simulate must be true or false, without quotes, not {simulate!r}"
        raise SettingsError(msg)
    return simulate
