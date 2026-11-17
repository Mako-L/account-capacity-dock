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
        if let tokens = account.tokenText {
          Text(tokens).font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(1)
        }
      }
    }
  }
}

struct AgentCell: View {
  let agent: CapacitySnapshot.Agent
  var body: some View {
    HStack(spacing: 10) {
      AgentRing(agent: agent, size: 36)
      VStack(alignment: .leading, spacing: 1) {
        Text(agent.progress.map { "\(Int($0))%" } ?? agent.state)
          .font(.system(size: 16, weight: .semibold, design: .rounded)).monospacedDigit()
          .foregroundStyle(signalColor(agent.signal))
        Text(agent.heading).font(.system(size: 11)).lineLimit(2)
        Text(agent.step.isEmpty ? agent.name : agent.step).font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(1)
        if let subs = agent.subagentText {
          Text(subs).font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(1)
        }
      }
    }
  }
}

struct EmptyHint: View {
  let text: String
  var body: some View {
    VStack(spacing: 8) {
      Image(systemName: "iphone.and.arrow.forward").font(.title2)
      Text(text).font(.footnote).multilineTextAlignment(.center).foregroundStyle(.secondary)
    }
    .padding()
  }
}

// Swipe sideways between the accounts and the agents, like the dock's two modes.
struct ContentView: View {
  @EnvironmentObject private var store: SnapshotStore
  var body: some View {
    TabView {
      NavigationStack {
        Group {
          if let accounts = store.snapshot?.accounts, !accounts.isEmpty {
            List(accounts) { account in AccountCell(account: account) }
          } else {
            EmptyHint(text: "Open Capacity on your iPhone to send your accounts here.")
          }
        }
        .navigationTitle("Capacity")
      }
      NavigationStack {
        Group {
          if let agents = store.snapshot?.agents, !agents.isEmpty {
            List(agents) { agent in AgentCell(agent: agent) }
          } else {
            EmptyHint(text: "Open the Agents tab on your iPhone to send your agents here.")
          }
        }
        .navigationTitle("Agents")
      }
    }
    .tabViewStyle(.verticalPage)
  }
}

@main
struct CapacityWatchApp: App {
  @StateObject private var store = SnapshotStore()
  var body: some Scene {
    WindowGroup { ContentView().environmentObject(store) }
  }
}
