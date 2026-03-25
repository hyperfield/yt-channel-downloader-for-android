# Third-Party Source Checkouts

This directory is reserved for optional maintainer-only source checkouts.

For FFmpeg, the recommended path is:

- `third_party/ffmpeg`

If that directory contains a valid FFmpeg source tree, the build helper can use
it automatically:

```bash
./scripts/build_ffmpeg_android.sh
```

If the directory is absent, nothing in the app build breaks. You can still point
the script at any external checkout:

```bash
./scripts/build_ffmpeg_android.sh ~/src/ffmpeg
```

To obtain the FFmpeg source:

```bash
git clone https://git.ffmpeg.org/ffmpeg.git third_party/ffmpeg
cd third_party/ffmpeg
git checkout <tag-or-commit>
cd ../..
```

After choosing a tag or commit, record it in `docs/ffmpeg-source.md`.

For Deno, the recommended path is:

- `third_party/deno`

If that directory contains a valid Deno source tree, the build helper can use
it automatically:

```bash
./scripts/build_deno_android.sh
```

If the directory is absent, nothing in the app build breaks. You can still
point the script at any external checkout:

```bash
./scripts/build_deno_android.sh ~/src/deno
```

To obtain the Deno source:

```bash
git clone --recurse-submodules https://github.com/denoland/deno.git third_party/deno
cd third_party/deno
git checkout <tag-or-commit>
git submodule update --init --recursive
cd ../..
```

After choosing a tag or commit, record it in `docs/deno-source.md`.
