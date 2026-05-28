@file:Suppress("UnsafeOptInUsageError")

package com.arflix.tv.ui.screens.tv.live

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import androidx.tv.material3.ExperimentalTvMaterial3Api
import androidx.tv.material3.Text

/**
 * Floating picture-in-picture tile shown on non-TV screens when a live stream is active.
 * Rendered in a Box overlay in ArflixApp, above the NavHost content.
 *
 * Dismiss: press Back (handled by HomeScreen's onInterceptBack) or tap the ✕ on touch devices.
 * Tap/OK the tile to return to the full TV guide.
 *
 * Surface handoff: the same ExoPlayer is used here and in LiveTvScreen. The update lambda
 * force-detaches then re-attaches the player surface as a fallback for mid-transition timing.
 */
@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun LiveTvMiniPlayerOverlay(
    player: ExoPlayer,
    channelName: String,
    programTitle: String,
    onClick: () -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .shadow(elevation = 16.dp, shape = RoundedCornerShape(10.dp))
            .width(240.dp)
            .clip(RoundedCornerShape(10.dp))
            .background(Color.Black)
            .clickable(onClick = onClick),
    ) {
        // Video area — 16:9 at 240dp wide = 135dp tall
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(135.dp),
        ) {
            AndroidView(
                factory = { ctx ->
                    PlayerView(ctx).apply {
                        this.player = player
                        useController = false
                        resizeMode = AspectRatioFrameLayout.RESIZE_MODE_ZOOM
                        setKeepContentOnPlayerReset(true)
                    }
                },
                update = { view ->
                    // Fallback surface handoff: force detach then reattach to ensure
                    // the surface is current when this view enters composition mid-transition.
                    if (view.player !== player) {
                        view.player = null
                        view.player = player
                    }
                },
                modifier = Modifier.fillMaxSize(),
            )
            LiveBug(modifier = Modifier.align(Alignment.TopStart).padding(6.dp))
        }

        // Info bar — channel name, program, and close button
        Row(
            modifier = Modifier
                .align(Alignment.BottomStart)
                .fillMaxWidth()
                .background(Color.Black.copy(alpha = 0.85f))
                .padding(horizontal = 8.dp, vertical = 5.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                if (channelName.isNotBlank()) {
                    Text(
                        text = channelName,
                        style = LiveType.Badge.copy(color = Color.White),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (programTitle.isNotBlank()) {
                    Text(
                        text = programTitle,
                        style = LiveType.Badge.copy(color = Color.White.copy(alpha = 0.6f)),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
            Spacer(modifier = Modifier.width(6.dp))
            // Close button — touch devices can tap this; TV users press Back to dismiss
            Box(
                modifier = Modifier
                    .size(26.dp)
                    .clip(CircleShape)
                    .background(Color.White.copy(alpha = 0.15f))
                    .clickable(onClick = onDismiss),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = Icons.Default.Close,
                    contentDescription = "Dismiss (or press Back)",
                    tint = Color.White.copy(alpha = 0.8f),
                    modifier = Modifier.size(14.dp),
                )
            }
        }
    }
}
