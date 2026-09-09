#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "${script_dir}/.." && pwd -P)"
template="${script_dir}/com.jielosc.csbaoyan-daily.plist.template"
target="/Users/${USER}/Library/LaunchAgents/com.jielosc.csbaoyan-daily.plist"
runner_app="${repo_root}/.runner/GreenDailyRunner.app"
runner_executable="${runner_app}/Contents/MacOS/GreenDailyRunner"
runner_was_built=false

if [[ ! -x "${repo_root}/.venv/bin/python" ]]; then
    printf 'Error: Python virtual environment not found: %s\n' "${repo_root}/.venv/bin/python" >&2
    exit 2
fi
if [[ ! -f "${repo_root}/.env" ]]; then
    printf 'Error: configure %s/.env before installing the LaunchAgent.\n' "$repo_root" >&2
    exit 2
fi
system_offset="$(date '+%z')"
shanghai_offset="$(TZ=Asia/Shanghai date '+%z')"
if [[ "$system_offset" != "$shanghai_offset" ]]; then
    printf '%s\n' \
        "Warning: launchd uses the macOS system timezone. The 06:30 trigger will not be 06:30 Asia/Shanghai while the offsets differ." \
        >&2
fi
if [[ ! -x "$runner_executable" ]]; then
    "${script_dir}/build_green_daily_runner.sh"
    runner_was_built=true
fi
if [[ ! -x "$runner_executable" ]]; then
    printf 'Error: GreenDailyRunner executable not found: %s\n' "$runner_executable" >&2
    exit 2
fi
if ! codesign --verify --deep --strict "$runner_app"; then
    printf 'Error: GreenDailyRunner code signature is invalid: %s\n' "$runner_app" >&2
    exit 2
fi
runner_identifier="$(codesign -d --verbose=4 "$runner_app" 2>&1 | sed -n 's/^Identifier=//p')"
if [[ "$runner_identifier" != "com.jielosc.greendaily.runner" ]]; then
    printf 'Error: unexpected GreenDailyRunner identifier: %s\n' "$runner_identifier" >&2
    exit 2
fi
"$runner_executable" --check

if [[ "$repo_root" == *['&<>']* || "$runner_executable" == *['&<>']* ]]; then
    printf '%s\n' "Error: paths containing XML special characters are unsupported." >&2
    exit 2
fi

mkdir -p "$(dirname "$target")" "${repo_root}/logs"
chmod 700 "${repo_root}/logs"
touch "${repo_root}/logs/launchd.out.log" "${repo_root}/logs/launchd.err.log"
chmod 600 "${repo_root}/logs/launchd.out.log" "${repo_root}/logs/launchd.err.log"
temporary="${target}.tmp"
sed \
    -e "s|__REPO_ROOT__|${repo_root}|g" \
    -e "s|__RUNNER_EXECUTABLE__|${runner_executable}|g" \
    "$template" > "$temporary"
plutil -lint "$temporary" >/dev/null
chmod 600 "$temporary"
mv "$temporary" "$target"

launchctl bootout "gui/${UID}" "$target" >/dev/null 2>&1 || true
launchctl bootstrap "gui/${UID}" "$target"
launchctl enable "gui/${UID}/com.jielosc.csbaoyan-daily"
launchctl print "gui/${UID}/com.jielosc.csbaoyan-daily"

printf '%s\n' "LaunchAgent now starts only: $runner_executable"
printf '%s\n' "Grant Full Disk Access to this app, not to Python: $runner_app"
if [[ "$runner_was_built" == true ]]; then
    open -R "$runner_app"
    open "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_AllFiles"
fi
