import AVFoundation
import Foundation
import Speech
import SwiftUI

/// On-device wake listen (SFSpeech), same gate as Android WakeListen.
final class WakeListenModel: NSObject, ObservableObject {
    @Published var level: Float = 0
    @Published var enabled = false

    private let speech = SFSpeechRecognizer(locale: Locale(identifier: "es-AR"))
    private var audioEngine: AVAudioEngine?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var firedPartial = false
    private let wake = try! NSRegularExpression(
        pattern: #"\b(ilaria|hilaria|ilaría|oye\s+ilaria|hey\s+ilaria|ok\s+ilaria)\b"#,
        options: [.caseInsensitive]
    )

    var onHeard: ((String) -> Void)?
    var onBargeIn: (() -> Void)?
    var busy: Bool = false
    var lastTalk: TimeInterval = 0
    var followMs: TimeInterval = 22_000

    func start() {
        guard !enabled else { return }
        SFSpeechRecognizer.requestAuthorization { [weak self] status in
            guard status == .authorized else { return }
            AVAudioSession.sharedInstance().requestRecordPermission { ok in
                guard ok else { return }
                DispatchQueue.main.async { self?.beginEngine() }
            }
        }
    }

    func stop() {
        enabled = false
        task?.cancel()
        task = nil
        request?.endAudio()
        request = nil
        audioEngine?.stop()
        audioEngine?.inputNode.removeTap(onBus: 0)
        audioEngine = nil
    }

    private func beginEngine() {
        stop()
        enabled = true
        firedPartial = false
        let engine = AVAudioEngine()
        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            req.append(buffer)
            guard let self else { return }
            let ch = buffer.floatChannelData?[0]
            let n = Int(buffer.frameLength)
            if let ch, n > 0 {
                var sum: Float = 0
                for i in 0..<n { sum += ch[i] * ch[i] }
                let rms = sqrt(sum / Float(n))
                DispatchQueue.main.async { self.level = min(1, rms * 8) }
            }
        }
        engine.prepare()
        do {
            try AVAudioSession.sharedInstance().setCategory(.playAndRecord, mode: .measurement, options: [.defaultToSpeaker, .allowBluetooth])
            try AVAudioSession.sharedInstance().setActive(true)
            try engine.start()
        } catch {
            return
        }
        audioEngine = engine
        request = req
        task = speech?.recognitionTask(with: req) { [weak self] result, error in
            guard let self else { return }
            if let result {
                let text = result.bestTranscription.formattedString
                if result.isFinal {
                    self.handle(text: text, partial: false)
                    self.restartSoon()
                } else {
                    self.handle(text: text, partial: true)
                }
            }
            if error != nil {
                self.restartSoon()
            }
        }
    }

    private func restartSoon() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { [weak self] in
            guard let self, self.enabled else { return }
            self.beginEngine()
        }
    }

    private func handle(text: String, partial: Bool) {
        if busy { return }
        if partial {
            let range = NSRange(text.startIndex..<text.endIndex, in: text)
            if wake.firstMatch(in: text, options: [], range: range) != nil, !firedPartial {
                firedPartial = true
                onBargeIn?()
                if let gated = gate(text), !gated.isEmpty {
                    onHeard?(gated)
                }
            }
            return
        }
        onBargeIn?()
        if let gated = gate(text), !gated.isEmpty {
            onHeard?(gated)
        }
    }

    private func gate(_ raw: String) -> String? {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        let woke = wake.firstMatch(in: text, options: [], range: range) != nil
        let follow = lastTalk > 0 && (Date().timeIntervalSince1970 - lastTalk) * 1000 < followMs
        guard woke || follow else { return nil }
        let cleaned = wake.stringByReplacingMatches(in: text, options: [], range: range, withTemplate: " ")
            .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if woke && cleaned.isEmpty { return "hola" }
        return cleaned.isEmpty ? text : cleaned
    }
}
