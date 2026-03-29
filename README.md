# Slack TUI

A full-featured terminal-based Slack client built with Python and [Textual](https://textual.textualize.io/). Browse channels, DMs, and group conversations in a fast, keyboard-driven interface without leaving your terminal.

<!-- Replace with an actual screenshot or GIF recording of the app in action -->
![Screenshot placeholder](https://via.placeholder.com/800x500.png?text=Slack+TUI+Screenshot)

```
+------------------+------------------------------------------+
| DMs              | #general                                 |
| * alice          |                                          |
|   bob            | -- Today --------------------------------|
|                  |                                          |
| DM Groups        |  alice                         just now  |
|   alice, carol   |    Hey everyone!                         |
|                  |    View Thread (3 replies)               |
| Channels         |                                          |
|   # general      |  bob                        2 minutes ago|
|   # random       |    What's up? :wave:                     |
|   # dev          |                                          |
|                  |  carol                     10 minutes ago|
|                  |    Check https://example.com             |
|                  |    [img] photo.png (45 KB) [Open]        |
|                  |                                          |
|                  +------------------------------------------+
|                  | /search  search messages                 |
|                  | /upload  upload a file                   |
|                  +------------------------------------------+
|                  | > Type a message... (/ for commands)     |
+------------------+------------------------------------------+
```

## Features

### Sidebar

- **Collapsible categories** -- Conversations are grouped into DMs, DM Groups, and Channels. Click or press Enter on a category header to expand or collapse it.
- **Smart sorting** -- All categories are sorted by most recent activity. Conversations idle for more than 90 days are filtered out automatically.
- **Unread indicators** -- Channels with unread messages are highlighted in bold with a dot marker.
- **Message previews** -- Each conversation shows a one-line preview of the latest message below the channel name.
- **User presence** -- DMs show a green filled circle for online users and a hollow circle for away users, updated every 60 seconds.
- **Readable MPDM names** -- Multi-person DM groups display member names instead of Slack's internal IDs.

### Messages

- **Colored usernames** -- Each user gets a consistent color from a 12-color palette for easy visual scanning.
- **Message grouping** -- Consecutive messages from the same user within 5 minutes are grouped together without repeating the username header.
- **Date separators** -- Messages are organized under human-friendly date labels (Today, Yesterday, 3 days ago, Jan 15, 2025).
- **Relative timestamps** -- Each message shows how long ago it was sent (just now, 5 minutes ago, 2 hours ago).
- **Clickable URLs** -- Both Slack-formatted links (`<url|label>`) and bare URLs are rendered as styled, clickable links that open in your default browser.
- **Inline image previews** -- Image attachments are rendered as half-block ASCII art directly in the terminal, with an [Open] link to view the full image in your system image viewer.
- **Emoji rendering** -- Slack `:shortcode:` notation is converted to Unicode emoji characters, including skin tone modifiers.
- **Text selection and copy** -- Select text with your mouse and copy it to the clipboard, just like in a regular terminal.

### Input and Autocomplete

- **Slash commands** -- Built-in commands with a floating autocomplete dropdown that supports arrow-key navigation and Tab completion.
- **Emoji autocomplete** -- Type `:` followed by at least two characters to search emoji by name. Press Tab to insert the selected emoji.
- **@mention autocomplete** -- Type `@` followed by a name to search users in your workspace. Tab inserts the mention, which is resolved to `<@USER_ID>` when sent.
- **File path autocomplete** -- The `/upload` command provides filesystem path completion with directory traversal and file size display.

### Threads

- **View threads** -- Click "View Thread (N replies)" on any message, or use the `/thread` command to open the most recent thread in the current channel.
- **Reply in threads** -- While in thread view, messages you send are posted as thread replies.
- **Thread polling** -- New replies appear automatically while you have a thread open.
- **Visual distinction** -- Thread view uses a distinct background color and left border to clearly indicate nested context.

### Search

- **Workspace search** -- Use `/search <query>` to search messages across your entire workspace.
- **Clickable results** -- Search results show the channel name, author, timestamp, and message text. Click a channel name to navigate directly to it.
- **Return to context** -- Use `/back` to return to the channel you were viewing before the search.

### Performance

- **Disk cache** -- Channels, users, and per-channel message history are cached to disk. On startup, cached data renders instantly while fresh data loads from the API in the background.
- **Rate limit handling** -- All API calls automatically retry on HTTP 429 responses, respecting the `Retry-After` header.
- **Batched API calls** -- Presence checks and last-message-timestamp fetches are batched with rate-limit-friendly delays.
- **Background polling** -- The current channel is polled every 3 seconds. Other channels are checked in rotating batches of 2, so unread indicators appear without hammering the API.
- **Optimistic message display** -- Messages you send appear immediately in the UI before the API call completes.

## Requirements

- **Python 3.11** or newer
- A terminal emulator with mouse support and 256-color (recommended: kitty, iTerm2, WezTerm, Windows Terminal, or any modern terminal)
- A Slack workspace where you can create a Slack app (or have an admin do it)

## Installation

### Clone and install

```bash
git clone https://github.com/your-username/slack-tui.git
cd slack-tui

# Option 1: pip (in a virtual environment)
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Option 2: uv
uv pip install -e .

# Option 3: pipx (installs globally in an isolated environment)
pipx install -e .
```

### Dependencies

The following packages are installed automatically:

| Package | Version | Purpose |
|---------|---------|---------|
| [textual](https://textual.textualize.io/) | >= 1.0.0 | TUI framework |
| [rich](https://rich.readthedocs.io/) | >= 13.0.0 | Terminal text formatting |
| [slack_sdk](https://slack.dev/python-slack-sdk/) | >= 3.27.0 | Slack Web API and Socket Mode |
| [aiohttp](https://docs.aiohttp.org/) | >= 3.9.0 | Async HTTP for file downloads and WebSocket |
| [Pillow](https://pillow.readthedocs.io/) | >= 10.0.0 | Image processing for inline ASCII art previews |
| [emoji](https://github.com/carpedm20/emoji) | >= 2.0.0 | Emoji shortcode-to-Unicode conversion |

## Slack App Setup

You need two tokens: a **Bot Token** (or User Token) and an **App-Level Token**.

### 1. Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App > From scratch**.
2. Name it (e.g., "Slack TUI") and select your workspace.

### 2. Enable Socket Mode

1. Navigate to **Settings > Socket Mode** and toggle it on.
2. Create an **App-Level Token** with the `connections:write` scope. Save this token (it starts with `xapp-`).

### 3. Configure OAuth Scopes

Navigate to **Features > OAuth & Permissions** and add scopes.

**Bot Token Scopes** (for `xoxb-` tokens):

| Scope | Purpose |
|-------|---------|
| `channels:read` | List public channels |
| `channels:history` | Read public channel messages |
| `groups:read` | List private channels |
| `groups:history` | Read private channel messages |
| `im:read` | List direct messages |
| `im:history` | Read DM messages |
| `mpim:read` | List group DMs |
| `mpim:history` | Read group DM messages |
| `chat:write` | Send messages and thread replies |
| `users:read` | Resolve user display names and presence |

**Optional scopes** (enable additional features):

| Scope | Purpose |
|-------|---------|
| `files:read` | Download image attachments for inline preview |
| `files:write` | Upload files via `/upload` command |
| `search:read` | Search messages via `/search` command (User Token only) |
| `users:read` | Fetch user presence (online/away indicators) |

> **Tip:** If you want messages to appear as *yourself* rather than as a bot, use a **User Token** (`xoxp-`) instead of a Bot Token. Add the same scopes under **User Token Scopes** on the OAuth & Permissions page. The app accepts either token type. Note that `search:read` is only available as a User Token scope.

### 4. Subscribe to Events

1. Navigate to **Features > Event Subscriptions** and enable events.
2. Under **Subscribe to bot events**, add:
   - `message.channels`
   - `message.groups`
   - `message.im`
   - `message.mpim`

### 5. Install the App

1. Go to **Settings > Install App** and click **Install to Workspace**.
2. Authorize the requested permissions.
3. Copy your **Bot Token** (`xoxb-...`) or **User Token** (`xoxp-...`).

You now have both tokens:

| Token | Prefix | Location |
|-------|--------|----------|
| Bot/User Token | `xoxb-` / `xoxp-` | Settings > OAuth & Permissions |
| App-Level Token | `xapp-` | Settings > Basic Information > App-Level Tokens |

## Usage

```bash
# Using the installed entry point
slack-tui

# Or as a Python module
python -m slack_tui
```

### First Run

On first launch, an authentication dialog prompts for your two tokens. They are saved to `~/.config/slack-tui/config.toml` with restricted file permissions (`0600`). Subsequent launches skip the dialog and connect automatically.

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Tab` | Switch focus between sidebar and message input |
| `Up` / `Down` | Navigate channels in sidebar, or cycle autocomplete suggestions |
| `Enter` | Select a channel, or send a message |
| `Tab` (in autocomplete) | Accept the highlighted suggestion |
| `Escape` | Dismiss autocomplete, or exit thread view |
| `Ctrl+U` | Open the `/upload` prompt |
| `Ctrl+Q` | Quit |

### Slash Commands

Type these in the message input. An autocomplete dropdown appears as you type.

| Command | Description |
|---------|-------------|
| `/msg @user` | Jump to a DM with the specified user |
| `/msg #channel` | Jump to the specified channel |
| `/search <query>` | Search messages across the workspace |
| `/upload <path> [message]` | Upload a file (max 100 MB), with optional comment |
| `/back` | Return to the channel you were in before a search |
| `/thread` | Open the most recent thread in the current channel |
| `/channels` | Reload the channel list from the Slack API |
| `/help` | Show available commands |

## Configuration

### Tokens

Tokens can be provided via environment variables or a config file. Environment variables take precedence.

**Environment variables:**

```bash
export SLACK_BOT_TOKEN="xoxb-..."   # or xoxp-... for a user token
export SLACK_APP_TOKEN="xapp-..."
```

**Config file** (`~/.config/slack-tui/config.toml`, respects `XDG_CONFIG_HOME`):

```toml
[tokens]
bot_token = "xoxb-..."
app_token = "xapp-..."
```

### Logging

Logs are written to `~/.cache/slack-tui/slack-tui.log`. Control the log level with an environment variable:

```bash
export SLACK_TUI_LOG_LEVEL=DEBUG   # DEBUG, INFO, WARNING (default), ERROR
```

### Cache

Cached data is stored at `~/.cache/slack-tui/` (respects `XDG_CACHE_HOME`):

```
~/.cache/slack-tui/
    channels.json          # Channel list with names and types
    users.json             # User ID to display name mapping
    history/
        C01ABC123.json     # Per-channel message history
        D02DEF456.json
    slack-tui.log          # Application log
```

To reset the cache, delete the directory:

```bash
rm -rf ~/.cache/slack-tui
```

## Architecture

```
slack_tui/
    __init__.py            Package marker
    __main__.py            Entry point (logging setup, app launch)
    app.py                 Main Textual app: event wiring, commands, polling loops
    app.tcss               Textual CSS stylesheet (layout, colors, thread styling)
    config.py              Token load/save (TOML config, XDG paths, env vars)
    cache.py               Disk cache for channels, users, and message history
    models.py              Dataclasses: Channel, User, Message, FileAttachment, SearchResult
    slack_client.py        Async Slack API wrapper (conversations, messages, files, search, presence)
    socket_listener.py     Socket Mode WebSocket listener for real-time message events
    image_render.py        Half-block ASCII art renderer for inline image previews
    screens/
        auth_screen.py     Modal token-entry screen (first-run setup)
    widgets/
        sidebar.py         Categorized channel list with collapsible headers and presence dots
        chat_panel.py      Right panel container (message view + autocomplete + input)
        message_view.py    Scrollable message display: colors, links, emoji, threads, search results
        message_input.py   Text input with Enter-to-send, emoji/mention/command autocomplete hooks
        autocomplete.py    Floating dropdown for command, emoji, mention, and path suggestions
pyproject.toml             Project metadata, dependencies, CLI entry point
```

The application uses a single async event loop. The `SlackClient` class wraps the Slack Web API with automatic rate-limit retry. The `SocketListener` provides real-time message delivery via Slack's Socket Mode WebSocket connection, with a background polling fallback that rotates through all channels. The Textual framework handles rendering, keyboard input, and the widget tree.

## License

This project is licensed under the [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.html). See the [LICENSE](LICENSE) file for details.
