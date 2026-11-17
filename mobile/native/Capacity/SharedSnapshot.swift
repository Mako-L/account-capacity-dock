import Foundation
import WatchConnectivity
import WidgetKit

// Hands the latest capacity snapshot to the widget (App Group) and the watch (WatchConnectivity).
@MainActor final class SharedSnapshot: PeachModule {
  init() {}

  func publish(_ json: String) -> [String: String] {
    let defaults = UserDefaults(suiteName: "group.dev.mako.capacity")
    defaults?.set(json, forKey: "capacity.snapshot")
    WidgetCenter.shared.reloadAllTimelines()
    return ["widget": defaults == nil ? "no-app-group" : "written", "watch": WatchLink.shared.send(json)]
  }
}

final class WatchLink: NSObject, WCSessionDelegate, @unchecked Sendable {
  static let shared = WatchLink()
  private var pending: String?

  func send(_ json: String) -> String {
    guard WCSession.isSupported() else { return "unsupported" }
    let session = WCSession.default
    if session.delegate == nil {
      session.delegate = self
    }
    guard session.activationState == .activated else {
      pending = json
      session.activate()
      return "activating"
    }
    return push(json, on: session)
  }

  private func push(_ json: String, on session: WCSession) -> String {
    guard session.isPaired, session.isWatchAppInstalled else { return "no-watch-app" }
    do {
      try session.updateApplicationContext(["snapshot": json])
      return "sent"
    } catch {
      return "failed"
    }
  }

  func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
    guard activationState == .activated, let json = pending else { return }
    pending = nil
    _ = push(json, on: session)
  }

  func sessionDidBecomeInactive(_ session: WCSession) {}

  func sessionDidDeactivate(_ session: WCSession) {
    session.activate()
  }
}
