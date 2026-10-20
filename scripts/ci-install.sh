#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT
#
# Install a hash-pinned requirement set, then this package on top.
#
#   scripts/ci-install.sh requirements/ci.txt
#
# Every dependency comes from the hash-pinned file (pip --require-hashes),
# and both editable installs below use --no-deps, so nothing in CI resolves
# an unpinned package (OpenSSF Scorecard Pinned-Dependencies).
#
# A coordinated change can rely on a matching branch of the core pain001
# library: when REF (the PR head or pushed branch, passed through the
# environment rather than interpolated) is main, feat/* or fix/* and the
# core repository has that branch, its checkout replaces the pinned core
# release. Any other ref keeps the pinned PyPI release.
set -euo pipefail

requirements="${1:?usage: scripts/ci-install.sh <requirements.txt>}"
core_repo="https://github.com/sebastienrousseau/pain001"
core_dir="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/pain001-core"
ref="${REF:-}"

pip install --require-hashes -r "$requirements"

if [[ "$ref" == main || "$ref" == feat/* || "$ref" == fix/* ]] &&
  git ls-remote --exit-code --heads "$core_repo" "$ref" >/dev/null 2>&1; then
  echo "Using pain001 from core branch $ref"
  rm -rf "$core_dir"
  git clone --quiet --depth 1 --branch "$ref" "$core_repo" "$core_dir"
  pip install --no-deps -e "$core_dir"
fi

pip install --no-deps -e .
pip check
