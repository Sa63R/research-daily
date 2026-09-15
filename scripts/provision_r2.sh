#!/usr/bin/env bash

set -euo pipefail

bucket=""
domain=""
site_origin=""
zone_id="${CLOUDFLARE_ZONE_ID:-}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cors_template="${script_dir}/../cloudflare/r2-cors.json"

usage() {
    printf '%s\n' "Usage: scripts/provision_r2.sh --zone-id ZONE_ID --bucket NAME --domain HOSTNAME --site-origin URL"
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
        --site-origin)
            site_origin="${2%/}"
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
[[ -n "$bucket" ]] || {
    printf '%s\n' "Error: pass --bucket." >&2
    exit 2
}
[[ -n "$domain" ]] || {
    printf '%s\n' "Error: pass --domain." >&2
    exit 2
}
[[ "$site_origin" =~ ^https?://[^/]+$ ]] || {
    printf '%s\n' "Error: pass --site-origin as an origin without a path, for example https://reports.example.com." >&2
    exit 2
}
command -v wrangler >/dev/null 2>&1 || {
    printf '%s\n' "Error: wrangler is not installed." >&2
    exit 2
}

export WRANGLER_LOG_PATH="${TMPDIR:-/tmp}/csbaoyan-wrangler.log"
cors_file="$(mktemp "${TMPDIR:-/tmp}/csbaoyan-r2-cors.XXXXXX")"
trap 'rm -f "$cors_file"' EXIT
sed "s|__SITE_ORIGIN__|${site_origin}|g" "$cors_template" > "$cors_file"

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
