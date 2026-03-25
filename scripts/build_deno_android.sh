#!/usr/bin/env bash

set -euo pipefail

# Ensure standard Unix tools win over similarly named utilities from other
# packages on macOS.
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${PATH}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_OUTPUT_DIR="${REPO_ROOT}/build/deno"
DEFAULT_JNI_LIBS_DIR="${REPO_ROOT}/app/src/main/jniLibs"
DEFAULT_SOURCE_DIR="${REPO_ROOT}/third_party/deno"
DEFAULT_ABIS="arm64-v8a,x86_64"
DEFAULT_API=24

API_LEVEL="${DEFAULT_API}"
ABIS="${DEFAULT_ABIS}"
OUTPUT_DIR="${DEFAULT_OUTPUT_DIR}"
JNI_LIBS_DIR="${DEFAULT_JNI_LIBS_DIR}"
INSTALL_JNI_LIBS=1
DENO_SOURCE_DIR=""
ENV_DENO_SOURCE_DIR="${DENO_SRC_DIR:-}"
NDK_ROOT="${ANDROID_NDK_ROOT:-${ANDROID_NDK_HOME:-}}"
ALLOW_UNSUPPORTED_HOST=0

usage() {
    cat <<EOF
Usage:
  $(basename "$0") [options] [/absolute/path/to/deno-source]

Options:
  --api <level>             Android API level to target (default: ${DEFAULT_API})
  --abis <list>             Comma-separated ABI list (default: ${DEFAULT_ABIS})
  --ndk <path>              Override Android NDK path
  --output-dir <path>       Build output root (default: ${DEFAULT_OUTPUT_DIR})
  --jni-libs-dir <path>     Native library output root (default: ${DEFAULT_JNI_LIBS_DIR})
  --no-install-jni-libs     Build only; do not copy binaries into app source tree
  --allow-unsupported-host  Continue on non-x86_64 hosts (experimental)
  --help                    Show this help text

Examples:
  $(basename "$0")
  $(basename "$0") ~/src/deno
  $(basename "$0") --api 24 --abis arm64-v8a,x86_64 ~/src/deno

Notes:
  - Source directory resolution order is:
      1. explicit positional path
      2. DENO_SRC_DIR
      3. ${DEFAULT_SOURCE_DIR} (if present)
  - Clone Deno with submodules:
      git clone --recurse-submodules https://github.com/denoland/deno.git third_party/deno
  - Official Deno/rusty_v8 Android build guidance targets x86_64 hosts.
  - This script builds the Deno CLI for each requested ABI and installs it as:
      app/src/main/jniLibs/<abi>/libdeno.so
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
        --jni-libs-dir)
            [[ $# -ge 2 ]] || { echo "error: --jni-libs-dir requires a value" >&2; exit 1; }
            JNI_LIBS_DIR="$2"
            shift 2
            ;;
        --no-install-jni-libs|--no-install-assets)
            INSTALL_JNI_LIBS=0
            shift
            ;;
        --allow-unsupported-host)
            ALLOW_UNSUPPORTED_HOST=1
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
            if [[ -n "${DENO_SOURCE_DIR}" ]]; then
                echo "error: only one Deno source directory may be provided" >&2
                usage >&2
                exit 1
            fi
            DENO_SOURCE_DIR="$1"
            shift
            ;;
    esac
done

if [[ -z "${DENO_SOURCE_DIR}" ]]; then
    DENO_SOURCE_DIR="${ENV_DENO_SOURCE_DIR}"
fi

if [[ -z "${DENO_SOURCE_DIR}" && -d "${DEFAULT_SOURCE_DIR}" && -f "${DEFAULT_SOURCE_DIR}/Cargo.toml" ]]; then
    DENO_SOURCE_DIR="${DEFAULT_SOURCE_DIR}"
fi

if [[ -z "${DENO_SOURCE_DIR}" ]]; then
    echo "error: Deno source directory not found. Pass a path, set DENO_SRC_DIR, or populate ${DEFAULT_SOURCE_DIR}." >&2
    usage >&2
    exit 1
fi

if [[ ! -d "${DENO_SOURCE_DIR}" || ! -f "${DENO_SOURCE_DIR}/Cargo.toml" ]]; then
    echo "error: ${DENO_SOURCE_DIR} does not look like a Deno source tree" >&2
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

require_command() {
    local name="$1"
    command -v "${name}" >/dev/null 2>&1 || {
        echo "error: required command not found: ${name}" >&2
        exit 1
    }
}

ensure_supported_host() {
    local host_arch
    host_arch="$(uname -m)"
    if [[ "${host_arch}" == "x86_64" || "${ALLOW_UNSUPPORTED_HOST}" == "1" ]]; then
        return
    fi

    cat >&2 <<EOF
error: official Deno/rusty_v8 Android build guidance targets x86_64 hosts.
current host: ${host_arch}

Use one of:
  - an x86_64 Linux/macOS builder
  - an x86_64 shell under Rosetta on Apple Silicon

If you still want to try this host experimentally, rerun with:
  $(basename "$0") --allow-unsupported-host ...
EOF
    exit 1
}

ensure_rust_target() {
    local rust_target="$1"
    if rustup target list --installed | grep -Fxq "${rust_target}"; then
        return
    fi

    echo "==> Installing Rust target ${rust_target}"
    rustup target add "${rust_target}"
}

update_submodules_if_possible() {
    if [[ ! -f "${DENO_SOURCE_DIR}/.gitmodules" ]]; then
        return
    fi
    if [[ ! -d "${DENO_SOURCE_DIR}/.git" && ! -f "${DENO_SOURCE_DIR}/.git" ]]; then
        echo "==> Skipping submodule update (source tree is not a git checkout)"
        return
    fi

    echo "==> Updating Deno submodules"
    git -C "${DENO_SOURCE_DIR}" submodule update --init --recursive
}

target_env_name() {
    printf '%s\n' "$1" | tr '[:lower:]-' '[:upper:]_'
}

target_cc_env_name() {
    printf '%s\n' "$1" | tr '-' '_'
}

build_one_abi() {
    local abi="$1"
    local rust_target

    case "${abi}" in
        arm64-v8a)
            rust_target="aarch64-linux-android"
            ;;
        x86_64)
            rust_target="x86_64-linux-android"
            ;;
        *)
            echo "error: unsupported ABI: ${abi}" >&2
            exit 1
            ;;
    esac

    ensure_rust_target "${rust_target}"

    local env_target_upper
    local env_target_lower
    env_target_upper="$(target_env_name "${rust_target}")"
    env_target_lower="$(target_cc_env_name "${rust_target}")"

    local cc_wrapper="${TOOLCHAIN_DIR}/bin/${rust_target}${API_LEVEL}-clang"
    local cxx_wrapper="${TOOLCHAIN_DIR}/bin/${rust_target}${API_LEVEL}-clang++"
    local ar_bin="${TOOLCHAIN_DIR}/bin/llvm-ar"
    local ranlib_bin="${TOOLCHAIN_DIR}/bin/llvm-ranlib"
    local strip_bin="${TOOLCHAIN_DIR}/bin/llvm-strip"
    local cargo_target_dir="${OUTPUT_DIR}/${abi}/cargo-target"
    local staged_bin_dir="${OUTPUT_DIR}/${abi}/bin"
    local staged_binary="${staged_bin_dir}/deno"
    local built_binary="${cargo_target_dir}/${rust_target}/release/deno"

    [[ -x "${cc_wrapper}" ]] || { echo "error: missing compiler wrapper: ${cc_wrapper}" >&2; exit 1; }
    [[ -x "${cxx_wrapper}" ]] || { echo "error: missing compiler wrapper: ${cxx_wrapper}" >&2; exit 1; }

    mkdir -p "${staged_bin_dir}"

    echo "==> Building Deno for ${abi}"
    (
        cd "${DENO_SOURCE_DIR}"

        env \
            "ANDROID_NDK_ROOT=${NDK_ROOT}" \
            "ANDROID_NDK_HOME=${NDK_ROOT}" \
            "CARGO_TARGET_DIR=${cargo_target_dir}" \
            "PYTHON=${PYTHON_BIN}" \
            "PROTOC=${PROTOC_BIN}" \
            "CLANG_BASE_PATH=${TOOLCHAIN_DIR}" \
            "NINJA=${NINJA_BIN}" \
            "CC_${env_target_lower}=${cc_wrapper}" \
            "CXX_${env_target_lower}=${cxx_wrapper}" \
            "AR_${env_target_lower}=${ar_bin}" \
            "RANLIB_${env_target_lower}=${ranlib_bin}" \
            "CARGO_TARGET_${env_target_upper}_LINKER=${cc_wrapper}" \
            "V8_FROM_SOURCE=1" \
            cargo build -vv --release --target "${rust_target}" -p deno
    )

    [[ -x "${built_binary}" ]] || {
        echo "error: expected Deno binary not found after build: ${built_binary}" >&2
        exit 1
    }

    cp -f "${built_binary}" "${staged_binary}"
    chmod 0755 "${staged_binary}"
    "${strip_bin}" "${staged_binary}" 2>/dev/null || true

    if [[ "${INSTALL_JNI_LIBS}" == "1" ]]; then
        local abi_jni_dir="${JNI_LIBS_DIR}/${abi}"
        mkdir -p "${abi_jni_dir}"
        cp -f "${staged_binary}" "${abi_jni_dir}/libdeno.so"
        chmod 0755 "${abi_jni_dir}/libdeno.so"
        echo "==> Installed ${abi_jni_dir}/libdeno.so"
    fi
}

ensure_supported_host
require_command cargo
require_command rustup
require_command git
require_command python3
require_command protoc
require_command cmake
require_command ninja

PYTHON_BIN="$(command -v python3)"
PROTOC_BIN="$(command -v protoc)"
NINJA_BIN="$(command -v ninja)"

NDK_ROOT="$(discover_ndk_root)"
TOOLCHAIN_DIR="$(detect_toolchain_dir "${NDK_ROOT}")"

echo "Deno source:   ${DENO_SOURCE_DIR}"
echo "NDK root:      ${NDK_ROOT}"
echo "Toolchain:     ${TOOLCHAIN_DIR}"
echo "API level:     ${API_LEVEL}"
echo "ABIs:          ${ABIS}"
echo "Output dir:    ${OUTPUT_DIR}"
echo "JNI libs dir:  ${JNI_LIBS_DIR}"

update_submodules_if_possible

mkdir -p "${OUTPUT_DIR}"

IFS=',' read -r -a ABI_LIST <<< "${ABIS}"
for abi in "${ABI_LIST[@]}"; do
    build_one_abi "${abi}"
done

echo "Done."
