#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "${script_dir}/.." && pwd -P)"
template="${script_dir}/com.jielosc.csbaoyan-daily.plist.template"
target="/Users/${USER}/Library/LaunchAgents/com.jielosc.csbaoyan-daily.plist"
python_command="${repo_root}/.venv/bin/python"

if [[ ! -x "$python_command" ]]; then
    printf 'Error: Python virtual environment not found: %s\n' "$python_command" >&2
    exit 2
fi
if [[ ! -f "${repo_root}/.env" ]]; then
    printf 'Error: configure %s/.env before installing the LaunchAgent.\n' "$repo_root" >&2
    exit 2
fi
if [[ "$repo_root" == *['&<>']* || "$python_command" == *['&<>']* ]]; then
    printf '%s\n' "Error: paths containing XML special characters are unsupported." >&2
    exit 2
fi

mkdir -p "$(dirname "$target")" "${repo_root}/logs"
temporary="${target}.tmp"
sed \
    -e "s|__REPO_ROOT__|${repo_root}|g" \
    -e "s|__PYTHON_COMMAND__|${python_command}|g" \
    "$template" > "$temporary"
plutil -lint "$temporary" >/dev/null
chmod 600 "$temporary"
mv "$temporary" "$target"

launchctl bootout "gui/${UID}" "$target" >/dev/null 2>&1 || true
launchctl bootstrap "gui/${UID}" "$target"
launchctl enable "gui/${UID}/com.jielosc.csbaoyan-daily"
launchctl print "gui/${UID}/com.jielosc.csbaoyan-daily"
