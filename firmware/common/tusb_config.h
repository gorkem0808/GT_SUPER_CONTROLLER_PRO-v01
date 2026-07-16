name: Build UF2 and Windows App

on:
  push:
    branches: [main]
    tags: ["v*"]
  pull_request:
    branches: [main]
  workflow_dispatch:
    inputs:
      version:
        description: "Artifact sürümü; boşsa VERSION + commit kullanılır"
        required: false
        type: string

concurrency:
  group: gt-build-${{ github.ref }}
  cancel-in-progress: ${{ github.ref_type != 'tag' }}

permissions:
  contents: read

env:
  PICO_SDK_VERSION: "2.3.0"
  PICO_SDK_COMMIT: "98a542c"

jobs:
  metadata:
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    outputs:
      version: ${{ steps.version.outputs.version }}
      file_version: ${{ steps.version.outputs.file_version }}
    steps:
      - uses: actions/checkout@v7.0.0

      - id: version
        name: Sürümü belirle ve doğrula
        shell: bash
        env:
          INPUT_VERSION: ${{ inputs.version }}
        run: |
          set -euo pipefail
          base_version="$(tr -d '\r\n' < VERSION)"
          if [[ "${GITHUB_REF_TYPE}" == "tag" ]]; then
            version="${GITHUB_REF_NAME#v}"
          elif [[ -n "${INPUT_VERSION:-}" ]]; then
            version="${INPUT_VERSION}"
          else
            version="${base_version}+${GITHUB_SHA::7}"
          fi
          python3 scripts/set_version.py "$version"
          python3 scripts/set_version.py --check
          file_version="${version//+/_}"
          file_version="${file_version//\//-}"
          echo "version=$version" >> "$GITHUB_OUTPUT"
          echo "file_version=$file_version" >> "$GITHUB_OUTPUT"

  firmware:
    needs: metadata
    runs-on: ubuntu-24.04
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v7.0.0

      - name: Sürüm dosyalarını ayarla
        run: python3 scripts/set_version.py "${{ needs.metadata.outputs.version }}"

      - name: Arm derleyici ve yapı araçlarını kur
        run: |
          sudo apt-get update
          sudo apt-get install -y --no-install-recommends \
            cmake ninja-build gcc-arm-none-eabi libnewlib-arm-none-eabi \
            libstdc++-arm-none-eabi-newlib

      - name: Pico SDK indir ve sürüm kimliğini doğrula
        shell: bash
        run: |
          set -euo pipefail
          git clone --branch "$PICO_SDK_VERSION" --depth 1 \
            --recurse-submodules --shallow-submodules \
            https://github.com/raspberrypi/pico-sdk.git "$RUNNER_TEMP/pico-sdk"
          actual_commit="$(git -C "$RUNNER_TEMP/pico-sdk" rev-parse --short=7 HEAD)"
          if [[ "$actual_commit" != "$PICO_SDK_COMMIT" ]]; then
            echo "Beklenen Pico SDK commit'i $PICO_SDK_COMMIT, gelen $actual_commit" >&2
            exit 1
          fi
          git -C "$RUNNER_TEMP/pico-sdk" submodule status --recursive

      - name: Flash şema geçişi host testini çalıştır
        shell: bash
        run: |
          set -euo pipefail
          cc -std=c11 -Wall -Wextra -Werror -Wformat=2 \
            -Ifirmware/host_tests/stubs -Ifirmware/common \
            firmware/common/crc32.c \
            firmware/common/flash_store.c \
            firmware/host_tests/flash_store_test.c \
            -o "$RUNNER_TEMP/flash_store_test"
          "$RUNNER_TEMP/flash_store_test"

      - name: Üç UF2'yi derle
        shell: bash
        run: |
          set -euo pipefail
          cmake -S firmware -B build/firmware -G Ninja \
            -DPICO_SDK_PATH="$RUNNER_TEMP/pico-sdk" \
            -DGT_FIRMWARE_VERSION="${{ needs.metadata.outputs.version }}" \
            -DPICO_BOARD=pico \
            -DCMAKE_BUILD_TYPE=Release
          cmake --build build/firmware --parallel
          arm-none-eabi-size \
            build/firmware/controller/gt_controller.elf \
            build/firmware/gun/gt_gun_p1.elf \
            build/firmware/gun/gt_gun_p2.elf
          python3 scripts/check_firmware_size.py \
            build/firmware/controller/gt_controller.bin \
            build/firmware/gun/gt_gun_p1.bin \
            build/firmware/gun/gt_gun_p2.bin

      - name: Firmware artifact hazırla
        shell: bash
        run: |
          set -euo pipefail
          mkdir -p dist/firmware
          cp build/firmware/controller/gt_controller.uf2 dist/firmware/
          cp build/firmware/gun/gt_gun_p1.uf2 dist/firmware/
          cp build/firmware/gun/gt_gun_p2.uf2 dist/firmware/
          (cd dist/firmware && sha256sum ./*.uf2 > SHA256SUMS_UF2.txt)

      - uses: actions/upload-artifact@v7.0.1
        with:
          name: GT_SUPER_CONTROLLER_UF2_${{ needs.metadata.outputs.file_version }}
          path: dist/firmware/*
          if-no-files-found: error
          retention-days: 30

  windows:
    needs: metadata
    runs-on: windows-2025
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v7.0.0

      - uses: actions/setup-python@v6.3.0
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: |
            desktop/requirements.txt
            desktop/requirements-dev.txt

      - name: Sürüm dosyalarını ayarla
        run: python scripts/set_version.py "${{ needs.metadata.outputs.version }}"

      - name: Bağımlılıkları kur
        working-directory: desktop
        run: |
          python -m pip install -r requirements-dev.txt

      - name: Kaynakları derleme denetiminden geçir
        working-directory: desktop
        run: python -m compileall -q gt_super_controller tests

      - name: Testleri çalıştır
        working-directory: desktop
        run: python -m pytest

      - name: Windows EXE üret
        working-directory: desktop
        run: python -m PyInstaller --noconfirm --clean GT_SUPER_CONTROLLER.spec

      - name: Windows artifact hazırla
        shell: pwsh
        run: |
          $Output = Join-Path $env:GITHUB_WORKSPACE "dist\windows"
          New-Item -ItemType Directory -Force -Path $Output | Out-Null
          $Name = "GT_SUPER_CONTROLLER_${{ needs.metadata.outputs.file_version }}.exe"
          $Target = Join-Path $Output $Name
          Copy-Item "desktop\dist\GT_SUPER_CONTROLLER.exe" $Target -Force
          $Hash = Get-FileHash $Target -Algorithm SHA256
          "{0} *{1}" -f $Hash.Hash.ToLowerInvariant(), $Name |
            Set-Content (Join-Path $Output "SHA256SUMS_WINDOWS.txt") -Encoding ascii

      - uses: actions/upload-artifact@v7.0.1
        with:
          name: GT_SUPER_CONTROLLER_WINDOWS_${{ needs.metadata.outputs.file_version }}
          path: dist/windows/*
          if-no-files-found: error
          retention-days: 30

  release:
    if: github.ref_type == 'tag'
    needs: [metadata, firmware, windows]
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v7.0.0

      - uses: actions/download-artifact@v8.0.1
        with:
          pattern: GT_SUPER_CONTROLLER_*
          path: release-assets
          merge-multiple: true

      - name: GitHub Release oluştur veya güncelle
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
          VERSION: ${{ needs.metadata.outputs.version }}
        run: |
          set -euo pipefail
          mapfile -d '' assets < <(find release-assets -maxdepth 1 -type f -print0 | sort -z)
          if [[ ${#assets[@]} -eq 0 ]]; then
            echo "Release dosyası bulunamadı" >&2
            exit 1
          fi
          if gh release view "$GITHUB_REF_NAME" >/dev/null 2>&1; then
            gh release upload "$GITHUB_REF_NAME" "${assets[@]}" --clobber
          else
            gh release create "$GITHUB_REF_NAME" "${assets[@]}" \
              --verify-tag \
              --title "GT SUPER CONTROLLER $VERSION" \
              --generate-notes
          fi
