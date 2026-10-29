#!/usr/bin/env bash
# Fails when a tracked file looks like proprietary model signature or
# calibration data. This repository is public, so such files must never be
# committed. See CONTRIBUTING.md ("Proprietary artifacts").
set -euo pipefail

# Files that legitimately mention the patterns below (this guard and its docs).
EXCLUDES=(
  ':(exclude)scripts/check_proprietary_artifacts.sh'
  ':(exclude).github/workflows/artifact-guard.yml'
  ':(exclude)CONTRIBUTING.md'
)

status=0

# Forbidden filenames. Git matches the glob pathspecs itself, so names that Git
# quotes in its output (non-ASCII, control characters) are still caught. A Git
# failure aborts the script through set -e.
names=$(git ls-files -- ':(glob)**/*.signature.json' ':(glob)**/calibration.json' "${EXCLUDES[@]}")
if [ -n "$names" ]; then
  while IFS= read -r path; do
    echo "::error file=${path}::Proprietary artifact filename is tracked: ${path}"
    status=1
  done <<< "$names"
fi

# Forbidden content. No -I flag, so binary files (e.g. .db) are searched too.
# git grep exits 1 for "no match", which is a pass; anything above 1 is a failure.
set +e
hits=$(git grep -lE 'std_curve|lep_curve' -- . "${EXCLUDES[@]}")
rc=$?
set -e
if [ "$rc" -gt 1 ]; then
  echo "::error::git grep failed with exit ${rc}; the guard could not complete."
  exit "$rc"
fi
if [ -n "$hits" ]; then
  while IFS= read -r path; do
    echo "::error file=${path}::Tracked file contains proprietary calibration marker: ${path}"
    status=1
  done <<< "$hits"
fi

if [ "$status" -ne 0 ]; then
  echo "Proprietary artifact guard failed. Remove the files above; see CONTRIBUTING.md."
else
  echo "Proprietary artifact guard passed."
fi
exit "$status"
