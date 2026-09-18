package app.gsuss.asistente

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private val Pink = Color(0xFFF8B4C8)
private val Bg = Color(0xFF0B0B0B)
private val Mute = Color(0xFFC9A0AE)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        AlertNotify.ensureChannel(this)
        val need = mutableListOf(
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.CAMERA,
            Manifest.permission.ACCESS_COARSE_LOCATION,
            Manifest.permission.ACCESS_FINE_LOCATION,
        )
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            need.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        val missing = need.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 41)
        }
        val prefs = Prefs(this)
        RemoteSync.applyDeepLink(prefs, intent?.data)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme(primary = Pink, background = Bg, surface = Bg)) {
                AppRoot(prefs)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        RemoteSync.applyDeepLink(Prefs(this), intent.data)
    }
}

private data class Bubble(val mine: Boolean, val text: String)

@Composable
private fun AppRoot(prefs: Prefs) {
    var screen by remember { mutableStateOf(if (prefs.inSession) "chat" else "welcome") }
    val context = LocalContext.current
    val notes = remember { NotesCache(context, prefs) }
    LaunchedEffect(Unit) {
        withContext(Dispatchers.IO) {
            try {
                AppUpdate.applyOnLaunch(context, prefs)
            } catch (_: Exception) {
            }
        }
    }
    Box(
        Modifier
            .fillMaxSize()
            .background(Bg)
            .statusBarsPadding()
            .navigationBarsPadding()
            .imePadding(),
    ) {
        when (screen) {
            "welcome" -> Column(Modifier = Modifier.fillMaxSize().padding(20.dp)) {
                Welcome(prefs) { screen = "chat" }
            }
            "chat" -> Chat(
                prefs,
                notes,
                onProfile = { screen = "profile" },
                onOut = { screen = "welcome" },
            )
            "profile" -> Column(Modifier = Modifier.fillMaxSize().padding(20.dp)) {
                Profile(prefs, notes, onBack = { screen = "chat" })
            }
        }
    }
}

@Composable
private fun Welcome(prefs: Prefs, onIn: () -> Unit) {
    val context = LocalContext.current
    var mode by remember { mutableStateOf("solo") } // solo | login | register
    var user by remember { mutableStateOf(prefs.username) }
    var pass by remember { mutableStateOf("") }
    var name by remember { mutableStateOf(prefs.displayName) }
    var city by remember { mutableStateOf(prefs.city.ifBlank { "Buenos Aires" }) }
    var err by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    Column(Modifier = Modifier.verticalScroll(rememberScrollState())) {
        Text("ILARIA", color = Pink, letterSpacing = 8.sp, modifier = Modifier.padding(bottom = 8.dp))
        Text(
            "App independiente en tu celular. Pensá, anotá y abrí apps sin la PC. " +
                "Si querés, más adelante sincronizás con Ilaria en la computadora.",
            color = Mute,
            fontSize = 14.sp,
            modifier = Modifier.padding(bottom = 16.dp),
        )
        Button(
            onClick = {
                err = ""
                busy = true
                scope.launch {
                    try {
                        withContext(Dispatchers.IO) {
                            prefs.enterSolo(user.ifBlank { "celular" })
                            SoloTts.warm(context)
                        }
                        onIn()
                    } catch (e: Exception) {
                        err = e.message ?: "No pude abrir el modo celular."
                    } finally {
                        busy = false
                    }
                }
            },
            enabled = !busy,
            colors = ButtonDefaults.buttonColors(containerColor = Pink, contentColor = Bg),
            modifier = Modifier.fillMaxWidth(),
        ) { Text(if (busy && mode == "solo") "…" else "Empezar en el celular") }

        Text(
            "Sincronizar con la PC (opcional)",
            color = Mute,
            fontSize = 12.sp,
            modifier = Modifier.padding(top = 28.dp, bottom = 8.dp),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            Button(
                onClick = { mode = "login"; err = "" },
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (mode == "login") Pink else Pink.copy(alpha = 0.25f),
                    contentColor = if (mode == "login") Bg else Color.White,
                ),
                modifier = Modifier.weight(1f),
            ) { Text("Enlazar PC") }
            Button(
                onClick = { mode = "register"; err = "" },
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (mode == "register") Pink else Pink.copy(alpha = 0.25f),
                    contentColor = if (mode == "register") Bg else Color.White,
                ),
                modifier = Modifier.weight(1f),
            ) { Text("Crear en PC") }
        }
        if (mode == "login" || mode == "register") {
            Field("Usuario", user) { user = it }
            Field(
                if (mode == "register") "Contraseña (mín. 8)" else "Contraseña de la PC",
                pass,
                password = true,
            ) { pass = it }
            if (mode == "register") {
                Field("Tu nombre", name) { name = it }
                Field("Ciudad", city) { city = it }
                Text(
                    "Crea la cuenta en la PC de esta Wi‑Fi. El celular sigue funcionando solo si la PC se apaga.",
                    color = Mute,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
        }
        if (err.isNotBlank()) Text(err, color = Color(0xFFFF5A6A), modifier = Modifier.padding(top = 8.dp))
        if (mode == "register") {
            Button(
                onClick = {
                    err = ""
                    busy = true
                    scope.launch {
                        try {
                            if (user.isBlank() || pass.length < 8) {
                                throw IllegalStateException("Usuario y contraseña de al menos 8 caracteres.")
                            }
                            withContext(Dispatchers.IO) {
                                prefs.baseUrl = resolvePc(context, prefs)
                                Brain(prefs).register(
                                    user = user,
                                    password = pass,
                                    name = name.ifBlank { user },
                                    city = city,
                                    packs = listOf("diario", "estudio"),
                                    groqKey = "",
                                )
                                prefs.solo = false
                            }
                            onIn()
                        } catch (e: Exception) {
                            err = e.message ?: "No pude crear la cuenta en la PC."
                        } finally {
                            busy = false
                        }
                    }
                },
                enabled = !busy,
                colors = ButtonDefaults.buttonColors(containerColor = Pink.copy(alpha = 0.85f), contentColor = Bg),
                modifier = Modifier.padding(top = 16.dp).fillMaxWidth(),
            ) { Text(if (busy) "…" else "Crear cuenta y sincronizar") }
        } else if (mode == "login") {
            Button(
                onClick = {
                    err = ""
                    busy = true
                    scope.launch {
                        try {
                            if (user.isBlank() || pass.isBlank()) {
                                throw IllegalStateException("Usuario y contraseña para la PC.")
                            }
                            withContext(Dispatchers.IO) {
                                prefs.baseUrl = resolvePc(context, prefs)
                                Brain(prefs).login(user, pass)
                                prefs.solo = false
                            }
                            onIn()
                        } catch (e: Exception) {
                            err = e.message ?: "No pude conectar con la PC."
                        } finally {
                            busy = false
                        }
                    }
                },
                enabled = !busy,
                colors = ButtonDefaults.buttonColors(containerColor = Pink.copy(alpha = 0.85f), contentColor = Bg),
                modifier = Modifier.padding(top = 16.dp).fillMaxWidth(),
            ) { Text(if (busy) "…" else "Enlazar y sincronizar") }
        }
    }
}

private fun resolvePc(context: android.content.Context, prefs: Prefs): String {
    val hybrid = RemoteSync.resolveHybrid(context, prefs)
    if (hybrid != null) return hybrid
    throw IllegalStateException(
        "Sin LAN ni URL remota viva. En Perfil: «Actualizar URL remota» (Telegram) " +
            "o tocá el link ilaria://sync que te manda el bot.",
    )
}

@Composable
private fun Chat(prefs: Prefs, notes: NotesCache, onProfile: () -> Unit, onOut: () -> Unit) {
    val context = LocalContext.current
    val brain = remember { Brain(prefs) }
    val log = remember { mutableStateListOf<Bubble>() }
    var input by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var online by remember { mutableStateOf(true) }
    var lastOnline by remember { mutableStateOf(false) }
    var lastTalk by remember { mutableStateOf(0L) }
    var mood by remember { mutableStateOf(OrbMood.Listen) }
    var caption by remember { mutableStateOf("") }
    var showCaption by remember { mutableStateOf(false) }
    var feedOpen by remember { mutableStateOf(false) }
    var captionJob by remember { mutableStateOf<Job?>(null) }
    var voice by remember { mutableFloatStateOf(0f) }
    val scope = rememberCoroutineScope()
    var pcLinked by remember { mutableStateOf(prefs.loggedIn) }

    LaunchedEffect(Unit) { SoloTts.warm(context) }

    fun hideCaptionLater() {
        captionJob?.cancel()
        captionJob = scope.launch {
            delay(7_000)
            showCaption = false
            if (!busy) mood = OrbMood.Listen
        }
    }

    fun speakHeard(text: String) {
        if (text.isBlank() || busy) return
        log.add(Bubble(true, text))
        captionJob?.cancel()
        caption = ""
        showCaption = true
        busy = true
        mood = OrbMood.Think
        scope.launch {
            val out = withContext(Dispatchers.IO) {
                try {
                    val local = PhoneLocal.handle(context, text, notes, prefs)
                    if (local != null) {
                        local
                    } else if (!prefs.solo && prefs.token.isNotBlank() && brain.heartbeat()) {
                        brain.replyStream(text, speak = true, DeviceSnap.json(context)) { token ->
                            scope.launch(Dispatchers.Main.immediate) {
                                caption += token
                                showCaption = true
                            }
                        }
                    } else {
                        ChatOut(
                            PhoneLocal.fallback(
                                prefs,
                                linked = prefs.token.isNotBlank() && !prefs.solo,
                            ),
                        )
                    }
                } catch (e: Exception) {
                    val local = PhoneLocal.handle(context, text, notes, prefs)
                    local ?: ChatOut(
                        e.message?.takeIf { prefs.token.isNotBlank() }
                            ?: PhoneLocal.fallback(prefs, linked = false),
                    )
                }
            }
            val reply = out.text
            out.phone.forEach { item ->
                when (val signal = PhoneHands.run(context, item)) {
                    "clear_http" -> brain.rebuildClients()
                    "refresh_device_snap" -> { /* next chat already ships DeviceSnap */ }
                    "screenshot_hint" -> {
                        caption = "Para capturar: Power + Volumen abajo."
                    }
                    else -> {
                        if (signal != null && signal.startsWith("clipboard:")) {
                            val clip = signal.removePrefix("clipboard:").ifBlank { "(vacío)" }
                            caption = "Portapapeles: $clip"
                            log.add(Bubble(false, "Portapapeles: $clip"))
                        }
                    }
                }
            }
            if (caption.isBlank()) caption = reply
            if (!out.fromPc) SoloTts.say(reply)
            log.add(Bubble(false, reply))
            lastTalk = System.currentTimeMillis()
            mood = OrbMood.Speak
            busy = false
            hideCaptionLater()
        }
    }

    WakeListen(
        enabled = true,
        busy = busy,
        onRms = { level -> voice = level },
        onBargeIn = {
            SoloTts.stop()
            brain.stopAudio()
        },
        onHeard = { raw ->
            if (busy) return@WakeListen
            val gated = gateWake(raw, followMs = 22_000L, lastTalk = lastTalk)
            if (gated.isNotBlank()) speakHeard(gated)
        },
    )
    LaunchedEffect(Unit) {
        while (true) {
            val ok = withContext(Dispatchers.IO) {
                try {
                    if (brain.heartbeat()) {
                        true
                    } else {
                        val found = LanFind.find(context) ?: return@withContext false
                        prefs.baseUrl = found
                        brain.heartbeat()
                    }
                } catch (_: Exception) {
                    false
                }
            }
            online = ok
            pcLinked = ok && prefs.token.isNotBlank()
            if (ok && prefs.token.isNotBlank()) {
                try {
                    AlertNotify.poll(context, brain, prefs)
                } catch (_: Exception) {
                }
            }
            if (ok && !lastOnline) {
                if (prefs.token.isNotBlank()) {
                    try {
                        notes.syncWith(brain)
                    } catch (_: Exception) {
                    }
                }
                try {
                    AppUpdate.applyOnLaunch(context, prefs)
                } catch (_: Exception) {
                }
            }
            lastOnline = ok
            if (!busy) mood = OrbMood.Listen
            delay(5_000)
        }
    }
    LaunchedEffect(Unit) {
        val welcome = withContext(Dispatchers.IO) {
            try {
                if (!prefs.solo && prefs.token.isNotBlank() && brain.heartbeat()) brain.welcome()
                else "Estoy en el celular, ${prefs.displayName.ifBlank { prefs.username }.ifBlank { "hola" }}. Independiente; sincronizá con la PC cuando quieras."
            } catch (e: Exception) {
                "Estoy en el celular. ${e.message ?: ""}".trim()
            }
        }
        val line = welcome.ifBlank { "En línea, ${prefs.displayName}." }
        log.clear()
        log.add(Bubble(false, line))
        caption = line
        showCaption = true
        mood = OrbMood.Speak
        hideCaptionLater()
    }
    val density = LocalDensity.current
    val imeOpen = WindowInsets.ime.getBottom(density) > 0
    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            if (!pcLinked) {
                Text(
                    if (prefs.token.isBlank()) {
                        "Modo independiente · en Perfil podés sincronizar con la PC cuando quieras"
                    } else {
                        "PC fuera de alcance · sigo en el celular. Tocá para buscarla."
                    },
                    color = Pink,
                    fontSize = 13.sp,
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(Color(0xFF1A1216))
                        .clickable {
                            scope.launch {
                                online = withContext(Dispatchers.IO) {
                                    try {
                                        if (brain.heartbeat()) true
                                        else {
                                            val found = LanFind.find(context) ?: return@withContext false
                                            prefs.baseUrl = found
                                            brain.heartbeat()
                                        }
                                    } catch (_: Exception) {
                                        false
                                    }
                                }
                                pcLinked = online && prefs.token.isNotBlank()
                            }
                        }
                        .padding(10.dp),
                )
            }
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("ILARIA", color = Pink, letterSpacing = 6.sp)
                Row {
                    TextButton(onClick = { feedOpen = !feedOpen }) {
                        Text(if (feedOpen) "Orbe" else "Ver chat", color = Pink)
                    }
                    TextButton(onClick = onProfile) { Text("Perfil", color = Pink) }
                    TextButton(
                        onClick = {
                            scope.launch {
                                withContext(Dispatchers.IO) {
                                    try {
                                        brain.logoutRemote()
                                    } finally {
                                        prefs.solo = false
                                    }
                                }
                                onOut()
                            }
                        },
                    ) { Text("Salir", color = Pink) }
                }
            }
            if (feedOpen) {
                LazyColumn(
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp),
                ) {
                    items(log) { bubble ->
                        Text(
                            bubble.text,
                            color = if (bubble.mine) Color(0xFFC9D6DA) else Pink,
                            modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
                        )
                    }
                }
            } else {
                Spacer(Modifier.weight(1f))
            }
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                OutlinedTextField(
                    value = input,
                    onValueChange = { input = it },
                    modifier = Modifier.weight(1f),
                    enabled = !busy,
                    singleLine = true,
                    placeholder = { Text("Escribí o decí Ilaria…", color = Mute) },
                    colors = fieldColors(),
                )
                Button(
                    onClick = {
                        val text = input.trim()
                        if (text.isEmpty() || busy) return@Button
                        input = ""
                        speakHeard(text)
                    },
                    enabled = !busy,
                    colors = ButtonDefaults.buttonColors(containerColor = Pink, contentColor = Bg),
                ) { Text(if (busy) "…" else "OK") }
            }
        }
        // Orb sits above the composer; hide while typing so the keyboard never covers the field.
        if (!imeOpen && !feedOpen) {
            Column(
                modifier = Modifier
                    .align(Alignment.BottomEnd)
                    .padding(end = 12.dp, bottom = 96.dp, start = 40.dp),
                horizontalAlignment = Alignment.End,
            ) {
                if (showCaption && caption.isNotBlank()) {
                    Text(
                        caption,
                        color = Color.White,
                        fontSize = 18.sp,
                        modifier = Modifier
                            .padding(bottom = 16.dp)
                            .background(Color(0x33FFFFFF), RoundedCornerShape(20.dp))
                            .padding(horizontal = 16.dp, vertical = 12.dp),
                    )
                }
                IlariaOrb(
                    mood = mood,
                    voice = if (busy) 0f else voice,
                )
                Text(
                    "Siempre oye. Recién reacciona si decís Ilaria.",
                    color = Mute,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
        }
    }
}

@Composable
private fun Profile(prefs: Prefs, notes: NotesCache, onBack: () -> Unit) {
    var host by remember { mutableStateOf(prefs.baseUrl) }
    var user by remember { mutableStateOf(prefs.username) }
    var pass by remember { mutableStateOf("") }
    var name by remember { mutableStateOf(prefs.displayName) }
    var city by remember { mutableStateOf(prefs.city.ifBlank { "Buenos Aires" }) }
    var creating by remember { mutableStateOf(false) }
    var err by remember { mutableStateOf("") }
    var ok by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
        TextButton(onClick = onBack) { Text("← Chat", color = Pink) }
        Text(
            "El celular es independiente. Sincronizar con la PC es opcional (cerebro grande + notas compartidas).",
            color = Mute,
            fontSize = 13.sp,
            modifier = Modifier.padding(bottom = 8.dp),
        )
        Text(
            "Sincronizar con la PC (opcional)",
            color = Pink,
            fontSize = 12.sp,
            modifier = Modifier.padding(top = 4.dp, bottom = 8.dp),
        )
        Field("URL de la PC", host) { host = it }
        Field("Bot Telegram (sin @)", prefs.telegramBot) { prefs.telegramBot = it }
        Field("Usuario PC", user) { user = it }
        Field("Contraseña PC", pass, password = true) { pass = it }
        if (creating) {
            Field("Tu nombre", name) { name = it }
            Field("Ciudad", city) { city = it }
        }
        if (err.isNotBlank()) Text(err, color = Color(0xFFFF5A6A), modifier = Modifier.padding(top = 8.dp))
        if (ok.isNotBlank()) Text(ok, color = Pink, modifier = Modifier.padding(top = 8.dp))
        Button(
            onClick = {
                err = ""
                ok = ""
                scope.launch {
                    val found = withContext(Dispatchers.IO) { LanFind.find(context) }
                    if (found == null) {
                        err = "No encuentro Ilaria en el Wi-Fi."
                    } else {
                        host = found
                        prefs.baseUrl = found
                        ok = "Encontré $found"
                    }
                }
            },
            colors = ButtonDefaults.buttonColors(containerColor = Pink, contentColor = Bg),
            modifier = Modifier.padding(top = 16.dp),
        ) { Text("Buscar PC") }
        Button(
            onClick = {
                err = ""
                ok = ""
                scope.launch {
                    val hybrid = withContext(Dispatchers.IO) { RemoteSync.resolveHybrid(context, prefs) }
                    if (hybrid != null) {
                        host = hybrid
                        ok = "PC lista: $hybrid"
                    } else {
                        err = "Desconectado: actualizá la URL remota por Telegram."
                        RemoteSync.openTelegramSync(context, prefs.telegramBot)
                    }
                }
            },
            colors = ButtonDefaults.buttonColors(
                containerColor = Color(0xFFFF5A6A),
                contentColor = Color.White,
            ),
            modifier = Modifier.padding(top = 8.dp),
        ) { Text("Desconectado: Actualizar URL Remota") }
        Button(
            onClick = {
                creating = !creating
                err = ""
                ok = ""
            },
            colors = ButtonDefaults.buttonColors(
                containerColor = if (creating) Pink else Pink.copy(alpha = 0.35f),
                contentColor = if (creating) Bg else Color.White,
            ),
            modifier = Modifier.padding(top = 8.dp),
        ) { Text(if (creating) "Cancelar crear cuenta" else "Crear cuenta nueva en la PC") }
        if (creating) {
            Button(
                onClick = {
                    err = ""
                    ok = ""
                    scope.launch {
                        try {
                            if (user.isBlank() || pass.length < 8) {
                                throw IllegalStateException("Usuario y contraseña de al menos 8 caracteres.")
                            }
                            withContext(Dispatchers.IO) {
                                prefs.baseUrl = host.ifBlank { resolvePc(context, prefs) }
                                val brain = Brain(prefs)
                                brain.register(
                                    user = user,
                                    password = pass,
                                    name = name.ifBlank { user },
                                    city = city,
                                    packs = listOf("diario", "estudio"),
                                    groqKey = "",
                                )
                                notes.syncWith(brain)
                                prefs.solo = false
                            }
                            creating = false
                            ok = "Cuenta creada. Celular + PC sincronizados."
                        } catch (e: Exception) {
                            err = e.message ?: "No pude crear la cuenta."
                        }
                    }
                },
                colors = ButtonDefaults.buttonColors(containerColor = Pink, contentColor = Bg),
                modifier = Modifier.padding(top = 8.dp),
            ) { Text("Crear y sincronizar") }
        } else {
            Button(
                onClick = {
                    err = ""
                    ok = ""
                    scope.launch {
                        try {
                            if (user.isBlank() || pass.isBlank()) {
                                throw IllegalStateException("Usuario y contraseña de la PC.")
                            }
                            withContext(Dispatchers.IO) {
                                prefs.baseUrl = host.ifBlank { resolvePc(context, prefs) }
                                val brain = Brain(prefs)
                                brain.login(user, pass)
                                notes.syncWith(brain)
                                prefs.solo = false
                            }
                            ok = "Sincronizado. El celular sigue andando si la PC se apaga."
                        } catch (e: Exception) {
                            err = e.message ?: "No pude enlazar."
                        }
                    }
                },
                colors = ButtonDefaults.buttonColors(containerColor = Pink, contentColor = Bg),
                modifier = Modifier.padding(top = 8.dp),
            ) { Text("Sincronizar con la PC") }
        }
        Button(
            onClick = {
                err = ""
                ok = ""
                scope.launch {
                    try {
                        withContext(Dispatchers.IO) {
                            if (prefs.token.isBlank()) throw IllegalStateException("Primero enlazá la PC.")
                            notes.syncWith(Brain(prefs))
                        }
                        ok = "Notas y datos al día."
                    } catch (e: Exception) {
                        err = e.message ?: "No pude sincronizar."
                    }
                }
            },
            colors = ButtonDefaults.buttonColors(containerColor = Pink, contentColor = Bg),
            modifier = Modifier.padding(top = 8.dp),
        ) { Text("Sincronizar ahora") }
        if (prefs.token.isNotBlank()) {
            Text(
                if (prefs.solo) {
                    "Sincronización en pausa: usás solo el celular."
                } else {
                    "Sincronización activa con la PC."
                },
                color = Mute,
                fontSize = 12.sp,
                modifier = Modifier.padding(top = 12.dp),
            )
            Button(
                onClick = {
                    prefs.solo = !prefs.solo
                    ok = if (prefs.solo) {
                        "Solo celular. La PC queda enlazada por si querés volver."
                    } else {
                        "Sincronización con PC reactivada."
                    }
                    err = ""
                },
                colors = ButtonDefaults.buttonColors(
                    containerColor = Pink.copy(alpha = 0.35f),
                    contentColor = Color.White,
                ),
                modifier = Modifier.padding(top = 8.dp).fillMaxWidth(),
            ) {
                Text(if (prefs.solo) "Reactivar sync con PC" else "Pausar sync (solo celular)")
            }
        }
        Button(
            onClick = {
                prefs.baseUrl = host
                onBack()
            },
            colors = ButtonDefaults.buttonColors(containerColor = Pink, contentColor = Bg),
            modifier = Modifier.padding(top = 8.dp),
        ) { Text("Guardar URL") }
        TextButton(
            onClick = {
                Brain(prefs).let { brain ->
                    scope.launch {
                        withContext(Dispatchers.IO) {
                            try {
                                brain.logoutRemote()
                            } finally {
                                prefs.unlinkPc()
                            }
                        }
                        ok = "PC desconectada. Seguís independiente en el celular."
                    }
                }
            },
        ) { Text("Dejar de sincronizar (solo celular)", color = Mute) }
    }
}

@Composable
private fun Field(label: String, value: String, password: Boolean = false, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        visualTransformation = if (password) {
            androidx.compose.ui.text.input.PasswordVisualTransformation()
        } else {
            androidx.compose.ui.text.input.VisualTransformation.None
        },
        colors = fieldColors(),
    )
}

@Composable
private fun fieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = Pink,
    unfocusedBorderColor = Pink.copy(alpha = 0.3f),
    focusedLabelColor = Pink,
    unfocusedLabelColor = Mute,
    cursorColor = Pink,
    focusedTextColor = Color.White,
    unfocusedTextColor = Color.White,
)
