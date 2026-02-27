package com.ytchanneldownloader.android

import android.os.Bundle
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.ListView
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.ytchanneldownloader.android.bridge.CoreSettingsDto
import com.ytchanneldownloader.android.bridge.PythonBridgeRepository
import com.ytchanneldownloader.android.bridge.ResolvedItem
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(applicationContext))
        }

        val urlInput = findViewById<EditText>(R.id.urlInput)
        val runButton = findViewById<Button>(R.id.runButton)
        val downloadButton = findViewById<Button>(R.id.downloadButton)
        val cancelButton = findViewById<Button>(R.id.cancelButton)
        val downloadProgressBar = findViewById<ProgressBar>(R.id.downloadProgressBar)
        val downloadStatusView = findViewById<TextView>(R.id.downloadStatusView)
        val outputView = findViewById<TextView>(R.id.outputView)
        val selectionSummaryView = findViewById<TextView>(R.id.selectionSummaryView)
        val resolvedItemsList = findViewById<ListView>(R.id.resolvedItemsList)

        val resolvedItemLabels = mutableListOf<String>()
        val resolvedItemsAdapter = ArrayAdapter(
            this,
            android.R.layout.simple_list_item_multiple_choice,
            resolvedItemLabels,
        )
        resolvedItemsList.choiceMode = ListView.CHOICE_MODE_MULTIPLE
        resolvedItemsList.adapter = resolvedItemsAdapter
        var currentResolvedItems: List<ResolvedItem> = emptyList()
        var renderedResolvedUrls: List<String> = emptyList()

        val settingsProvider = {
            CoreSettingsDto.defaults(
                downloadDirectory = getExternalFilesDir(null)?.absolutePath ?: filesDir.absolutePath,
            )
        }
        val viewModel = ViewModelProvider(
            this,
            MainViewModelFactory(
                repository = PythonBridgeRepository(),
                settingsProvider = settingsProvider,
            ),
        )[MainViewModel::class.java]

        runButton.setOnClickListener {
            viewModel.resolveUrl(urlInput.text.toString())
        }

        downloadButton.setOnClickListener {
            viewModel.startDownload(urlInput.text.toString())
        }

        cancelButton.setOnClickListener {
            viewModel.cancelDownload()
        }

        resolvedItemsList.setOnItemClickListener { _, _, position, _ ->
            val item = currentResolvedItems.getOrNull(position) ?: return@setOnItemClickListener
            viewModel.setItemSelected(item.url, resolvedItemsList.isItemChecked(position))
        }

        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.uiState.collect { state ->
                    val resolvedUrls = state.resolvedItems.map { it.url }
                    currentResolvedItems = state.resolvedItems
                    if (resolvedUrls != renderedResolvedUrls) {
                        renderedResolvedUrls = resolvedUrls
                        resolvedItemsList.clearChoices()
                        resolvedItemLabels.clear()
                        state.resolvedItems.forEachIndexed { index, item ->
                            val itemTitle = if (item.title.isBlank()) item.url else item.title
                            resolvedItemLabels.add("${index + 1}. $itemTitle")
                        }
                        resolvedItemsAdapter.notifyDataSetChanged()
                    }

                    for (i in currentResolvedItems.indices) {
                        val itemUrl = currentResolvedItems[i].url
                        val shouldBeChecked = state.selectedItemUrls.contains(itemUrl)
                        if (resolvedItemsList.isItemChecked(i) != shouldBeChecked) {
                            resolvedItemsList.setItemChecked(i, shouldBeChecked)
                        }
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

                    runButton.isEnabled = !state.isResolving && !state.isDownloading
                    downloadButton.isEnabled = !state.isDownloading
                    cancelButton.isEnabled = state.isDownloading
                    downloadProgressBar.progress = state.downloadProgress.coerceIn(0, 100)
                    downloadStatusView.text = state.downloadStatus
                    outputView.text = state.outputText
                }
            }
        }
    }
}
