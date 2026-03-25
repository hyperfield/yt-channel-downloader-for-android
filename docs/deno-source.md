# Deno Source Provenance

This project can optionally bundle a Deno executable for Android so `yt-dlp`
can use `yt-dlp-ejs` with an explicit JavaScript runtime. The bundled runtime
is copied into the Android native library source set as:

- `app/src/main/jniLibs/<abi>/libdeno.so`

## Recommended Maintainer Workflow

Use one of these source layouts:

1. External checkout outside this repo, for example `~/src/deno`
2. Plain git checkout at `third_party/deno` inside this repo (not as a submodule)

The build script resolves the source directory in this order:

1. explicit positional path passed to `scripts/build_deno_android.sh`
2. `DENO_SRC_DIR`
3. `third_party/deno` if it exists and looks like a Deno source tree

This means you can run either:

```bash
./scripts/build_deno_android.sh ~/src/deno
```

or, if `third_party/deno` exists:

```bash
./scripts/build_deno_android.sh
```

## Current Project Choice

The recommended workflow for this repo is a normal git checkout at
`third_party/deno`, without using a submodule:

```bash
git clone --recurse-submodules https://github.com/denoland/deno.git third_party/deno
cd third_party/deno
git checkout <tag-or-commit>
git submodule update --init --recursive
cd ../..
```

## Host Build Constraint

Upstream Deno build documentation points to source builds via Cargo, and the
official `rusty_v8` Android build guidance documents Android builds from an
`x86_64` host. In practice, maintainers should plan to run the Android Deno
build from:

1. an `x86_64` Linux/macOS builder, or
2. an `x86_64` shell under Rosetta on Apple Silicon.

The helper script enforces that by default and requires
`--allow-unsupported-host` to proceed on other hosts.

## Recorded Source For This Repo

When you choose a tag or commit, record it here before shipping updated
binaries:

- Upstream URL: `https://github.com/denoland/deno.git`
- Local source path: `third_party/deno` (or external path if used instead)
- Selected tag: `<fill in>`
- Exact commit SHA: `<fill in>`
- Build command: `./scripts/build_deno_android.sh` (or exact variant used)
- Local patches: `none` (or list them)

## Record Keeping

When you ship updated binaries, keep the following recorded alongside the
release:

- upstream Deno URL
- exact tag or commit used
- exact build command
- any local patches (if any)

This keeps the Android build reproducible and makes later runtime/tooling
updates easier to audit.
