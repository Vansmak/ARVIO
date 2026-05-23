package com.arflix.tv.server

import android.util.Log
import com.arflix.tv.data.model.MediaItem
import com.arflix.tv.data.model.MediaType
import fi.iki.elonen.NanoHTTPD
import org.json.JSONArray
import org.json.JSONObject

/**
 * Lightweight HTTP server that exposes the current user's watchlist as JSON
 * so Episeerr can poll it directly over LAN.
 *
 * GET /watchlist  →  JSON array of { title, tmdb_id, media_type, year }
 */
class WatchlistApiServer(
    private val getItems: () -> List<MediaItem>,
    port: Int = DEFAULT_PORT
) : NanoHTTPD(port) {

    override fun serve(session: IHTTPSession): Response {
        if (session.method != Method.GET || session.uri != "/watchlist") {
            return newFixedLengthResponse(Response.Status.NOT_FOUND, MIME_PLAINTEXT, "Not found")
        }
        return try {
            val items = getItems()
            val array = JSONArray()
            for (item in items) {
                array.put(JSONObject().apply {
                    put("title", item.title)
                    put("tmdb_id", item.id)
                    put("media_type", if (item.mediaType == MediaType.TV) "show" else "movie")
                    put("year", item.year.toIntOrNull() ?: 0)
                    put("poster_path", item.image)
                })
            }
            val response = newFixedLengthResponse(Response.Status.OK, "application/json", array.toString())
            response.addHeader("Access-Control-Allow-Origin", "*")
            response
        } catch (e: Exception) {
            Log.e(TAG, "serve error", e)
            newFixedLengthResponse(
                Response.Status.INTERNAL_ERROR,
                MIME_PLAINTEXT,
                "Error: ${e.message}"
            )
        }
    }

    companion object {
        const val DEFAULT_PORT = 7979
        private const val TAG = "WatchlistApiServer"

        @Volatile
        private var instance: WatchlistApiServer? = null

        fun start(getItems: () -> List<MediaItem>, port: Int = DEFAULT_PORT) {
            stop()
            try {
                val server = WatchlistApiServer(getItems, port)
                server.start(SOCKET_READ_TIMEOUT, false)
                instance = server
                Log.i(TAG, "Started on port $port")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start on port $port: ${e.message}")
            }
        }

        fun stop() {
            instance?.stop()
            instance = null
        }

        fun isRunning(): Boolean = instance?.isAlive == true
        fun currentPort(): Int = instance?.listeningPort ?: DEFAULT_PORT
    }
}
