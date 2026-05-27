package com.arflix.tv.data.repository

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import com.arflix.tv.data.model.MediaType
import com.arflix.tv.util.settingsDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.first
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import javax.inject.Inject
import javax.inject.Singleton

val WEBHOOK_ENABLED_KEY = booleanPreferencesKey("webhook_enabled")
val WEBHOOK_URL_KEY = stringPreferencesKey("webhook_url")
val WEBHOOK_INTERVAL_KEY = stringPreferencesKey("webhook_interval_seconds")
val WEBHOOK_COMPLETION_PERCENT_KEY = stringPreferencesKey("webhook_completion_percent")
val WATCHLIST_API_ENABLED_KEY = booleanPreferencesKey("watchlist_api_enabled")
val WATCHLIST_API_PORT_KEY = stringPreferencesKey("watchlist_api_port")
val EPISEERR_URL_KEY = stringPreferencesKey("episeerr_url")
// Sync server URL — used by "Connect to Server" on the profile screen.
// Separate from EPISEERR_URL_KEY, which is for the Episeerr media-management addon.
// They may point at the same host in a typical self-hosted setup.
val SYNC_SERVER_URL_KEY = stringPreferencesKey("sync_server_url")
val USER_TMDB_API_KEY = stringPreferencesKey("user_tmdb_api_key")
val USER_TRAKT_CLIENT_ID = stringPreferencesKey("user_trakt_client_id")
val USER_TRAKT_CLIENT_SECRET = stringPreferencesKey("user_trakt_client_secret")

@Singleton
class ProgressWebhookRepository @Inject constructor(
    @ApplicationContext private val context: Context,
    private val okHttpClient: OkHttpClient
) {
    private var lastFireTimeMs = 0L

    suspend fun maybeFireWebhook(
        event: String,
        mediaType: MediaType,
        tmdbId: Int,
        title: String,
        season: Int?,
        episode: Int?,
        positionSeconds: Long,
        durationSeconds: Long,
        progressPercent: Int,
        serverItemId: String? = null
    ) {
        val prefs = context.settingsDataStore.data.first()
        if (prefs[WEBHOOK_ENABLED_KEY] != true) return
        val url = prefs[WEBHOOK_URL_KEY].orEmpty().trim()
        if (url.isBlank()) return
        val intervalSeconds = prefs[WEBHOOK_INTERVAL_KEY]?.toIntOrNull() ?: 30

        val now = System.currentTimeMillis()
        val isLifecycleEvent = event == "start" || event == "pause" || event == "stop"
        if (!isLifecycleEvent && now - lastFireTimeMs < intervalSeconds * 1000L) return
        lastFireTimeMs = now

        runCatching {
            val payload = JSONObject().apply {
                put("event", event)
                put("media_type", if (mediaType == MediaType.MOVIE) "movie" else "tv")
                put("tmdb_id", tmdbId)
                put("title", title)
                if (season != null) put("season", season)
                if (episode != null) put("episode", episode)
                put("position_seconds", positionSeconds)
                put("duration_seconds", durationSeconds)
                put("progress_percent", progressPercent)
                if (!serverItemId.isNullOrBlank()) put("server_item_id", serverItemId)
            }
            val body = payload.toString().toRequestBody("application/json".toMediaType())
            val request = Request.Builder()
                .url(url)
                .post(body)
                .build()
            okHttpClient.newCall(request).execute().close()
        }
    }
}
