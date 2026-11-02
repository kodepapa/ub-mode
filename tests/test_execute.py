"""What install.py does to the machine, and what it reports while doing it."""

import contextlib
import io
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import install
from install import Copy, Note, Run, Shim


@contextlib.contextmanager
def captured_fd1():
    """Capture what child processes write to file descriptor 1."""
    captured = []
    with tempfile.TemporaryFile(mode="w+") as sink:
        sys.stdout.flush()
        saved = os.dup(1)
        os.dup2(sink.fileno(), 1)
        try:
            yield captured
        finally:
            sys.stdout.flush()
            os.dup2(saved, 1)
            os.close(saved)
            sink.seek(0)
            captured.append(sink.read())


def execute(steps, dry_run=False):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = install.execute(steps, dry_run)
    return code, out.getvalue(), err.getvalue()


def python(code):
    return (sys.executable, "-c", code)


class TempDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def script(self, relative, text):
        path = self.tmp / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        path.chmod(0o755)
        return path


class Shims(TempDir):
    def echo_launcher(self):
        return self.script("tool dir/launch", '#!/bin/sh\nprintf "%s|" "$0" "$@"\n')

    def test_a_shim_runs_its_launcher_by_path_with_the_callers_arguments(self):
        launcher = self.echo_launcher()
        Shim("put tool on PATH", self.tmp / "bin/tool", launcher).apply()
        result = subprocess.run([str(self.tmp / "bin/tool"), "a b", "c"], capture_output=True, text=True)
        self.assertEqual(f"{launcher}|a b|c|", result.stdout)

    def test_a_second_install_rewrites_the_shim(self):
        launcher = self.echo_launcher()
        self.script("bin/tool", "#!/bin/sh\necho stale\n")
        Shim("put tool on PATH", self.tmp / "bin/tool", launcher).apply()
        result = subprocess.run([str(self.tmp / "bin/tool")], capture_output=True, text=True)
        self.assertEqual(f"{launcher}|", result.stdout)


class Copies(TempDir):
    def test_the_skill_is_copied_into_a_new_skill_dir(self):
        source = self.script("src/SKILL.md", "# ub-mode\n")
        target = self.tmp / "skills/ub-mode/SKILL.md"
        Copy("install the skill", source, target).apply()
        self.assertEqual("# ub-mode\n", target.read_text())

    def test_a_second_install_replaces_the_old_skill(self):
        source = self.script("src/SKILL.md", "# new\n")
        target = self.script("skills/ub-mode/SKILL.md", "# old\n")
        Copy("install the skill", source, target).apply()
        self.assertEqual("# new\n", target.read_text())


class Execution(TempDir):
    def steps(self):
        marker = self.tmp / "ran"
        return [
            Copy("install the skill", self.script("SKILL.md", "skill"), self.tmp / "skills/ub-mode/SKILL.md"),
            Run("touch a marker", python(f"open({str(marker)!r}, 'w')")),
            Note("mind the gap"),
        ]

    def test_a_dry_run_shows_every_step_and_its_reason_and_changes_nothing(self):
        steps = self.steps()
        code, out, _ = execute(steps, dry_run=True)
        self.assertEqual(0, code)
        self.assertFalse((self.tmp / "skills").exists())
        self.assertFalse((self.tmp / "ran").exists())
        for text in ("install the skill", "touch a marker", shlex.join(steps[1].argv), "mind the gap"):
            self.assertIn(text, out)

    def test_an_install_applies_every_step(self):
        code, out, err = execute(self.steps())
        self.assertEqual((0, ""), (code, err))
        self.assertEqual("skill", (self.tmp / "skills/ub-mode/SKILL.md").read_text())
        self.assertTrue((self.tmp / "ran").exists())
        self.assertIn("mind the gap", out)

    def test_the_first_failure_stops_the_install_and_names_the_step(self):
        steps = [Run("fail on purpose", python("raise SystemExit(3)"))] + self.steps()
        code, _, err = execute(steps)
        self.assertEqual(1, code)
        self.assertIn("could not fail on purpose", err)
        self.assertFalse((self.tmp / "skills").exists())

    def test_a_missing_program_is_a_failure_not_a_crash(self):
        code, _, err = execute([Run("run a ghost", (str(self.tmp / "ghost"),))])
        self.assertEqual(1, code)
        self.assertIn("could not run a ghost", err)

    def test_a_quiet_run_hides_what_the_command_prints(self):
        with captured_fd1() as captured:
            execute([Run("check", python("print('no' + 'ise')"), quiet=True)])
        self.assertNotIn("noise", captured[0])

    def test_a_loud_run_shows_what_the_command_prints(self):
        with captured_fd1() as captured:
            execute([Run("fetch", python("print('pro' + 'gress')"))])
        self.assertIn("progress", captured[0])


class Observation(TempDir):
    def test_a_checkout_supplies_its_own_skill(self):
        self.script("SKILL.md", "skill")
        script = self.script("install.py", "")
        self.assertEqual(self.tmp, install.World.observe(str(script)).source)

    def test_an_installer_without_a_skill_beside_it_has_no_source(self):
        script = self.script("install.py", "")
        self.assertIsNone(install.World.observe(str(script)).source)

    def test_a_piped_installer_has_no_source(self):
        self.assertIsNone(install.World.observe("<stdin>").source)

    def test_the_installing_python_is_observed(self):
        world = install.World.observe("<stdin>")
        self.assertEqual((sys.executable, tuple(sys.version_info[:2])), (world.python, world.version))
        self.assertEqual(Path.home(), world.home)

    def test_the_filesystem_and_path_are_observed(self):
        self.script("bin/git", "#!/bin/sh\n")
        self.script("bin/zsh", "")
        (self.tmp / "bin/zsh").chmod(0o644)
        path = f"{self.tmp / 'bin'}{os.pathsep}/nowhere"
        with mock.patch.dict(os.environ, {"PATH": path}):
            world = install.World.observe("<stdin>")
        self.assertEqual((str(self.tmp / "bin"), "/nowhere"), world.path)
        self.assertEqual(frozenset({"git"}), world.commands)
        self.assertTrue(world.exists(self.tmp / "bin/git"))
        self.assertFalse(world.exists(self.tmp / "missing"))


class Main(TempDir):
    def world(self, version=(3, 11)):
        return install.World(
            home=self.tmp / "home",
            source=Path(__file__).resolve().parents[1],
            python=sys.executable,
            version=version,
            path=(),
            commands=frozenset({"git"}),
            exists=Path.exists,
        )

    def main(self, *argv, version=(3, 11)):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = install.main(list(argv), self.world(version))
        return code, out.getvalue(), err.getvalue()

    def test_an_old_python_stops_the_install_before_any_step(self):
        code, out, err = self.main("--dry-run", version=(3, 9))
        self.assertEqual((1, ""), (code, out))
        self.assertIn("Python 3.11", err)

    def test_a_dry_run_prints_the_plan_and_leaves_home_alone(self):
        code, out, err = self.main("--dry-run")
        self.assertEqual((0, ""), (code, err))
        self.assertIn("fetch crapper", out)
        self.assertIn("nothing was changed", out)
        self.assertFalse((self.tmp / "home").exists())

    def test_a_failed_fetch_fails_the_install(self):
        with captured_fd1():
            code, out, err = self.main("--git-base", str(self.tmp / "nowhere"))
        self.assertEqual(1, code)
        self.assertIn("could not fetch crapper", err)
        self.assertNotIn("installed", out)

    def test_a_finished_install_says_how_to_use_it(self):
        with mock.patch.object(install, "plan", return_value=[Note("ready")]):
            code, out, _ = self.main()
        self.assertEqual(0, code)
        self.assertIn("ub-mode is installed", out)


if __name__ == "__main__":
    unittest.main()
