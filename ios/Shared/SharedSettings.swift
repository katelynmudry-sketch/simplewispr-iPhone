import Foundation

/// Settings shared between the MyWispr host app and the MyWisprKeyboard extension
/// via an App Group container. Mirrors the relevant subset of src/settings.py.
enum SharedSettings {
    static let appGroupID = "group.com.mywispr.ios"

    private static var defaults: UserDefaults {
        UserDefaults(suiteName: appGroupID) ?? .standard
    }

    private enum Keys {
        static let disfluencyList = "disfluencyList"
        static let languageIdentifier = "languageIdentifier"
    }

    static let defaultDisfluencyList = [
        "um", "uh", "like", "you know", "so", "actually",
        "basically", "literally", "I mean", "right",
    ]

    static var disfluencyList: [String] {
        get { defaults.stringArray(forKey: Keys.disfluencyList) ?? defaultDisfluencyList }
        set { defaults.set(newValue, forKey: Keys.disfluencyList) }
    }

    /// nil means "use the device's current locale" (auto-detect).
    static var languageIdentifier: String? {
        get { defaults.string(forKey: Keys.languageIdentifier) }
        set { defaults.set(newValue, forKey: Keys.languageIdentifier) }
    }
}
