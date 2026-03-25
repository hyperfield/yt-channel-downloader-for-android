package com.ytchanneldownloader.android.bridge

data class ResolvedItem(
    val index: Int,
    val title: String,
    val url: String,
    val durationSeconds: Int?,
    val thumbnailUrl: String?,
)

data class ResolveResult(
    val ok: Boolean,
    val kind: String,
    val inputUrl: String,
    val normalizedUrl: String,
    val items: List<ResolvedItem>,
    val error: String?,
) {
    val count: Int
        get() = items.size
}

data class DownloadItemState(
    val index: Int,
    val title: String,
    val url: String,
    val status: String,
    val progress: Double,
    val speed: String,
    val error: String?,
    val requestedQuality: String?,
    val actualQuality: String?,
    val actualWidth: Int?,
    val actualHeight: Int?,
    val outputFilename: String?,
    val formatSummary: String?,
    val warning: String?,
    val diagnostic: String?,
    val fallbackReason: String?,
)

data class DownloadJobState(
    val jobId: String,
    val status: String,
    val progress: Double,
    val speed: String,
    val error: String?,
    val cancelRequested: Boolean,
    val totalCount: Int,
    val completedCount: Int,
    val failedCount: Int,
    val currentItemIndex: Int?,
    val currentItemTitle: String?,
    val items: List<DownloadItemState>,
) {
    val isTerminal: Boolean
        get() = status in setOf("completed", "completed_with_errors", "error", "cancelled", "missing")
}
