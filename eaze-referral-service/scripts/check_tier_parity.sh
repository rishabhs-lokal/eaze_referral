#!/usr/bin/env bash
# Are the two tiers actually running the same thing?
#
# The tiers deliberately share one codebase and differ only in config, but they are deployed
# independently — which is the point, and also means one can silently fall behind the other.
# That has happened twice in this project: a change landed, only tier-1000 was rebuilt, and
# tier-500 kept serving older code while looking perfectly healthy.
#
# Checks what can actually diverge: the running image, the schema version, and the API surface.
# Config differences (coin amounts, ports, database) are expected and are NOT flagged.
#
#   ./scripts/check_tier_parity.sh
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

TIER_1000_URL="${TIER_1000_URL:-http://localhost:8091}"
TIER_500_URL="${TIER_500_URL:-http://localhost:8092}"
drift=0

note_drift() { echo "   -> DRIFT: $1"; drift=1; }

echo "== image contents =="
for f in app/services/eaze_wallet.py app/services/scheduler.py app/services/verification.py; do
  a=$(docker run --rm --entrypoint sh eaze-referral-service-tier-1000-app:latest \
        -c "test -f $f && echo yes || echo no" 2>/dev/null)
  b=$(docker run --rm --entrypoint sh eaze-referral-service-tier-500-app:latest \
        -c "test -f $f && echo yes || echo no" 2>/dev/null)
  printf '  %-34s 1000=%-3s 500=%s\n' "$(basename "$f")" "$a" "$b"
  [ "$a" = "$b" ] || note_drift "$f present in one tier only"
done

echo "== schema version =="
for tier in 1000 500; do
  v=$(docker compose -f "docker-compose.tier-$tier.yml" exec -T db \
        psql -U postgres -d eaze -tAc "SELECT version_num FROM alembic_version;" 2>/dev/null | tr -d '[:space:]')
  printf '  tier-%-5s %s\n' "$tier" "${v:-unreachable}"
  eval "v$tier=\$v"
done
[ "${v1000:-x}" = "${v500:-y}" ] || note_drift "schema versions differ — run the migration on the older tier"

echo "== API surface =="
# Field names on the reconcile response are a cheap proxy for "same build": a tier missing a
# field is running code from before that field existed.
a=$(curl -s -X POST "$TIER_1000_URL/api/referral/admin/reconcile" | tr ',' '\n' | grep -o '"[a-zA-Z]*":' | sort | tr -d '":' | tr '\n' ' ')
b=$(curl -s -X POST "$TIER_500_URL/api/referral/admin/reconcile"  | tr ',' '\n' | grep -o '"[a-zA-Z]*":' | sort | tr -d '":' | tr '\n' ' ')
echo "  tier-1000: ${a:-unreachable}"
echo "  tier-500 : ${b:-unreachable}"
[ "$a" = "$b" ] || note_drift "reconcile response fields differ — one tier is running older code"

echo
if [ "$drift" -eq 0 ]; then
  echo "OK — tiers are in parity."
else
  echo "Tiers have drifted. Rebuild the stale one:"
  echo "  docker compose -f docker-compose.tier-<n>.yml build app migrate"
  echo "  docker compose -f docker-compose.tier-<n>.yml run --rm migrate"
  echo "  docker compose -f docker-compose.tier-<n>.yml up -d app"
fi
exit "$drift"
