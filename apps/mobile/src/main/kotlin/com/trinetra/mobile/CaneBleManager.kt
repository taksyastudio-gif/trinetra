package com.trinetra.mobile

import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothProfile
import android.os.SystemClock
import java.util.UUID

/**
 * Manages low-power Bluetooth (BLE) connection to the Smart White Cane.
 * Receives physical ranging telemetry (forward ultrasonic + downward ToF LiDAR)
 * and enforces deterministic OR-logic safety vetoes.
 */
data class CaneTelemetry(
    val forwardDistCm: Float?,
    val groundDistCm: Float?,
    val nominalGroundCm: Float = 85.0f,
    val pitchDeg: Float = 0.0f,
    val rollDeg: Float = 0.0f,
    val caneTapping: Boolean = true,
    val timestampMs: Long = SystemClock.elapsedRealtime()
)

data class FusedSafetyDecision(
    val alertLevel: String,         // "CRITICAL_STOP", "WARNING", "CLEAR"
    val vetoApplied: Boolean,       // True if physical ranging vetoed optimistic vision
    val descriptionNe: String,
    val distanceM: Float? = null
)

class CaneBleManager(
    private val criticalForwardStopCm: Float = 90.0f,
    private val potholeDropThresholdCm: Float = 12.0f,
    private val stepUpThresholdCm: Float = 12.0f,
    private val onCriticalAlertTriggered: (FusedSafetyDecision) -> Unit
) {
    @Volatile
    private var lastTelemetry: CaneTelemetry? = null

    companion object {
        val CANE_SERVICE_UUID: UUID = UUID.fromString("0000FFE0-0000-1000-8000-00805F9B34FB")
        val CANE_CHAR_UUID: UUID = UUID.fromString("0000FFE1-0000-1000-8000-00805F9B34FB")
    }

    /**
     * Parses incoming ASCII telemetry lines:
     * CSV: CANE,forward_cm,ground_cm,pitch,roll,tapping
     */
    fun parseIncomingLine(rawLine: String): CaneTelemetry? {
        val trimmed = rawLine.trim()
        if (!trimmed.startsWith("CANE,")) return null

        val parts = trimmed.split(",")
        if (parts.size < 3) return null

        val forward = parts[1].toFloatOrNull()
        val ground = parts[2].toFloatOrNull()
        val pitch = if (parts.size > 3) parts[3].toFloatOrNull() ?: 0.0f else 0.0f
        val roll = if (parts.size > 4) parts[4].toFloatOrNull() ?: 0.0f else 0.0f
        val tap = if (parts.size > 5) parts[5] == "1" else true

        val packet = CaneTelemetry(
            forwardDistCm = forward,
            groundDistCm = ground,
            pitchDeg = pitch,
            rollDeg = roll,
            caneTapping = tap
        )
        lastTelemetry = packet
        evaluateRealtimeHazard(packet)
        return packet
    }

    /**
     * Immediate hardware-priority check on packet arrival.
     * Physical hazards immediately dispatch without waiting for camera frame cycles.
     */
    private fun evaluateRealtimeHazard(packet: CaneTelemetry) {
        // 1. Forward Ultrasonic Obstacle (head/chest/forward level)
        if (packet.forwardDistCm != null && packet.forwardDistCm < criticalForwardStopCm) {
            val decision = FusedSafetyDecision(
                alertLevel = "CRITICAL_STOP",
                vetoApplied = true,
                descriptionNe = "अगाडि नजिकै अवरोध छ, रोकिनुहोस्!",
                distanceM = packet.forwardDistCm / 100.0f
            )
            onCriticalAlertTriggered(decision)
            return
        }

        // 2. Downward ToF LiDAR Drop-off (Pothole / Open Manhole)
        if (packet.groundDistCm != null) {
            val delta = packet.groundDistCm - packet.nominalGroundCm
            if (delta > potholeDropThresholdCm) {
                val decision = FusedSafetyDecision(
                    alertLevel = "CRITICAL_STOP",
                    vetoApplied = true,
                    descriptionNe = "अगाडि जमिन भासिएको वा खुल्ला खाल्डो छ, रोकिनुहोस्!",
                    distanceM = packet.groundDistCm / 100.0f
                )
                onCriticalAlertTriggered(decision)
                return
            }
        }
    }

    /**
     * Evaluates physical sensors against an optimistic vision report.
     */
    fun evaluateWithVision(visionHazardDetected: Boolean, visionMessageNe: String): FusedSafetyDecision {
        val telemetry = lastTelemetry
        val now = SystemClock.elapsedRealtime()

        if (telemetry != null && (now - telemetry.timestampMs < 350L)) {
            // Forward obstacle check
            if (telemetry.forwardDistCm != null && telemetry.forwardDistCm < criticalForwardStopCm) {
                return FusedSafetyDecision(
                    alertLevel = "CRITICAL_STOP",
                    vetoApplied = !visionHazardDetected,
                    descriptionNe = "अगाडि नजिकै अवरोध छ, रोकिनुहोस्!",
                    distanceM = telemetry.forwardDistCm / 100.0f
                )
            }
            // Ground drop check
            if (telemetry.groundDistCm != null) {
                val delta = telemetry.groundDistCm - telemetry.nominalGroundCm
                if (delta > potholeDropThresholdCm) {
                    return FusedSafetyDecision(
                        alertLevel = "CRITICAL_STOP",
                        vetoApplied = !visionHazardDetected,
                        descriptionNe = "अगाडि जमिन भासिएको वा खुल्ला खाल्डो छ, रोकिनुहोस्!",
                        distanceM = telemetry.groundDistCm / 100.0f
                    )
                }
            }
        }

        // If physical sensors are clear, fall back to vision
        return if (visionHazardDetected) {
            FusedSafetyDecision("WARNING", vetoApplied = false, descriptionNe = visionMessageNe)
        } else {
            FusedSafetyDecision("CLEAR", vetoApplied = false, descriptionNe = "बाटो सफा छ")
        }
    }
}
