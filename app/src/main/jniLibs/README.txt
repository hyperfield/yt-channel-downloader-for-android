Bundled FFmpeg executables now ship from this native-library source set.

Expected layout:

  app/src/main/jniLibs/<abi>/libffmpeg.so
  app/src/main/jniLibs/<abi>/libffprobe.so
  app/src/main/jniLibs/<abi>/libdeno.so

Examples:

  app/src/main/jniLibs/arm64-v8a/libffmpeg.so
  app/src/main/jniLibs/arm64-v8a/libffprobe.so
  app/src/main/jniLibs/arm64-v8a/libdeno.so
  app/src/main/jniLibs/x86_64/libffmpeg.so
  app/src/main/jniLibs/x86_64/libffprobe.so
  app/src/main/jniLibs/x86_64/libdeno.so

These files are Android-native executables renamed with ".so" extensions so the
package manager extracts them into the app's native library directory.

The app detects them via applicationInfo.nativeLibraryDir and passes the exact
ffmpeg executable path to yt-dlp as ffmpeg_location.

The same native-library directory is also used for a bundled JavaScript runtime.
The current runtime manager looks for a Deno executable at libdeno.so (or deno)
and passes it to yt-dlp via the js_runtimes option.

Maintainer build helpers:

  ./scripts/build_ffmpeg_android.sh
  ./scripts/build_deno_android.sh

For Deno specifically, the upstream Android build path is intended for x86_64
hosts. On Apple Silicon, use an x86_64/Rosetta shell or a separate x86_64
builder when producing libdeno.so.
