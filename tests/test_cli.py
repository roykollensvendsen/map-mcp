"""The command line says what the voice would hear, and a broken config says how to fix it."""

import pytest

from map_mcp import cli
from map_mcp.service import UNREACHABLE


def test_find_says_what_the_voice_would_hear(capsys):
    assert cli.main(["find", "Prøveby", "--simulate"]) == 0
    assert capsys.readouterr().out == "Simulated: Prøveby, a town.\n"


def test_a_real_run_asks_kartverket_and_says_when_it_cannot_be_reached(tmp_path, monkeypatch, capsys):
    """Here the network is shut (conftest), so a real run proves it asked, and never got through."""
    config = tmp_path / "config.toml"
    config.write_text("[device]\nsimulate = false\n")
    monkeypatch.setenv("MAP_MCP_CONFIG", str(config))
    assert cli.main(["find", "Prøveby"]) == 0
    assert capsys.readouterr().out == UNREACHABLE + "\n"


def test_a_broken_config_stops_the_command_with_the_fix(tmp_path, monkeypatch, capsys):
    config = tmp_path / "config.toml"
    config.write_text("[device\n")
    monkeypatch.setenv("MAP_MCP_CONFIG", str(config))
    assert cli.main(["find", "Prøveby"]) == 2
    assert "delete it to use the defaults" in capsys.readouterr().err


def test_every_verb_is_one_the_command_takes():
    for verb in cli.COMMANDS:
        with pytest.raises(SystemExit) as shown:
            cli.main([verb, "--help"])
        assert shown.value.code == 0
