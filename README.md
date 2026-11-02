# ub-mode

`ub-mode` is an agent skill that enforces disciplined software engineering principles when writing or changing code. It is loosely based on portions of [@poteto](https://github.com/poteto)'s rules (`poteto-mode` / `pstack`), reduced and paired with deterministic quality-gate tools:

1. **First Make it Work** — Laziness Protocol, Foundational Thinking, TDD, Redesign From First Principles, Attack the Premise, Subtract Before You Add, Outcome-Oriented Execution, Build the Lever, and Architecture (Model the Domain, Boundary Discipline, Type System Discipline, Make Operations Idempotent, Separate Before Serializing Shared State).
2. **Then Make it Right** — Fix Root Causes, Sequence Work into Verifiable Units, Test Behavior (Not Implementation), [Crapper](https://github.com/unclebob/crapper) (`CRAP < 10`), [Dryer](https://github.com/unclebob/dryer) (duplication `< 0.8`), [Mutator](https://github.com/unclebob/mutator) (cover the uncovered, kill the survivors, delete dead code), and Refactoring.
3. **Practice** — Keep a Log, Guard the Context Window, Worktree Cleanup, and Commit and Push in small ordered commits.

## Companion Tool Repositories

`ub-mode` relies on deterministic quality-gate tools to enforce structure, complexity, duplication, and test thoroughness:

- [unclebob/crapper](https://github.com/unclebob/crapper) — Computes cyclomatic complexity, test coverage, and CRAP score per function so every function stays under the CRAP threshold (`< 10`).
- [unclebob/dryer](https://github.com/unclebob/dryer) — Detects structural code duplication so duplicate blocks (`>= 0.8` similarity) are eliminated.
- [unclebob/mutator](https://github.com/unclebob/mutator) — Runs mutation testing to expose uncovered code and surviving mutants that tests fail to catch.
- [unclebob/uml-viewer](https://github.com/unclebob/uml-viewer) — Visualizes components, coverage, CRAP, mutation scores, and dependency directions.

## Installation

One command installs the skill into every agent harness it finds, and installs the companion tools:

```bash
curl -fsSL https://raw.githubusercontent.com/unclebob/ub-mode/master/install.py | python3 -
```

Or from a checkout:

```bash
git clone https://github.com/unclebob/ub-mode && python3 ub-mode/install.py
```

Then invoke `/ub-mode`. The installer needs Python 3.11+ and git, as the companions do, on macOS or Linux (on Windows, use WSL). It prints each step and the reason for it:

- It copies `SKILL.md` to `<config>/skills/ub-mode/SKILL.md` for each harness whose config directory exists: `~/.agents`, `~/.claude`, `~/.codex`, `~/.cursor`, `~/.gemini`, `~/.grok`, and `~/.config/opencode`. If there is none, it uses `~/.agents/skills`.
- It clones crapper, dryer, mutator, and uml-viewer side by side into `~/.local/share/ub-mode`, because mutator imports `../crapper`. Each Python tool gets its own virtualenv and is run once to prove it works.
- It puts `crapper`, `dryer`, `mutator`, and `get-uml-viewer` in `~/.local/bin`, and says so if that directory is not on `PATH`. uml-viewer also needs the Clojure CLI, Java 21+, and zsh, and the installer names any that are missing.

Run it again to update; from a checkout, `git pull` first. Nothing else in those directories is touched.

```bash
python3 install.py --dry-run                        # print the plan, change nothing
python3 install.py --skills-dir .claude/skills      # a project, or any other harness; repeatable
python3 install.py --tools-dir DIR --bin-dir DIR    # put the companions somewhere else
```

To remove ub-mode, delete `~/.local/share/ub-mode`, the four commands in `~/.local/bin`, and each `skills/ub-mode` directory.

## Development

```bash
python3 -m unittest discover -s .
crapper && dryer && mutator install.py
```
