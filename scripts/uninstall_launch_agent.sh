#!/usr/bin/env bash

set -euo pipefail

target="/Users/${USER}/Library/LaunchAgents/com.jielosc.csbaoyan-daily.plist"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "${script_dir}/.." && pwd -P)"
runner_app="${repo_root}/.runner/GreenDailyRunner.app"
remove_runner=false

if [[ ${1:-} == "--remove-runner" ]]; then
    remove_runner=true
    shift
fi
if (($# > 0)); then
    printf 'Usage: %s [--remove-runner]\n' "$0" >&2
    exit 2
fi

launchctl bootout "gui/${UID}" "$target" >/dev/null 2>&1 || true
if [[ -f "$target" ]]; then
    rm "$target"
fi
printf '%s\n' "Removed com.jielosc.csbaoyan-daily."
if [[ "$remove_runner" == true && -d "$runner_app" ]]; then
    rm -rf "$runner_app"
    printf '%s\n' "Removed $runner_app. Its Full Disk Access entry can now be removed from System Settings."
elif [[ -d "$runner_app" ]]; then
    printf '%s\n' "Kept $runner_app to preserve its Full Disk Access identity."
fi
