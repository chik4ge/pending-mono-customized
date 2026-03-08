#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

GITHUB_API_BASE = "https://api.github.com/repos/yuru7/pending-mono/releases"
DEFAULT_TOOL_VENV = Path('.tool-venv') / 'opentype-feature-freezer'
DEFAULT_PRESETS_FILE = Path('presets.json')
KNOWN_ASSET_PREFIXES = {
    'PendingMono',
    'PendingMonoHW',
    'PendingMonoJPDOC',
    'PendingMonoHWJPDOC',
    'PendingMonoNF',
    'PendingMonoHWNF',
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            'Download a release from yuru7/pending-mono and freeze OpenType '
            'features into every TTF in the chosen asset.'
        )
    )
    parser.add_argument(
        '--asset',
        help=(
            'Release asset prefix or filename. Examples: PendingMono, '
            'PendingMonoHWNF, PendingMono_v0.0.3.zip'
        ),
    )
    parser.add_argument(
        '--features',
        help="Comma-separated OpenType feature tags passed to pyftfeatfreeze, e.g. 'zero,ss01'",
    )
    parser.add_argument('--preset', help='Preset name from presets.json or another file passed with --presets-file')
    parser.add_argument(
        '--presets-file',
        default=str(DEFAULT_PRESETS_FILE),
        help='JSON file containing named presets. Default: presets.json',
    )
    parser.add_argument('--list-presets', action='store_true', help='List available presets and exit')
    parser.add_argument('--tag', default='latest', help="Release tag such as 'v0.0.3' or 'latest'")
    parser.add_argument('--script', help="Optional OpenType script tag passed with -s, e.g. 'latn'")
    parser.add_argument('--lang', help="Optional OpenType language tag passed with -l, e.g. 'JAN '")
    parser.add_argument(
        '--suffix',
        help=(
            'Custom font-family suffix for pyftfeatfreeze -S -U. '
            'Defaults to a sanitized version of --features.'
        ),
    )
    parser.add_argument(
        '--replace-name',
        action='append',
        default=[],
        metavar='SEARCH/REPLACE',
        help="Forwarded to pyftfeatfreeze -R. Can be specified multiple times.",
    )
    parser.add_argument('--output-root', default='dist', help='Directory where frozen fonts are written')
    parser.add_argument('--cache-dir', default='.cache/pending-mono', help='Directory for downloaded and extracted release files')
    parser.add_argument(
        '--tool-venv',
        default=str(DEFAULT_TOOL_VENV),
        help='Virtualenv used to install opentype-feature-freezer when pyftfeatfreeze is unavailable',
    )
    parser.add_argument('--pyftfeatfreeze', help='Path to an existing pyftfeatfreeze executable')
    parser.add_argument('--report', action='store_true', help='Run pyftfeatfreeze -r against the first extracted font before freezing')
    parser.add_argument('--verbose', action='store_true', help='Print executed commands')
    return parser.parse_args()


def log(message: str) -> None:
    print(message, file=sys.stderr)


def load_presets(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f'Preset file not found: {path}')
    with path.open(encoding='utf-8') as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise SystemExit(f'Preset file must contain a JSON object at top level: {path}')
    return data


def enabled_feature_tags(preset: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for section_name in ('alternates', 'features'):
        section = preset.get(section_name, {})
        if not isinstance(section, dict):
            continue
        for tag, enabled in section.items():
            if enabled:
                tags.append(tag)
    return sorted(set(tags))


def resolve_requested_features(args: argparse.Namespace) -> tuple[str, str | None]:
    preset_name = args.preset
    features_arg = args.features

    if args.list_presets:
        presets = load_presets(Path(args.presets_file))
        for name, preset in presets.items():
            tags = ','.join(enabled_feature_tags(preset)) or '(none)'
            print(f'{name}: {tags}')
        raise SystemExit(0)

    if preset_name:
        presets = load_presets(Path(args.presets_file))
        if preset_name not in presets:
            available = ', '.join(sorted(presets))
            raise SystemExit(f'Unknown preset {preset_name!r}. Available presets: {available}')
        features = enabled_feature_tags(presets[preset_name])
        if not features:
            raise SystemExit(f'Preset {preset_name!r} does not enable any OpenType features')
        return ','.join(features), preset_name

    if not features_arg:
        raise SystemExit('Either --features or --preset is required')

    return features_arg, None


def http_get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'pending-mono-feature-freezer',
        },
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def fetch_release(tag: str) -> dict[str, Any]:
    if tag == 'latest':
        return http_get_json(f'{GITHUB_API_BASE}/latest')
    return http_get_json(f'{GITHUB_API_BASE}/tags/{tag}')


def resolve_asset(release: dict[str, Any], requested: str) -> dict[str, Any]:
    requested_name = requested if requested.endswith('.zip') else None
    for asset in release['assets']:
        if requested_name and asset['name'] == requested_name:
            return asset

    prefix = requested.removesuffix('.zip')
    candidates = [asset for asset in release['assets'] if asset['name'].startswith(prefix + '_') and asset['name'].endswith('.zip')]
    if len(candidates) == 1:
        return candidates[0]

    available = ', '.join(asset['name'] for asset in release['assets'])
    raise SystemExit(f'Could not resolve asset {requested!r}. Available assets: {available}')


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, destination.open('wb') as out:
        shutil.copyfileobj(response, out)


def extract_zip(zip_path: Path, destination: Path) -> None:
    if destination.exists():
        return
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(destination)


def iter_font_files(root: Path) -> list[Path]:
    fonts = sorted(path for path in root.rglob('*.ttf') if path.is_file())
    if not fonts:
        raise SystemExit(f'No TTF fonts found under {root}')
    return fonts


def sanitize_suffix(features: str) -> str:
    return ''.join(ch for ch in features.replace(',', '-') if ch.isalnum() or ch in {'-', '_'}) or 'Frozen'


def run(cmd: list[str], *, verbose: bool = False, capture: bool = False) -> subprocess.CompletedProcess[str]:
    if verbose:
        log('+ ' + ' '.join(cmd))
    return subprocess.run(cmd, check=True, text=True, capture_output=capture)


def ensure_pyftfeatfreeze(explicit: str | None, tool_venv: Path, verbose: bool) -> Path:
    if explicit:
        path = shutil.which(explicit) if os.sep not in explicit else explicit
        if path and Path(path).exists():
            return Path(path)
        raise SystemExit(f'pyftfeatfreeze not found: {explicit}')

    installed = shutil.which('pyftfeatfreeze')
    if installed:
        return Path(installed)

    python_bin = tool_venv / 'bin' / 'python'
    pyftfeatfreeze = tool_venv / 'bin' / 'pyftfeatfreeze'
    if pyftfeatfreeze.exists():
        return pyftfeatfreeze

    tool_venv.parent.mkdir(parents=True, exist_ok=True)
    run([sys.executable, '-m', 'venv', str(tool_venv)], verbose=verbose)
    run([str(python_bin), '-m', 'pip', 'install', '--upgrade', 'pip'], verbose=verbose)
    run([str(python_bin), '-m', 'pip', 'install', 'opentype-feature-freezer'], verbose=verbose)
    return pyftfeatfreeze


def maybe_report(pyftfeatfreeze: Path, font_path: Path, verbose: bool) -> None:
    report = run([str(pyftfeatfreeze), '-r', str(font_path)], verbose=verbose, capture=True)
    print(report.stdout.rstrip())


def build_output_dir(output_root: Path, asset_name: str, tag_name: str, suffix: str) -> Path:
    stem = asset_name[:-4] if asset_name.endswith('.zip') else asset_name
    output_dir = output_root / tag_name / stem / suffix
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def freeze_fonts(
    pyftfeatfreeze: Path,
    fonts: list[Path],
    output_dir: Path,
    features: str,
    script: str | None,
    lang: str | None,
    suffix: str,
    replace_names: list[str],
    verbose: bool,
) -> None:
    replace_arg = ','.join(replace_names) if replace_names else None
    for font in fonts:
        out_path = output_dir / font.name
        cmd = [
            str(pyftfeatfreeze),
            '-f', features,
            '-S',
            '-U', suffix,
        ]
        if script:
            cmd.extend(['-s', script])
        if lang:
            cmd.extend(['-l', lang])
        if replace_arg:
            cmd.extend(['-R', replace_arg])
        cmd.extend([str(font), str(out_path)])
        run(cmd, verbose=verbose)
        print(f'generated {out_path}')


def main() -> int:
    args = parse_args()
    features, preset_name = resolve_requested_features(args)
    if not args.asset:
        raise SystemExit('--asset is required unless you only use --list-presets')

    if args.asset.removesuffix('.zip') not in KNOWN_ASSET_PREFIXES and not args.asset.endswith('.zip'):
        log('warning: asset is not one of the known Pending Mono release prefixes; attempting exact/prefix match anyway')

    release = fetch_release(args.tag)
    asset = resolve_asset(release, args.asset)

    cache_dir = Path(args.cache_dir)
    zip_path = cache_dir / 'downloads' / asset['name']
    if not zip_path.exists():
        log(f'downloading {asset["browser_download_url"]}')
        download_file(asset['browser_download_url'], zip_path)

    extract_root = cache_dir / 'extracted' / release['tag_name'] / asset['name'].removesuffix('.zip')
    extract_zip(zip_path, extract_root)
    fonts = iter_font_files(extract_root)

    pyftfeatfreeze = ensure_pyftfeatfreeze(args.pyftfeatfreeze, Path(args.tool_venv), args.verbose)

    if args.report:
        maybe_report(pyftfeatfreeze, fonts[0], args.verbose)

    suffix = args.suffix or preset_name or sanitize_suffix(features)
    output_dir = build_output_dir(Path(args.output_root), asset['name'], release['tag_name'], suffix)
    freeze_fonts(
        pyftfeatfreeze=pyftfeatfreeze,
        fonts=fonts,
        output_dir=output_dir,
        features=features,
        script=args.script,
        lang=args.lang,
        suffix=suffix,
        replace_names=args.replace_name,
        verbose=args.verbose,
    )

    print('output_dir=' + str(output_dir.resolve()))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', 'replace').strip()
        raise SystemExit(f'GitHub API request failed: {exc.code} {exc.reason}\n{detail}') from exc
