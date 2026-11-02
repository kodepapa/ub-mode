"""What install.py decides to do, before it does anything."""

import unittest
from pathlib import Path

import install
from install import Copy, Note, Run, Shim

HOME = Path("/home/u")
TOOLS = HOME / ".local/share/ub-mode"
BIN = HOME / ".local/bin"
SOURCE = Path("/src/ub-mode")
PYTHON = "/usr/bin/python3.11"
EVERY_COMMAND = ("git", "zsh", "clojure", "java")
PYTHON_TOOLS = ("crapper", "dryer", "mutator")


def world(existing=(), source=SOURCE, commands=EVERY_COMMAND, path=(str(BIN),), version=(3, 11)):
    found = {HOME / name for name in existing}
    return install.World(
        home=HOME,
        source=source,
        python=PYTHON,
        version=version,
        path=tuple(path),
        commands=frozenset(commands),
        exists=found.__contains__,
    )


def plan(*argv, **facts):
    return install.plan(install.parse_options(list(argv), HOME), world(**facts))


def of_type(steps, kind):
    return [step for step in steps if isinstance(step, kind)]


def commands(steps):
    return [step.argv for step in of_type(steps, Run)]


def skill_targets(steps):
    return [step.target for step in of_type(steps, Copy)]


def index_of(steps, argv):
    return commands(steps).index(argv)


class SkillPlacement(unittest.TestCase):
    def test_the_skill_goes_to_every_detected_harness(self):
        steps = plan(existing=(".claude", ".cursor", ".config/opencode"))
        self.assertEqual(
            [
                HOME / ".claude/skills/ub-mode/SKILL.md",
                HOME / ".cursor/skills/ub-mode/SKILL.md",
                HOME / ".config/opencode/skills/ub-mode/SKILL.md",
            ],
            skill_targets(steps),
        )
        self.assertEqual({SOURCE / "SKILL.md"}, {step.source for step in of_type(steps, Copy)})

    def test_every_known_harness_is_detected(self):
        homes = (".agents", ".claude", ".codex", ".cursor", ".gemini", ".grok", ".config/opencode")
        targets = skill_targets(plan(existing=homes))
        self.assertEqual([HOME / h / "skills/ub-mode/SKILL.md" for h in homes], targets)

    def test_without_a_known_harness_the_shared_agents_dir_is_used(self):
        self.assertEqual([HOME / ".agents/skills/ub-mode/SKILL.md"], skill_targets(plan()))

    def test_named_skills_dirs_replace_detection(self):
        steps = plan("--skills-dir", "/p/.claude/skills", "--skills-dir", "/q/skills", existing=(".claude",))
        self.assertEqual(
            [Path("/p/.claude/skills/ub-mode/SKILL.md"), Path("/q/skills/ub-mode/SKILL.md")],
            skill_targets(steps),
        )

    def test_a_piped_installer_fetches_the_skill_first(self):
        steps = plan(source=None)
        self.assertEqual(
            ("git", "clone", "--quiet", "https://github.com/unclebob/ub-mode.git", str(TOOLS / "ub-mode")),
            commands(steps)[0],
        )
        self.assertEqual({TOOLS / "ub-mode/SKILL.md"}, {step.source for step in of_type(steps, Copy)})

    def test_a_checked_out_installer_uses_its_own_skill(self):
        steps = plan()
        self.assertNotIn(str(TOOLS / "ub-mode"), [argv[-1] for argv in commands(steps)])


class Companions(unittest.TestCase):
    def test_a_fresh_install_clones_every_companion_side_by_side(self):
        steps = plan()
        for name in PYTHON_TOOLS + ("uml-viewer",):
            url = f"https://github.com/unclebob/{name}.git"
            self.assertIn(("git", "clone", "--quiet", url, str(TOOLS / name)), commands(steps))

    def test_a_rerun_pulls_the_existing_checkouts(self):
        names = PYTHON_TOOLS + ("uml-viewer",)
        steps = plan(existing=[f".local/share/ub-mode/{name}/.git" for name in names])
        for name in names:
            self.assertIn(("git", "-C", str(TOOLS / name), "pull", "--ff-only", "--quiet"), commands(steps))
        self.assertNotIn("clone", [argv[1] for argv in commands(steps)])

    def test_python_tools_get_a_virtualenv_from_the_installing_python(self):
        steps = plan()
        for name in PYTHON_TOOLS:
            venv = TOOLS / name / ".venv"
            self.assertIn((PYTHON, "-m", "venv", str(venv)), commands(steps))
            self.assertIn(
                (str(venv / "bin/python"), "-m", "pip", "install", "--quiet",
                 "--disable-pip-version-check", "-e", str(TOOLS / name)),
                commands(steps),
            )

    def test_an_existing_virtualenv_is_kept_and_its_dependencies_refreshed(self):
        steps = plan(existing=[f".local/share/ub-mode/{name}/.venv/bin/python" for name in PYTHON_TOOLS])
        self.assertNotIn("venv", [argv[2] for argv in commands(steps) if len(argv) > 2])
        self.assertEqual(3, sum(1 for argv in commands(steps) if "pip" in argv))

    def test_uml_viewer_gets_no_virtualenv(self):
        steps = plan()
        self.assertFalse([argv for argv in commands(steps) if str(TOOLS / "uml-viewer") in argv and "pip" in argv])

    def test_each_companion_gets_a_shim_on_the_bin_dir(self):
        shims = {(step.target, step.launcher) for step in of_type(plan(), Shim)}
        self.assertEqual(
            {
                (BIN / "crapper", TOOLS / "crapper/crapper"),
                (BIN / "dryer", TOOLS / "dryer/dryer"),
                (BIN / "mutator", TOOLS / "mutator/mutator"),
                (BIN / "get-uml-viewer", TOOLS / "uml-viewer/scripts/get-uml-viewer"),
            },
            shims,
        )

    def test_each_python_tool_is_run_once_to_prove_it_works(self):
        steps = plan()
        checks = [step for step in of_type(steps, Run) if step.argv[-1] == "--help"]
        self.assertEqual([(str(BIN / name), "--help") for name in PYTHON_TOOLS], [c.argv for c in checks])
        self.assertTrue(all(check.quiet for check in checks))

    def test_only_the_proof_runs_are_quiet(self):
        noisy = [step for step in of_type(plan(), Run) if step.argv[-1] != "--help"]
        self.assertFalse(any(step.quiet for step in noisy))

    def test_crapper_is_ready_before_mutator_needs_it(self):
        steps = plan()
        crapper_ready = index_of(steps, (str(BIN / "crapper"), "--help"))
        mutator_fetch = index_of(steps, ("git", "clone", "--quiet", "https://github.com/unclebob/mutator.git", str(TOOLS / "mutator")))
        self.assertLess(crapper_ready, mutator_fetch)

    def test_a_mirror_replaces_github(self):
        steps = plan("--git-base", "file:///mirror/", source=None)
        urls = [argv[3] for argv in commands(steps) if argv[1] == "clone"]
        self.assertEqual(
            [f"file:///mirror/{name}.git" for name in ("ub-mode",) + PYTHON_TOOLS + ("uml-viewer",)],
            urls,
        )

    def test_named_tools_and_bin_dirs_are_used(self):
        steps = plan("--tools-dir", "/opt/ub", "--bin-dir", "/opt/bin")
        self.assertIn(("git", "clone", "--quiet", "https://github.com/unclebob/dryer.git", "/opt/ub/dryer"), commands(steps))
        self.assertIn(Path("/opt/bin/dryer"), [step.target for step in of_type(steps, Shim)])


class Notes(unittest.TestCase):
    def notes(self, **facts):
        return [step.text for step in of_type(plan(**facts), Note)]

    def test_nothing_to_note_when_everything_is_ready(self):
        self.assertEqual([], self.notes())

    def test_a_bin_dir_off_the_path_is_noted(self):
        notes = self.notes(path=("/usr/bin",))
        self.assertEqual(1, len(notes))
        self.assertIn(f'export PATH="{BIN}:$PATH"', notes[0])

    def test_missing_uml_viewer_prerequisites_are_noted(self):
        notes = self.notes(commands=("git", "java"))
        self.assertEqual(1, len(notes))
        self.assertEqual("get-uml-viewer needs zsh, clojure before it can run.", notes[0])

    def test_notes_come_last(self):
        steps = plan(path=(), commands=("git",))
        self.assertEqual([Note, Note], [type(step) for step in steps[-2:]])


class Blockers(unittest.TestCase):
    def test_a_ready_machine_has_no_blockers(self):
        self.assertEqual([], install.blockers(world()))

    def test_python_older_than_3_11_blocks(self):
        problems = install.blockers(world(version=(3, 10)))
        self.assertEqual(1, len(problems))
        self.assertIn("Python 3.11", problems[0])
        self.assertIn("3.10", problems[0])

    def test_python_3_12_is_fine(self):
        self.assertEqual([], install.blockers(world(version=(3, 12))))

    def test_missing_git_blocks(self):
        problems = install.blockers(world(commands=("zsh",)))
        self.assertEqual(["git is required to fetch the companion tools."], problems)


if __name__ == "__main__":
    unittest.main()
