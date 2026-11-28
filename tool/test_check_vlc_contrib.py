"""Contrib orchestration: dependency order, fail-fast, safe cache reuse/invalidation."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from check_vlc_contrib import dependents, topology, clean_packages, parse_plan


class DependencyGraphTest(unittest.TestCase):
    def test_order_and_reverse_invalidation(self):
        packages = {name: {'dependencies': deps} for name, deps in
                    {'base': [], 'codec': ['base'], 'plugin': ['codec'], 'other': []}.items()}
        self.assertEqual(topology(packages, {'plugin'}), ['base', 'codec', 'plugin'])
        self.assertEqual(dependents(packages, {'codec'}), {'codec', 'plugin'})
        packages['base']['dependencies'] = ['plugin']
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            topology(packages, {'plugin'})

    def test_cleanup_rejects_symlink_before_removing_stamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'build'; source.mkdir()
            external = root / 'external'; external.mkdir()
            (source / 'escape').symlink_to(external, target_is_directory=True)
            (source / '.a').touch()
            with self.assertRaisesRegex(ValueError, 'unsafe'):
                clean_packages(source, {'a': {'sources': ['escape']}}, {'a'})
            self.assertTrue((source / '.a').exists())
            self.assertTrue(external.exists())

    def test_database_environment_is_not_a_package(self):
        packages, config = parse_plan("""OPX_PLAN|a|
OPX_CONFIG|CC|gcc
SECRET = private-fixture
.a: a-src toolchain.cmake
# recipe to execute (from '../src/a/rules.mak', line 2):
\t@touch $@
""")
        self.assertEqual(packages['a']['rule'], '../src/a/rules.mak')
        self.assertNotIn('SECRET', packages)
        self.assertEqual(config, {'CC': 'gcc'})


@unittest.skipUnless(shutil.which('make'), 'GNU make required')
class ContribRunnerTest(unittest.TestCase):
    def test_failure_resume_recipe_change_and_independent_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root / 'contrib/build'; build.mkdir(parents=True)
            source = root / 'contrib/src'; source.mkdir()
            (build / 'Makefile').write_text('''PKGS = a b c d
PKGS_ALL = a b c d
DEPS_b = a
DEPS_c = b
PREFIX = prefix
include ../src/*/rules.mak
''')
            for name in 'abcd':
                directory = source / name; directory.mkdir()
                dependency = {'b': '.a', 'c': '.b'}.get(name, '')
                directory.joinpath('rules.mak').write_text(f'''.{name}: {name}-src {dependency}
\t@test ! -e fail-{name}
\t@echo {name} >> builds.log
\t@touch $@
{name}-src:
\t@mkdir -p $@
''')
            (build / 'fail-b').touch()
            script = Path(__file__).with_name('check_vlc_contrib.py')
            env = dict(os.environ, OPX_TEST_SECRET='do-not-retain-this-fixture')

            def run(report, *args):
                folder = root / report
                process = subprocess.run([sys.executable, str(script), '--directory', str(build),
                                          '--report', str(folder), '--jobs', '4', *args],
                                         env=env, text=True, capture_output=True)
                summary = folder / 'summary.json'
                self.assertTrue(summary.exists(), process.stderr)
                return process, json.loads(summary.read_text()), folder

            result, summary, first = run('first')
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual([p['status'] for p in summary['packages']],
                             ['passed', 'failed', 'not_run', 'not_run'])
            self.assertEqual((build / 'builds.log').read_text().split(), ['a'])
            (build / 'fail-b').unlink()
            result, summary, second = run('second')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(summary['packages'][0]['cached'])
            self.assertEqual((build / 'builds.log').read_text().split(), ['a', 'b', 'c', 'd'])
            self.assertTrue((first / 'b.log').exists())
            self.assertFalse((first / 'c.log').exists())
            self.assertTrue((second / 'c.log').exists())
            for path in first.rglob('*'):
                if path.is_file():
                    self.assertNotIn('do-not-retain-this-fixture', path.read_text())
            with (source / 'b/rules.mak').open('a') as file:
                file.write('# changed package recipe\n')
            result, summary, _ = run('changed', '--only', 'c')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([p['package'] for p in summary['packages']], ['a', 'b', 'c'])
            self.assertEqual((build / 'builds.log').read_text().split(), ['a', 'b', 'c', 'd', 'b', 'c'])
            self.assertTrue((build / '.d').exists())
            # Installed .pc files can remove locally built packages from PKGS.
            # Pending invalidations must survive a run selecting another unit.
            makefile = build / 'Makefile'
            makefile.write_text(makefile.read_text().replace('PKGS = a b c d', 'PKGS = a d'))
            result, summary, _ = run('invalidate-unselected', '--only', 'd', '--rebuild', 'b')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((build / '.b').exists())
            result, summary, _ = run('resume-invalidated', '--only', 'c')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([p['package'] for p in summary['packages']], ['a', 'b', 'c'])
            self.assertEqual((build / 'builds.log').read_text().split(),
                             ['a', 'b', 'c', 'd', 'b', 'c', 'b', 'c'])


if __name__ == '__main__':
    unittest.main()
