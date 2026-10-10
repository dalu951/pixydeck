#!/usr/bin/env bash
# Build the .deb in a clean Ubuntu 24.04 container (same as the release CI).
# Usage: packaging/deb/docker-build.sh [output-dir]
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
mkdir -p "${1:-$ROOT/dist}"
OUT=$(cd "${1:-$ROOT/dist}" && pwd)

docker run --rm \
    -e PIP_BREAK_SYSTEM_PACKAGES=1 -e PIP_ROOT_USER_ACTION=ignore -e DEBIAN_FRONTEND=noninteractive \
    -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
    -v "$ROOT":/src:ro -v "$OUT":/out \
    ubuntu:24.04 bash -euc '
        apt-get update -qq >/dev/null
        xargs apt-get install -y -qq python3 python3-pip dpkg-dev >/dev/null < /src/packaging/deb/runtime-libs.txt
        cp -r /src /build
        /build/packaging/deb/build-deb.sh /out
        chown "$HOST_UID:$HOST_GID" /out/*.deb
    '
