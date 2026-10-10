#!/usr/bin/env bash
# Build pixydeck_<version>_amd64.deb for Ubuntu/Pop!_OS 24.04 (Python 3.12).
#
# The distribution does not ship current PySide6/OpenCV/ONNX Runtime, so the
# Python dependencies are bundled into /opt/pixydeck/lib. Qt modules
# PixyDeck never loads are pruned to keep the package small; a resolver
# check and an import test make sure nothing needed was removed.
#
# Usage: packaging/deb/build-deb.sh [output-dir]
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUT=${1:-"$ROOT/dist"}
PYTHON=${PYTHON:-python3}
VERSION=$("$PYTHON" -c 'import tomllib,sys; print(tomllib.load(open(sys.argv[1],"rb"))["project"]["version"])' "$ROOT/pyproject.toml")
PYVER=$("$PYTHON" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
PYNEXT=$("$PYTHON" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1] + 1}")')
ARCH=amd64
# Shared libraries the bundled Qt/OpenCV wheels expect from the system
# (Ubuntu 24.04 package names). docker-build.sh installs the same list.
RUNTIME_LIBS=$(tr '\n' ' ' < "$ROOT/packaging/deb/runtime-libs.txt" | sed 's/ *$//; s/ /, /g')
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
PKG="$WORK/pixydeck_${VERSION}_${ARCH}"
LIB="$PKG/opt/pixydeck/lib"

echo "==> Bundling Python packages for Python $PYVER"
"$PYTHON" -m pip install --quiet --no-compile --no-warn-script-location --target "$LIB" "${ROOT}[ai]"
rm -rf "${LIB:?}/bin"

echo "==> Pruning unused Qt modules"
QT="$LIB/PySide6"
unused='3D|Bluetooth|Charts|DataVisualization|Graphs|HttpServer|Location|Nfc|Pdf|Positioning|Quick3D|RemoteObjects|Scxml|SerialBus|SerialPort|Sensors|SpatialAudio|StateMachine|TextToSpeech|VirtualKeyboard|WebChannel|WebSockets|Designer|Help|UiTools|QuickWidgets|QuickControls|QuickDialogs|QuickLayouts|QuickTest|QuickParticles|QuickShapes|QuickTimeline|QuickEffects|QuickVectorImage|MultimediaQuick|ShaderTools|Sql|Test'
find "$QT" -maxdepth 1 -regextype egrep -regex ".*/Qt($unused)[A-Za-z]*\.(abi3\.so|pyi)" -delete
find "$QT/Qt/lib" -regextype egrep -regex ".*/libQt6($unused)[A-Za-z]*\.so.*" -delete
for dir in Qt/qml Qt/translations Qt/libexec Qt/metatypes examples glue include typesystems scripts; do
    rm -rf "${QT:?}/$dir"
done
for tool in designer lupdate lrelease linguist assistant qmllint qmlformat qmlls balsam balsamui svgtoqml uic rcc; do
    rm -f "${QT:?}/$tool"
done
for plugin in designer qmltooling qmllint sqldrivers sceneparsers geometryloaders renderers renderplugins \
              sensors position geoservices texttospeech webview virtualkeyboard canbus assetimporters help qmlls; do
    rm -rf "${QT:?}/Qt/plugins/$plugin"
done

# Note: Qt's FFmpeg multimedia plugin links Qml/Quick, so those libraries stay.
# Plugins/libraries that only served the removed modules now have unresolved
# dependencies: drop them too, repeatedly, until everything left resolves.
unresolved() {
    find "$QT" -name '*.so*' -type f -print0 | while IFS= read -r -d '' lib; do
        if ldd "$lib" 2>/dev/null | grep -q 'libQt6.*not found'; then
            echo "$lib"
        fi
    done
}
while true; do
    mapfile -t broken < <(unresolved)
    ((${#broken[@]})) || break
    rm -f "${broken[@]}"
done

echo "==> Checking that everything PixyDeck needs is still there"
required=(
    Qt/lib/libQt6Core.so.6 Qt/lib/libQt6Gui.so.6 Qt/lib/libQt6Widgets.so.6
    Qt/lib/libQt6Multimedia.so.6 Qt/lib/libQt6MultimediaWidgets.so.6 Qt/lib/libQt6Network.so.6
    Qt/lib/libQt6Svg.so.6 Qt/lib/libQt6XcbQpa.so.6 Qt/lib/libQt6WaylandClient.so.6
    Qt/plugins/platforms/libqxcb.so Qt/plugins/platforms/libqwayland.so
    Qt/plugins/platforms/libqoffscreen.so Qt/plugins/multimedia/libffmpegmediaplugin.so
    Qt/plugins/imageformats/libqjpeg.so Qt/plugins/imageformats/libqsvg.so
    Qt/plugins/iconengines/libqsvgicon.so
    QtMultimedia.abi3.so QtMultimediaWidgets.abi3.so QtWidgets.abi3.so QtGui.abi3.so QtCore.abi3.so
)
for file in "${required[@]}"; do
    if [[ ! -e "$QT/$file" ]]; then
        echo "Pruning removed a required Qt file: $file" >&2
        exit 1
    fi
done
PYTHONPATH="$LIB" QT_QPA_PLATFORM=offscreen "$PYTHON" -c \
    'import PySide6.QtMultimedia, PySide6.QtMultimediaWidgets, PySide6.QtWidgets, cv2, onnxruntime, pixydeck.gui'

echo "==> Installing application files"
install -d "$PKG/usr/bin"
printf '#!/bin/sh\nPYTHONPATH=/opt/pixydeck/lib exec /usr/bin/python3 -P -m pixydeck "$@"\n' > "$PKG/usr/bin/pixydeck"
printf '#!/bin/sh\nPYTHONPATH=/opt/pixydeck/lib exec /usr/bin/python3 -P -m pixydeck.backend "$@"\n' > "$PKG/usr/bin/pixydeck-cli"
chmod 755 "$PKG/usr/bin/pixydeck" "$PKG/usr/bin/pixydeck-cli"
install -Dm755 "$ROOT/deploy/virtual-camera-device" "$PKG/usr/lib/pixydeck/virtual-camera-device"
install -Dm755 "$ROOT/deploy/pixydeck-setup" "$PKG/usr/lib/pixydeck/pixydeck-setup"
install -Dm644 "$ROOT/deploy/70-pixydeck.rules" "$PKG/usr/lib/udev/rules.d/70-pixydeck.rules"
install -d "$PKG/usr/lib/systemd/system" "$PKG/usr/share/polkit-1/actions" "$PKG/usr/share/applications"
sed 's#@LIBDIR@#/usr/lib/pixydeck#g' "$ROOT/deploy/pixydeck-virtual-camera.service.in" \
    > "$PKG/usr/lib/systemd/system/pixydeck-virtual-camera.service"
sed 's#@HELPER@#/usr/lib/pixydeck/pixydeck-setup#g' "$ROOT/deploy/io.github.dalu951.pixydeck.policy.in" \
    > "$PKG/usr/share/polkit-1/actions/io.github.dalu951.pixydeck.policy"
sed 's#@EXEC@#pixydeck#g' "$ROOT/deploy/pixydeck.desktop.in" > "$PKG/usr/share/applications/pixydeck.desktop"
install -Dm644 "$ROOT/assets/pixydeck.svg" "$PKG/usr/share/icons/hicolor/scalable/apps/pixydeck.svg"
install -Dm644 "$ROOT/LICENSE" "$PKG/usr/share/doc/pixydeck/copyright"
gzip -9cn "$ROOT/CHANGELOG.md" > "$PKG/usr/share/doc/pixydeck/changelog.gz"
chmod 644 "$PKG/usr/share/doc/pixydeck/changelog.gz"

echo "==> Writing package metadata"
# Package modes must not depend on the builder's umask (mktemp -d is 0700).
chmod 755 "$PKG"
chmod -R u+rwX,go+rX,go-w "$PKG"
install -d "$PKG/DEBIAN"
SIZE=$(du -sk --exclude=DEBIAN "$PKG" | cut -f1)
cat > "$PKG/DEBIAN/control" <<CONTROL
Package: pixydeck
Version: $VERSION
Architecture: $ARCH
Maintainer: dalu951 <https://github.com/dalu951/pixydeck>
Installed-Size: $SIZE
Depends: python3 (>= $PYVER), python3 (<< $PYNEXT), v4l-utils, ffmpeg, v4l2loopback-utils, v4l2loopback-dkms | v4l2loopback-modules, pkexec | policykit-1, ${RUNTIME_LIBS}
Section: video
Priority: optional
Homepage: https://github.com/dalu951/pixydeck
Description: Linux control suite for the EMEET PIXY webcam (unofficial)
 EMEET PixyDeck controls pan, tilt and zoom, the camera's on-board AI
 (tracking, privacy, gestures, click-to-focus) and adds auto-framing,
 AI background blur/replacement, green screen, stabilization and a
 virtual camera for Meet, Zoom, Teams and OBS.
 .
 Not affiliated with or endorsed by EMEET.
CONTROL
for script in postinst prerm postrm; do
    install -m755 "$ROOT/packaging/deb/$script" "$PKG/DEBIAN/$script"
done

mkdir -p "$OUT"
dpkg-deb --root-owner-group -Zxz --build "$PKG" "$OUT/pixydeck_${VERSION}_${ARCH}.deb"
ls -lh "$OUT/pixydeck_${VERSION}_${ARCH}.deb"
