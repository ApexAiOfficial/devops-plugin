#!/bin/sh
# Install the pinned Claude Code CLI that validates the plugin.
#
# npm ci installs exactly what package-lock.json pins, integrity-checked, and
# runs no install script. Then only the package's own install.cjs runs: it
# hard-links (or copies) the native binary of the platform package the lockfile
# just installed over the bin placeholder, and fetches nothing.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
npm ci --prefix "$here" --ignore-scripts --no-audit --no-fund
node "$here/node_modules/@anthropic-ai/claude-code/install.cjs"
