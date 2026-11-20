# map-mcp

Addresses and places in Norway, by voice. This is an MCP server that a voice assistant reaches
through claude-voice, as one of its plugins. It reads only, and no answer carries a position.

Address and place-name data © Kartverket, under CC BY 4.0. A real run asks Kartverket's address
search (ws.geonorge.no) and its place-name search (api.kartverket.no), sending only the words searched
for.

Two tools: `map_find` finds an address or place, and `map_nearby` names the nearest three of one
kind near a place, such as groceries or chargers. Nearby places will come from OpenStreetMap
(© OpenStreetMap contributors, ODbL). Until that backend is built, a real run says it has no
nearby-places service, and only `--simulate` answers, from made-up places.

It started from claude-voice's plugin template. The guide for writing one is
`docs/write-a-plugin.md` in claude-voice, and `docs/plugin-standard.md` there holds the rules.

## Try it

<!-- not run: it needs the project installed, which `just setup` does -->
```
just setup
uv run map-mcp find Prøveby --simulate
```

The second line prints what the voice would hear, from the made-up places in `fake.py`.

## Install it in claude-voice

<!-- not run: it changes the owner's own bridge config, and asks in a terminal -->
```
claude-voice plugins install map --from <this folder>
```

It reads `claude-voice-plugin.toml`, writes `config.default.toml` as your first config, and
ends with the usual typed-name approval. A run then asks Kartverket, which needs no key and no
setup; `simulate = true` in that config answers from the made-up places instead.

## What is where

| Part | What it is for |
|---|---|
| `src/map_mcp/server.py` | The MCP tools. Each answer carries a `say`, the sentence the voice reads aloud. |
| `src/map_mcp/service.py` | The core: it asks the backends and words every answer, failures included. |
| `src/map_mcp/interfaces.py` | What the service needs from a map service. Each real backend answers one. |
| `src/map_mcp/fake.py` | A made-up Kartverket that refuses what the real one refuses. |
| `src/map_mcp/settings.py` | The plugin's own config, from its own folder. |
| `src/map_mcp/platform/` | The one place that knows the operating system. |
| `scripts/ratchet.py` | The quality levels, which may never get worse than main's. |
| `scripts/mutate.py` | Switches each rule off in turn, to prove its test can fail. |

## The checks

Every check is a recipe in the `justfile`, and CI runs the same lines.
`just check` runs the ones a pull request needs, with no network.

<!-- not run: these are the gates; running them from a gate would recurse -->
```
just check
just commits
just ratchet
```

A new test must fail on the code before it, and the `red-first` job proves that. It runs only
the test files a change touches. So it does not see a change to shared test setup, such as
`tests/conftest.py`; say that in the pull request.

A rule is a line marked `# RULE: what it says`. Each one needs a test with its words as the
name, and a row in `scripts/mutations/`.

A commit may carry `Co-Authored-By` and an outside contributor's `Signed-off-by`, and no other
trailers. Any other note
belongs in the pull request's text. `just setup` turns on the hook that says so early.

## Cleaning up your own worktree

A session that worked in a worktree of its own removes it when it is done. Do it in this order.

1. While `scripts/.mutate-recovery.json` exists, a mutation run of yours still has a line
   switched off. Stop that run with SIGTERM, and it puts the line back itself.
2. Run the repair, which puts back a line a killed run left and runs nothing else.
3. Check that `git status` shows nothing. A plain `git worktree remove` refuses a worktree with
   changes, and that refusal is the point: never add `--force`.
4. Remove the worktree. Each run's temporary folder went with the run itself.

<!-- not run: these clean up a worktree, so they would remove the one the docs check runs in -->
```
kill -TERM <the mutation run's process>
uv run python scripts/mutate.py --repair-only
git status --short
git worktree remove <the worktree's path>
```
