import SwiftUI
import WatchConnectivity
import WidgetKit

@MainActor final class SnapshotStore: NSObject, ObservableObject, WCSessionDelegate {
  @Published var snapshot: CapacitySnapshot?

  override init() {
    super.init()
    snapshot = WatchShelf.load()
    guard WCSession.isSupported() else { return }
    WCSession.default.delegate = self
    WCSession.default.activate()
  }

  private func receive(_ context: [String: Any]) {
    guard let text = context["snapshot"] as? String, let decoded = CapacitySnapshot.decode(text) else { return }
    WatchShelf.save(text)
    snapshot = decoded
    WidgetCenter.shared.reloadAllTimelines()
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
