package com.ytchanneldownloader.android

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.ytchanneldownloader.android.bridge.CoreSettingsDto
import com.ytchanneldownloader.android.bridge.DownloadJobState
import com.ytchanneldownloader.android.bridge.PythonBridgeRepository
import com.ytchanneldownloader.android.bridge.ResolveResult
import com.ytchanneldownloader.android.bridge.ResolvedItem
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class MainUiState(
    val isResolving: Boolean = false,
    val resolvedInputUrl: String = "",
    val resolvedKind: String? = null,
    val resolvedItems: List<ResolvedItem> = emptyList(),
    val selectedItemUrls: Set<String> = emptySet(),
    val outputText: String = "Result will appear here.",
    val isDownloading: Boolean = false,
    val activeJobId: String? = null,
    val downloadProgress: Int = 0,
    val downloadStatus: String = "Download idle.",
    val downloadDetails: String = "",
)

class MainViewModel(
    private val repository: PythonBridgeRepository,
    private val settingsProvider: () -> CoreSettingsDto,
) : ViewModel() {
    private val _uiState = MutableStateFlow(MainUiState())
    val uiState: StateFlow<MainUiState> = _uiState.asStateFlow()

    private var pollJob: Job? = null

    fun resolveUrl(rawUrl: String) {
        val url = rawUrl.trim()
        if (url.isEmpty()) {
            _uiState.update { it.copy(outputText = "Resolve failed: URL is empty.") }
            return
        }
        if (_uiState.value.isResolving) {
            return
        }

        viewModelScope.launch {
            resolveUrlInternal(url, settingsProvider())
        }
    }

    fun startDownload(rawUrl: String) {
        val url = rawUrl.trim()
        if (url.isEmpty()) {
            _uiState.update { it.copy(downloadStatus = "Download failed: URL is empty.") }
            return
        }
        if (_uiState.value.isDownloading) {
            return
        }

        viewModelScope.launch {
            val settings = settingsProvider()
            _uiState.update {
                it.copy(
                    downloadProgress = 0,
                    downloadStatus = "Resolving URL before download...",
                    downloadDetails = "",
                )
            }

            var stateSnapshot = _uiState.value
            if (stateSnapshot.resolvedItems.isEmpty() || stateSnapshot.resolvedInputUrl != url) {
                val resolveResult = resolveUrlInternal(url, settings) ?: return@launch
                if (resolveResult.items.isEmpty()) {
                    _uiState.update { it.copy(downloadStatus = "Download failed: no media items resolved.") }
                    return@launch
                }
                stateSnapshot = _uiState.value
            }

            val selectedItems = stateSnapshot.resolvedItems.filter {
                stateSnapshot.selectedItemUrls.contains(it.url)
            }
            if (selectedItems.isEmpty()) {
                _uiState.update { it.copy(downloadStatus = "Download failed: no items selected.") }
                return@launch
            }

            try {
                val jobId = repository.startBatchDownload(selectedItems, settings)
                _uiState.update {
                    it.copy(
                        isDownloading = true,
                        activeJobId = jobId,
                        downloadProgress = 0,
                        downloadStatus = "Download job queued...",
                        downloadDetails = "",
                    )
                }
                monitorDownloadJob(jobId)
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        isDownloading = false,
                        activeJobId = null,
                        downloadStatus = "Download failed: ${e.message ?: e::class.java.simpleName}",
                        downloadDetails = "",
                    )
                }
            }
        }
    }

    fun setItemSelected(itemUrl: String, selected: Boolean) {
        _uiState.update { state ->
            val validUrls = state.resolvedItems.map { it.url }.toSet()
            if (!validUrls.contains(itemUrl)) {
                return@update state
            }

            val next = state.selectedItemUrls.toMutableSet()
            if (selected) {
                next.add(itemUrl)
            } else {
                next.remove(itemUrl)
            }
            state.copy(selectedItemUrls = next)
        }
    }

    fun cancelDownload() {
        val jobId = _uiState.value.activeJobId ?: return
        viewModelScope.launch {
            _uiState.update { it.copy(downloadStatus = "Cancelling download...") }
            try {
                val state = repository.cancelDownloadJob(jobId)
                _uiState.update {
                    it.copy(
                        isDownloading = !state.isTerminal,
                        activeJobId = if (state.isTerminal) null else jobId,
                        downloadProgress = state.progress.coerceIn(0.0, 100.0).toInt(),
                        downloadStatus = formatDownloadStatus(state),
                        downloadDetails = formatDownloadDetails(state),
                    )
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        downloadStatus = "Cancellation failed: ${e.message ?: e::class.java.simpleName}",
                        downloadDetails = "",
                    )
                }
            }
        }
    }

    override fun onCleared() {
        super.onCleared()
        pollJob?.cancel()
    }

    private suspend fun resolveUrlInternal(
        url: String,
        settings: CoreSettingsDto,
    ): ResolveResult? {
        _uiState.update {
            it.copy(
                isResolving = true,
                outputText = "Resolving URL...",
            )
        }

        return try {
            val result = repository.resolveUrl(url, settings)
            if (!result.ok || result.items.isEmpty()) {
                _uiState.update {
                    it.copy(
                        resolvedInputUrl = url,
                        resolvedKind = null,
                        resolvedItems = emptyList(),
                        selectedItemUrls = emptySet(),
                        outputText = "Resolve failed: ${result.error ?: "unknown error"}",
                    )
                }
                null
            } else {
                val selectedUrls = result.items.map { it.url }.toSet()
                _uiState.update {
                    it.copy(
                        resolvedInputUrl = url,
                        resolvedKind = result.kind,
                        resolvedItems = result.items,
                        selectedItemUrls = selectedUrls,
                        outputText = formatResolveSummary(result),
                    )
                }
                result
            }
        } catch (e: Exception) {
            _uiState.update {
                it.copy(
                    resolvedInputUrl = url,
                    resolvedKind = null,
                    resolvedItems = emptyList(),
                    selectedItemUrls = emptySet(),
                    outputText = "Resolve failed: ${e.message ?: e::class.java.simpleName}",
                )
            }
            null
        } finally {
            _uiState.update { it.copy(isResolving = false) }
        }
    }

    private fun monitorDownloadJob(jobId: String) {
        pollJob?.cancel()
        pollJob = viewModelScope.launch {
            while (true) {
                val state = try {
                    repository.getJobState(jobId)
                } catch (e: Exception) {
                        _uiState.update {
                            it.copy(
                                isDownloading = false,
                                activeJobId = null,
                                downloadStatus = "Download failed: ${e.message ?: e::class.java.simpleName}",
                                downloadDetails = "",
                            )
                        }
                    return@launch
                }

                _uiState.update {
                    it.copy(
                        isDownloading = !state.isTerminal,
                        activeJobId = if (state.isTerminal) null else jobId,
                        downloadProgress = state.progress.coerceIn(0.0, 100.0).toInt(),
                        downloadStatus = formatDownloadStatus(state),
                        downloadDetails = formatDownloadDetails(state),
                    )
                }

                if (state.isTerminal) {
                    return@launch
                }
                delay(400)
            }
        }
    }

    private fun formatResolveSummary(result: ResolveResult): String {
        val first = result.items.firstOrNull()
        val firstTitle = first?.title ?: "n/a"
        val firstUrl = first?.url ?: "n/a"
        return "Resolved kind=${result.kind}, count=${result.count}, first_title=\"$firstTitle\", first_url=$firstUrl"
    }

    private fun formatDownloadStatus(state: DownloadJobState): String {
        val detailedError = state.error ?: state.items.firstNotNullOfOrNull { it.error }
        val warning = state.items.firstNotNullOfOrNull { it.warning }
        return when (state.status) {
            "queued" -> "Download queued..."
            "starting" -> "Download starting..."
            "downloading" -> {
                val done = "${state.completedCount}/${state.totalCount}"
                "Downloading $done | ${state.progress.toInt()}% | ${state.speed}"
            }
            "cancelling" -> "Cancelling download..."
            "completed" -> {
                val base = "Download completed (${state.completedCount}/${state.totalCount})."
                if (warning.isNullOrBlank()) base else "$base $warning"
            }
            "completed_with_errors" -> {
                "Completed with errors (${state.failedCount} failed of ${state.totalCount}): ${detailedError ?: "Unknown error"}"
            }
            "cancelled" -> "Download cancelled."
            "error" -> "Download failed: ${detailedError ?: "Unknown error"}"
            "missing" -> "Download failed: job not found."
            else -> "Download status: ${state.status}"
        }
    }

    private fun formatDownloadDetails(state: DownloadJobState): String {
        val focusItem = state.currentItemIndex?.let { index ->
            state.items.getOrNull(index)
        }
            ?: state.items.lastOrNull { item ->
                !item.diagnostic.isNullOrBlank() ||
                    !item.warning.isNullOrBlank() ||
                    !item.outputFilename.isNullOrBlank()
            }
            ?: return ""

        val lines = ArrayList<String>()
        focusItem.requestedQuality?.takeIf { it.isNotBlank() }?.let {
            lines += "Requested: $it"
        }

        val actualParts = ArrayList<String>()
        focusItem.actualQuality?.takeIf { it.isNotBlank() }?.let { actualParts += it }
        if (focusItem.actualWidth != null && focusItem.actualHeight != null) {
            actualParts += "${focusItem.actualWidth}x${focusItem.actualHeight}"
        }
        if (actualParts.isNotEmpty()) {
            lines += "Actual: ${actualParts.joinToString(" | ")}"
        }

        focusItem.outputFilename?.takeIf { it.isNotBlank() }?.let {
            lines += "Saved as: $it"
        }
        focusItem.formatSummary?.takeIf { it.isNotBlank() }?.let {
            lines += "Format: $it"
        }
        focusItem.warning?.takeIf { it.isNotBlank() }?.let {
            lines += "Warning: $it"
        }
        focusItem.fallbackReason?.takeIf { it.isNotBlank() }?.let {
            lines += "Fallback: $it"
        }
        focusItem.diagnostic?.takeIf { it.isNotBlank() }?.let {
            lines += "Details: $it"
        }
        return lines.joinToString("\n")
    }
}

class MainViewModelFactory(
    private val repository: PythonBridgeRepository,
    private val settingsProvider: () -> CoreSettingsDto,
) : ViewModelProvider.Factory {
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        if (modelClass.isAssignableFrom(MainViewModel::class.java)) {
            @Suppress("UNCHECKED_CAST")
            return MainViewModel(
                repository = repository,
                settingsProvider = settingsProvider,
            ) as T
        }
        throw IllegalArgumentException("Unknown ViewModel class: ${modelClass.name}")
    }
}
