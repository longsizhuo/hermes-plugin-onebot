"""Pytest bootstrap for the standalone plugin repo.

The plugin is imported the same way the production loader loads it
(``hermes_cli/plugins_loader.py::_load_directory_module``): a package built
from the repo-root ``__init__.py`` with ``submodule_search_locations`` pointed
at the repo root. The test namespace is ``onebot_platform`` (production uses
the synthetic ``hermes_plugins.onebot_platform`` — same mechanism, shorter
name).

Top-level imports (repo root on ``sys.path``) do NOT work for this suite: the
host ``gateway.platforms.base`` module re-inserts the hermes-agent root at
``sys.path[0]`` (gateway/platforms/base.py:424) and its lazy helpers import
the core ``tools`` package, which would collide with the plugin's root-level
``tools.py``. The package shape keeps the two apart, exactly like production.

The ``gateway`` package comes from a hermes-agent checkout: point
``HERMES_AGENT_HOME`` at one when it is not importable by default.

Like the upstream suite, tests never touch the real ``~/.hermes/``:
``HERMES_HOME`` (and ``HOME``) are redirected to a per-test tempdir.
"""

import importlib.util
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

_AGENT_HOME = os.environ.get("HERMES_AGENT_HOME", "")
if _AGENT_HOME:
    _agent_root = str(Path(_AGENT_HOME).resolve())
    if Path(_agent_root).is_dir():
        while _agent_root in sys.path:
            sys.path.remove(_agent_root)
        sys.path.insert(0, _agent_root)

_TEST_NS = "onebot_platform"
if _TEST_NS not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        _TEST_NS,
        str(_REPO_ROOT / "__init__.py"),
        submodule_search_locations=[str(_REPO_ROOT)],
    )
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_TEST_NS] = _mod
    _spec.loader.exec_module(_mod)

import pytest


@pytest.fixture(autouse=True)
def _sandbox_hermes_home(tmp_path, monkeypatch):
    """Keep tests off the real Hermes home (mirrors upstream tests/conftest.py)."""
    fake_home = tmp_path / "hermes-home"
    fake_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(fake_home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    yield
