# Slack TUI

A terminal-based Slack client built with Python and [Textual](https://textual.textualize.io/). Browse channels, DMs, and group conversations in a fast, keyboard-driven interface without leaving your terminal.

```
+------------------+------------------------------------------+
| DMs              | #general                                 |
|   alice          |                                          |
|   bob            | -- Today --------------------------------|
|                  | [09:31] alice: Hey everyone!             |
| DM Groups        | [09:33] bob: What's up?                  |
|   alice, carol   | [10:15] carol: Check https://example.com |
|                  |                                          |
| Channels         |                                          |
|   # general      |                                          |
|   # random       |                                          |
|   # dev          |                                          |
|                  +------------------------------------------+
|                  | > Type a message... (/ for commands)     |
+------------------+------------------------------------------+
```

The left sidebar shows conversations grouped under collapsible headers (DMs, DM Groups, Channels). The right panel displays message history with colored usernames, timestamps, date separators, and clickable links. A message input bar with slash-command autocomplete sits at the bottom.

## Features

- **Categorized sidebar** -- Conversations are grouped into DMs, DM Groups, and Channels with collapsible category headers (click or press Enter to toggle).
- **Smart sorting** -- Channels are sorted by recent activity. Conversations with no activity in the last 30 days are automatically filtered out.
- **Readable MPDM names** -- Multi-person DM groups display member names instead of Slack's internal IDs.
- **Real-time messages** -- New messages arrive via Socket Mode (WebSocket) with background polling across all channels as a fallback.
- **Colored usernames** -- Each user is assigned a consistent color from a 12-color palette for easy visual scanning.
- **Date separators** -- Messages are grouped by date with human-friendly labels (Today, Yesterday, N days ago, or a formatted date).
- **Clickable URLs** -- Both Slack-formatted links (`<url|label>`) and bare URLs are rendered as styled, clickable links in terminals that support it.
- **Unread indicators** -- Channels with new messages are shown in bold with a dot marker in the sidebar.
- **Slash commands** -- Built-in commands (`/msg`, `/channels`, `/help`) with an autocomplete dropdown that supports arrow-key navigation and Tab completion.
- **Disk cache** -- Channels, users, and message history are cached to disk for near-instant startup on subsequent runs.
- **Keyboard-driven** -- Full keyboard navigation with Tab to switch panels, arrow keys to browse, Enter to select, and Ctrl+Q to quit.

## Slack App Setup

Before running Slack TUI, you need to create a Slack app and obtain two tokens.

### 1. Create a Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps).
2. Click **Create New App** and choose **From scratch**.
3. Give it a name (e.g., "Slack TUI") and select your workspace.

### 2. Enable Socket Mode

1. In your app settings, navigate to **Settings > Socket Mode**.
2. Toggle **Enable Socket Mode** to on.
3. Create an **App-Level Token** with the `connections:write` scope. Save this token -- it starts with `xapp-`.

### 3. Configure Token Scopes

Navigate to **Features > OAuth & Permissions** and add the following scopes.

**If using a Bot Token (`xoxb-`)**, add these under **Bot Token Scopes**:

| Scope | Purpose |
|---|---|
| `channels:read` | List public channels |
| `channels:history` | Read public channel messages |
| `groups:read` | List private channels |
| `groups:history` | Read private channel messages |
| `im:read` | List direct messages |
| `im:history` | Read DM messages |
| `mpim:read` | List group DMs |
| `mpim:history` | Read group DM messages |
| `chat:write` | Send messages |
| `users:read` | Resolve user display names |

> **Tip:** If you want messages to appear as *yourself* rather than as the bot, use a **User Token** (`xoxp-`) instead of a Bot Token. Add the same scopes listed above under **User Token Scopes** on the same OAuth & Permissions page. The app accepts either token type.

### 4. Subscribe to Events

1. Navigate to **Features > Event Subscriptions** and toggle **Enable Events** to on.
2. Under **Subscribe to bot events**, add:
   - `message.channels`
   - `message.groups`
   - `message.im`
   - `message.mpim`

### 5. Install the App

1. Navigate to **Settings > Install App** and click **Install to Workspace**.
2. Authorize the requested permissions.
3. Copy the **Bot Token** (starts with `xoxb-`) or **User Token** (starts with `xoxp-`).

You now have the two tokens required:

| Token | Prefix | Where to find it |
|---|---|---|
| App-Level Token | `xapp-` | Settings > Basic Information > App-Level Tokens |
| Bot/User Token | `xoxb-` / `xoxp-` | Settings > OAuth & Permissions |

## Installation

**Requirements:** Python 3.11 or newer.

```bash
# Clone the repository
git clone <repo-url> slack-cli
cd slack-cli

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the package in editable mode
pip install -e .
```

This installs three dependencies automatically: `textual`, `slack_sdk`, and `aiohttp`.

## Usage

```bash
# Run using the installed entry point
slack-tui

# Or run as a Python module
python -m slack_tui
```

### First Run

On first launch, an authentication dialog will prompt you for your two Slack tokens:

- **Bot/User Token** -- your `xoxb-...` or `xoxp-...` token
- **App-Level Token** -- your `xapp-...` token

Tokens are saved to `~/.config/slack-tui/config.toml` with restricted file permissions (`0600`). On subsequent runs, tokens are loaded automatically and you go straight to the main interface.

To reconfigure, edit or delete `~/.config/slack-tui/config.toml`:

```toml
[tokens]
bot_token = "xoxb-..."
app_token = "xapp-..."
```

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Tab` | Switch focus between sidebar and message input |
| `Up` / `Down` | Navigate channels in sidebar, or cycle autocomplete suggestions |
| `Enter` | Select a channel in the sidebar, or send a message |
| `Tab` (in autocomplete) | Accept the highlighted autocomplete suggestion |
| `Escape` | Dismiss the autocomplete dropdown |
| `Ctrl+Q` | Quit the application |

## Slash Commands

Type these in the message input bar. An autocomplete dropdown appears as you type.

| Command | Description |
|---|---|
| `/msg @user` | Jump to a DM with the specified user |
| `/msg #channel` | Jump to the specified channel |
| `/channels` | Reload the channel list from the Slack API |
| `/help` | Show available commands |

## Cache

Slack TUI caches data to disk for fast startup:

- **Location:** `~/.cache/slack-tui/` (respects `XDG_CACHE_HOME` if set)
- **Contents:** `channels.json`, `users.json`, and per-channel message history under `history/`

On startup, cached data is displayed immediately while fresh data is fetched from the Slack API in the background. To clear the cache, delete the `~/.cache/slack-tui/` directory.

## Logging

Debug logs are written to `/tmp/slack-tui.log`. Check this file when troubleshooting connectivity or message delivery issues.

## Project Structure

```
slack_tui/
    __init__.py          Package marker
    __main__.py          Entry point (logging setup, app launch)
    app.py               Main Textual app, event wiring, slash commands, polling
    app.tcss             Textual CSS stylesheet (layout, colors, auth dialog)
    config.py            Token load/save (TOML format, XDG config paths)
    cache.py             Disk cache for channels, users, message history
    models.py            Data classes: Channel, User, Message, ChannelType
    slack_client.py      Async Slack API wrapper (channels, history, send, users)
    socket_listener.py   Socket Mode WebSocket listener for real-time events
    screens/
        auth_screen.py   Modal token-entry screen
    widgets/
        sidebar.py       Categorized channel list with collapsible headers
        chat_panel.py    Right panel container (messages + input)
        message_view.py  Scrollable message display with colors, links, dates
        message_input.py Text input with Enter-to-send and autocomplete hooks
        autocomplete.py  Floating dropdown for slash-command suggestions
pyproject.toml           Project metadata, dependencies, entry point
```

## Tech Stack

| Component | Library |
|---|---|
| TUI framework | [Textual](https://textual.textualize.io/) >= 1.0.0 |
| Slack API | [slack_sdk](https://slack.dev/python-slack-sdk/) >= 3.27.0 |
| Async HTTP / WebSocket | [aiohttp](https://docs.aiohttp.org/) >= 3.9.0 |
| Language | Python 3.11+ |
