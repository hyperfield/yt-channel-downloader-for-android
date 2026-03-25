# Deno Android Build Notes

This note is for maintainers who want to bundle a Deno runtime into the Android
app so `yt-dlp-ejs` can use a supported JavaScript runtime.

The app expects the runtime to be packaged as:

- `app/src/main/jniLibs/arm64-v8a/libdeno.so`
- `app/src/main/jniLibs/x86_64/libdeno.so`

Those files are not committed by default. You build them locally and then
rebuild the Android app.

## Why This Exists

The Android app uses Python `yt-dlp` through Chaquopy. For YouTube, modern
`yt-dlp` behavior increasingly depends on JavaScript execution support via
`yt-dlp-ejs`.

Without a supported JavaScript runtime, the app may still appear to work, but
`yt-dlp` emits warnings like:

- `No supported JavaScript runtime could be found`

and the practical consequences can include:

- incomplete YouTube extraction
- missing formats
- lower-quality fallback downloads than expected
- more brittle behavior when YouTube changes its extraction logic

This is separate from FFmpeg:

- FFmpeg is needed for adaptive video/audio merging
- Deno is needed so `yt-dlp-ejs` has a supported JavaScript runtime

So the motivation for bundling Deno is not cosmetic. It is part of making the
Android app behave more like the desktop ancestor for YouTube extraction,
format discovery, and quality selection.

## Recommended Build Host

The safest host is:

- `x86_64` Linux

Why:

- upstream `rusty_v8` Android build guidance explicitly documents Android
  cross-builds from an `x86_64` host
- Deno depends on V8 via `rusty_v8`

You can likely make this work on Intel macOS too, but `x86_64` Linux is the
cleanest path.

## Ubuntu x86_64 Setup

These commands assume Ubuntu 24.04 or a similar recent Debian/Ubuntu system.

### 1. Install OS packages

```bash
sudo apt update
sudo apt install -y \
  git \
  curl \
  unzip \
  zip \
  openjdk-17-jdk \
  python3 \
  python3-venv \
  cmake \
  ninja-build \
  protobuf-compiler \
  libglib2.0-dev \
  libclang-19-dev
```

### 2. Install Rust

```bash
curl https://sh.rustup.rs -sSf | sh
source "$HOME/.cargo/env"
rustc -V
cargo -V
```

### 3. Install Android Studio or command-line SDK tools

Android Studio is available for Linux, but it is optional for the Deno build
itself. If you only want to build `libdeno.so`, the SDK + NDK are enough.

Official Android Studio install docs:

- https://developer.android.com/studio/install

If you use Android Studio, install:

- Android SDK
- Android SDK Platform-Tools
- Android SDK Build-Tools
- Android NDK (Side by side)

If you prefer CLI tools only, install the Android command-line tools and then:

```bash
export ANDROID_SDK_ROOT="$HOME/Android/Sdk"
yes | "$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager" --licenses
"$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager" \
  "platform-tools" \
  "platforms;android-36" \
  "build-tools;36.0.0" \
  "ndk;29.0.14206865"
```

Adjust versions if you intentionally use a different SDK/NDK revision.

### 4. Export useful environment variables

```bash
export ANDROID_SDK_ROOT="$HOME/Android/Sdk"
export ANDROID_NDK_ROOT="$ANDROID_SDK_ROOT/ndk/29.0.14206865"
export LIBCLANG_PATH="/usr/lib/llvm-19/lib"
source "$HOME/.cargo/env"
```

## Clone the Repositories

### 1. Clone this app

```bash
git clone <your-android-repo-url> yt-channel-downloader-for-android
cd yt-channel-downloader-for-android
```

### 2. Clone Deno with submodules

Recommended in-repo checkout:

```bash
git clone --recurse-submodules https://github.com/denoland/deno.git third_party/deno
cd third_party/deno
git checkout <tag-or-commit>
git submodule update --init --recursive
cd ../..
```

Record the selected tag and commit in:

- `docs/deno-source.md`

## Build the Android Deno Runtime

The repo includes:

- `scripts/build_deno_android.sh`

Default usage, if `third_party/deno` exists:

```bash
./scripts/build_deno_android.sh
```

Or with an explicit source path:

```bash
./scripts/build_deno_android.sh ~/src/deno
```

The script will:

- resolve the Android SDK/NDK
- add missing Rust Android targets if needed
- build Deno for `arm64-v8a` and `x86_64`
- copy the result into:
  - `app/src/main/jniLibs/arm64-v8a/libdeno.so`
  - `app/src/main/jniLibs/x86_64/libdeno.so`

Useful variants:

```bash
./scripts/build_deno_android.sh --api 24 --abis arm64-v8a,x86_64
./scripts/build_deno_android.sh --no-install-jni-libs
./scripts/build_deno_android.sh --ndk "$ANDROID_NDK_ROOT"
```

## Rebuild the Android App

After `libdeno.so` is in place:

```bash
./gradlew :app:assembleDebug
```

Then reinstall/run the app on emulator or device.

## What Success Looks Like

On the main app screen, the runtime status line should change from:

- `Bundled JS runtime (deno): not detected.`

to something like:

- `Bundled JS runtime (deno): detected at .../libdeno.so`

And the previous yt-dlp warning about no supported JavaScript runtime should
stop appearing.

## Useful Validation Commands

Check that the binaries exist:

```bash
find app/src/main/jniLibs -name 'libdeno.so' -ls
```

Check that the Android build still works:

```bash
./gradlew :app:assembleDebug
```

If you are running on a device/emulator and want to inspect app logs:

```bash
ADB="$HOME/Android/Sdk/platform-tools/adb"
PID="$($ADB shell pidof -s com.ytchanneldownloader.android | tr -d '\r')"
$ADB logcat --pid="$PID" | grep -E 'YTCD-|QuietYDLLogger|deno|js runtime'
```

## Important Notes

### 1. This is a maintainer workflow

End users of the APK do not need the Deno source tree. Only maintainers who
rebuild the bundled runtime need it.

### 2. Deno source checkout is intentionally local-only

The repo ignores:

- `third_party/deno/`

That keeps the checkout out of version control while still allowing a stable
local path for builds.

### 3. The runtime is packaged as `libdeno.so` on purpose

The app looks in `applicationInfo.nativeLibraryDir`, where Android extracts
native libraries. This is the same packaging strategy already used for FFmpeg.

### 4. Deno on Apple Silicon

The helper script defaults to rejecting non-`x86_64` hosts because upstream
Android build guidance is `x86_64`-oriented. There is an escape hatch:

```bash
./scripts/build_deno_android.sh --allow-unsupported-host
```

but that should be treated as experimental.

### 5. Upstream references

- Deno source build docs:
  - https://github.com/denoland/deno/blob/main/.github/CONTRIBUTING.md
- Deno README:
  - https://github.com/denoland/deno/blob/main/README.md
- `rusty_v8` Android build guidance:
  - https://github.com/denoland/rusty_v8/blob/main/README.md
