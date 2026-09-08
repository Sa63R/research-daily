#!/usr/bin/env bash

set -euo pipefail

bucket="csbaoyan-chat-daily"
domain="data.csbaoyan.icelon.top"
zone_id="${CLOUDFLARE_ZONE_ID:-}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cors_file="${script_dir}/../cloudflare/r2-cors.json"

usage() {
    printf '%s\n' "Usage: scripts/provision_r2.sh --zone-id ZONE_ID [--bucket NAME] [--domain HOSTNAME]"
}

while (($# > 0)); do
    case "$1" in
        --zone-id)
            zone_id="$2"
            shift 2
            ;;
        --bucket)
            bucket="$2"
            shift 2
            ;;
        --domain)
            domain="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown argument: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

[[ -n "$zone_id" ]] || {
    printf '%s\n' "Error: pass --zone-id or set CLOUDFLARE_ZONE_ID." >&2
    exit 2
}
command -v wrangler >/dev/null 2>&1 || {
    printf '%s\n' "Error: wrangler is not installed." >&2
    exit 2
}

export WRANGLER_LOG_PATH="${TMPDIR:-/tmp}/csbaoyan-wrangler.log"

if ! wrangler r2 bucket info "$bucket" --json >/dev/null 2>&1; then
    wrangler r2 bucket create "$bucket" --location apac
fi

wrangler r2 bucket cors set "$bucket" --file "$cors_file" --force

if ! wrangler r2 bucket domain get "$bucket" --domain "$domain" >/dev/null 2>&1; then
    wrangler r2 bucket domain add "$bucket" \
        --domain "$domain" \
        --zone-id "$zone_id" \
        --min-tls 1.2 \
        --force
fi

wrangler r2 bucket dev-url disable "$bucket" --force
wrangler r2 bucket info "$bucket"
wrangler r2 bucket domain get "$bucket" --domain "$domain"
wrangler r2 bucket cors list "$bucket"
