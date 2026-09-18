import Foundation
import UIKit

/// Shared preferences for LAN link + solo mode.
@MainActor
final class Prefs: ObservableObject {
    @Published var baseUrl: String {
        didSet { UserDefaults.standard.set(Self.normalizeBase(baseUrl), forKey: "base") }
    }
    @Published var token: String {
        didSet { UserDefaults.standard.set(token, forKey: "token") }
    }
    @Published var username: String {
        didSet { UserDefaults.standard.set(username, forKey: "username") }
    }
    @Published var displayName: String {
        didSet { UserDefaults.standard.set(displayName, forKey: "display") }
    }
    @Published var city: String {
        didSet { UserDefaults.standard.set(city, forKey: "city") }
    }
    @Published var solo: Bool {
        didSet { UserDefaults.standard.set(solo, forKey: "solo") }
    }
    @Published var telegramBot: String {
        didSet {
            UserDefaults.standard.set(
                telegramBot.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "@")),
                forKey: "tg_bot"
            )
        }
    }

    init() {
        let ud = UserDefaults.standard
        baseUrl = ud.string(forKey: "base") ?? ""
        token = ud.string(forKey: "token") ?? ""
        username = ud.string(forKey: "username") ?? ""
        displayName = ud.string(forKey: "display") ?? ""
        city = ud.string(forKey: "city") ?? ""
        // Default independent: phone works without PC until the user opts into sync.
        solo = ud.object(forKey: "solo") == nil ? true : ud.bool(forKey: "solo")
        telegramBot = ud.string(forKey: "tg_bot") ?? ""
    }

    var loggedIn: Bool { !token.isEmpty }
    var inSession: Bool { solo || loggedIn }

    static func normalizeBase(_ raw: String) -> String {
        var value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        while value.hasSuffix("/") { value.removeLast() }
        if value.isEmpty { return "" }
        if !value.hasPrefix("http://") && !value.hasPrefix("https://") {
            value = "http://\(value)"
        }
        while value.hasSuffix("/") { value.removeLast() }
        return value
    }

    static func isWanTunnel(_ raw: String) -> Bool {
        let h = normalizeBase(raw).lowercased()
        if h.isEmpty { return false }
        if h.hasPrefix("https://") { return true }
        return ["ngrok", "loca.lt", "trycloudflare", "cloudflared", "serveo"].contains { h.contains($0) }
    }

    var lastLanUrl: String {
        get { UserDefaults.standard.string(forKey: "lan_base") ?? "" }
        set { UserDefaults.standard.set(Self.normalizeBase(newValue), forKey: "lan_base") }
    }

    /// LAN UDP → last LAN / ilaria.local → keep current if alive.
    func preferLanBase() -> String {
        if let found = LanFind.find(), Self.probeHealth(found) {
            let url = Self.normalizeBase(found)
            baseUrl = url
            lastLanUrl = url
            return url
        }
        for candidate in [lastLanUrl, "http://ilaria.local:8787"] {
            let url = Self.normalizeBase(candidate)
            guard !url.isEmpty, !Self.isWanTunnel(url), Self.probeHealth(url) else { continue }
            baseUrl = url
            lastLanUrl = url
            return url
        }
        return Self.normalizeBase(baseUrl)
    }

    static func probeHealth(_ base: String) -> Bool {
        let root = normalizeBase(base)
        guard let url = URL(string: "\(root)/health") else { return false }
        var ok = false
        let sem = DispatchSemaphore(value: 0)
        var req = URLRequest(url: url, timeoutInterval: 3)
        req.httpMethod = "GET"
        URLSession.shared.dataTask(with: req) { _, resp, _ in
            ok = ((resp as? HTTPURLResponse)?.statusCode ?? 0) < 400
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + 3.5)
        return ok
    }

    func resolveUrl(_ path: String) -> URL? {
        if path.hasPrefix("http://") || path.hasPrefix("https://") {
            return URL(string: path)
        }
        let base = Self.normalizeBase(baseUrl)
        guard !base.isEmpty else { return nil }
        let joined = path.hasPrefix("/") ? "\(base)\(path)" : "\(base)/\(path)"
        return URL(string: joined)
    }

    func logout() {
        token = ""
        solo = true
    }

    func enterSolo(user: String = "") {
        let who = user.trimmingCharacters(in: .whitespacesAndNewlines)
        if !who.isEmpty {
            username = who
            if displayName.isEmpty { displayName = who }
        }
        solo = true
    }

    func facts() -> [String: String] {
        guard let raw = UserDefaults.standard.string(forKey: "facts"),
              let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: String]
        else { return [:] }
        return obj
    }

    func putFact(key: String, value: String) {
        var next = facts()
        next[key.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()] =
            value.trimmingCharacters(in: .whitespacesAndNewlines)
        if let data = try? JSONSerialization.data(withJSONObject: next),
           let raw = String(data: data, encoding: .utf8) {
            UserDefaults.standard.set(raw, forKey: "facts")
        }
    }

    func notes() -> [String] {
        UserDefaults.standard.stringArray(forKey: "notes") ?? []
    }

    func addNote(_ text: String) {
        var items = notes()
        items.insert(text, at: 0)
        UserDefaults.standard.set(Array(items.prefix(80)), forKey: "notes")
    }
}
