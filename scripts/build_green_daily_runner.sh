#!/usr/bin/env bash

set -euo pipefail
umask 077

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "${script_dir}/.." && pwd -P)"
source_dir="${script_dir}/green_daily_runner"
runner_root="${repo_root}/.runner"
runner_app="${runner_root}/GreenDailyRunner.app"
bundle_identifier="com.jielosc.greendaily.runner"
force=false

if [[ ${1:-} == "--force" ]]; then
    force=true
    shift
fi
if (($# > 0)); then
    printf 'Usage: %s [--force]\n' "$0" >&2
    exit 2
fi

if [[ -e "$runner_app" && "$force" != true ]]; then
    printf '%s\n' "GreenDailyRunner already exists: $runner_app"
    printf '%s\n' "Keeping it preserves its Full Disk Access identity. Use --force only when replacing the runner intentionally."
    exit 0
fi

command -v xcrun >/dev/null 2>&1 || {
    printf '%s\n' "Error: Xcode Command Line Tools are required (xcrun not found)." >&2
    exit 1
}
command -v codesign >/dev/null 2>&1 || {
    printf '%s\n' "Error: codesign is required." >&2
    exit 1
}

temporary_root="$(mktemp -d "${TMPDIR:-/tmp}/green-daily-runner.XXXXXX")"
trap 'rm -rf "$temporary_root"' EXIT
temporary_app="${temporary_root}/GreenDailyRunner.app"
mkdir -p "${temporary_app}/Contents/MacOS"
install -m 600 "${source_dir}/Info.plist" "${temporary_app}/Contents/Info.plist"
xcrun swiftc \
    -O \
    -target "$(uname -m)-apple-macos13.0" \
    "${source_dir}/main.swift" \
    -o "${temporary_app}/Contents/MacOS/GreenDailyRunner"
chmod 700 "${temporary_app}/Contents/MacOS/GreenDailyRunner"
codesign --force --deep --sign - --identifier "$bundle_identifier" "$temporary_app"
plutil -lint "${temporary_app}/Contents/Info.plist" >/dev/null
codesign --verify --deep --strict "$temporary_app"

mkdir -p "$runner_root"
chmod 700 "$runner_root"
if [[ -e "$runner_app" ]]; then
    rm -rf "$runner_app"
fi
mv "$temporary_app" "$runner_app"
chmod 700 "$runner_app" "$runner_app/Contents" "$runner_app/Contents/MacOS"

printf '%s\n' "Built: $runner_app"
printf '%s\n' "Bundle identifier: $bundle_identifier"
printf '%s\n' "Replacing this app later may require granting Full Disk Access again."
