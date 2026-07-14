import Foundation

/// Swift port of src/postprocess.py's `clean()`. Keep behavior in sync with that file —
/// same tier1/tier2 word lists, same regex passes, same normalization order.
struct DisfluencyCleaner {
    static let tier1: [String] = ["um", "uh"]

    static let tier2Defaults: [String] = [
        "like", "you know", "so", "actually", "basically",
        "literally", "I mean", "right",
    ]

    func clean(_ text: String, disfluencyList: [String]? = nil) -> String {
        let list = disfluencyList ?? (Self.tier2Defaults + Self.tier1)
        let loweredList = list.map { $0.lowercased() }

        let tier1Words = Self.tier1.filter { loweredList.contains($0) }
        let tier2Words = list.filter { !Self.tier1.contains($0.lowercased()) }

        var result = text

        // Tier 1: strip wherever found; replace with space so adjacent words don't merge.
        if !tier1Words.isEmpty {
            let alts = tier1Words.map { NSRegularExpression.escapedPattern(for: $0) }.joined(separator: "|")
            let pattern = "(?:,\\s*)?\\b(?:\(alts))\\b(?:,\\s*)?"
            result = Self.replace(result, pattern: pattern, options: [.caseInsensitive], with: " ")
        }

        // Tier 2: strip only when bounded by delimiters.
        if !tier2Words.isEmpty {
            result = Self.applyTier2(result, words: tier2Words)
        }

        result = Self.normalize(result)

        // Re-capitalize only if the first word was removed.
        if let r0 = result.first, let t0 = text.first, r0.lowercased() != t0.lowercased() {
            result = r0.uppercased() + result.dropFirst()
        }

        return result
    }

    private static func applyTier2(_ text: String, words: [String]) -> String {
        // Sort longest first to prevent partial matches (e.g. "I mean" before "I").
        let sorted = words.sorted { $0.count > $1.count }
        var current = text
        var previous: String? = nil

        while previous != current {
            previous = current

            // Pass A: lone fillers (entire remaining text is just the word).
            for word in sorted {
                let w = NSRegularExpression.escapedPattern(for: word)
                current = replace(current, pattern: "^\\s*\(w)\\s*$", options: [.caseInsensitive], with: "")
            }

            // Pass B: sentence-start and sentence-end.
            for word in sorted {
                let w = NSRegularExpression.escapedPattern(for: word)
                current = replace(
                    current,
                    pattern: "(?:^|(?<=[.!?…])\\s*)\(w)\\s*,\\s*",
                    options: [.caseInsensitive, .anchorsMatchLines],
                    with: ""
                )
                current = replace(
                    current,
                    pattern: "\\s*,\\s*\(w)\\s*(?=$|[.!?…])",
                    options: [.caseInsensitive, .anchorsMatchLines],
                    with: ""
                )
            }

            // Pass C: mid-sentence ", WORD," -> " ".
            for word in sorted {
                let w = NSRegularExpression.escapedPattern(for: word)
                current = replace(current, pattern: "\\s*,\\s*\(w)\\s*,\\s*", options: [.caseInsensitive], with: " ")
            }
        }

        return current
    }

    private static func normalize(_ text: String) -> String {
        var result = text
        result = replace(result, pattern: ",\\s*,+", options: [], with: ",")
        result = replace(result, pattern: "^\\s*,\\s*", options: [], with: "")
        result = replace(result, pattern: ",\\s*$", options: [], with: "")
        result = replace(result, pattern: "\\s+([,.?!…])", options: [], with: "$1")
        result = replace(result, pattern: "  +", options: [], with: " ")
        return result.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func replace(
        _ text: String,
        pattern: String,
        options: NSRegularExpression.Options,
        with template: String
    ) -> String {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: options) else { return text }
        let range = NSRange(text.startIndex..., in: text)
        return regex.stringByReplacingMatches(in: text, options: [], range: range, withTemplate: template)
    }
}
