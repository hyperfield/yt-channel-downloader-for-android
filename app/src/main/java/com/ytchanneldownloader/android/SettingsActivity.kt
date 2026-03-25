package com.ytchanneldownloader.android

import android.os.Bundle
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.Spinner
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.ytchanneldownloader.android.bridge.CoreSettingsDto
import com.ytchanneldownloader.android.settings.AppSettingsStore
import com.google.android.material.appbar.MaterialToolbar
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

class SettingsActivity : AppCompatActivity() {
    private lateinit var settingsStore: AppSettingsStore
    private lateinit var defaultDownloadDirectory: String

    private lateinit var downloadDirectoryInput: EditText
    private lateinit var audioOnlyCheck: CheckBox
    private lateinit var downloadThumbnailCheck: CheckBox
    private lateinit var showThumbnailsCheck: CheckBox
    private lateinit var videoFormatSpinner: Spinner
    private lateinit var videoQualitySpinner: Spinner
    private lateinit var audioFormatSpinner: Spinner
    private lateinit var audioQualitySpinner: Spinner
    private lateinit var proxyTypeSpinner: Spinner
    private lateinit var proxyAddrInput: EditText
    private lateinit var proxyPortInput: EditText
    private lateinit var channelLimitInput: EditText
    private lateinit var playlistLimitInput: EditText
    private lateinit var channelBatchSizeInput: EditText
    private lateinit var saveButton: Button
    private lateinit var cancelButton: Button

    private var loadedSettings: CoreSettingsDto? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        settingsStore = AppSettingsStore(applicationContext)
        defaultDownloadDirectory = getExternalFilesDir(null)?.absolutePath ?: filesDir.absolutePath

        val topAppBar = findViewById<MaterialToolbar>(R.id.settingsTopAppBar)
        setSupportActionBar(topAppBar)
        setTitle(R.string.settings_title)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)

        bindViews()
        setupSpinners()
        setupActions()
        loadSettings()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    private fun bindViews() {
        downloadDirectoryInput = findViewById(R.id.downloadDirectoryInput)
        audioOnlyCheck = findViewById(R.id.audioOnlyCheck)
        downloadThumbnailCheck = findViewById(R.id.downloadThumbnailCheck)
        showThumbnailsCheck = findViewById(R.id.showThumbnailsCheck)
        videoFormatSpinner = findViewById(R.id.videoFormatSpinner)
        videoQualitySpinner = findViewById(R.id.videoQualitySpinner)
        audioFormatSpinner = findViewById(R.id.audioFormatSpinner)
        audioQualitySpinner = findViewById(R.id.audioQualitySpinner)
        proxyTypeSpinner = findViewById(R.id.proxyTypeSpinner)
        proxyAddrInput = findViewById(R.id.proxyAddrInput)
        proxyPortInput = findViewById(R.id.proxyPortInput)
        channelLimitInput = findViewById(R.id.channelLimitInput)
        playlistLimitInput = findViewById(R.id.playlistLimitInput)
        channelBatchSizeInput = findViewById(R.id.channelBatchSizeInput)
        saveButton = findViewById(R.id.saveSettingsButton)
        cancelButton = findViewById(R.id.cancelSettingsButton)
    }

    private fun setupSpinners() {
        configureSpinner(videoFormatSpinner, R.array.video_format_options)
        configureSpinner(videoQualitySpinner, R.array.video_quality_options)
        configureSpinner(audioFormatSpinner, R.array.audio_format_options)
        configureSpinner(audioQualitySpinner, R.array.audio_quality_options)
        configureSpinner(proxyTypeSpinner, R.array.proxy_type_options)
    }

    private fun setupActions() {
        proxyTypeSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: android.view.View?, position: Int, id: Long) {
                updateProxyInputsEnabled()
            }

            override fun onNothingSelected(parent: AdapterView<*>?) {
                updateProxyInputsEnabled()
            }
        }

        cancelButton.setOnClickListener { finish() }
        saveButton.setOnClickListener { saveSettings() }
    }

    private fun loadSettings() {
        lifecycleScope.launch {
            val settings = settingsStore.settingsFlow(defaultDownloadDirectory).first()
            loadedSettings = settings
            renderSettings(settings)
        }
    }

    private fun saveSettings() {
        val baseline = loadedSettings ?: CoreSettingsDto.defaults(defaultDownloadDirectory)
        val proxyType = proxyTypeSpinner.selectedItem?.toString() ?: baseline.proxyServerType
        val sanitizedProxyAddr = if (proxyType == "None") "" else proxyAddrInput.text.toString().trim()
        val sanitizedProxyPort = if (proxyType == "None") "" else proxyPortInput.text.toString().trim()

        val nextSettings = baseline.copy(
            downloadDirectory = downloadDirectoryInput.text.toString().trim().ifBlank { defaultDownloadDirectory },
            preferredVideoFormat = videoFormatSpinner.selectedItem?.toString() ?: baseline.preferredVideoFormat,
            preferredAudioFormat = audioFormatSpinner.selectedItem?.toString() ?: baseline.preferredAudioFormat,
            preferredVideoQuality = videoQualitySpinner.selectedItem?.toString() ?: baseline.preferredVideoQuality,
            preferredAudioQuality = audioQualitySpinner.selectedItem?.toString() ?: baseline.preferredAudioQuality,
            proxyServerType = proxyType,
            proxyServerAddr = sanitizedProxyAddr,
            proxyServerPort = sanitizedProxyPort,
            downloadThumbnail = downloadThumbnailCheck.isChecked,
            audioOnly = audioOnlyCheck.isChecked,
            showThumbnails = showThumbnailsCheck.isChecked,
            channelFetchLimit = parsePositiveInt(channelLimitInput.text.toString(), baseline.channelFetchLimit),
            playlistFetchLimit = parsePositiveInt(playlistLimitInput.text.toString(), baseline.playlistFetchLimit),
            channelFetchBatchSize = parsePositiveInt(
                channelBatchSizeInput.text.toString(),
                baseline.channelFetchBatchSize,
            ),
        )

        lifecycleScope.launch {
            settingsStore.save(nextSettings)
            Toast.makeText(this@SettingsActivity, R.string.settings_saved, Toast.LENGTH_SHORT).show()
            finish()
        }
    }

    private fun renderSettings(settings: CoreSettingsDto) {
        downloadDirectoryInput.setText(settings.downloadDirectory)
        audioOnlyCheck.isChecked = settings.audioOnly
        downloadThumbnailCheck.isChecked = settings.downloadThumbnail
        showThumbnailsCheck.isChecked = settings.showThumbnails
        videoFormatSpinner.selectValue(settings.preferredVideoFormat)
        videoQualitySpinner.selectValue(settings.preferredVideoQuality)
        audioFormatSpinner.selectValue(settings.preferredAudioFormat)
        audioQualitySpinner.selectValue(settings.preferredAudioQuality)
        proxyTypeSpinner.selectValue(settings.proxyServerType)
        proxyAddrInput.setText(settings.proxyServerAddr)
        proxyPortInput.setText(settings.proxyServerPort)
        channelLimitInput.setText(settings.channelFetchLimit.toString())
        playlistLimitInput.setText(settings.playlistFetchLimit.toString())
        channelBatchSizeInput.setText(settings.channelFetchBatchSize.toString())
        updateProxyInputsEnabled()
    }

    private fun updateProxyInputsEnabled() {
        val enabled = proxyTypeSpinner.selectedItem?.toString() != "None"
        proxyAddrInput.isEnabled = enabled
        proxyPortInput.isEnabled = enabled
    }

    private fun configureSpinner(spinner: Spinner, arrayResId: Int) {
        val adapter = ArrayAdapter.createFromResource(
            this,
            arrayResId,
            android.R.layout.simple_spinner_item,
        )
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spinner.adapter = adapter
    }

    private fun Spinner.selectValue(value: String) {
        val targetIndex = (0 until count).firstOrNull { index ->
            getItemAtPosition(index)?.toString() == value
        } ?: 0
        setSelection(targetIndex)
    }

    private fun parsePositiveInt(text: String, fallback: Int): Int {
        val parsed = text.trim().toIntOrNull() ?: return fallback
        return if (parsed > 0) parsed else fallback
    }
}
