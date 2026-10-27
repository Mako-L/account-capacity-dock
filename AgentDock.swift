import AppKit
import Combine
import SwiftUI

// The agents dock: a second floating dock with a ring per running coding agent.
// agents.py reads Herdr, Claude Code and Codex; this file only draws its snapshot.

struct AgentStep: Codable, Hashable {
    let title: String?
    let status: String?
}

struct AgentSubagent: Codable, Identifiable {
    let id: String
    let name: String?
    let description: String?
    let model: String?
    let running: Bool?
    let step: String?
    let updated: Double?
    let said: String?
    var activity: [AgentEvent]?
    var children: [AgentSubagent]?
    let kind: String?
    let steps: [AgentStep]?
    let progress: Double?
    let phase: String?
    let summary: String?
    let idle: Bool?
    let usage: AgentUsage?

    var heading: String { kind == "workflow" ? (name ?? "Workflow") : (description ?? name ?? "Subagent") }
    var stepCount: String? {
        if kind == "workflow" { return summary }
        guard let steps, !steps.isEmpty else { return nil }
        return "\(steps.filter { $0.status == "done" }.count)/\(steps.count) steps"
    }
    var signal: Color { running == true ? .yellow : idle == true ? .gray : .green }
    var stateLabel: String { running == true ? "Working" : idle == true ? "Idle" : "Finished" }
    var kindLabel: String { kind == "workflow" ? "Workflow" : kind == "codex" ? "Codex" : (name ?? "Subagent") }
    func withoutActivity() -> AgentSubagent {
        var copy = self
        copy.activity = nil
        copy.children = children?.map { $0.withoutActivity() }
        return copy
    }
}

struct AgentUsage: Codable, Hashable {
    let input: Double?
    let output: Double?
    let cacheRead: Double?
    let cacheWrite: Double?
    let cost: Double?
}

/// Tokens in and out, cache reads and writes, and the API price, as one short line.
func usageLine(_ usage: AgentUsage?) -> String? {
    guard let usage else { return nil }
    let count: (Double?) -> String = { value in
        let v = value ?? 0
        return v >= 1e9 ? String(format: "%.1fB", v / 1e9) : v >= 1e6 ? String(format: "%.1fM", v / 1e6) : v >= 1e3 ? String(format: "%.0fK", v / 1e3) : String(Int(v))
    }
    let cost = usage.cost.map { String(format: "$%.2f", $0) }
    return [cost, "in \(count(usage.input))", "out \(count(usage.output))", "cache \(count(usage.cacheRead)) read · \(count(usage.cacheWrite)) write"]
        .compactMap { $0 }.joined(separator: " · ")
}

struct AgentEvent: Codable, Hashable {
    let at: Double?
    let text: String
    let kind: String?
}

struct AgentItem: Codable, Identifiable {
    let id: String
    let pane: String?
    let agent: String
    let name: String?
    let tabName: String?
    let status: String
    let title: String?
    let project: String?
    let task: String?
    let prompt: String?
    let now: String?
    let steps: [AgentStep]?
    var activity: [AgentEvent]?
    let updated: Double?
    let progress: Double?
    let stepCount: [Int]?
    var subagents: [AgentSubagent]?
    let usage: AgentUsage?
    let totalUsage: AgentUsage?

    var provider: String { agent == "codex" ? "Codex" : "Claude" }
    var heading: String { task ?? title ?? name ?? provider }
    var live: Bool { status == "working" || status == "blocked" }
    var runningSubagents: Int { (subagents ?? []).filter { $0.running == true }.count }
    /// Three colours: yellow while it works, red when it needs you, green when it finished.
    var signal: Color {
        switch status {
        case "working": return .yellow
        case "blocked": return .red
        case "done": return .green
        default: return .gray
        }
    }
    var stateLabel: String {
        switch status {
        case "working": return "Working"
        case "blocked": return "Needs you"
        case "done": return "Finished"
        default: return "Idle"
        }
    }
    /// The ring: progress when known, full when finished, a short arc while it works.
    var ring: Double { progress ?? (status == "done" ? 100 : live ? 8 : 0) }
}

struct AgentSnapshot: Codable {
    let agents: [AgentItem]
}

func ago(_ timestamp: Double?) -> String {
    guard let timestamp else { return "" }
    let seconds = max(0, Int(Date().timeIntervalSince1970 - timestamp))
    if seconds < 60 { return "\(seconds)s ago" }
    if seconds < 3600 { return "\(seconds / 60)m ago" }
    if seconds < 86400 { return "\(seconds / 3600)h ago" }
    return "\(seconds / 86400)d ago"
}

/// Runs a command with the folders where Homebrew and Herdr install, which apps opened from Finder lack.
func runTool(_ path: String, _ arguments: [String]) -> Process {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: path)
    process.arguments = arguments
    var environment = ProcessInfo.processInfo.environment
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    environment["PATH"] = ["\(home)/.local/bin", "/opt/homebrew/bin", "/usr/local/bin", environment["PATH"] ?? "/usr/bin:/bin"].joined(separator: ":")
    process.environment = environment
    process.standardOutput = FileHandle.nullDevice
    process.standardError = FileHandle.nullDevice
    return process
}

@MainActor
final class AgentStore: ObservableObject {
    @Published var agents: [AgentItem] = []
    @Published var edge = UserDefaults.standard.string(forKey: "agentDockEdge") ?? "left"
    private var timer: Timer?
    private var running = false
    private var observed = Date.distantPast
    private var lastData: Data?
    private var lastSettings: [Bool] = []
    static let snapshot = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Mako Capacity/agents.json")

    init() {
        load()
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 6, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
    }

    func load() {
        let showIdle = Self.showIdle(), showActivity = Self.showActivity()
        guard let data = try? Data(contentsOf: Self.snapshot), data != lastData || [showIdle, showActivity] != lastSettings,
              let snapshot = try? JSONDecoder().decode(AgentSnapshot.self, from: data) else { return }
        lastData = data
        lastSettings = [showIdle, showActivity]
        // Idle agents and recent activity show only when Settings turns them on, the same settings the terminal app uses.
        let shown = showIdle ? snapshot.agents : snapshot.agents.filter { $0.status != "idle" }
        agents = showActivity ? shown : shown.map { agent in
            var copy = agent
            copy.activity = nil
            copy.subagents = agent.subagents?.map { $0.withoutActivity() }
            return copy
        }
    }

    static let settings = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".mako-capacity/settings.json")
    static func showIdle() -> Bool { setting("SHOW_IDLE_AGENTS") }
    static func showActivity() -> Bool { setting("SHOW_AGENT_ACTIVITY") }
    static func setting(_ key: String) -> Bool {
        guard let data = try? Data(contentsOf: settings),
              let values = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
        return values[key] as? String == "1"
    }

    func setSetting(_ key: String, _ on: Bool) {
        // settings.json may hold the proxy key: keep its mode, and create it private.
        var values = (try? Data(contentsOf: Self.settings)).flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
        values[key] = on ? "1" : nil
        guard let data = try? JSONSerialization.data(withJSONObject: values, options: [.prettyPrinted, .sortedKeys]) else { return }
        if FileManager.default.fileExists(atPath: Self.settings.path) {
            try? data.write(to: Self.settings)
        } else {
            try? FileManager.default.createDirectory(at: Self.settings.deletingLastPathComponent(), withIntermediateDirectories: true)
            FileManager.default.createFile(atPath: Self.settings.path, contents: data, attributes: [.posixPermissions: 0o600])
        }
        lastData = nil
        load()
    }

    func refresh() {
        guard !running, let script = Bundle.main.resourceURL?.appendingPathComponent("agents.py") else { return }
        running = true
        // The observer model runs at most every 45 s; the cheap parts run every time.
        let observe = Date().timeIntervalSince(observed) > 45
        if observe { observed = Date() }
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let process = runTool("/usr/bin/python3", [script.path] + (observe ? ["--observe"] : []))
            try? process.run()
            process.waitUntilExit()
            DispatchQueue.main.async {
                self?.running = false
                self?.load()
            }
        }
    }

    /// Brings the agent's Herdr pane forward, then the terminal that shows Herdr.
    func focus(_ agent: AgentItem) {
        guard let pane = agent.pane else { return }
        let process = runTool("/usr/bin/env", ["herdr", "agent", "focus", pane])
        try? process.run()
        for id in ["com.mitchellh.ghostty", "net.kovidgoyal.kitty", "com.github.wez.wezterm"] {
            if let app = NSRunningApplication.runningApplications(withBundleIdentifier: id).first {
                app.activate()
                break
            }
        }
    }
}

struct AgentRing: View {
    let agent: AgentItem
    var size: CGFloat = 42
    var dot: some View {
        Circle().fill(agent.signal).overlay(Circle().stroke(Color(white: 0.065), lineWidth: 2))
    }
    var body: some View {
        ZStack {
            Circle().stroke(.black.opacity(0.75), lineWidth: 6)
            Circle().stroke(.white.opacity(0.12), lineWidth: 4)
            Circle().trim(from: 0, to: min(agent.ring, 100) / 100)
                .stroke(agent.signal, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                .rotationEffect(.degrees(-90))
            ProviderMark(provider: agent.provider).frame(width: size * 0.43, height: size * 0.43).foregroundStyle(.white)
        }
        .frame(width: size, height: size)
        .overlay(alignment: .bottomTrailing) {
            Group {
                if agent.status == "working" {
                    // A clock drives the pulse, not a SwiftUI transaction, so the card around the ring never animates with it.
                    TimelineView(.animation(minimumInterval: 1.0 / 30)) { context in
                        let phase = context.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1.2) / 1.2
                        ZStack {
                            Circle().stroke(agent.signal, lineWidth: 1.5).scaleEffect(1 + 1.4 * phase).opacity(0.9 * (1 - phase))
                            dot.scaleEffect(1 + 0.3 * sin(phase * .pi))
                        }
                    }
                } else {
                    dot
                }
            }
            .frame(width: size * 0.26, height: size * 0.26)
            .offset(x: 2, y: 2)
        }
        .accessibilityLabel("\(agent.provider), \(agent.heading), \(agent.stateLabel)")
    }
}

/// Which subagent row is open on each card. Cards watch it, so marking a row does not redraw the card or reset its scroll.
final class CardTrail: ObservableObject {
    @Published var ids: [String] = []
    func id(_ level: Int) -> String? { level < ids.count ? ids[level] : nil }
}

struct AgentCard: View {
    let agent: AgentItem
    var focus: () -> Void
    var openSub: (AgentSubagent) -> Void = { _ in }
    var marks = CardTrail()
    func section(_ title: String) -> some View {
        Text(title.uppercased()).font(.system(size: 10, weight: .bold)).foregroundStyle(.secondary).padding(.top, 2)
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(agent.provider.uppercased()).font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(agent.provider == "Codex" ? Color.mint : .orange)
                Spacer()
                Text(agent.stateLabel).font(.system(size: 10, weight: .semibold)).foregroundStyle(agent.signal)
                    .padding(.horizontal, 7).padding(.vertical, 2).background(agent.signal.opacity(0.16), in: Capsule())
            }
            HStack(spacing: 12) {
                AgentRing(agent: agent, size: 40)
                VStack(alignment: .leading, spacing: 3) {
                    Text(agent.heading).font(.headline).lineLimit(2).fixedSize(horizontal: false, vertical: true)
                    Text([agent.name, agent.tabName].compactMap { $0 }.uniqued().joined(separator: " · "))
                        .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer(minLength: 0)
                if let progress = agent.progress {
                    Text("\(Int(progress))%").font(.system(size: 22, weight: .semibold, design: .rounded)).foregroundStyle(agent.signal)
                }
            }
            if let now = agent.now?.trimmingCharacters(in: .whitespacesAndNewlines), !now.isEmpty {
                HStack(spacing: 8) {
                    Circle().fill(agent.signal).frame(width: 7, height: 7)
                    Text(now).font(.caption).lineLimit(2)
                }
                .padding(9).frame(maxWidth: .infinity, alignment: .leading)
                .background(agent.signal.opacity(0.09), in: RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(agent.signal.opacity(0.25)))
            }
            if let steps = agent.steps, !steps.isEmpty {
                section(agent.stepCount.map { "Steps · \($0[0]) of \($0[1])" } ?? "Steps")
                StepList(steps: steps, signal: agent.signal)
            }
            if let subagents = agent.subagents, !subagents.isEmpty {
                SubagentList(subagents: subagents, open: openSub, marks: marks, level: 0)
            }
            if let activity = agent.activity, !activity.isEmpty {
                section("Recent activity")
                ForEach(Array(activity.suffix(4).reversed().enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .top, spacing: 8) {
                        Text(ago(item.at)).frame(width: 48, alignment: .leading).foregroundStyle(.secondary)
                        Text(item.text).foregroundStyle(item.kind == "say" ? .primary : .secondary).lineLimit(1)
                    }.font(.system(size: 10))
                }
            }
            if let own = usageLine(agent.usage) {
                cardSection("Tokens")
                Text(own).font(.system(size: 10)).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                if agent.totalUsage != agent.usage, let total = usageLine(agent.totalUsage) {
                    Text("With subagents: " + total).font(.system(size: 10)).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
            }
            HStack {
                Text(ago(agent.updated)).font(.system(size: 10)).foregroundStyle(.secondary)
                Spacer()
                if agent.pane != nil { Button("Go to pane", action: focus) }
            }
        }
        .padding(16)
        .background(.white.opacity(0.045), in: RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(.white.opacity(0.07)))
    }
}

func cardSection(_ title: String) -> some View {
    Text(title.uppercased()).font(.system(size: 10, weight: .bold)).foregroundStyle(.secondary).padding(.top, 2)
}

/// Steps as a short timeline: a check when done, a lit dot for the active one, an empty ring for the rest.
struct StepList: View {
    let steps: [AgentStep]
    let signal: Color
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(steps.enumerated()), id: \.offset) { _, step in
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: step.status == "done" ? "checkmark.circle.fill" : step.status == "active" ? "circle.inset.filled" : "circle")
                        .foregroundStyle(step.status == "done" ? Color.green : step.status == "active" ? signal : .secondary)
                    Text(step.title ?? "").foregroundStyle(step.status == "pending" ? .secondary : .primary)
                        .fontWeight(step.status == "active" ? .semibold : .regular)
                        .fixedSize(horizontal: false, vertical: true)
                }.font(.caption)
            }
        }
    }
}

/// A subagent's progress ring: yellow while it runs, full and green once it finished.
struct SubRing: View {
    let sub: AgentSubagent
    let size: CGFloat
    var body: some View {
        let value = sub.progress ?? (sub.running == true ? 8 : 100)
        ZStack {
            Circle().stroke(.white.opacity(0.12), lineWidth: size > 30 ? 4 : 2.5)
            Circle().trim(from: 0, to: value / 100).stroke(sub.signal, style: StrokeStyle(lineWidth: size > 30 ? 4 : 2.5, lineCap: .round))
                .rotationEffect(.degrees(-90))
            if size > 30 {
                Text("\(Int(value))%").font(.system(size: 11, weight: .bold)).foregroundStyle(sub.signal)
            } else {
                Circle().fill(sub.signal).frame(width: 5, height: 5)
            }
        }
        .frame(width: size, height: size)
    }
}

/// The subagents of an agent or of a subagent, in a fixed-height list that scrolls.
/// Workflow agents sit under the phase they ran in. A hover on a row opens that subagent's card beside this one.
struct SubagentList: View {
    let subagents: [AgentSubagent]
    var open: (AgentSubagent) -> Void
    @ObservedObject var marks: CardTrail
    let level: Int
    var openID: String? { marks.id(level) }

    var groups: [(phase: String?, subs: [AgentSubagent])] {
        var groups: [(phase: String?, subs: [AgentSubagent])] = []
        for sub in subagents {
            if let last = groups.last, last.phase == sub.phase { groups[groups.count - 1].subs.append(sub) }
            else { groups.append((sub.phase, [sub])) }
        }
        return groups
    }

    var body: some View {
        let running = subagents.filter { $0.running == true }.count
        let groups = groups
        let headers = groups.filter { $0.phase != nil }.count
        cardSection("Subagents · \(subagents.count)" + (running > 0 ? ", \(running) running" : ""))
        ShadowScrollView {
            VStack(alignment: .leading, spacing: 2) {
                ForEach(Array(groups.enumerated()), id: \.offset) { index, group in
                    if let phase = group.phase {
                        HStack(spacing: 6) {
                            Text(phase.uppercased()).font(.system(size: 9, weight: .bold))
                                .foregroundStyle(group.subs.contains { $0.running == true } ? Color.yellow : .secondary)
                            Text("\(group.subs.filter { $0.running != true }.count)/\(group.subs.count) done")
                                .font(.system(size: 9)).foregroundStyle(.secondary)
                        }
                        .padding(.leading, 6).padding(.top, index == 0 ? 2 : 8).padding(.bottom, 2)
                    }
                    ForEach(group.subs) { sub in row(sub) }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(height: min(230, CGFloat(subagents.count) * 42 + CGFloat(headers) * 24))
        .padding(.horizontal, -6)
    }

    func row(_ sub: AgentSubagent) -> some View {
        HStack(spacing: 8) {
            SubRing(sub: sub, size: 22)
            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text(sub.heading).font(.caption.weight(.semibold)).lineLimit(1)
                    if let model = sub.model, !model.isEmpty {
                        Text(model).font(.system(size: 9)).foregroundStyle(.secondary)
                            .padding(.horizontal, 5).background(.white.opacity(0.08), in: Capsule())
                    }
                }
                let kids = sub.kind == "workflow" ? 0 : sub.children?.count ?? 0
                Text([sub.running == true ? "▸ " + (sub.step ?? "Working") : sub.stateLabel, sub.stepCount, ago(sub.updated),
                      kids > 0 ? "\(kids) inside" : nil].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer(minLength: 0)
            if let progress = sub.progress {
                Text("\(Int(progress))%").font(.system(size: 10, weight: .semibold)).foregroundStyle(sub.signal)
            }
            Image(systemName: "chevron.right").font(.system(size: 9, weight: .semibold)).foregroundStyle(.secondary)
        }
        .padding(.horizontal, 6).padding(.vertical, 5)
        .background(sub.id == openID ? Color.white.opacity(0.08) : .clear, in: RoundedRectangle(cornerRadius: 8))
        .contentShape(Rectangle())
        .onHover { inside in if inside { open(sub) } }
    }
}

/// A subagent's own card: what it does now, what it said last, its own subagents and its latest activity.
struct SubagentCard: View {
    let sub: AgentSubagent
    var openSub: (AgentSubagent) -> Void
    let marks: CardTrail
    let level: Int
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                SubRing(sub: sub, size: 42)
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text(sub.kindLabel.uppercased()).font(.system(size: 10, weight: .semibold)).foregroundStyle(.secondary).lineLimit(1)
                        Text(sub.stateLabel).font(.system(size: 10, weight: .semibold)).foregroundStyle(sub.signal)
                            .padding(.horizontal, 7).padding(.vertical, 2).background(sub.signal.opacity(0.16), in: Capsule())
                        if let model = sub.model, !model.isEmpty {
                            Text(model).font(.system(size: 9)).foregroundStyle(.secondary)
                                .padding(.horizontal, 5).padding(.vertical, 2).background(.white.opacity(0.08), in: Capsule())
                        }
                        Spacer()
                    }
                    Text(sub.kind == "workflow" ? sub.name ?? "Workflow" : sub.phase.map { "Phase: \($0)" } ?? sub.stepCount ?? "Subagent")
                        .font(.system(size: 12, weight: .semibold)).lineLimit(1)
                }
            }
            Text(sub.kind == "workflow" ? (sub.description ?? sub.heading) : sub.heading).font(.headline).fixedSize(horizontal: false, vertical: true)
            if sub.running == true, let step = sub.step {
                HStack(spacing: 8) {
                    Circle().fill(sub.signal).frame(width: 7, height: 7)
                    Text(step).font(.caption).lineLimit(2)
                }
                .padding(9).frame(maxWidth: .infinity, alignment: .leading)
                .background(sub.signal.opacity(0.09), in: RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(sub.signal.opacity(0.25)))
            }
            if let said = sub.said {
                Text("“\(said)”").font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            if let steps = sub.steps, !steps.isEmpty {
                cardSection((sub.kind == "workflow" ? "Phases" : "Steps") + (sub.stepCount.map { " · \($0)" } ?? ""))
                StepList(steps: steps, signal: sub.signal)
            }
            if let children = sub.children, !children.isEmpty {
                SubagentList(subagents: children, open: openSub, marks: marks, level: level)
            }
            if let activity = sub.activity, !activity.isEmpty {
                cardSection("Recent activity")
                ForEach(Array(activity.reversed().enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .top, spacing: 8) {
                        Text(ago(item.at)).frame(width: 48, alignment: .leading).foregroundStyle(.secondary)
                        Text(item.text).foregroundStyle(item.kind == "say" ? .primary : .secondary).lineLimit(1)
                    }.font(.system(size: 10))
                }
            }
            if let usage = usageLine(sub.usage) {
                cardSection("Tokens")
                Text(usage).font(.system(size: 10)).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            Text("Last write \(ago(sub.updated))").font(.system(size: 10)).foregroundStyle(.secondary)
        }
        .padding(16)
        .background(.white.opacity(0.045), in: RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(.white.opacity(0.07)))
    }
}

extension Array where Element == String {
    func uniqued() -> [String] { reduce(into: []) { if !$0.contains($1) { $0.append($1) } } }
}

/// One agent in a dock: its ring, its progress or state, and its name.
struct AgentCell: View {
    let agent: AgentItem
    let horizontal: Bool
    var focus: () -> Void
    var hover: (AgentItem?) -> Void
    var body: some View {
        Button(action: focus) {
            VStack(spacing: 3) {
                AgentRing(agent: agent, size: horizontal ? 36 : 42)
                Text(agent.progress.map { "\(Int($0))%" } ?? agent.stateLabel)
                    .font(.system(size: agent.progress == nil ? 10 : 15, weight: .medium)).monospacedDigit()
                    .foregroundStyle(agent.signal).lineLimit(1)
                Text(agent.name ?? agent.project ?? "").font(.system(size: 9, weight: .medium)).foregroundStyle(.white.opacity(0.6)).lineLimit(1)
            }.frame(width: horizontal ? 72 : 64, height: 78)
        }.buttonStyle(.plain).onHover { inside in hover(inside ? agent : nil) }
            .help("\(agent.provider) · \(agent.heading) · \(agent.stateLabel)")
    }
}

struct NoAgents: View {
    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: "sparkles").font(.system(size: 18)).foregroundStyle(.secondary)
            Text("No agents").font(.system(size: 9)).foregroundStyle(.secondary)
        }.frame(width: 64, height: 78)
    }
}

struct AgentRailView: View {
    @ObservedObject var store: AgentStore
    @ObservedObject var capacity: CapacityStore
    var hover: (AgentItem?) -> Void
    var hide: () -> Void
    var horizontal: Bool { store.edge == "top" || store.edge == "bottom" }
    func cell(_ agent: AgentItem) -> some View {
        AgentCell(agent: agent, horizontal: horizontal, focus: { store.focus(agent) }, hover: hover)
    }
    var empty: some View { NoAgents() }
    var body: some View {
        GeometryReader { geometry in
            content
                .frame(width: geometry.size.width / capacity.dockScale, height: geometry.size.height / capacity.dockScale)
                .scaleEffect(capacity.dockScale, anchor: .topLeading)
        }
        .contextMenu { Button("Hide agents dock", action: hide) }
    }
    var content: some View {
        Group {
            if horizontal {
                HStack(spacing: 8) {
                    Image(systemName: "line.3.horizontal").font(.system(size: 10)).foregroundStyle(.secondary).help("Drag to attach to a screen edge")
                    ShadowScrollView(axis: .horizontal, showsIndicators: false) {
                        HStack(spacing: 8) { if store.agents.isEmpty { empty }; ForEach(store.agents) { cell($0) } }
                    }
                }.padding(.horizontal, 34).padding(.vertical, 14)
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "line.3.horizontal").font(.system(size: 12)).foregroundStyle(.secondary)
                        .padding(.top, store.edge == "floating" ? 12 : 32).help("Drag to attach to a screen edge")
                    ShadowScrollView(showsIndicators: false) {
                        VStack(spacing: 6) { if store.agents.isEmpty { empty }; ForEach(store.agents) { cell($0) } }.padding(.horizontal, 12)
                    }
                    Image(systemName: "sparkles").font(.system(size: 12)).foregroundStyle(.secondary).help("Agents")
                        .padding(.bottom, store.edge == "floating" ? 12 : 32)
                }
            }
        }
        .foregroundStyle(.white)
        .background(DockSurface(edge: store.edge).fill(Color(white: 0.065).opacity(capacity.dockOpacity)))
        .overlay(DockSurface(edge: store.edge).stroke(.white.opacity(0.12)))
        .preferredColorScheme(.dark)
    }
}

/// Owns the agents dock panel: placement on an edge or floating, drag to snap, and the hover card.
@MainActor
final class AgentDockController: NSObject, NSWindowDelegate {
    let store = AgentStore()
    let capacity: CapacityStore
    var panel: NSPanel!
    var closeDetailWork: DispatchWorkItem?
    var dockingWork: DispatchWorkItem?
    var placing = false
    var subscription: AnyCancellable?
    /// The capacity dock, which holds the agents when they share it.
    weak var host: NSPanel?
    var anchor: NSPanel { capacity.agentsInDock ? host ?? panel : panel }

    init(capacity: CapacityStore) {
        self.capacity = capacity
        super.init()
        panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 88, height: 400), styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.hasShadow = false
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.isMovableByWindowBackground = true
        panel.hidesOnDeactivate = false
        panel.delegate = self
        panel.contentView = NSHostingView(rootView: AgentRailView(store: store, capacity: capacity,
            hover: { [weak self] in self?.showDetail($0) }, hide: { [weak self] in self?.setVisible(false) }))
        place(edge: store.edge)
        subscription = Publishers.CombineLatest(store.$agents, capacity.$dockScale).dropFirst().receive(on: RunLoop.main)
            .sink { [weak self] _, _ in self?.place(edge: self?.store.edge ?? "left") }
        if !capacity.agentsInDock && UserDefaults.standard.object(forKey: "agentDockVisible") as? Bool ?? true { panel.orderFrontRegardless() }
    }

    /// Hides the agents dock while the capacity dock holds the agents, and brings it back after.
    func syncMerged() {
        if capacity.agentsInDock {
            panel.orderOut(nil)
        } else if UserDefaults.standard.object(forKey: "agentDockVisible") as? Bool ?? true {
            place(edge: store.edge)
            panel.orderFrontRegardless()
        }
    }

    func closeCards() {
        closeDetailWork?.cancel()
        openWork?.cancel()
        cards.forEach { $0.orderOut(nil) }
        hoveredAgent = nil
        trail = []
    }

    var visible: Bool { panel.isVisible }

    func setVisible(_ visible: Bool) {
        UserDefaults.standard.set(visible, forKey: "agentDockVisible")
        if visible { place(edge: store.edge); panel.orderFrontRegardless() } else { panel.orderOut(nil); cards.forEach { $0.orderOut(nil) } }
    }

    func place(edge: String, screen preferred: NSScreen? = nil) {
        guard let screen = preferred ?? panel.screen ?? NSScreen.main else { return }
        placing = true
        store.edge = edge
        UserDefaults.standard.set(edge, forKey: "agentDockEdge")
        let horizontal = edge == "top" || edge == "bottom"
        let scale = capacity.dockScale
        let count = max(1, store.agents.count)
        let padding: CGFloat = edge == "floating" ? 12 : 32
        let length = horizontal ? CGFloat(90 + count * 72 + (count - 1) * 8) : padding * 2 + 44 + CGFloat(count * 78 + (count - 1) * 6)
        let size = horizontal ? NSSize(width: min(length * scale, screen.visibleFrame.width), height: 114 * scale)
            : NSSize(width: 88 * scale, height: min(length * scale, screen.visibleFrame.height - 24))
        let offset = UserDefaults.standard.object(forKey: "agentDockOffset") as? Double ?? 0.5
        var origin = NSPoint(x: screen.visibleFrame.minX + (screen.visibleFrame.width - size.width) * offset,
                             y: screen.visibleFrame.minY + (screen.visibleFrame.height - size.height) * offset)
        switch edge {
        case "right": origin.x = screen.frame.maxX - size.width
        case "left": origin.x = screen.frame.minX
        case "top": origin.y = screen.visibleFrame.maxY - size.height
        case "bottom": origin.y = screen.visibleFrame.minY
        default:
            origin.x = UserDefaults.standard.object(forKey: "agentFloatingX") as? Double ?? origin.x
            // A floating dock grows downwards from its top edge as agents start.
            let top = UserDefaults.standard.object(forKey: "agentFloatingTop") as? Double ?? (origin.y + size.height)
            origin.y = top - size.height
            origin.x = max(screen.visibleFrame.minX, min(origin.x, screen.visibleFrame.maxX - size.width))
            origin.y = max(screen.visibleFrame.minY, min(origin.y, screen.visibleFrame.maxY - size.height))
        }
        panel.setFrame(NSRect(origin: origin, size: size), display: true)
        placing = false
    }

    func windowDidMove(_ notification: Notification) {
        guard !placing else { return }
        closeDetailWork?.cancel()
        cards.forEach { $0.orderOut(nil) }
        scheduleDocking()
    }

    func scheduleDocking() {
        dockingWork?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            if NSEvent.pressedMouseButtons != 0 { self.scheduleDocking(); return }
            guard let screen = self.panel.screen ?? NSScreen.main else { return }
            let frame = self.panel.frame
            let candidates: [(String, CGFloat)] = [("left", abs(frame.minX - screen.frame.minX)), ("right", abs(frame.maxX - screen.frame.maxX)),
                                                   ("top", abs(frame.maxY - screen.visibleFrame.maxY)), ("bottom", abs(frame.minY - screen.visibleFrame.minY))]
            let nearest = candidates.min(by: { $0.1 < $1.1 })!
            if nearest.1 <= 48 {
                let horizontal = nearest.0 == "top" || nearest.0 == "bottom"
                let span = horizontal ? screen.visibleFrame.width - frame.width : screen.visibleFrame.height - frame.height
                let distance = horizontal ? frame.minX - screen.visibleFrame.minX : frame.minY - screen.visibleFrame.minY
                UserDefaults.standard.set(max(0, min(1, span > 0 ? distance / span : 0.5)), forKey: "agentDockOffset")
                self.place(edge: nearest.0, screen: screen)
            } else {
                UserDefaults.standard.set(frame.minX, forKey: "agentFloatingX")
                UserDefaults.standard.set(frame.maxY, forKey: "agentFloatingTop")
                self.place(edge: "floating", screen: screen)
            }
        }
        dockingWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15, execute: work)
    }

    /// Cards open in a row away from the dock: the agent first, then each hovered subagent, down the tree.
    var cards: [NSPanel] = []
    var hoveredAgent: AgentItem?
    var trail: [AgentSubagent] = [] { didSet { marks.ids = trail.map(\.id) } }
    let marks = CardTrail()
    var openWork: DispatchWorkItem?

    func showDetail(_ agent: AgentItem?) {
        guard let agent else { scheduleClose(); return }
        closeDetailWork?.cancel()
        if hoveredAgent?.id != agent.id { trail = [] }
        hoveredAgent = agent
        render(anchorY: NSEvent.mouseLocation.y)
    }

    func scheduleClose() {
        closeDetailWork?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            self.openWork?.cancel()
            self.cards.forEach { $0.orderOut(nil) }
            self.hoveredAgent = nil
            self.trail = []
        }
        closeDetailWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3, execute: work)
    }

    func open(level: Int, _ sub: AgentSubagent) {
        closeDetailWork?.cancel()
        openWork?.cancel()
        if trail.count > level, trail[level].id == sub.id, cards.count > level + 1, cards[level + 1].isVisible { return }
        // Rows slide under the pointer while the list scrolls, so a card opens only after the pointer rests on a row.
        let work = DispatchWorkItem { [weak self] in
            guard let self, self.hoveredAgent != nil, self.cards.count > level, self.cards[level].isVisible else { return }
            self.trail = Array(self.trail.prefix(level)) + [sub]
            // The card at `level` keeps its view and scroll; only the cards after it are drawn.
            self.render(anchorY: NSEvent.mouseLocation.y, from: level + 1)
        }
        openWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2, execute: work)
    }

    func card(_ index: Int) -> NSPanel {
        while cards.count <= index {
            let panel = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
            panel.hasShadow = false
            panel.isOpaque = false
            panel.backgroundColor = .clear
            panel.level = .floating
            panel.hidesOnDeactivate = false
            panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
            cards.append(panel)
        }
        return cards[index]
    }

    /// Draws cards from `from` onwards. Earlier cards stay where they are, so the row does not jump.
    func render(anchorY: CGFloat, from: Int = 0) {
        guard let agent = hoveredAgent else { return }
        let dock = anchor
        let screen = dock.screen?.visibleFrame ?? NSScreen.main!.visibleFrame
        let outwardRight = dock.frame.minX - 380 < screen.minX
        let placed = DetailPlacement(dock: dock.frame, edge: capacity.agentsInDock ? capacity.dockEdge : store.edge,
                                     screen: screen, mouse: NSEvent.mouseLocation)
        for index in from...trail.count {
            let body: AnyView
            if index == 0 {
                body = AnyView(AgentCard(agent: agent, focus: { [weak self] in self?.store.focus(agent) },
                                         openSub: { [weak self] in self?.open(level: 0, $0) }, marks: marks))
            } else {
                let level = index
                body = AnyView(SubagentCard(sub: trail[index - 1], openSub: { [weak self] in self?.open(level: level, $0) }, marks: marks, level: level))
            }
            let previous = index == 0 ? dock.frame : cards[index - 1].frame
            // The row grows away from the dock and turns back at the screen edge.
            var right: Bool
            if index == 0 { right = outwardRight }
            else if index == 1 && placed.vertical { right = previous.midX < screen.midX }
            else { right = previous.minX >= (index == 1 ? dock.frame.maxX : cards[index - 2].frame.maxX) }
            if right && previous.maxX + 360 > screen.maxX { right = false }
            if !right && previous.minX - 360 < screen.minX { right = true }
            // Above a bottom dock or below a top dock, the first card's tail points down or up at the ring.
            let tail: Edge = index == 0 && placed.vertical ? placed.tail : right ? .leading : .trailing
            let content = body.frame(width: 330).padding(8)
                .padding(Edge.Set(tail), 20)
                .background(DetailBubble(tail: tail, at: index == 0 ? placed.tailAt : nil).fill(Color(white: 0.065)))
                .onHover { [weak self] inside in if inside { self?.closeDetailWork?.cancel() } else { self?.scheduleClose() } }
                .preferredColorScheme(.dark)
            let view = NSHostingView(rootView: content)
            let size = view.fittingSize
            var x = right ? previous.maxX + (index == 0 ? 8 : 4) : previous.minX - size.width - (index == 0 ? 8 : 4)
            let target = card(index)
            let top = anchorY + size.height / 2
            var y = min(screen.maxY - size.height, max(screen.minY, top - size.height))
            if placed.vertical {
                if index == 0 { (x, y) = placed.origin(size: size) }
                // Subagent cards stay clear of the dock, on the same side as the first card.
                else if placed.tail == .bottom { y = max(y, dock.frame.maxY + 4) }
                else { y = min(y, dock.frame.minY - size.height - 4) }
            }
            target.contentView = view
            target.setFrame(NSRect(origin: NSPoint(x: x, y: y), size: size), display: true)
            target.orderFrontRegardless()
        }
        for extra in cards.dropFirst(trail.count + 1) { extra.orderOut(nil) }
    }
}
