package com.ytchanneldownloader.android.bridge

import com.chaquo.python.Python
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Callable
import java.util.concurrent.ExecutionException
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException

class PythonBridgeRepository(
    private val moduleName: String = "yt_channel_downloader.core.bridge",
) {
    private val bridge by lazy { Python.getInstance().getModule(moduleName) }

    suspend fun resolveUrl(
        url: String,
        settings: CoreSettingsDto,
    ): ResolveResult = withContext(Dispatchers.IO) {
        val jsonPayload = runBridgeCall(timeoutSeconds = RESOLVE_TIMEOUT_SECONDS) {
            bridge.callAttr(
                "resolve_url_json",
                url,
                settings.toPythonMap(),
            ).toString()
        }
        parseResolveResult(JSONObject(jsonPayload))
    }

    suspend fun startBatchDownload(
        items: List<ResolvedItem>,
        settings: CoreSettingsDto,
    ): String = withContext(Dispatchers.IO) {
        val payload = ArrayList<HashMap<String, Any>>(items.size)
        items.forEachIndexed { position, item ->
            payload.add(
                hashMapOf(
                    "index" to (item.index.takeIf { it >= 0 } ?: position),
                    "title" to item.title,
                    "url" to item.url,
                ),
            )
        }
        runBridgeCall(timeoutSeconds = WRITE_TIMEOUT_SECONDS) {
            bridge.callAttr("start_batch_download", payload, settings.toPythonMap()).toString()
        }
    }

    suspend fun getJobState(jobId: String): DownloadJobState = withContext(Dispatchers.IO) {
        val jsonPayload = runBridgeCall(timeoutSeconds = READ_TIMEOUT_SECONDS) {
            bridge.callAttr("get_job_state_json", jobId).toString()
        }
        parseDownloadJobState(JSONObject(jsonPayload))
    }

    suspend fun cancelDownloadJob(jobId: String): DownloadJobState = withContext(Dispatchers.IO) {
        runBridgeCall(timeoutSeconds = WRITE_TIMEOUT_SECONDS) {
            bridge.callAttr("cancel_download_job", jobId)
        }
        val jsonPayload = runBridgeCall(timeoutSeconds = READ_TIMEOUT_SECONDS) {
            bridge.callAttr("get_job_state_json", jobId).toString()
        }
        parseDownloadJobState(JSONObject(jsonPayload))
    }

    private fun <T> runBridgeCall(
        timeoutSeconds: Long,
        block: () -> T,
    ): T {
        val future = bridgeExecutor.submit(Callable { block() })
        return try {
            future.get(timeoutSeconds, TimeUnit.SECONDS)
        } catch (e: TimeoutException) {
            future.cancel(true)
            throw RuntimeException("Python bridge timed out after ${timeoutSeconds}s", e)
        } catch (e: InterruptedException) {
            future.cancel(true)
            Thread.currentThread().interrupt()
            throw RuntimeException("Python bridge call interrupted", e)
        } catch (e: ExecutionException) {
            val cause = e.cause
            if (cause is RuntimeException) {
                throw cause
            }
            throw RuntimeException(cause?.message ?: "Python bridge call failed", cause ?: e)
        }
    }

    private fun parseResolveResult(root: JSONObject): ResolveResult {
        val itemsArray = root.optJSONArray("items") ?: JSONArray()
        val items = ArrayList<ResolvedItem>(itemsArray.length())
        for (i in 0 until itemsArray.length()) {
            val item = itemsArray.optJSONObject(i) ?: continue
            items.add(
                ResolvedItem(
                    index = parseOptionalInt(item.opt("index")) ?: i,
                    title = item.optString("title", "Untitled"),
                    url = item.optString("url", ""),
                    durationSeconds = parseOptionalInt(item.opt("duration")),
                ),
            )
        }

        return ResolveResult(
            ok = root.optBoolean("ok", false),
            kind = root.optString("kind", "unknown"),
            inputUrl = root.optString("input_url", ""),
            normalizedUrl = root.optString("normalized_url", ""),
            items = items.filter { it.url.isNotBlank() },
            error = root.optNullableString("error"),
        )
    }

    private fun parseDownloadJobState(root: JSONObject): DownloadJobState {
        val itemsArray = root.optJSONArray("items") ?: JSONArray()
        val items = ArrayList<DownloadItemState>(itemsArray.length())
        for (i in 0 until itemsArray.length()) {
            val item = itemsArray.optJSONObject(i) ?: continue
            items.add(
                DownloadItemState(
                    index = parseOptionalInt(item.opt("index")) ?: i,
                    title = item.optString("title", "Item ${i + 1}"),
                    url = item.optString("url", ""),
                    status = item.optString("status", "unknown"),
                    progress = parseOptionalDouble(item.opt("progress")) ?: 0.0,
                    speed = item.optString("speed", "N/A"),
                    error = item.optNullableString("error"),
                ),
            )
        }

        return DownloadJobState(
            jobId = root.optString("job_id", ""),
            status = root.optString("status", "unknown"),
            progress = parseOptionalDouble(root.opt("progress")) ?: 0.0,
            speed = root.optString("speed", "N/A"),
            error = root.optNullableString("error"),
            cancelRequested = root.optBoolean("cancel_requested", false),
            totalCount = root.optInt("total_count", items.size),
            completedCount = root.optInt("completed_count", 0),
            failedCount = root.optInt("failed_count", 0),
            currentItemIndex = parseOptionalInt(root.opt("current_item_index")),
            currentItemTitle = root.optNullableString("current_item_title"),
            items = items,
        )
    }

    private fun parseOptionalInt(value: Any?): Int? {
        return when (value) {
            null -> null
            is Int -> value
            is Long -> value.toInt()
            is Double -> value.toInt()
            is Float -> value.toInt()
            is String -> value.toIntOrNull()
            else -> null
        }
    }

    private fun parseOptionalDouble(value: Any?): Double? {
        return when (value) {
            null -> null
            is Double -> value
            is Float -> value.toDouble()
            is Int -> value.toDouble()
            is Long -> value.toDouble()
            is String -> value.toDoubleOrNull()
            else -> null
        }
    }

    companion object {
        private const val RESOLVE_TIMEOUT_SECONDS = 25L
        private const val READ_TIMEOUT_SECONDS = 8L
        private const val WRITE_TIMEOUT_SECONDS = 12L
        private val bridgeExecutor = Executors.newCachedThreadPool()
    }
}

private fun JSONObject.optNullableString(key: String): String? {
    if (!has(key) || isNull(key)) {
        return null
    }
    val value = optString(key, "")
    return if (value.isBlank()) null else value
}
