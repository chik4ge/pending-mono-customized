#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
import json
import urllib.request
from pathlib import Path

DEFAULT_ASSETS = [
    'PendingMono',
    'PendingMonoHW',
    'PendingMonoJPDOC',
    'PendingMonoHWJPDOC',
    'PendingMonoNF',
    'PendingMonoHWNF',
]
GITHUB_LATEST_RELEASE = 'https://api.github.com/repos/yuru7/pending-mono/releases/latest'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Build release zip assets for multiple Pending Mono release variants.'
    )
    parser.add_argument('--tag', default='latest', help="Upstream release tag such as 'v0.0.3' or 'latest'")
    parser.add_argument('--preset', required=True, help='Preset name passed through to freeze_pending_mono.py')
    parser.add_argument('--assets', nargs='*', default=DEFAULT_ASSETS, help='Asset prefixes to build')
    parser.add_argument('--release-assets-dir', default='release-assets', help='Directory where output zip files are written')
    parser.add_argument('--output-root', default='dist', help='Output root passed through to freeze_pending_mono.py')
    parser.add_argument('--verbose', action='store_true', help='Print commands before running them')
    return parser.parse_args()


def run(cmd: list[str], *, verbose: bool = False, cwd: Path | None = None) -> None:
    if verbose:
        print('+ ' + ' '.join(cmd), file=sys.stderr)
    subprocess.run(cmd, check=True, cwd=cwd)


def resolve_upstream_tag(tag: str) -> str:
    if tag != 'latest':
        return tag
    request = urllib.request.Request(
        GITHUB_LATEST_RELEASE,
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'pending-mono-release-builder',
        },
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)['tag_name']


def main() -> int:
    args = parse_args()
    release_assets_dir = Path(args.release_assets_dir)
    release_assets_dir.mkdir(parents=True, exist_ok=True)
    upstream_tag = resolve_upstream_tag(args.tag)

    for asset in args.assets:
        run([
            './freeze_pending_mono.py',
            '--tag', args.tag,
            '--asset', asset,
            '--preset', args.preset,
            '--output-root', args.output_root,
        ], verbose=args.verbose)

        source_dir = Path(args.output_root) / upstream_tag / f'{asset}_{upstream_tag}' / args.preset
        if not source_dir.exists():
            raise SystemExit(f'Expected generated directory not found: {source_dir}')

        zip_path = release_assets_dir / f'{asset}_{upstream_tag}_{args.preset}.zip'
        if zip_path.exists():
            zip_path.unlink()
        run(['zip', '-q', '-r', str(zip_path.resolve()), '.'], verbose=args.verbose, cwd=source_dir)
        print(f'generated {zip_path}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
