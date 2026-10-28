Mako Capacity 1.1 brings your agents into the dock: timed steps, subagents, workflows and the cost of each agent.

[![What is new in 1.1](https://mako-l.github.io/account-capacity-dock/media/whats-new-1.1.gif?v=2)](https://mako-l.github.io/account-capacity-dock/media/whats-new-1.1.mp4)

[Watch the film with sound](https://mako-l.github.io/account-capacity-dock/media/whats-new-1.1.mp4) (22 seconds, demo data).

## Downloads

| File | For |
| --- | --- |
| `Mako-Capacity-macOS.dmg` | macOS 14 or newer, Apple Silicon and Intel. Open it and drag the app to Applications. |
| `mako-capacity-windows-x64.exe` | Windows 10 and 11, 64-bit. Run it directly. |
| `mako-capacity-linux-x64` | Linux desktop, 64-bit. Run `chmod +x mako-capacity-linux-x64` once, then run it. |
| `LICENSES.txt` | The licence notices for the app and its bundled assets |
| `SHA256SUMS.txt` | Checksums for the files above |

The app needs Python 3.9 or newer. To add accounts, run CLIProxyAPI in Docker or on another machine; the README covers both.

> [!WARNING]
> Windows and Linux are untested by hand. The builds compile and pass the automated checks, but nobody has used them on a real machine yet.

**macOS:** the app is not notarised. After you drag it to Applications, run `xattr -dr com.apple.quarantine "/Applications/Mako Capacity.app"` once, or right-click it and choose **Open**.

**Windows:** the app is not signed, so SmartScreen may warn on first run. Choose **More info**, then **Run anyway**.

## What is new in 1.1

- **Agents in the dock:** a switch moves between accounts and agents. Each agent shows a progress ring, a status colour and its Herdr workspace name.
- **Agent cards:** the task, the current step and how long each step took.
- **Subagents and workflows:** each one opens its own card. They list running, then finished, then idle.
- **Cost per agent:** tokens, API-equivalent cost and about how much of a weekly limit each agent used.
- **Account cards:** spend per quota window, share of the plan price, when a window fills at this pace.
- **No proxy needed:** the dock reads the local Claude Code and Codex logins.
- **Herdr:** a plain-text agents widget, and the GPUIX app pinned in a pane.

The full list is in [CHANGELOG.md](https://github.com/Mako-L/account-capacity-dock/blob/main/CHANGELOG.md).
