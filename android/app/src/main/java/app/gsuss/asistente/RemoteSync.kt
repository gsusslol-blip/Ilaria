package app.gsuss.asistente

import android.content.Context
import android.content.Intent
import android.net.Uri

/**
 * Hybrid PC discovery: LAN UDP → mDNS/last LAN → saved prefs → (UI) Telegram.
 * Always prefers LAN over ngrok/WAN so home use does not burn tunnel sessions.
 */
object RemoteSync {
    const val SYNC_HOST = "sync"
    const val REQUEST_TEXT = "ILARIA_REQUEST_SYNC_URL"

    fun applyDeepLink(prefs: Prefs, uri: Uri?): Boolean {
        if (uri == null) return false
        if (!uri.scheme.equals("ilaria", ignoreCase = true)) return false
        val host = uri.host?.lowercase() ?: return false
        when (host) {
            SYNC_HOST -> {
                val url = uri.getQueryParameter("url")?.trim().orEmpty()
                if (url.isBlank()) return false
                prefs.baseUrl = prefs.normalizeBase(url)
                return true
            }
            "connected", "lan" -> {
                val ip = uri.getQueryParameter("ip")?.trim().orEmpty()
                if (ip.isBlank()) return false
                val lan = prefs.normalizeBase(
                    if (ip.contains("://")) ip else "http://$ip:8787",
                )
                prefs.baseUrl = lan
                prefs.lastLanUrl = lan
                return true
            }
        }
        return false
    }

    /**
     * Phase 1 LanFind → Phase 2 last LAN / ilaria.local → Phase 3 saved (incl. WAN).
     */
    fun resolveHybrid(context: Context, prefs: Prefs): String? {
        val lan = discoverLan(context, prefs)
        if (lan != null) return lan

        val saved = prefs.normalizeBase(prefs.baseUrl)
        if (saved.isNotBlank() && !prefs.looksLikeRouter(saved) && Brain.probe(saved)) {
            if (!prefs.isWanTunnel(saved)) {
                prefs.lastLanUrl = saved
            }
            return saved
        }
        return null
    }

    /** Prefer live LAN even when baseUrl already points at ngrok. */
    fun preferLan(context: Context, prefs: Prefs): String {
        val lan = discoverLan(context, prefs)
        if (lan != null) return lan
        val cur = prefs.normalizeBase(prefs.baseUrl)
        return cur
    }

    private fun discoverLan(context: Context, prefs: Prefs): String? {
        val found = LanFind.find(context)
        if (found != null && Brain.probe(found)) {
            val url = prefs.normalizeBase(found)
            prefs.baseUrl = url
            prefs.lastLanUrl = url
            return url
        }
        for (candidate in listOf(prefs.lastLanUrl, "http://ilaria.local:8787")) {
            val url = prefs.normalizeBase(candidate)
            if (url.isBlank() || prefs.looksLikeRouter(url) || prefs.isWanTunnel(url)) continue
            if (Brain.probe(url)) {
                prefs.baseUrl = url
                prefs.lastLanUrl = url
                return url
            }
        }
        return null
    }

    fun openTelegramSync(context: Context, botUsername: String) {
        val bot = botUsername.trim().removePrefix("@")
        val uri = if (bot.isNotBlank()) {
            Uri.parse("https://t.me/$bot?text=${Uri.encode(REQUEST_TEXT)}")
        } else {
            Uri.parse("https://t.me/")
        }
        context.startActivity(Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}
