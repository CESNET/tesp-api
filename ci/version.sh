#!/usr/bin/env bash
set -e
# Get project version
# Usage:
# * get-version <changelog-version-file>

CHANGELOG_FILE="$1"

changelog_version=$(grep -E '^##[ \t]+\[.+\]' "${CHANGELOG_FILE}" | \
                    awk '{print substr($2,2,length($2)-2)}' | grep -v '[Uu]nreleased' | head -1)

echo "${changelog_version}"
