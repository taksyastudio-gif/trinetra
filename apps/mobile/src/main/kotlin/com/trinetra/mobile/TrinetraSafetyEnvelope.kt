package com.trinetra.mobile

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.os.SystemClock
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import kotlin.math.sin

/**
 * Trinetra Safety Envelope for Android Edge Deployment
 * Enforces frame freshness (<150ms), 800ms watchdog stall alerts,
 * and periodic acoustic heartbeat pulses.
 */
class TrinetraSafetyEnvelope(
    private val onWatchdogStalled: () -> Unit,
    private val onWatchdogRecovered: () -> Unit,
    val maxFrameLatencyMs: Long = 150L,
    val watchdogStallThresholdMs: Long = 800L,
    val heartbeatIntervalMs: Long = 2500L
) {
    private val lastFrameTimestamp = AtomicLong(0L)
    private val isStalled = AtomicBoolean(false)
    private val isRunning = AtomicBoolean(false)
    private var watchdogThread: Thread? = null

    // Heartbeat tone generator (subtle 320 Hz sine wave for 20ms)
    private val heartbeatAudioTrack: AudioTrack by lazy {
        val sampleRate = 44100
        val durationMs = 20
        val numSamples = (durationMs * sampleRate) / 1000
        val buffer = ShortArray(numSamples)
        val freq = 320.0

        for (i in 0 until numSamples) {
            val angle = 2.0 * Math.PI * i / (sampleRate / freq)
            buffer[i] = (sin(angle) * Short.MAX_VALUE * 0.15).toInt().toShort() // Soft 15% volume
        }

        AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(sampleRate)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build()
            )
            .setBufferSizeInBytes(buffer.size * 2)
            .setTransferMode(AudioTrack.MODE_STATIC)
            .build().apply {
                write(buffer, 0, buffer.size)
            }
    }

    fun start() {
        if (isRunning.getAndSet(true)) return
        lastFrameTimestamp.set(SystemClock.elapsedRealtime())

        watchdogThread = Thread({
            var lastHeartbeatTime = 0L

            while (isRunning.get()) {
                val now = SystemClock.elapsedRealtime()
                val lastFrame = lastFrameTimestamp.get()
                val elapsedSinceFrame = now - lastFrame

                // 1. Check for frame pipeline stall
                if (elapsedSinceFrame > watchdogStallThresholdMs) {
                    if (!isStalled.getAndSet(true)) {
                        onWatchdogStalled()
                    }
                } else {
                    if (isStalled.getAndSet(false)) {
                        onWatchdogRecovered()
                    }
                }

                // 2. Play acoustic heartbeat tone every 2.5 seconds
                if (!isStalled.get() && (now - lastHeartbeatTime >= heartbeatIntervalMs)) {
                    playHeartbeatTone()
                    lastHeartbeatTime = now
                }

                try {
                    Thread.sleep(100)
                } catch (e: InterruptedException) {
                    break
                }
            }
        }, "TrinetraWatchdogThread").apply {
            isDaemon = true
            start()
        }
    }

    fun stop() {
        isRunning.set(false)
        watchdogThread?.interrupt()
        watchdogThread = null
    }

    /**
     * Called on each incoming CameraX frame before inference.
     * Returns true if frame is within freshness deadline (<150ms).
     */
    fun onNewFrame(frameCaptureTimestampMs: Long): Boolean {
        val now = SystemClock.elapsedRealtime()
        val age = now - frameCaptureTimestampMs

        if (age > maxFrameLatencyMs) {
            // Drop stale frame to eliminate latency drift
            return false
        }

        lastFrameTimestamp.set(now)
        return true
    }

    private fun playHeartbeatTone() {
        try {
            heartbeatAudioTrack.stop()
            heartbeatAudioTrack.reloadStaticData()
            heartbeatAudioTrack.play()
        } catch (ignored: Exception) {}
    }
}
