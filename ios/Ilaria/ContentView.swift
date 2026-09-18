import SwiftUI
import UIKit

struct Bubble: Identifiable {
    let id = UUID()
    let mine: Bool
    let text: String
}

struct ContentView: View {
    @EnvironmentObject private var prefs: Prefs
    @State private var brain: Brain?
    @State private var log: [Bubble] = []
    @State private var draft = ""
    @State private var busy = false
    @State private var showProfile = false
    @State private var status = "Listo"
    @StateObject private var wake = WakeListenModel()
    @State private var lastTalk: TimeInterval = 0
    @State private var listenOn = false

    var body: some View {
        ZStack {
            Color(red: 0.04, green: 0.04, blue: 0.04).ignoresSafeArea()
            VStack(spacing: 0) {
                HStack {
                    Text("ILARIA")
                        .font(.system(size: 22, weight: .bold, design: .rounded))
                        .foregroundStyle(Color(red: 1, green: 0.16, blue: 0.33))
                    Spacer()
                    Text(status)
                        .font(.caption)
                        .foregroundStyle(.white.opacity(0.55))
                    Button("Perfil") { showProfile = true }
                        .font(.caption.weight(.semibold))
                }
                .padding()

                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 10) {
                            ForEach(log) { b in
                                Text(b.text)
                                    .foregroundStyle(.white)
                                    .padding(12)
                                    .frame(maxWidth: .infinity, alignment: b.mine ? .trailing : .leading)
                                    .background(
                                        RoundedRectangle(cornerRadius: 14)
                                            .fill(b.mine ? Color.white.opacity(0.08) : Color(red: 1, green: 0.16, blue: 0.33).opacity(0.18))
                                    )
                                    .id(b.id)
                            }
                        }
                        .padding(.horizontal)
                    }
                    .onChange(of: log.count) { _, _ in
                        if let last = log.last?.id {
                            withAnimation { proxy.scrollTo(last, anchor: .bottom) }
                        }
                    }
                }

                HStack(spacing: 8) {
                    TextField("escribe una frase", text: $draft)
                        .textFieldStyle(.plain)
                        .padding(12)
                        .background(RoundedRectangle(cornerRadius: 12).fill(Color.white.opacity(0.08)))
                        .foregroundStyle(.white)
                        .disabled(busy)
                    Button(listenOn ? "Oír" : "Mic") {
                        listenOn.toggle()
                        if listenOn {
                            wake.busy = busy
                            wake.lastTalk = lastTalk
                            wake.onBargeIn = { SoloTts.stop() }
                            wake.onHeard = { text in
                                Task { await speakHeard(text) }
                            }
                            wake.start()
                            status = "escuchando — decí Ilaria"
                        } else {
                            wake.stop()
                            status = prefs.loggedIn && !prefs.solo ? "sync PC" : "independiente"
                        }
                    }
                    .buttonStyle(.bordered)
                    .tint(listenOn ? Color(red: 1, green: 0.16, blue: 0.33) : .gray)
                    Button("OK") { Task { await send() } }
                        .buttonStyle(.borderedProminent)
                        .tint(Color(red: 1, green: 0.16, blue: 0.33))
                        .disabled(busy || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                .padding()
            }
        }
        .sheet(isPresented: $showProfile) {
            ProfileSheet()
                .environmentObject(prefs)
        }
        .onAppear {
            if !prefs.inSession { prefs.enterSolo() }
            if brain == nil { brain = Brain(prefs: prefs) }
            UIDevice.current.isBatteryMonitoringEnabled = true
            status = prefs.loggedIn && !prefs.solo ? "sync PC" : "independiente"
        }
        .onChange(of: busy) { _, v in wake.busy = v }
    }

    private func speakHeard(_ text: String) async {
        guard !busy else { return }
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return }
        draft = cleaned
        await send()
    }

    private func send() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        draft = ""
        log.append(Bubble(mine: true, text: text))
        busy = true
        status = "…"
        defer {
            busy = false
            lastTalk = Date().timeIntervalSince1970
            wake.lastTalk = lastTalk
            if listenOn { status = "escuchando — decí Ilaria" }
        }
        do {
            let engine = brain ?? Brain(prefs: prefs)
            brain = engine
            let out = try await engine.chat(text)
            for item in out.phone {
                switch PhoneHands.run(item) {
                case "clear_http":
                    break
                case "screenshot_hint":
                    status = "Captura: lateral + vol ▲"
                case "lock_hint":
                    status = "Bloqueo: botón lateral"
                case "volume_hint":
                    status = "Volumen: botones laterales"
                case let s? where s.hasPrefix("clipboard:"):
                    let clip = String(s.dropFirst("clipboard:".count))
                    let body = clip.isEmpty ? "(vacío)" : clip
                    log.append(Bubble(mine: false, text: "Portapapeles: \(body)"))
                default:
                    break
                }
            }
            log.append(Bubble(mine: false, text: out.text))
            SoloTts.speak(out.text)
            status = out.fromPc ? "PC" : "independiente"
        } catch {
            if let local = PhoneLocal.handle(raw: text, prefs: prefs) {
                for item in local.phone { _ = PhoneHands.run(item) }
                log.append(Bubble(mine: false, text: local.text))
            } else {
                log.append(Bubble(mine: false, text: error.localizedDescription))
            }
            status = "error"
        }
    }
}

struct ProfileSheet: View {
    @EnvironmentObject private var prefs: Prefs
    @Environment(\.dismiss) private var dismiss
    @State private var user = ""
    @State private var pass = ""
    @State private var info = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("El iPhone es independiente. Sincronizar con la PC es opcional (cerebro grande + notas compartidas).")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                Section("Celular (siempre)") {
                    TextField("Tu nombre", text: $prefs.displayName)
                    TextField("Usuario", text: $prefs.username)
                        .textInputAutocapitalization(.never)
                    Button("Usar solo el iPhone") {
                        prefs.enterSolo(user: prefs.username)
                        info = "Independiente. La PC no hace falta."
                    }
                }
                Section("Sincronizar con la PC (opcional)") {
                    TextField("http://192.168.x.x:8787", text: $prefs.baseUrl)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                    Button("Buscar PC en Wi‑Fi") {
                        info = "Buscando…"
                        Task.detached {
                            let found = LanFind.find()
                            await MainActor.run {
                                if let found {
                                    prefs.baseUrl = Prefs.normalizeBase(found)
                                    info = "Encontrada: \(prefs.baseUrl)"
                                    var comps = URLComponents()
                                    comps.scheme = "ilaria"
                                    comps.host = "connected"
                                    comps.queryItems = [URLQueryItem(name: "ip", value: prefs.baseUrl)]
                                    if let deep = comps.url {
                                        UIApplication.shared.open(deep)
                                    }
                                } else {
                                    info = "No encontré la PC. Misma Wi‑Fi y run.bat abierto."
                                }
                            }
                        }
                    }
                    TextField("Bot Telegram (sin @)", text: $prefs.telegramBot)
                        .textInputAutocapitalization(.never)
                    Button("Desconectado: Actualizar URL Remota") {
                        let bot = prefs.telegramBot.trimmingCharacters(in: .whitespacesAndNewlines)
                            .trimmingCharacters(in: CharacterSet(charactersIn: "@"))
                        let encoded = "ILARIA_REQUEST_SYNC_URL".addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
                        let link = bot.isEmpty ? "https://t.me/" : "https://t.me/\(bot)?text=\(encoded)"
                        if let url = URL(string: link) {
                            UIApplication.shared.open(url)
                            info = "Pedí SYNC al bot y tocá ilaria://sync en la respuesta."
                        }
                    }
                    TextField("usuario PC", text: $user)
                        .textInputAutocapitalization(.never)
                    SecureField("clave PC", text: $pass)
                    Button("Sincronizar con la PC") {
                        Task {
                            do {
                                let name = try await Brain(prefs: prefs).login(user: user, password: pass)
                                prefs.solo = false
                                info = "Sincronizado, \(name). El iPhone sigue andando si la PC se apaga."
                            } catch {
                                info = error.localizedDescription
                            }
                        }
                    }
                    if prefs.loggedIn {
                        Toggle("Pausar sync (solo iPhone)", isOn: $prefs.solo)
                        Button("Dejar de sincronizar", role: .destructive) {
                            prefs.logout()
                            info = "PC desconectada. Seguís independiente."
                        }
                    }
                }
                if !info.isEmpty {
                    Section { Text(info) }
                }
            }
            .navigationTitle("Perfil")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cerrar") { dismiss() }
                }
            }
        }
    }
}
