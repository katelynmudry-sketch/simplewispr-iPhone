import AVFoundation
import Foundation
import Speech

/// Wraps SFSpeechRecognizer + AVAudioEngine for on-device-only continuous dictation.
/// No audio or text ever leaves the device — requiresOnDeviceRecognition is always true.
final class SpeechRecognizer: NSObject {
    enum RecognizerError: Error {
        case notAuthorized
        case recognizerUnavailable
        case onDeviceUnavailable
    }

    private let audioEngine = AVAudioEngine()
    private var recognizer: SFSpeechRecognizer?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?

    private(set) var isRecording = false

    var onPartialResult: ((String) -> Void)?
    var onFinalResult: ((String) -> Void)?
    var onError: ((Error) -> Void)?

    /// Requests both speech-recognition and microphone permission.
    func requestAuthorization(completion: @escaping (Bool) -> Void) {
        SFSpeechRecognizer.requestAuthorization { speechStatus in
            guard speechStatus == .authorized else {
                DispatchQueue.main.async { completion(false) }
                return
            }
            AVAudioSession.sharedInstance().requestRecordPermission { micGranted in
                DispatchQueue.main.async { completion(micGranted) }
            }
        }
    }

    func start(localeIdentifier: String?) throws {
        guard !isRecording else { return }

        let resolvedRecognizer: SFSpeechRecognizer?
        if let localeIdentifier {
            resolvedRecognizer = SFSpeechRecognizer(locale: Locale(identifier: localeIdentifier))
        } else {
            resolvedRecognizer = SFSpeechRecognizer()
        }
        guard let recognizer = resolvedRecognizer, recognizer.isAvailable else {
            throw RecognizerError.recognizerUnavailable
        }
        guard recognizer.supportsOnDeviceRecognition else {
            throw RecognizerError.onDeviceUnavailable
        }
        self.recognizer = recognizer

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        request.requiresOnDeviceRecognition = true
        self.request = request

        // .record + .measurement + .duckOthers asks for stricter exclusive control of the
        // shared audio session than an app extension (as opposed to the containing app) is
        // reliably granted -- it was failing with AVAudioSessionErrorCodeUnspecified ('what')
        // on setActive. .playAndRecord + .default + .mixWithOthers is the gentler combination
        // extensions have better luck with.
        let audioSession = AVAudioSession.sharedInstance()
        try audioSession.setCategory(.playAndRecord, mode: .default, options: .mixWithOthers)
        try audioSession.setActive(true, options: .notifyOthersOnDeactivation)

        let inputNode = audioEngine.inputNode
        let recordingFormat = inputNode.outputFormat(forBus: 0)
        inputNode.removeTap(onBus: 0)
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { [weak self] buffer, _ in
            self?.request?.append(buffer)
        }

        audioEngine.prepare()
        try audioEngine.start()
        isRecording = true

        task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            guard let self else { return }
            if let result {
                let text = result.bestTranscription.formattedString
                if result.isFinal {
                    self.onFinalResult?(text)
                } else {
                    self.onPartialResult?(text)
                }
            }
            if let error {
                self.onError?(error)
            }
        }
    }

    /// Stops capturing audio and signals end-of-input; the final transcript
    /// arrives shortly after via onFinalResult.
    func stop() {
        guard isRecording else { return }
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        request?.endAudio()
        isRecording = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    func cancel() {
        task?.cancel()
        task = nil
        stop()
    }
}
