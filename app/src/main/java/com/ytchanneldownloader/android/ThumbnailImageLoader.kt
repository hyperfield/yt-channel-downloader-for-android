package com.ytchanneldownloader.android

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.LruCache
import android.widget.ImageView
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL

object ThumbnailImageLoader {
    private const val CONNECT_TIMEOUT_MS = 6000
    private const val READ_TIMEOUT_MS = 6000
    private const val CACHE_SIZE_BYTES = 12 * 1024 * 1024

    private val cache = object : LruCache<String, Bitmap>(CACHE_SIZE_BYTES) {
        override fun sizeOf(key: String, value: Bitmap): Int {
            return value.byteCount
        }
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    fun loadInto(
        imageView: ImageView,
        imageUrl: String?,
    ) {
        val normalizedUrl = imageUrl?.trim().orEmpty()
        imageView.tag = normalizedUrl

        if (normalizedUrl.isBlank()) {
            imageView.setImageDrawable(null)
            return
        }

        cache.get(normalizedUrl)?.let { bitmap ->
            imageView.setImageBitmap(bitmap)
            return
        }

        imageView.setImageDrawable(null)

        scope.launch {
            val bitmap = downloadBitmap(normalizedUrl)
            if (bitmap != null) {
                cache.put(normalizedUrl, bitmap)
            }
            withContext(Dispatchers.Main) {
                if (imageView.tag != normalizedUrl) {
                    return@withContext
                }
                if (bitmap != null) {
                    imageView.setImageBitmap(bitmap)
                } else {
                    imageView.setImageDrawable(null)
                }
            }
        }
    }

    private fun downloadBitmap(imageUrl: String): Bitmap? {
        val connection = (URL(imageUrl).openConnection() as? HttpURLConnection) ?: return null
        return try {
            connection.connectTimeout = CONNECT_TIMEOUT_MS
            connection.readTimeout = READ_TIMEOUT_MS
            connection.instanceFollowRedirects = true
            connection.doInput = true
            connection.connect()
            if (connection.responseCode !in 200..299) {
                return null
            }
            connection.inputStream.use { inputStream: InputStream ->
                BitmapFactory.decodeStream(inputStream)
            }
        } catch (_: Exception) {
            null
        } finally {
            connection.disconnect()
        }
    }
}
