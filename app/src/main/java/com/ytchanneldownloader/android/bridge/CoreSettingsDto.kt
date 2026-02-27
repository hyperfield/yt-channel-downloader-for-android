package com.ytchanneldownloader.android.bridge

data class CoreSettingsDto(
    val downloadDirectory: String,
    val preferredVideoFormat: String = "Any",
    val preferredAudioFormat: String = "mp3",
    val preferredVideoQuality: String = "1080p (Full HD)",
    val preferredAudioQuality: String = "Best available",
    val proxyServerType: String = "None",
    val proxyServerAddr: String = "",
    val proxyServerPort: String = "",
    val downloadThumbnail: Boolean = false,
    val audioOnly: Boolean = false,
    val showThumbnails: Boolean = true,
    val downloadsCompleted: Int = 0,
    val supportPromptNextAt: Int = 25,
    val supportPromptLastShownAt: Int = 0,
    val channelFetchLimit: Int = 500,
    val playlistFetchLimit: Int = 50,
    val channelFetchBatchSize: Int = 200,
) {
    fun toPythonMap(): HashMap<String, Any> = hashMapOf(
        "download_directory" to downloadDirectory,
        "preferred_video_format" to preferredVideoFormat,
        "preferred_audio_format" to preferredAudioFormat,
        "preferred_video_quality" to preferredVideoQuality,
        "preferred_audio_quality" to preferredAudioQuality,
        "proxy_server_type" to proxyServerType,
        "proxy_server_addr" to proxyServerAddr,
        "proxy_server_port" to proxyServerPort,
        "download_thumbnail" to downloadThumbnail,
        "audio_only" to audioOnly,
        "show_thumbnails" to showThumbnails,
        "downloads_completed" to downloadsCompleted,
        "support_prompt_next_at" to supportPromptNextAt,
        "support_prompt_last_shown_at" to supportPromptLastShownAt,
        "channel_fetch_limit" to channelFetchLimit,
        "playlist_fetch_limit" to playlistFetchLimit,
        "channel_fetch_batch_size" to channelFetchBatchSize,
    )

    companion object {
        fun defaults(downloadDirectory: String): CoreSettingsDto {
            return CoreSettingsDto(downloadDirectory = downloadDirectory)
        }
    }
}
