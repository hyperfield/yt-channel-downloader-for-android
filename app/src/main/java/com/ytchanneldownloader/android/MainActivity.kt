package com.ytchanneldownloader.android

import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.ytchanneldownloader.android.bridge.CoreSettingsDto
import com.ytchanneldownloader.android.bridge.FfmpegBinaryManager
import com.ytchanneldownloader.android.bridge.JsRuntimeBinaryManager
import com.ytchanneldownloader.android.bridge.PythonBridgeRepository
import com.ytchanneldownloader.android.settings.AppSettingsStore
import com.google.android.material.appbar.MaterialToolbar
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(applicationContext))
        }
        runCatching {
            Python.getInstance()
                .getModule("yt_channel_downloader.core.bridge")
                .callAttr("configure_android_logging", "INFO")
        }.onFailure { error ->
            Log.w("YTCD-MainActivity", "Failed to enable Python Logcat logging", error)
        }

        val topAppBar = findViewById<MaterialToolbar>(R.id.topAppBar)
        val urlInput = findViewById<EditText>(R.id.urlInput)
        val pasteUrlButton = findViewById<Button>(R.id.pasteUrlButton)
        val runButton = findViewById<Button>(R.id.runButton)
        val downloadButton = findViewById<Button>(R.id.downloadButton)
        val downloadProgressBar = findViewById<ProgressBar>(R.id.downloadProgressBar)
        val downloadStatusView = findViewById<TextView>(R.id.downloadStatusView)
        val downloadDetailsView = findViewById<TextView>(R.id.downloadDetailsView)
        val ffmpegStatusView = findViewById<TextView>(R.id.ffmpegStatusView)
        val jsRuntimeStatusView = findViewById<TextView>(R.id.jsRuntimeStatusView)
        val outputView = findViewById<TextView>(R.id.outputView)
        val selectionSummaryView = findViewById<TextView>(R.id.selectionSummaryView)
        val resolvedItemsList = findViewById<RecyclerView>(R.id.resolvedItemsList)

        setSupportActionBar(topAppBar)

        val defaultDownloadDirectory = getExternalFilesDir(null)?.absolutePath ?: filesDir.absolutePath
        val settingsStore = AppSettingsStore(applicationContext)
        val ffmpegBinaryManager = FfmpegBinaryManager(applicationContext)
        val jsRuntimeBinaryManager = JsRuntimeBinaryManager(applicationContext)
        var currentSettings = CoreSettingsDto.defaults(defaultDownloadDirectory)
        val settingsProvider = {
            currentSettings
        }
        val viewModel = ViewModelProvider(
            this,
            MainViewModelFactory(
                repository = PythonBridgeRepository(
                    extraSettingsProvider = {
                        hashMapOf<String, Any>().apply {
                            putAll(ffmpegBinaryManager.extraSettings())
                            putAll(jsRuntimeBinaryManager.extraSettings())
                        }
                    },
                ),
                settingsProvider = settingsProvider,
            ),
        )[MainViewModel::class.java]
        val resolvedItemsAdapter = ResolvedItemsAdapter { itemUrl, selected ->
            viewModel.setItemSelected(itemUrl, selected)
        }
        resolvedItemsList.layoutManager = LinearLayoutManager(this)
        resolvedItemsList.adapter = resolvedItemsAdapter
        var renderedResolvedUrls: List<String> = emptyList()
        var renderedSelectedUrls: Set<String> = emptySet()
        var renderedShowThumbnails = currentSettings.showThumbnails
        var isDownloading = false

        runButton.setOnClickListener {
            viewModel.resolveUrl(urlInput.text.toString())
        }

        pasteUrlButton.setOnClickListener {
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = clipboard.primaryClip
            val pastedText = clip
                ?.takeIf { it.itemCount > 0 }
                ?.getItemAt(0)
                ?.coerceToText(this)
                ?.toString()
                ?.trim()
                .orEmpty()

            if (pastedText.isBlank()) {
                Toast.makeText(this, R.string.paste_url_empty, Toast.LENGTH_SHORT).show()
            } else {
                urlInput.setText(pastedText)
                urlInput.setSelection(pastedText.length)
                urlInput.requestFocus()
            }
        }

        downloadButton.setOnClickListener {
            if (isDownloading) {
                viewModel.cancelDownload()
            } else {
                viewModel.startDownload(urlInput.text.toString())
            }
        }

        lifecycleScope.launch {
            val binaryStatus = withContext(Dispatchers.IO) {
                val ffmpegLocation = ffmpegBinaryManager.detectedLocation()
                val ffmpegFailureReason = ffmpegBinaryManager.failureReason()
                val jsRuntimeLocation = jsRuntimeBinaryManager.detectedLocation()
                val jsRuntimeFailureReason = jsRuntimeBinaryManager.failureReason()
                BinaryStatus(
                    ffmpegLocation = ffmpegLocation,
                    ffmpegFailureReason = ffmpegFailureReason,
                    jsRuntimeLocation = jsRuntimeLocation,
                    jsRuntimeFailureReason = jsRuntimeFailureReason,
                )
            }
            ffmpegStatusView.text = when {
                !binaryStatus.ffmpegLocation.isNullOrBlank() -> {
                    getString(R.string.ffmpeg_status_detected, binaryStatus.ffmpegLocation)
                }
                !binaryStatus.ffmpegFailureReason.isNullOrBlank() -> {
                    getString(R.string.ffmpeg_status_unusable, binaryStatus.ffmpegFailureReason)
                }
                else -> {
                    getString(R.string.ffmpeg_status_missing)
                }
            }
            jsRuntimeStatusView.text = when {
                !binaryStatus.jsRuntimeLocation.isNullOrBlank() -> {
                    getString(
                        R.string.js_runtime_status_detected,
                        jsRuntimeBinaryManager.runtimeName(),
                        binaryStatus.jsRuntimeLocation,
                    )
                }
                !binaryStatus.jsRuntimeFailureReason.isNullOrBlank() -> {
                    getString(
                        R.string.js_runtime_status_unusable,
                        jsRuntimeBinaryManager.runtimeName(),
                        binaryStatus.jsRuntimeFailureReason,
                    )
                }
                else -> {
                    getString(R.string.js_runtime_status_missing, jsRuntimeBinaryManager.runtimeName())
                }
            }
        }

        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch {
                    settingsStore.settingsFlow(defaultDownloadDirectory).collect { storedSettings ->
                        val thumbnailVisibilityChanged = storedSettings.showThumbnails != renderedShowThumbnails
                        currentSettings = storedSettings
                        if (thumbnailVisibilityChanged) {
                            renderedShowThumbnails = storedSettings.showThumbnails
                            val uiState = viewModel.uiState.value
                            resolvedItemsAdapter.submit(
                                uiState.resolvedItems,
                                uiState.selectedItemUrls,
                                renderedShowThumbnails,
                            )
                        }
                    }
                }
                launch {
                    viewModel.uiState.collect { state ->
                        val resolvedUrls = state.resolvedItems.map { it.url }
                        val itemsChanged = resolvedUrls != renderedResolvedUrls
                        val selectionChanged = state.selectedItemUrls != renderedSelectedUrls
                        if (itemsChanged || selectionChanged) {
                            renderedResolvedUrls = resolvedUrls
                            renderedSelectedUrls = state.selectedItemUrls
                            resolvedItemsAdapter.submit(
                                state.resolvedItems,
                                state.selectedItemUrls,
                                renderedShowThumbnails,
                            )
                        }

                        selectionSummaryView.text = if (state.resolvedItems.isEmpty()) {
                            getString(R.string.resolved_items_empty)
                        } else {
                            val selectedCount = state.resolvedItems.count {
                                state.selectedItemUrls.contains(it.url)
                            }
                            getString(
                                R.string.resolved_items_selection_summary,
                                selectedCount,
                                state.resolvedItems.size,
                            )
                        }

                        isDownloading = state.isDownloading
                        runButton.isEnabled = !state.isResolving && !state.isDownloading
                        downloadButton.isEnabled = state.isDownloading || !state.isResolving
                        downloadButton.text = getString(
                            if (state.isDownloading) R.string.cancel_download
                            else R.string.run_download_smoke_test,
                        )
                        downloadProgressBar.progress = state.downloadProgress.coerceIn(0, 100)
                        downloadStatusView.text = state.downloadStatus
                        if (state.downloadDetails.isBlank()) {
                            downloadDetailsView.visibility = View.GONE
                            downloadDetailsView.text = getString(R.string.download_details_placeholder)
                        } else {
                            downloadDetailsView.visibility = View.VISIBLE
                            downloadDetailsView.text = state.downloadDetails
                        }
                        outputView.text = state.outputText
                    }
                }
            }
        }
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main_actions, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_settings -> {
                startActivity(Intent(this, SettingsActivity::class.java))
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    private data class BinaryStatus(
        val ffmpegLocation: String?,
        val ffmpegFailureReason: String?,
        val jsRuntimeLocation: String?,
        val jsRuntimeFailureReason: String?,
    )
}
