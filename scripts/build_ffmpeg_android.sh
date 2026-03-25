#!/usr/bin/env bash

set -euo pipefail

# Ensure standard Unix tool binaries win over similarly named utilities
# (for example the HTTP "head" command from libwww-perl on some macOS setups).
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${PATH}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_OUTPUT_DIR="${REPO_ROOT}/build/ffmpeg"
DEFAULT_JNI_LIBS_DIR="${REPO_ROOT}/app/src/main/jniLibs"
DEFAULT_SOURCE_DIR="${REPO_ROOT}/third_party/ffmpeg"
DEFAULT_ABIS="arm64-v8a,x86_64"
DEFAULT_API=21

API_LEVEL="${DEFAULT_API}"
ABIS="${DEFAULT_ABIS}"
OUTPUT_DIR="${DEFAULT_OUTPUT_DIR}"
JNI_LIBS_DIR="${DEFAULT_JNI_LIBS_DIR}"
INSTALL_ASSETS=1
FFMPEG_SOURCE_DIR=""
ENV_FFMPEG_SOURCE_DIR="${FFMPEG_SRC_DIR:-}"
NDK_ROOT="${ANDROID_NDK_ROOT:-${ANDROID_NDK_HOME:-}}"

usage() {
    cat <<EOF
Usage:
  $(basename "$0") [options] [/absolute/path/to/ffmpeg-source]

Options:
  --api <level>           Android API level to target (default: ${DEFAULT_API})
  --abis <list>           Comma-separated ABI list (default: ${DEFAULT_ABIS})
  --ndk <path>            Override Android NDK path
  --output-dir <path>     Build/install prefix root (default: ${DEFAULT_OUTPUT_DIR})
  --jni-libs-dir <path>   Native library output root (default: ${DEFAULT_JNI_LIBS_DIR})
  --asset-dir <path>      Deprecated alias for --jni-libs-dir
  --no-install-assets     Build only; do not copy binaries into app source tree
  --help                  Show this help text

Examples:
  $(basename "$0")
  $(basename "$0") ~/src/ffmpeg
  $(basename "$0") --api 24 --abis arm64-v8a,x86_64 ~/src/ffmpeg

Notes:
  - This script builds LGPL-safe executables by not enabling GPL or nonfree options.
  - Source directory resolution order is:
      1. explicit positional path
      2. FFMPEG_SRC_DIR
      3. ${DEFAULT_SOURCE_DIR} (if present)
  - It produces ffmpeg/ffprobe binaries for each requested ABI.
  - If installation is enabled, it copies binaries to:
      app/src/main/jniLibs/<abi>/libffmpeg.so
      app/src/main/jniLibs/<abi>/libffprobe.so
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --api)
            [[ $# -ge 2 ]] || { echo "error: --api requires a value" >&2; exit 1; }
            API_LEVEL="$2"
            shift 2
            ;;
        --abis)
            [[ $# -ge 2 ]] || { echo "error: --abis requires a value" >&2; exit 1; }
            ABIS="$2"
            shift 2
            ;;
        --ndk)
            [[ $# -ge 2 ]] || { echo "error: --ndk requires a value" >&2; exit 1; }
            NDK_ROOT="$2"
            shift 2
            ;;
        --output-dir)
            [[ $# -ge 2 ]] || { echo "error: --output-dir requires a value" >&2; exit 1; }
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --jni-libs-dir|--asset-dir)
            [[ $# -ge 2 ]] || { echo "error: $1 requires a value" >&2; exit 1; }
            JNI_LIBS_DIR="$2"
            shift 2
            ;;
        --no-install-assets)
            INSTALL_ASSETS=0
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        -*)
            echo "error: unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
        *)
            if [[ -n "${FFMPEG_SOURCE_DIR}" ]]; then
                echo "error: only one FFmpeg source directory may be provided" >&2
                usage >&2
                exit 1
            fi
            FFMPEG_SOURCE_DIR="$1"
            shift
            ;;
    esac
done

if [[ -z "${FFMPEG_SOURCE_DIR}" ]]; then
    FFMPEG_SOURCE_DIR="${ENV_FFMPEG_SOURCE_DIR}"
fi

if [[ -z "${FFMPEG_SOURCE_DIR}" && -d "${DEFAULT_SOURCE_DIR}" && -f "${DEFAULT_SOURCE_DIR}/configure" ]]; then
    FFMPEG_SOURCE_DIR="${DEFAULT_SOURCE_DIR}"
fi

if [[ -z "${FFMPEG_SOURCE_DIR}" ]]; then
    echo "error: FFmpeg source directory not found. Pass a path, set FFMPEG_SRC_DIR, or populate ${DEFAULT_SOURCE_DIR}." >&2
    usage >&2
    exit 1
fi

if [[ ! -d "${FFMPEG_SOURCE_DIR}" || ! -f "${FFMPEG_SOURCE_DIR}/configure" ]]; then
    echo "error: ${FFMPEG_SOURCE_DIR} does not look like an FFmpeg source tree" >&2
    exit 1
fi

resolve_sdk_root() {
    if [[ -n "${ANDROID_SDK_ROOT:-}" ]]; then
        printf '%s\n' "${ANDROID_SDK_ROOT}"
        return
    fi

    if [[ -n "${ANDROID_HOME:-}" ]]; then
        printf '%s\n' "${ANDROID_HOME}"
        return
    fi

    if [[ -f "${REPO_ROOT}/local.properties" ]]; then
        local sdk_dir
        sdk_dir="$(sed -n 's/^sdk.dir=//p' "${REPO_ROOT}/local.properties" | sed -n '1p')"
        if [[ -n "${sdk_dir}" ]]; then
            printf '%s\n' "${sdk_dir}"
            return
        fi
    fi

    if [[ -d "${HOME}/Library/Android/sdk" ]]; then
        printf '%s\n' "${HOME}/Library/Android/sdk"
        return
    fi

    return 1
}

discover_ndk_root() {
    if [[ -n "${NDK_ROOT}" ]]; then
        printf '%s\n' "${NDK_ROOT}"
        return
    fi

    local sdk_root
    sdk_root="$(resolve_sdk_root)" || {
        echo "error: could not determine Android SDK root; set ANDROID_SDK_ROOT or use --ndk" >&2
        exit 1
    }

    local ndk_parent="${sdk_root}/ndk"
    [[ -d "${ndk_parent}" ]] || {
        echo "error: Android NDK not found under ${ndk_parent}; install it or use --ndk" >&2
        exit 1
    }

    local latest_ndk
    latest_ndk="$(find "${ndk_parent}" -mindepth 1 -maxdepth 1 -type d | sort | sed -n '$p')"
    [[ -n "${latest_ndk}" ]] || {
        echo "error: no Android NDK versions found under ${ndk_parent}" >&2
        exit 1
    }
    printf '%s\n' "${latest_ndk}"
}

detect_toolchain_dir() {
    local ndk_root="$1"
    local prebuilt_root="${ndk_root}/toolchains/llvm/prebuilt"
    [[ -d "${prebuilt_root}" ]] || {
        echo "error: NDK toolchain directory not found: ${prebuilt_root}" >&2
        exit 1
    }

    local host_dir
    host_dir="$(find "${prebuilt_root}" -mindepth 1 -maxdepth 1 -type d | sort | sed -n '1p')"
    [[ -n "${host_dir}" ]] || {
        echo "error: no NDK host toolchains found under ${prebuilt_root}" >&2
        exit 1
    }
    printf '%s\n' "${host_dir}"
}

cpu_count() {
    local count
    count="$(getconf _NPROCESSORS_ONLN 2>/dev/null || true)"
    if [[ -z "${count}" ]]; then
        count="$(sysctl -n hw.ncpu 2>/dev/null || true)"
    fi
    if [[ -z "${count}" ]]; then
        count=4
    fi
    printf '%s\n' "${count}"
}

build_one_abi() {
    local abi="$1"
    local arch
    local cpu
    local triple

    case "${abi}" in
        arm64-v8a)
            arch="aarch64"
            cpu="armv8-a"
            triple="aarch64-linux-android"
            ;;
        x86_64)
            arch="x86_64"
            cpu=""
            triple="x86_64-linux-android"
            ;;
        armeabi-v7a)
            arch="arm"
            cpu="armv7-a"
            triple="armv7a-linux-androideabi"
            ;;
        *)
            echo "error: unsupported ABI: ${abi}" >&2
            exit 1
            ;;
    esac

    local prefix_dir="${OUTPUT_DIR}/${abi}"
    local bin_dir="${prefix_dir}/bin"
    local cc="${TOOLCHAIN_DIR}/bin/clang --target=${triple}${API_LEVEL}"
    local cxx="${TOOLCHAIN_DIR}/bin/clang++ --target=${triple}${API_LEVEL}"
    local false_bin
    false_bin="$(command -v false)"

    mkdir -p "${prefix_dir}"

    echo "==> Building FFmpeg for ${abi}"
    (
        cd "${FFMPEG_SOURCE_DIR}"
        make distclean >/dev/null 2>&1 || true

        local configure_args=(
            "--prefix=${prefix_dir}"
            "--target-os=android"
            "--arch=${arch}"
            "--enable-cross-compile"
            "--cc=${cc}"
            "--cxx=${cxx}"
            "--ar=${TOOLCHAIN_DIR}/bin/llvm-ar"
            "--nm=${TOOLCHAIN_DIR}/bin/llvm-nm"
            "--ranlib=${TOOLCHAIN_DIR}/bin/llvm-ranlib"
            "--strip=${TOOLCHAIN_DIR}/bin/llvm-strip"
            "--disable-shared"
            "--enable-static"
            "--disable-doc"
            "--disable-debug"
            "--pkg-config=${false_bin}"
        )
        if [[ -n "${cpu}" ]]; then
            configure_args+=("--cpu=${cpu}")
        fi

        ./configure "${configure_args[@]}"
        make -j"$(cpu_count)" ffmpeg ffprobe
        make install
    )

    "${TOOLCHAIN_DIR}/bin/llvm-strip" "${bin_dir}/ffmpeg" "${bin_dir}/ffprobe"

    if [[ ${INSTALL_ASSETS} -eq 1 ]]; then
        local jni_target="${JNI_LIBS_DIR}/${abi}"
        mkdir -p "${jni_target}"
        cp -f "${bin_dir}/ffmpeg" "${jni_target}/libffmpeg.so"
        cp -f "${bin_dir}/ffprobe" "${jni_target}/libffprobe.so"
        echo "    Installed native binaries to ${jni_target}"
    fi
}

NDK_ROOT="$(discover_ndk_root)"
TOOLCHAIN_DIR="$(detect_toolchain_dir "${NDK_ROOT}")"

if [[ ! -x "${TOOLCHAIN_DIR}/bin/clang" ]]; then
    echo "error: clang not found under ${TOOLCHAIN_DIR}/bin" >&2
    exit 1
fi

mkdir -p "${OUTPUT_DIR}"
if [[ ${INSTALL_ASSETS} -eq 1 ]]; then
    mkdir -p "${JNI_LIBS_DIR}"
fi

echo "FFmpeg source: ${FFMPEG_SOURCE_DIR}"
echo "NDK root:      ${NDK_ROOT}"
echo "Toolchain:     ${TOOLCHAIN_DIR}"
echo "API level:     ${API_LEVEL}"
echo "ABIs:          ${ABIS}"
echo "Output dir:    ${OUTPUT_DIR}"
if [[ ${INSTALL_ASSETS} -eq 1 ]]; then
    echo "JNI libs dir:  ${JNI_LIBS_DIR}"
fi

IFS=',' read -r -a ABI_LIST <<< "${ABIS}"
for abi in "${ABI_LIST[@]}"; do
    build_one_abi "${abi}"
done

echo "Done."
