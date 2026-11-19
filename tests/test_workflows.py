"""How the checks' runs share out, pinned so a later edit cannot quietly change it."""

import pathlib

import pytest

WORKFLOWS = pathlib.Path(__file__).parent.parent / ".github/workflows"

#: One group per pull request, and one per run for everything else.
CONCURRENCY = """\
concurrency:
  group: ${{ github.workflow }}-${{ github.event_name == 'pull_request' && github.ref || github.run_id }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
"""


@pytest.mark.parametrize("workflow", ["checks.yml", "red-first.yml"])
def test_only_a_pull_request_s_stale_run_is_ever_stopped_and_every_main_commit_runs(workflow):
    """GitHub keeps one waiting run per group, so a group per ref skipped a main commit between two.

    Keyed by run id, every run on main, a tag or by hand is its own group and always runs to the
    end. Only a newer push to the same pull request stops that pull request's stale run.
    """
    assert CONCURRENCY in (WORKFLOWS / workflow).read_text(encoding="utf-8")
