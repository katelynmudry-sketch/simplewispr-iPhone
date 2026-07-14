import SwiftUI

struct ContentView: View {
    @State private var disfluencyList: [String] = SharedSettings.disfluencyList
    @State private var newWord: String = ""

    var body: some View {
        NavigationView {
            List {
                Section("Set up the MyWispr keyboard") {
                    stepRow(1, "Settings → General → Keyboard → Keyboards → Add New Keyboard → MyWispr.")
                    stepRow(2, "Tap MyWispr in the keyboard list, then turn on Allow Full Access. This is required for microphone + on-device speech recognition — nothing leaves your phone.")
                    stepRow(3, "In any app, tap and hold the globe key on the keyboard, choose MyWispr, then tap the mic to dictate.")
                }

                Section {
                    ForEach(disfluencyList, id: \.self) { word in
                        Text(word)
                    }
                    .onDelete { indices in
                        disfluencyList.remove(atOffsets: indices)
                        SharedSettings.disfluencyList = disfluencyList
                    }
                    HStack {
                        TextField("Add word or phrase", text: $newWord)
                        Button("Add") {
                            let trimmed = newWord.trimmingCharacters(in: .whitespaces)
                            guard !trimmed.isEmpty else { return }
                            disfluencyList.append(trimmed)
                            SharedSettings.disfluencyList = disfluencyList
                            newWord = ""
                        }
                        .disabled(newWord.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                } header: {
                    Text("Words to strip out")
                } footer: {
                    Text("These filler words are removed from your dictated text before it's typed. Changes apply immediately, no need to reinstall the keyboard.")
                }
            }
            .navigationTitle("MyWispr")
            .toolbar { EditButton() }
        }
        .navigationViewStyle(.stack)
    }

    private func stepRow(_ number: Int, _ text: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Text("\(number)")
                .font(.headline)
                .frame(width: 24, height: 24)
                .background(Circle().fill(Color.accentColor.opacity(0.15)))
            Text(text)
                .font(.subheadline)
        }
        .padding(.vertical, 4)
    }
}
