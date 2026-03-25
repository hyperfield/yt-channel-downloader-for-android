package com.ytchanneldownloader.android.bridge

import android.content.Context
import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit

class JsRuntimeBinaryManager(
    private val context: Context,
) {
    private val lock = Any()

    @Volatile
    private var didInitialize = false

    @Volatile
    private var cachedLocation: String? = null

    @Volatile
    private var cachedFailureReason: String? = null

    fun extraSettings(): Map<String, Any> {
        val location = ensureBinaryLocation() ?: return emptyMap()
        return mapOf(
            "js_runtime_name" to RUNTIME_NAME,
            "js_runtime_location" to location,
        )
    }

    fun detectedLocation(): String? {
        return ensureBinaryLocation()
    }

    fun failureReason(): String? {
        ensureBinaryLocation()
        return cachedFailureReason
    }

    fun runtimeName(): String = RUNTIME_NAME

    private fun ensureBinaryLocation(): String? {
        if (didInitialize) {
            return cachedLocation
        }

        synchronized(lock) {
            if (didInitialize) {
                return cachedLocation
            }

            val candidateLocation = findBundledBinary()
            val failureReason = validateLocation(candidateLocation)
            cachedFailureReason = failureReason
            cachedLocation = if (failureReason == null) candidateLocation else null
            didInitialize = true
            return cachedLocation
        }
    }

    private fun findBundledBinary(): String? {
        val nativeLibraryDir = context.applicationInfo.nativeLibraryDir ?: return null
        if (nativeLibraryDir.isBlank()) {
            return null
        }

        val directory = File(nativeLibraryDir)
        if (!directory.isDirectory) {
            return null
        }

        val executablePath = File(directory, RUNTIME_BINARY)
        if (executablePath.isFile) {
            return executablePath.absolutePath
        }

        val sharedObjectPath = File(directory, RUNTIME_SO_BINARY)
        if (sharedObjectPath.isFile) {
            return sharedObjectPath.absolutePath
        }

        return null
    }

    private fun validateLocation(executablePath: String?): String? {
        if (executablePath.isNullOrBlank()) {
            return null
        }
        return probeBinary(File(executablePath))
    }

    private fun probeBinary(binaryFile: File): String? {
        if (!binaryFile.isFile) {
            return "is missing"
        }

        return try {
            val process = ProcessBuilder(binaryFile.absolutePath, "--version")
                .redirectErrorStream(true)
                .start()

            if (!process.waitFor(PROBE_TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
                process.destroyForcibly()
                "timed out"
            } else if (process.exitValue() == 0) {
                null
            } else {
                "exited with code ${process.exitValue()}"
            }
        } catch (e: IOException) {
            "is not runnable (${e.message ?: e::class.java.simpleName})"
        } catch (e: SecurityException) {
            "is blocked (${e.message ?: e::class.java.simpleName})"
        }
    }

    companion object {
        private const val RUNTIME_NAME = "deno"
        private const val RUNTIME_BINARY = "deno"
        private const val RUNTIME_SO_BINARY = "libdeno.so"
        private const val PROBE_TIMEOUT_SECONDS = 3L
    }
}
