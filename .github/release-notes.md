First stable release of Mako Capacity: one view of how much capacity is left on every Claude, Codex and Cursor account.

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

## What is in 1.0

- A dock with a quota ring per account, hover details and an All accounts dashboard.
- Hide, restore and delete accounts from the dashboard.
- Claude and Codex logins through one CLIProxyAPI, local or on another machine.
- A Herdr widget with rings, layouts that follow the pane width, and pinning: `herdr plugin install Mako-L/account-capacity-dock/herdr-plugin`.
- Today's local token use and API-equivalent cost from CodeBurn.
