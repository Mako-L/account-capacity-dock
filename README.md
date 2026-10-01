# Mako Capacity

A separate native macOS app inspired by CodeBurn's Capacity Dock, showing **every
Claude, Codex, and Cursor account together**. Its black dock attaches flush to the
right edge of the screen, with quota rings, percentages, account labels, and
inward-facing detail bubbles.

## Use

Launch **Mako Capacity.app**. The capacity dock appears on the right edge; it stays
above ordinary windows and follows you across Spaces. Hover an account to see its
email, quota windows, reset countdowns, and connection status. Click an account
to open the overview with all accounts visible together.

Drag the dock by its handle to move it along the edge. Drop it within 48 points
of any screen edge to attach there, or pull it away to float. Position and edge
are remembered. The menu-bar gauge offers **Attach to screen → Right**, show/hide,
refresh, overview, and quit. Closing the overview leaves the dock running.

Click the dock's **gear** (or choose **Dock settings…** from the menu-bar gauge)
to adjust size, length, circular or rounded-square icons, account labels,
background opacity, and screen edge. Changes apply immediately and persist across
launches. Short docks scroll to keep every account accessible. **Restore defaults**
returns to the original right-edge appearance. Settings also open with Command-comma.

The dock reports **percent used**, using the most constrained reported quota
window. Missing capacity is shown as `—`, with an explanation in the detail
bubble. Exhausted and disconnected accounts remain visible.

## Account sources

- **Claude:** reads the saved account inventory from `~/.claude-swap-backup/`
  and OAuth access tokens owned by the proxy in `~/claude-proxy/auths/`.
  Accounts are deduplicated by organization identity. Saved accounts without a
  usable proxy login remain visible with a reconnect message.
- **Codex:** reads every account in `~/codex-proxy/data/accounts.json`, including
  cached quota as a fallback, then fetches current usage using the access token.
- **Cursor:** reads the Cursor app's local state database in read-only mode and
  queries its usage-summary endpoint using the existing session.

The app never rotates refresh tokens, signs you in, switches accounts, or routes
model traffic. Credential lifecycle remains with the existing apps and proxies.
The local snapshot contains account metadata and capacity, never tokens. Network
usage checks run at most every five minutes; refresh can request an earlier read,
but respects rate-limit backoff. Failed reads keep previous capacity visible with
a stale status. Authentication failures clear quota so it cannot look live.

Add Claude accounts in the Claude proxy dashboard. Add Codex accounts in the Codex
proxy. Sign in to Cursor through Cursor. The next inventory refresh picks up new
proxy accounts automatically. A saved account without a login remains visible.

## Build

Requires macOS 14+, Xcode Command Line Tools (Swift and Python 3), and the account
sources above. There are no package dependencies.

```sh
./build.sh
open 'build/Mako Capacity.app'
```

To open the overview on launch:

```sh
open 'build/Mako Capacity.app' --args --overview
```

To inspect the credential-free collector output:

```sh
python3 collector.py
```

To run the collector checks:

```sh
python3 -m unittest discover -s tests -v
```

## CodeBurn attribution

The dock's interaction and visual design are based on
[CodeBurn](https://github.com/getagentseal/codeburn), licensed MIT by AgentSeal.
Provider icons are reused under that license. Quota endpoint formats follow its
provider adapters; the collector and native multi-account app are independent
implementations. The adapted ring, edge flare, and detail-tail geometry retain
CodeBurn's MIT attribution in `Resources/CodeBurn-LICENSE.txt`.

This repository is separate from the full CodeBurn app and does not replace it.
