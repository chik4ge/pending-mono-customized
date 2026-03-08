# Pending Mono Feature Freezer

`freeze_pending_mono.py` downloads a release asset from [`yuru7/pending-mono`](https://github.com/yuru7/pending-mono), extracts all matching TTF files, and runs `pyftfeatfreeze` with one shared configuration.

It supports either direct `--features` input or a named preset loaded from `presets.json`.

## Requirements

- Python 3
- Network access to GitHub and PyPI on first run

If `pyftfeatfreeze` is not already installed, the script creates a local virtualenv under `.tool-venv/opentype-feature-freezer` and installs `opentype-feature-freezer` there.

## Examples

Freeze `zero` into the regular Pending Mono release:

```bash
./freeze_pending_mono.py \
  --asset PendingMono \
  --features zero \
  --suffix Zero
```

List bundled presets:

```bash
./freeze_pending_mono.py --list-presets
```

Freeze the bundled `editor-default` preset:

```bash
./freeze_pending_mono.py \
  --asset PendingMono \
  --preset editor-default
```

Freeze `ss01,zero` into the Nerd Fonts build from `v0.0.3`:

```bash
./freeze_pending_mono.py \
  --tag v0.0.3 \
  --asset PendingMonoNF \
  --features ss01,zero \
  --suffix SS01Zero
```

Inspect the first extracted font's scripts and features before freezing:

```bash
./freeze_pending_mono.py \
  --asset PendingMono \
  --features zero \
  --report
```

If you need to rename internal names beyond a suffix, forward `-R` replacements:

```bash
./freeze_pending_mono.py \
  --asset PendingMono \
  --features zero \
  --suffix Zero \
  --replace-name 'PendingMono/PendingMonoZero'
```

## Output layout

Generated fonts are written under:

```text
dist/<tag>/<asset-name-without-zip>/<suffix>/
```

For example:

```text
dist/v0.0.3/PendingMono_v0.0.3/Zero/
```

## Notes

- By default the script processes `*.ttf`. Use `--include-pattern '*.otf'` if a future release ships OTF files.
- The bundled preset [presets.json](/home/chikage/dev/pending-mono-customized/presets.json) only keeps enabled OpenType tags under `alternates` and `features`.
- `pyftfeatfreeze` only supports substitutions it can remap through `cmap` and GSUB. It does not freeze arbitrary layout behavior.
- The upstream tool recommends changing names appropriately if your redistribution target has naming restrictions.
