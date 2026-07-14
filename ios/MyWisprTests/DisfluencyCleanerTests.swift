import XCTest

final class DisfluencyCleanerTests: XCTestCase {
    // Mirrors tests/test_postprocess.py's CASES table — keep in sync.
    private let cases: [(String, String)] = [
        ("Um, I think so", "I think so"),
        ("I um went to the store", "I went to the store"),
        ("uh hello there", "Hello there"),
        ("That was, um, pretty good", "That was pretty good"),
        ("Uh, uh, let me think", "Let me think"),

        ("So, I think that's right", "I think that's right"),
        ("it was, like, huge", "it was huge"),
        ("Actually, we should go", "We should go"),
        ("We should go, actually", "We should go"),
        ("Basically, it works", "It works"),
        ("It works, basically", "It works"),
        ("Right, let's do this", "Let's do this"),
        ("You know, it's hard", "It's hard"),
        ("I mean, that's the point", "That's the point"),

        ("I like pizza", "I like pizza"),
        ("turn right here", "turn right here"),
        ("so far so good", "so far so good"),
        ("That's actually correct", "That's actually correct"),
        ("literally on fire", "literally on fire"),
        ("I literally can't even", "I literally can't even"),

        ("So, like, I think", "I think"),
        ("Um, so, basically", ""),

        ("like, we need to talk", "We need to talk"),

        ("I  went", "I went"),
    ]

    func testCleanMatchesPythonReference() {
        let cleaner = DisfluencyCleaner()
        for (input, expected) in cases {
            let result = cleaner.clean(input)
            XCTAssertEqual(result, expected, "Input: \(input)")
        }
    }
}
