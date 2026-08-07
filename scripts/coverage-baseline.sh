#!/usr/bin/env bash
# Ratchet baseline tool for the mist-datasource (pytest) coverage threshold.
#
# Reads coverage-summary.json (produced by `uv run pytest`, addopts carries
# --cov-report=json), computes the overall line coverage, and writes back
# [tool.coverage.report].fail_under in pyproject.toml with the LARGER of the
# old committed value and the measured value — so the floor only ever rises.
#
# Run locally (never in CI):
#   1. uv run pytest
#   2. bash scripts/coverage-baseline.sh
#   3. review the diff (pyproject.toml + ci.yml), then commit
#
# CI only READS the committed threshold (--cov-fail-under in ci.yml) to enforce
# the gate; it never mutates the repository.

set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f coverage-summary.json ]]; then
  echo "coverage-summary.json not found. Run 'uv run pytest' first." >&2
  exit 1
fi

# Extract overall line coverage percent from coverage.py's JSON (totals.line_percent
# is the line coverage, rounded to 2 decimals by coverage.py).
MEASURED=$(python3 -c "
import json, sys
with open('coverage-summary.json') as f:
    d = json.load(f)
# coverage.py JSON has 'totals' with 'percent_covered' (line coverage)
totals = d.get('totals', {})
pct = totals.get('percent_covered')
if pct is None:
    print('No totals.percent_covered in coverage-summary.json', file=sys.stderr)
    sys.exit(1)
print(round(pct, 2))
")

# Current committed fail_under (from [tool.coverage.report]).
COMMITTED=$(python3 -c "
import tomllib
with open('pyproject.toml', 'rb') as f:
    d = tomllib.load(f)
print(d.get('tool', {}).get('coverage', {}).get('report', {}).get('fail_under', 0))
")

echo "Measured line coverage: ${MEASURED}%"
echo "Committed fail_under:   ${COMMITTED}"

# Bash float comparison: use awk
RAISE=$(awk -v m="$MEASURED" -v c="$COMMITTED" 'BEGIN { print (m > c) ? 1 : 0 }')
if [[ "$RAISE" == "1" ]]; then
  # Update pyproject.toml fail_under
  python3 -c "
import re, sys
measured = sys.argv[1]
with open('pyproject.toml') as f:
    content = f.read()
content = re.sub(r'(fail_under\s*=\s*)[0-9.]+', r'\g<1>' + measured, content)
with open('pyproject.toml', 'w') as f:
    f.write(content)
" "$MEASURED"
  # Update ci.yml --cov-fail-under
  python3 -c "
import re, sys
measured = sys.argv[1]
with open('.github/workflows/ci.yml') as f:
    content = f.read()
content = re.sub(r'--cov-fail-under=[0-9.]+', '--cov-fail-under=' + measured, content)
with open('.github/workflows/ci.yml', 'w') as f:
    f.write(content)
" "$MEASURED"
  echo "Ratchet raised: ${COMMITTED}% -> ${MEASURED}% (written to pyproject.toml + ci.yml)."
elif [[ $(awk -v m="$MEASURED" -v c="$COMMITTED" 'BEGIN { print (m < c) ? 1 : 0 }') == "1" ]]; then
  echo "Measured ${MEASURED}% < committed ${COMMITTED}%. NOT lowering the baseline (ratchet only rises)."
  echo "If this drop is intentional, edit pyproject.toml + ci.yml manually."
else
  echo "No change: ${MEASURED}% == ${COMMITTED}%."
fi
