package com.ytchanneldownloader.android.settings

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.ytchanneldownloader.android.bridge.CoreSettingsDto
import java.io.IOException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.map

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "app_settings")

class AppSettingsStore(context: Context) {
    private val appContext = context.applicationContext

    fun settingsFlow(defaultDownloadDirectory: String): Flow<CoreSettingsDto> {
        return appContext.dataStore.data
            .catch { error ->
                if (error is IOException) {
                    emit(emptyPreferences())
                } else {
                    throw error
                }
            }
            .map { prefs ->
                val defaults = CoreSettingsDto.defaults(defaultDownloadDirectory)
                CoreSettingsDto(
                    downloadDirectory = prefs[downloadDirectoryKey] ?: defaults.downloadDirectory,
                    preferredVideoFormat = prefs[preferredVideoFormatKey] ?: defaults.preferredVideoFormat,
                    preferredAudioFormat = prefs[preferredAudioFormatKey] ?: defaults.preferredAudioFormat,
                    preferredVideoQuality = prefs[preferredVideoQualityKey] ?: defaults.preferredVideoQuality,
                    preferredAudioQuality = prefs[preferredAudioQualityKey] ?: defaults.preferredAudioQuality,
                    proxyServerType = prefs[proxyServerTypeKey] ?: defaults.proxyServerType,
                    proxyServerAddr = prefs[proxyServerAddrKey] ?: defaults.proxyServerAddr,
                    proxyServerPort = prefs[proxyServerPortKey] ?: defaults.proxyServerPort,
                    downloadThumbnail = prefs[downloadThumbnailKey] ?: defaults.downloadThumbnail,
                    audioOnly = prefs[audioOnlyKey] ?: defaults.audioOnly,
                    showThumbnails = prefs[showThumbnailsKey] ?: defaults.showThumbnails,
                    downloadsCompleted = prefs[downloadsCompletedKey] ?: defaults.downloadsCompleted,
                    supportPromptNextAt = prefs[supportPromptNextAtKey] ?: defaults.supportPromptNextAt,
                    supportPromptLastShownAt = prefs[supportPromptLastShownAtKey] ?: defaults.supportPromptLastShownAt,
                    channelFetchLimit = prefs[channelFetchLimitKey] ?: defaults.channelFetchLimit,
                    playlistFetchLimit = prefs[playlistFetchLimitKey] ?: defaults.playlistFetchLimit,
                    channelFetchBatchSize = prefs[channelFetchBatchSizeKey] ?: defaults.channelFetchBatchSize,
                )
            }
    }

    suspend fun save(settings: CoreSettingsDto) {
        appContext.dataStore.edit { prefs ->
            prefs[downloadDirectoryKey] = settings.downloadDirectory
            prefs[preferredVideoFormatKey] = settings.preferredVideoFormat
            prefs[preferredAudioFormatKey] = settings.preferredAudioFormat
            prefs[preferredVideoQualityKey] = settings.preferredVideoQuality
            prefs[preferredAudioQualityKey] = settings.preferredAudioQuality
            prefs[proxyServerTypeKey] = settings.proxyServerType
            prefs[proxyServerAddrKey] = settings.proxyServerAddr
            prefs[proxyServerPortKey] = settings.proxyServerPort
            prefs[downloadThumbnailKey] = settings.downloadThumbnail
            prefs[audioOnlyKey] = settings.audioOnly
            prefs[showThumbnailsKey] = settings.showThumbnails
            prefs[downloadsCompletedKey] = settings.downloadsCompleted
            prefs[supportPromptNextAtKey] = settings.supportPromptNextAt
            prefs[supportPromptLastShownAtKey] = settings.supportPromptLastShownAt
            prefs[channelFetchLimitKey] = settings.channelFetchLimit
            prefs[playlistFetchLimitKey] = settings.playlistFetchLimit
            prefs[channelFetchBatchSizeKey] = settings.channelFetchBatchSize
        }
    }

    companion object {
        private val downloadDirectoryKey = stringPreferencesKey("download_directory")
        private val preferredVideoFormatKey = stringPreferencesKey("preferred_video_format")
        private val preferredAudioFormatKey = stringPreferencesKey("preferred_audio_format")
        private val preferredVideoQualityKey = stringPreferencesKey("preferred_video_quality")
        private val preferredAudioQualityKey = stringPreferencesKey("preferred_audio_quality")
        private val proxyServerTypeKey = stringPreferencesKey("proxy_server_type")
        private val proxyServerAddrKey = stringPreferencesKey("proxy_server_addr")
        private val proxyServerPortKey = stringPreferencesKey("proxy_server_port")
        private val downloadThumbnailKey = booleanPreferencesKey("download_thumbnail")
        private val audioOnlyKey = booleanPreferencesKey("audio_only")
        private val showThumbnailsKey = booleanPreferencesKey("show_thumbnails")
        private val downloadsCompletedKey = intPreferencesKey("downloads_completed")
        private val supportPromptNextAtKey = intPreferencesKey("support_prompt_next_at")
        private val supportPromptLastShownAtKey = intPreferencesKey("support_prompt_last_shown_at")
        private val channelFetchLimitKey = intPreferencesKey("channel_fetch_limit")
        private val playlistFetchLimitKey = intPreferencesKey("playlist_fetch_limit")
        private val channelFetchBatchSizeKey = intPreferencesKey("channel_fetch_batch_size")
    }
}
