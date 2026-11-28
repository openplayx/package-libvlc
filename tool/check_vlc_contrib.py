#!/usr/bin/env python3
"""Check bootstrapped VLC contrib packages individually, preserving GNU make's cache.

Run only against an idle source tree. build_libvlc.sh callers already hold its
workspace lock. --rebuild cleans selected packages and their dependent packages;
all other installed dependencies stay available.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
CONFIG_KEYS = ('BUILD', 'HOST', 'PREFIX', 'CC', 'CXX', 'CFLAGS', 'CXXFLAGS',
               'CPPFLAGS', 'LDFLAGS', 'AR', 'RANLIB', 'PKG_CONFIG_PATH')


def topology(packages: dict, selected: set[str]) -> list[str]:
    result, visiting, visited = [], set(), set()

    def visit(name):
        if name in visited:
            return
        if name in visiting:
            raise ValueError(f'cyclic contrib dependency: {name}')
        if name not in packages:
            raise ValueError(f'unknown contrib package: {name}')
        visiting.add(name)
        for dependency in sorted(packages[name]['dependencies']):
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        result.append(name)

    for name in sorted(selected):
        visit(name)
    return result


def dependents(packages: dict, changed: set[str]) -> set[str]:
    affected = set(changed)
    while True:
        more = {name for name, info in packages.items()
                if affected.intersection(info['dependencies'])}
        if more <= affected:
            return affected
        affected.update(more)


def parse_plan(output: str) -> tuple[dict, dict]:
    packages, configuration = {}, {}
    for line in output.splitlines():
        if line.startswith('OPX_PLAN|'):
            _, name, deps = line.split('|', 2)
            if not NAME.fullmatch(name):
                raise ValueError(f'invalid contrib package name: {name}')
            packages[name] = {'dependencies': deps.split(), 'sources': [], 'rule': ''}
        elif line.startswith('OPX_CONFIG|'):
            _, key, value = line.split('|', 2)
            configuration[key] = value
    # The database is used only in memory. Never retain or print it: GNU make
    # also includes environment variables in its database.
    current = None
    for line in output.splitlines():
        match = re.match(r'^\.([A-Za-z0-9][A-Za-z0-9_.-]*):(?:\s+(.*))?$', line)
        if match:
            current = match[1] if match[1] in packages else None
            if current:
                packages[current]['sources'] = sorted({word for word in (match[2] or '').split()
                                                       if NAME.fullmatch(word)})
        elif line and not line.startswith(('#', '\t', ' ')):
            current = None
        if current:
            origin = re.search(r"#\s+(?:recipe|commands) to execute \(from [`']([^']+)'", line)
            if origin:
                packages[current]['rule'] = origin[1]
    if not packages:
        raise ValueError('GNU make did not return a contrib package plan')
    return packages, configuration


def planner(previous=()) -> str:
    if any(not NAME.fullmatch(name) for name in previous):
        raise ValueError('invalid cached package name')
    lines = ['.PHONY: opx-check-plan', 'opx-check-plan: ; @:']
    lines += ['OPX_PREVIOUS_PACKAGES := ' + ' '.join(sorted(previous)),
              'OPX_CHECK_PACKAGES := $(sort $(PKGS) $(foreach p,$(PKGS_ALL),$(if $(wildcard .$(p)),$(p))) $(filter $(PKGS_ALL),$(OPX_PREVIOUS_PACKAGES)))',
              '$(foreach p,$(OPX_CHECK_PACKAGES),$(info OPX_PLAN|$(p)|$(filter $(OPX_CHECK_PACKAGES),$(DEPS_$(p)))))']
    lines += [f'$(info OPX_CONFIG|{key}|$({key}))' for key in CONFIG_KEYS]
    lines += ['$(info OPX_CONFIG|CC_VERSION|$(shell $(CC) --version 2>/dev/null | head -n1))',
              '$(info OPX_CONFIG|CXX_VERSION|$(shell $(CXX) --version 2>/dev/null | head -n1))']
    return '\n'.join(lines) + '\n'


def unit_makefile(order: list[str]) -> str:
    # Serialize packages in this make invocation. Recursive makes can still
    # use the jobserver to compile each package in parallel.
    lines = ['.NOTPARALLEL:', '.PHONY: opx-check-all',
             'opx-check-all: ' + ' '.join('opx-unit-' + name for name in order)]
    for name in order:
        lines += [f'.PHONY: opx-start-{name} opx-unit-{name}',
                  f'opx-start-{name}:', f"\t@printf '%s\\n' 'OPX_START|{name}'",
                  f'opx-unit-{name}: opx-start-{name} .{name}',
                  f"\t@printf '%s\\n' 'OPX_DONE|{name}'"]
    return '\n'.join(lines) + '\n'


def atomic_json(path: Path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def fingerprint(directory: Path, info: dict) -> str:
    rule = (directory / info['rule']).resolve() if info['rule'] else None
    source = directory.parent / 'src'
    if rule and rule.is_relative_to(source.resolve()):
        files = sorted(p for p in rule.parent.rglob('*') if p.is_file())
    else:
        raise ValueError('cannot identify package recipe; refusing an unsafe cache check')
    h = hashlib.sha256()
    for path in files:
        h.update(str(path.relative_to(source)).encode())
        h.update(path.read_bytes())
    h.update(json.dumps(info['dependencies'], sort_keys=True).encode())
    return h.hexdigest()


def clean_packages(directory: Path, packages: dict, names: set[str]):
    # Validate the entire removal plan before making any changes. Only direct
    # extracted source directories under this contrib build directory qualify.
    roots = set()
    for name in names:
        if not NAME.fullmatch(name):
            raise ValueError(f'invalid package: {name}')
        for source in packages[name]['sources']:
            path = directory / source
            if path.is_dir():
                if path.is_symlink() or path.resolve().parent != directory.resolve():
                    raise ValueError(f'unsafe contrib source directory: {path}')
                roots.add(path)
    for name in names:
        for stamp in (f'.{name}', f'.dep-{name}'):
            (directory / stamp).unlink(missing_ok=True)
    for path in sorted(roots):
        shutil.rmtree(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True, help='bootstrapped contrib/opx-TARGET directory')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--only', default='', help='comma-separated packages, including their dependency closure')
    parser.add_argument('--rebuild', default='', help='clean these packages and all dependent packages')
    parser.add_argument('--jobs', type=int, default=2, help='parallel compilation jobs inside each package')
    parser.add_argument('--adopt-existing', action='store_true',
                        help='explicitly adopt already verified make stamps on first use')
    parser.add_argument('--cache-key', default='', help='validated source-cache key (full checks only)')
    parser.add_argument('--list', action='store_true')
    args = parser.parse_args()
    if args.cache_key and not re.fullmatch(r'[a-f0-9]{16}', args.cache_key):
        parser.error('cache-key must contain 16 lowercase hexadecimal digits')
    directory, report = args.directory.resolve(), args.report.resolve()
    if args.jobs < 1 or not (directory / 'Makefile').is_file():
        parser.error('jobs must be positive and directory must contain a contrib Makefile')
    report.mkdir(parents=True, exist_ok=True)
    atomic_json(report / 'summary.json', {'overall': 'not_run', 'packages': []})
    state_file = directory / '.opx-package-checks.json'
    state = json.loads(state_file.read_text(encoding='utf-8')) if state_file.exists() else {'packages': {}}
    previous = set(state['packages']) | set(state.get('invalidated', []))
    plan_file = report / 'plan.mk'
    plan_file.write_text(planner(previous), encoding='utf-8')
    make = shutil.which('make.exe' if os.name == 'nt' else 'make') or 'make'
    # The only selected target is a no-op. Do not use make -n/-q on package
    # targets, since recursive make recipes may execute even with those flags.
    probe = subprocess.run([make, '-p', '--no-print-directory', '-f', 'Makefile',
                            '-f', plan_file.as_posix(), 'opx-check-plan'], cwd=directory,
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
    (report / 'plan-stderr.log').write_text(probe.stderr, encoding='utf-8')
    if probe.returncode:
        raise RuntimeError(f'contrib plan failed; see {report / "plan-stderr.log"}')
    packages, configuration = parse_plan(probe.stdout)
    selected = set(filter(None, args.only.split(','))) or set(packages)
    order = topology(packages, selected)
    if args.list:
        print('\n'.join(order))
        return 0
    hashes = {name: fingerprint(directory, packages[name]) for name in packages}
    # System/flag changes should use a separate source cache (the Windows CI
    # key includes those inputs). Refuse silent reuse if an operator changes
    # the effective contrib configuration in the same directory.
    global_hash = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    legacy = {key: value for key, value in configuration.items() if key in CONFIG_KEYS}
    legacy_hash = hashlib.sha256(json.dumps(legacy, sort_keys=True).encode()).hexdigest()
    adopting_v1 = args.adopt_existing and not state.get('schema') and state.get('configuration') == legacy_hash
    if state.get('configuration') not in (None, global_hash) and not adopting_v1:
        raise ValueError('contrib compiler/configuration changed; use a separate source cache')
    common = hashlib.sha256()
    common_files = [directory.parent / 'bootstrap', *sorted((directory.parent / 'src').glob('*'))]
    for path in common_files:
        if path.is_file():
            common.update(path.name.encode())
            common.update(path.read_bytes())
    common_hash = common.hexdigest()
    if state.get('common_recipe') not in (None, common_hash):
        raise ValueError('global contrib recipe changed; use a separate source cache')
    if state.get('packages') and not state.get('common_recipe') and not args.adopt_existing:
        raise ValueError('adopt the verified legacy cache once with --adopt-existing')
    changed = set(filter(None, args.rebuild.split(','))) | set(state.get('invalidated', []))
    unknown = changed - packages.keys()
    if unknown:
        raise ValueError(f'unknown rebuild package(s): {sorted(unknown)}')
    for name in packages:
        previous = state['packages'].get(name)
        if previous and previous['recipe'] != hashes[name]:
            changed.add(name)
        elif not previous and name in order and not args.adopt_existing:
            changed.add(name)
    affected = dependents(packages, changed)
    clean_packages(directory, packages, affected)
    for name in affected:
        state['packages'].pop(name, None)
    state['configuration'] = global_hash
    state['schema'] = 2
    state['common_recipe'] = common_hash
    state['invalidated'] = sorted(affected)
    atomic_json(state_file, state)
    rows = {name: {'package': name, 'dependencies': packages[name]['dependencies'],
                   'status': 'not_run', 'recipe': hashes[name]} for name in order}
    summary = {'overall': 'running', 'selected': len(order), 'available': len(packages), 'packages': list(rows.values())}
    atomic_json(report / 'summary.json', summary)
    units = report / 'units.mk'
    units.write_text(unit_makefile(order), encoding='utf-8')
    current, log, start, before = None, None, 0.0, None
    command = [make, '--no-print-directory', f'-j{args.jobs}', '-f', 'Makefile', '-f', units.as_posix(), 'opx-check-all']
    with (report / 'make.log').open('w', encoding='utf-8') as combined:
        process = subprocess.Popen(command, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding='utf-8', errors='replace')
        try:
            for line in process.stdout:
                combined.write(line)
                if line.startswith('OPX_START|'):
                    current = line.strip().split('|', 1)[1]
                    start = time.monotonic()
                    stamp = directory / f'.{current}'
                    before = stamp.stat().st_mtime_ns if stamp.exists() else None
                    log = (report / f'{current}.log').open('w', encoding='utf-8')
                    rows[current]['status'] = 'running'
                    print(f'checking {current}...', flush=True)
                elif line.startswith('OPX_DONE|'):
                    name = line.strip().split('|', 1)[1]
                    if name != current:
                        raise RuntimeError('out-of-order contrib result')
                    stamp = directory / f'.{name}'
                    if not stamp.is_file():
                        raise RuntimeError(f'make succeeded without an install stamp: {name}')
                    rows[name].update(status='passed', seconds=round(time.monotonic() - start, 2),
                                      cached=before == stamp.stat().st_mtime_ns)
                    state['packages'][name] = {'recipe': hashes[name]}
                    state['invalidated'] = [package for package in state['invalidated'] if package != name]
                    atomic_json(state_file, state)
                    log.close(); log = None; current = None
                    atomic_json(report / 'summary.json', summary)
                    print(f'passed {name}', flush=True)
                elif log:
                    log.write(line)
            code = process.wait()
        finally:
            if log:
                log.close()
            if process.poll() is None:
                process.terminate()
                process.wait()
    if current:
        rows[current].update(status='failed', seconds=round(time.monotonic() - start, 2), exit_code=code)
    summary['overall'] = 'passed' if code == 0 and all(row['status'] == 'passed' for row in rows.values()) else 'failed'
    atomic_json(report / 'summary.json', summary)
    if summary['overall'] == 'passed' and args.cache_key and not args.only:
        marker = directory.parent.parent / '.opx-source-cache-key'
        temporary = marker.with_suffix('.tmp')
        temporary.write_text(args.cache_key + '\n', encoding='ascii')
        temporary.replace(marker)
    print(f'{summary["overall"]}: {sum(row["status"] == "passed" for row in rows.values())}/{len(order)} selected packages; {report}', flush=True)
    return 0 if summary['overall'] == 'passed' else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
