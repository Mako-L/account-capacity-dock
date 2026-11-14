import SwiftUI
import WatchConnectivity

// The phone pushes the same snapshot it writes for the widget; see native/Capacity/SharedSnapshot.swift.
struct CapacitySnapshot: Codable {
  struct Account: Codable, Identifiable {
    let id: String
    let provider: String
    let email: String
    let used: Double?
    let window: String
    let resetAt: Double?
    let state: String
    let signal: String
  }
  let updatedAt: Double
  let accounts: [Account]
}

@MainActor final class SnapshotStore: NSObject, ObservableObject, WCSessionDelegate {
  static let storageKey = "capacity.snapshot"
  @Published var snapshot: CapacitySnapshot?

  override init() {
    super.init()
    snapshot = Self.decode(UserDefaults.standard.string(forKey: Self.storageKey))
    guard WCSession.isSupported() else { return }
    WCSession.default.delegate = self
    WCSession.default.activate()
  }

  static func decode(_ text: String?) -> CapacitySnapshot? {
    guard let text else { return nil }
    return try? JSONDecoder().decode(CapacitySnapshot.self, from: Data(text.utf8))
  }

  private func receive(_ context: [String: Any]) {
    guard let text = context["snapshot"] as? String, let decoded = Self.decode(text) else { return }
    UserDefaults.standard.set(text, forKey: Self.storageKey)
    snapshot = decoded
  }

  nonisolated func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
    let context = session.receivedApplicationContext as? [String: String] ?? [:]
    Task { @MainActor in self.receive(context) }
  }

  nonisolated func session(_ session: WCSession, didReceiveApplicationContext applicationContext: [String: Any]) {
    let context = applicationContext as? [String: String] ?? [:]
    Task { @MainActor in self.receive(context) }
  }
}

func signalColor(_ name: String) -> Color {
  switch name {
  case "red": return .red
  case "orange": return .orange
  case "yellow": return .yellow
  default: return .green
  }
}

struct ProviderMark: View {
  let provider: String
  var body: some View {
    Image(provider.lowercased()).resizable().renderingMode(.template).scaledToFit()
  }
}

// Same geometry as the dock's AccountRing in dock style: rounded square, 0.30 corner, 4pt stroke.
struct AccountRing: View {
  let account: CapacitySnapshot.Account
  let size: CGFloat
  var body: some View {
    let shape = RoundedRectangle(cornerRadius: size * 0.30, style: .continuous)
    ZStack {
      shape.stroke(.white.opacity(0.12), lineWidth: 4)
      if let used = account.used {
        shape.trim(from: 0, to: used / 100)
          .stroke(signalColor(account.signal), style: StrokeStyle(lineWidth: 4, lineCap: .round))
          .rotationEffect(.degrees(-90))
      }
      ProviderMark(provider: account.provider).frame(width: size * 0.43, height: size * 0.43).foregroundStyle(.white)
    }
    .frame(width: size, height: size)
  }
}

struct AccountCell: View {
  let account: CapacitySnapshot.Account
  var body: some View {
    HStack(spacing: 10) {
      AccountRing(account: account, size: 38)
      VStack(alignment: .leading, spacing: 1) {
        Text(account.used.map { "\(Int($0.rounded()))%" } ?? "—")
          .font(.system(size: 18, weight: .semibold, design: .rounded)).monospacedDigit()
          .foregroundStyle(signalColor(account.signal))
        Text(account.email).font(.system(size: 11)).lineLimit(1)
        if let resetAt = account.resetAt, resetAt > Date().timeIntervalSince1970 {
          Text("\(account.window) · \(Text(Date(timeIntervalSince1970: resetAt), style: .relative))")
            .font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(1)
        } else {
          Text(account.window).font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(1)
        }
      }
    }
  }
}

struct ContentView: View {
  @EnvironmentObject private var store: SnapshotStore
  var body: some View {
    NavigationStack {
      Group {
        if let accounts = store.snapshot?.accounts, !accounts.isEmpty {
          List(accounts) { account in AccountCell(account: account) }
        } else {
          VStack(spacing: 8) {
            Image(systemName: "iphone.and.arrow.forward").font(.title2)
            Text("Open Capacity on your iPhone to send your accounts here.")
              .font(.footnote).multilineTextAlignment(.center).foregroundStyle(.secondary)
          }
          .padding()
        }
      }
      .navigationTitle("Capacity")
    }
  }
}

@main
struct CapacityWatchApp: App {
  @StateObject private var store = SnapshotStore()
  var body: some Scene {
    WindowGroup { ContentView().environmentObject(store) }
  }
}
