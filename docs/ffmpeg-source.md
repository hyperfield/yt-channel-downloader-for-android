# FFmpeg Source Provenance

This project can optionally bundle Android `ffmpeg` and `ffprobe` executables
for adaptive stream merging. Those binaries are built from upstream FFmpeg
source and then copied into the Android native library source set as:

- `app/src/main/jniLibs/<abi>/libffmpeg.so`
- `app/src/main/jniLibs/<abi>/libffprobe.so`

## Recommended Maintainer Workflow

Use one of these source layouts:

1. External checkout outside this repo, for example `~/src/ffmpeg`
2. Plain git checkout at `third_party/ffmpeg` inside this repo (not as a submodule)

The build script resolves the source directory in this order:

1. explicit positional path passed to `scripts/build_ffmpeg_android.sh`
2. `FFMPEG_SRC_DIR`
3. `third_party/ffmpeg` if it exists and looks like an FFmpeg source tree

This means you can run either:

```bash
./scripts/build_ffmpeg_android.sh ~/src/ffmpeg
```

or, if `third_party/ffmpeg` exists:

```bash
./scripts/build_ffmpeg_android.sh
```

## Current Project Choice

The current recommended workflow for this repo is a normal git checkout at
`third_party/ffmpeg`, without using a submodule:

```bash
git clone https://git.ffmpeg.org/ffmpeg.git third_party/ffmpeg
cd third_party/ffmpeg
git checkout <tag-or-commit>
cd ../..
```

This keeps the FFmpeg source tree local to the maintainer checkout without
adding submodule management to the app repo.

## Recorded Source For This Repo

When you choose a tag or commit, record it here before shipping updated
binaries:

- Upstream URL: `https://git.ffmpeg.org/ffmpeg.git`
- Local source path: `third_party/ffmpeg` (or external path if used instead)
- Selected tag: `n8.0.1 (894da5ca7d742e4429ffb2af534fcda0103ef593)`
- Build command: `./scripts/build_ffmpeg_android.sh` (or exact variant used)
- Local patches: `none` (or list them)

## Record Keeping

When you ship updated binaries, keep the following recorded alongside the
release:

- upstream FFmpeg URL
- exact tag or commit used
- exact build command
- any local patches (if any)

This keeps the Android build reproducible and helps satisfy FFmpeg source
redistribution obligations.
