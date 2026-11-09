package com.trinetra.mobile

import android.content.Context
import android.telephony.SmsManager
import android.util.Log
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Dispatches emergency SMS directly through Android native SmsManager over cellular 2G/4G/5G.
 * Operates 100% offline with zero cloud API or third-party SMS gateway dependencies.
 */
class EmergencySmsDispatcher(private val context: Context) {

    companion object {
        private const val TAG = "TrinetraSms"
        private const val SMS_COOLDOWN_MS = 180_000L // 3 minutes cooldown
    }

    private var lastSentTimestampMs: Long = 0L

    fun formatEmergencyMessage(
        userName: String = "हजुर",
        alertReason: String,
        latitude: Double?,
        longitude: Double?,
        batteryPct: Int?
    ): String {
        val timeStr = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())
        val locStr = if (latitude != null && longitude != null) {
            " स्थान: https://maps.google.com/?q=%.5f,%.5f".format(latitude, longitude)
        } else {
            ""
        }
        val battStr = if (batteryPct != null) " (ब्याट्री $batteryPct%)" else ""

        return "[त्रिनेत्र आपतकालीन] $userName: $alertReason।$locStr$battStr समय: $timeStr"
    }

    fun dispatchEmergencySms(
        recipientPhoneNumber: String,
        alertReason: String = "लड्नुभएको शंका",
        latitude: Double? = null,
        longitude: Double? = null,
        batteryPct: Int? = null,
        force: Boolean = false
    ): Boolean {
        val now = System.currentTimeMillis()
        if (!force && (now - lastSentTimestampMs < SMS_COOLDOWN_MS)) {
            Log.w(TAG, "Emergency SMS suppressed due to cooldown window")
            return false
        }

        if (recipientPhoneNumber.isBlank()) {
            Log.e(TAG, "Cannot dispatch SMS: recipient phone number is empty")
            return false
        }

        val messageText = formatEmergencyMessage(
            alertReason = alertReason,
            latitude = latitude,
            longitude = longitude,
            batteryPct = batteryPct
        )

        return try {
            val smsManager: SmsManager = context.getSystemService(SmsManager::class.java)
                ?: @Suppress("DEPRECATION") SmsManager.getDefault()

            val parts = smsManager.divideMessage(messageText)
            if (parts.size > 1) {
                smsManager.sendMultipartTextMessage(recipientPhoneNumber, null, parts, null, null)
            } else {
                smsManager.sendTextMessage(recipientPhoneNumber, null, messageText, null, null)
            }
            lastSentTimestampMs = now
            Log.i(TAG, "Emergency SMS dispatched successfully to $recipientPhoneNumber")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send emergency SMS: ${e.message}", e)
            false
        }
    }
}
