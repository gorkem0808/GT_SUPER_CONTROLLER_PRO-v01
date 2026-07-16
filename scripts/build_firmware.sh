#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '\r\n' < "$ROOT/VERSION")"
: "${PICO_SDK_PATH:?PICO_SDK_PATH tanımlanmalıdır}"
cmake -S "$ROOT/firmware" -B "$ROOT/build/firmware" -G Ninja \
  -DPICO_SDK_PATH="$PICO_SDK_PATH" \
  -DGT_FIRMWARE_VERSION="$VERSION" \
  -DPICO_BOARD=pico \
  -DCMAKE_BUILD_TYPE=Release
cmake --build "$ROOT/build/firmware" --parallel
python3 "$ROOT/scripts/check_firmware_size.py" \
  "$ROOT/build/firmware/controller/gt_controller.bin" \
  "$ROOT/build/firmware/gun/gt_gun_p1.bin" \
  "$ROOT/build/firmware/gun/gt_gun_p2.bin"
mkdir -p "$ROOT/dist/firmware"
cp "$ROOT/build/firmware/controller/gt_controller.uf2" "$ROOT/dist/firmware/"
cp "$ROOT/build/firmware/gun/gt_gun_p1.uf2" "$ROOT/dist/firmware/"
cp "$ROOT/build/firmware/gun/gt_gun_p2.uf2" "$ROOT/dist/firmware/"
(cd "$ROOT/dist/firmware" && sha256sum ./*.uf2 > SHA256SUMS_UF2.txt)
