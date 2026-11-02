#!/usr/bin/env python3
"""Install the ub-mode skill and the companion tools it relies on.

    python3 install.py                 # from a checkout
    curl -fsSL https://raw.githubusercontent.com/unclebob/ub-mode/master/install.py | python3 -

Run it again to update. Run it with --dry-run to see every step and the
reason for it without changing anything.

Glossary
  skill       SKILL.md, the instructions an agent follows.
  harness     An agent program that loads skills (Claude Code, Codex, Cursor,
              Gemini CLI, Grok, OpenCode, ...). Each reads <config>/skills.
  skills dir  A harness's skills directory. The skill lands in
              <skills dir>/ub-mode/SKILL.md.
  companion   A quality-gate tool the skill tells the agent to run:
              crapper, dryer, mutator, and uml-viewer.
  tools dir   Where the companions are checked out, side by side, because
              mutator imports ../crapper.
  launcher    The script a companion ships to run itself.
  shim        A two-line script in the bin dir that execs a launcher, so the
              companion is on PATH.
  plan        The ordered steps an install takes, each with its reason.
"""

from __future__ import annotations

import argparse
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SKILL = "ub-mode"
GITHUB = "https://github.com/unclebob"
MINIMUM_PYTHON = (3, 11)

# Config directories, relative to home, of harnesses that load <dir>/skills.
HARNESSES = (".agents", ".claude", ".codex", ".cursor", ".gemini", ".grok", ".config/opencode")
SHARED_HARNESS = ".agents"


@dataclass(frozen=True)
class Companion:
    name: str
    launcher: str
    command: str
    python: bool = True
    needs: tuple[str, ...] = ()


COMPANIONS = (
    Companion("crapper", "crapper", "crapper"),
    Companion("dryer", "dryer", "dryer"),
    Companion("mutator", "mutator", "mutator"),
    Companion(
        "uml-viewer",
        "scripts/get-uml-viewer",
        "get-uml-viewer",
        python=False,
        needs=("zsh", "clojure", "java"),
    ),
)


@dataclass(frozen=True)
class Options:
    skills_dirs: tuple[Path, ...]
    tools_dir: Path
    bin_dir: Path
    git_base: str
    dry_run: bool


@dataclass(frozen=True)
class World:
    """What install.py observed about the machine before planning."""

    home: Path
    source: Path | None  # the checkout holding SKILL.md, or None when piped
    python: str
    version: tuple[int, int]
    path: tuple[str, ...]
    commands: frozenset[str]
    exists: Callable[[Path], bool]


@dataclass(frozen=True)
class Run:
    why: str
    argv: tuple[str, ...]
    quiet: bool = False


@dataclass(frozen=True)
class Copy:
    why: str
    source: Path
    target: Path


@dataclass(frozen=True)
class Shim:
    why: str
    target: Path
    launcher: Path


@dataclass(frozen=True)
class Note:
    text: str


def parse_options(argv: list[str] | None, home: Path) -> Options:
    parser = argparse.ArgumentParser(
        prog="install.py",
        description="Install the ub-mode skill and its companion tools.",
    )
    parser.add_argument(
        "--skills-dir",
        action="append",
        default=[],
        type=Path,
        metavar="DIR",
        help="a harness skills directory; repeatable (default: every detected harness)",
    )
    parser.add_argument("--tools-dir", type=Path, default=home / ".local/share" / SKILL, metavar="DIR")
    parser.add_argument("--bin-dir", type=Path, default=home / ".local/bin", metavar="DIR")
    parser.add_argument("--git-base", default=GITHUB, metavar="URL", help="where the repositories live")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and change nothing")
    args = parser.parse_args(argv)
    return Options(
        skills_dirs=tuple(_absolute(d) for d in args.skills_dir),
        tools_dir=_absolute(args.tools_dir),
        bin_dir=_absolute(args.bin_dir),
        git_base=args.git_base.rstrip("/"),
        dry_run=args.dry_run,
    )


def _absolute(path: Path) -> Path:
    return path.expanduser().absolute()


def blockers(world: World) -> list[str]:
    problems = []
    if world.version < MINIMUM_PYTHON:
        have = ".".join(map(str, world.version))
        problems.append(f"The companion tools need Python 3.11 or newer; this is {have}. Run install.py with python3.11+.")
    if "git" not in world.commands:
        problems.append("git is required to fetch the companion tools.")
    return problems


def plan(options: Options, world: World) -> list:
    steps = []
    source = world.source
    if source is None:
        source = options.tools_dir / SKILL
        steps.append(_fetch(SKILL, options, world))
    for companion in COMPANIONS:
        steps.extend(_companion_steps(companion, options, world))
    for skills_dir in _skills_dirs(options, world):
        steps.append(Copy(f"install the skill into {skills_dir}", source / "SKILL.md", skills_dir / SKILL / "SKILL.md"))
    return steps + _notes(options, world)


def _skills_dirs(options: Options, world: World) -> tuple[Path, ...]:
    if options.skills_dirs:
        return options.skills_dirs
    found = tuple(world.home / h / "skills" for h in HARNESSES if world.exists(world.home / h))
    return found or (world.home / SHARED_HARNESS / "skills",)


def _fetch(name: str, options: Options, world: World) -> Run:
    checkout = options.tools_dir / name
    if world.exists(checkout / ".git"):
        return Run(f"update {name}", ("git", "-C", str(checkout), "pull", "--ff-only", "--quiet"))
    url = f"{options.git_base}/{name}.git"
    return Run(f"fetch {name}", ("git", "clone", "--quiet", url, str(checkout)))


def _companion_steps(companion: Companion, options: Options, world: World) -> list:
    checkout = options.tools_dir / companion.name
    shim = options.bin_dir / companion.command
    steps = [_fetch(companion.name, options, world)]
    if companion.python:
        steps.extend(_bootstrap(companion.name, checkout, world))
    steps.append(Shim(f"put {companion.command} on PATH", shim, checkout / companion.launcher))
    if companion.python:
        steps.append(Run(f"prove {companion.command} runs", (str(shim), "--help"), quiet=True))
    return steps


def _bootstrap(name: str, checkout: Path, world: World) -> list:
    venv = checkout / ".venv"
    python = venv / "bin/python"
    steps = []
    if not world.exists(python):
        steps.append(Run(f"create {name}'s virtualenv", (world.python, "-m", "venv", str(venv))))
    pip = (str(python), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "-e", str(checkout))
    steps.append(Run(f"install {name}'s dependencies", pip))
    return steps


def _notes(options: Options, world: World) -> list:
    notes = []
    if str(options.bin_dir) not in world.path:
        notes.append(Note(f'{options.bin_dir} is not on PATH. Add it: export PATH="{options.bin_dir}:$PATH"'))
    for companion in COMPANIONS:
        missing = [need for need in companion.needs if need not in world.commands]
        if missing:
            notes.append(Note(f"{companion.command} needs {', '.join(missing)} before it can run."))
    return notes
