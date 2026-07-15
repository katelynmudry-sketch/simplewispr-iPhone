import UIKit

/// Custom keyboard: tap the mic to start dictating, tap again to stop.
/// The final transcript is cleaned (DisfluencyCleaner, same rules as the Mac app's
/// postprocess.py) and inserted at the cursor via textDocumentProxy — this is the
/// iOS equivalent of the Mac app's auto-paste step.
final class KeyboardViewController: UIInputViewController {
    private let recognizer = SpeechRecognizer()
    private let cleaner = DisfluencyCleaner()

    private let micButton = UIButton(type: .system)
    private let statusLabel = UILabel()
    private let backspaceButton = UIButton(type: .system)
    private let nextKeyboardButton = UIButton(type: .system)

    private var isRecording = false

    override func viewDidLoad() {
        super.viewDidLoad()
        setupUI()
        wireRecognizer()
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        nextKeyboardButton.isHidden = !needsInputModeSwitchKey
    }

    private func setupUI() {
        view.backgroundColor = .secondarySystemBackground
        view.heightAnchor.constraint(equalToConstant: 216).isActive = true

        micButton.translatesAutoresizingMaskIntoConstraints = false
        micButton.setImage(UIImage(systemName: "mic.fill"), for: .normal)
        micButton.tintColor = .white
        micButton.backgroundColor = .systemBlue
        micButton.layer.cornerRadius = 32
        micButton.addTarget(self, action: #selector(micTapped), for: .touchUpInside)
        view.addSubview(micButton)

        statusLabel.translatesAutoresizingMaskIntoConstraints = false
        statusLabel.text = "Tap to speak"
        statusLabel.textAlignment = .center
        statusLabel.font = .preferredFont(forTextStyle: .footnote)
        statusLabel.textColor = .secondaryLabel
        statusLabel.numberOfLines = 2
        view.addSubview(statusLabel)

        backspaceButton.translatesAutoresizingMaskIntoConstraints = false
        backspaceButton.setImage(UIImage(systemName: "delete.left"), for: .normal)
        backspaceButton.addTarget(self, action: #selector(backspaceTapped), for: .touchUpInside)
        view.addSubview(backspaceButton)

        nextKeyboardButton.translatesAutoresizingMaskIntoConstraints = false
        nextKeyboardButton.setImage(UIImage(systemName: "globe"), for: .normal)
        nextKeyboardButton.addTarget(self, action: #selector(handleInputModeList(from:with:)), for: .allTouchEvents)
        view.addSubview(nextKeyboardButton)

        NSLayoutConstraint.activate([
            micButton.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            micButton.topAnchor.constraint(equalTo: view.topAnchor, constant: 24),
            micButton.widthAnchor.constraint(equalToConstant: 64),
            micButton.heightAnchor.constraint(equalToConstant: 64),

            statusLabel.topAnchor.constraint(equalTo: micButton.bottomAnchor, constant: 8),
            statusLabel.centerXAnchor.constraint(equalTo: view.centerXAnchor),

            backspaceButton.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16),
            backspaceButton.centerYAnchor.constraint(equalTo: micButton.centerYAnchor),
            backspaceButton.widthAnchor.constraint(equalToConstant: 44),
            backspaceButton.heightAnchor.constraint(equalToConstant: 44),

            nextKeyboardButton.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16),
            nextKeyboardButton.centerYAnchor.constraint(equalTo: micButton.centerYAnchor),
            nextKeyboardButton.widthAnchor.constraint(equalToConstant: 44),
            nextKeyboardButton.heightAnchor.constraint(equalToConstant: 44),
        ])
    }

    private func wireRecognizer() {
        recognizer.onFinalResult = { [weak self] text in
            self?.handleFinalTranscript(text)
        }
        recognizer.onError = { [weak self] error in
            self?.handleError(error)
        }
    }

    @objc private func micTapped() {
        guard hasFullAccess else {
            statusLabel.text = "Enable “Allow Full Access” in Settings"
            return
        }
        if isRecording {
            stopRecording()
        } else {
            startRecording()
        }
    }

    private func startRecording() {
        statusLabel.text = "Requesting access…"
        recognizer.requestAuthorization { [weak self] granted in
            guard let self else { return }
            guard granted else {
                self.statusLabel.text = "Microphone / Speech access not authorized"
                return
            }
            do {
                try self.recognizer.start(localeIdentifier: SharedSettings.languageIdentifier)
                self.isRecording = true
                self.micButton.backgroundColor = .systemRed
                self.statusLabel.text = "Listening…"
            } catch {
                self.handleError(error)
            }
        }
    }

    private func stopRecording() {
        recognizer.stop()
        isRecording = false
        micButton.backgroundColor = .systemBlue
        statusLabel.text = "Cleaning up…"
    }

    private func handleFinalTranscript(_ text: String) {
        let cleaned = cleaner.clean(text, disfluencyList: SharedSettings.disfluencyList)
        if !cleaned.isEmpty {
            textDocumentProxy.insertText(cleaned)
        }
        statusLabel.text = "Tap to speak"
    }

    private func handleError(_ error: Error) {
        // Surfaces the raw domain/code (not just a friendly message) while on-device
        // testing is still turning up new failure modes — revert to a plain message
        // once recognition is verified working end-to-end.
        isRecording = false
        micButton.backgroundColor = .systemBlue
        let nsError = error as NSError
        statusLabel.text = "\(nsError.domain) (\(nsError.code)) — try again"
    }

    @objc private func backspaceTapped() {
        textDocumentProxy.deleteBackward()
    }
}
