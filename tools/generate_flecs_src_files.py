#!/usr/bin/env python3
"""
Scan native/flecs/src for .c files and produce a Zig `src_files` array that
can be pasted into `src/Flecs.NET.Native/build.zig` or optionally applied
in-place with --apply.

Usage:
  python tools/generate_flecs_src_files.py [--apply]

Options:
  --root DIR   Root path to project (defaults to repo root where this script lives).
  --apply      Write the generated array into src/Flecs.NET.Native/build.zig,
               replacing the existing src_files block. Use with caution.
"""
import argparse
from pathlib import Path
import sys
import re

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[1]
DEFAULT_BUILD = REPO_ROOT / 'src' / 'Flecs.NET.Native' / 'build.zig'
NATIVE_SRC = REPO_ROOT / 'native' / 'flecs' / 'src'

ZIG_ARRAY_HEADER = 'const src_files = [_][]const u8{'


def find_c_files(root: Path):
    files = []
    if not root.exists():
        raise SystemExit(f"Source directory not found: {root}")
    for p in sorted(root.rglob('*.c')):
        # Only include files under native/flecs/src (ignore examples/tests outside src)
        try:
            rel = p.relative_to(REPO_ROOT)
        except Exception:
            rel = p
        # normalize to posix-style relative path (native/flecs/src/...)
        files.append(str(rel).replace('\\', '/'))
    return files


def format_zig_array(entries):
    lines = []
    lines.append(ZIG_ARRAY_HEADER)
    lines.append('    "../../native/flecs_helpers.c",')
    lines.append('')
    # Group files by the first path segment under native/flecs/src
    groups = {}
    prefix = 'native/flecs/src/'
    for e in entries:
        if not e.startswith(prefix):
            continue
        rel = e[len(prefix):]
        parts = rel.split('/')
        if len(parts) == 1:
            group = 'core'
        else:
            group = parts[0]
        groups.setdefault(group, []).append(e)

    # Keep a consistent order: core first, then sorted groups
    ordered_groups = []
    if 'core' in groups:
        ordered_groups.append('core')
    for g in sorted(k for k in groups.keys() if k != 'core'):
        ordered_groups.append(g)

    for gname in ordered_groups:
        lines.append(f'    // {gname}')
        for p in sorted(groups[gname]):
            lines.append(f'    "../../{p}",')
        lines.append('')

    lines.append('};')
    return '\n'.join(lines)


def replace_block_in_build(build_path: Path, new_block: str):
    txt = build_path.read_text(encoding='utf-8')
    # Replace from the line that declares const src_files to the closing '};'
    new_txt, n = re.subn(r"const\s+src_files\s*=\s*\[\_]\[\]const\s+u8\{[\s\S]*?\n\};\n", new_block + "\n\n", txt)
    if n == 0:
        raise SystemExit('Failed to locate src_files block in build.zig')
    return new_txt


def replace_block_in_build_paths(input_path: Path, output_path: Path, new_block: str):
    """Read the file at input_path, replace the src_files block, and write result to output_path."""
    txt = input_path.read_text(encoding='utf-8')
    new_txt, n = re.subn(r"const\s+src_files\s*=\s*\[\_]\[\]const\s+u8\{[\s\S]*?\n\};\n", new_block + "\n\n", txt)
    if n == 0:
        raise SystemExit('Failed to locate src_files block in build.zig')
    output_path.write_text(new_txt, encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=REPO_ROOT)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    entries = find_c_files(args.root / 'native' / 'flecs' / 'src')
    # ensure essential helpers are present (flecs_helpers lives at native/)
    # filter out test/example directories that aren't under src
    generated = format_zig_array(entries)

    print(generated)

    if args.apply:
        build_path = args.root / 'src' / 'Flecs.NET.Native' / 'build.zig'
        backup = build_path.with_suffix('.zig.bak')
        # If the build.zig exists, move it to backup. If it doesn't exist but a backup
        # already exists (from a previous run), use that as the input. This makes repeated
        # runs idempotent and avoids FileNotFound errors.
        if build_path.exists():
            build_path.replace(backup)
            src_input = backup
        else:
            if backup.exists():
                # previous run already created backup; use it as source
                src_input = backup
            else:
                raise SystemExit(f'Neither {build_path} nor {backup} exist; cannot apply')

        # Read from src_input, replace block, and write updated content to build_path
        try:
            replace_block_in_build_paths(src_input, build_path, generated)
            print(f'Applied updated src_files to {build_path} (backup at {backup})')
        except Exception:
            # if something goes wrong and build_path was created, remove it to avoid partial state
            if build_path.exists():
                try:
                    build_path.unlink()
                except Exception:
                    pass
            raise


if __name__ == '__main__':
    main()
