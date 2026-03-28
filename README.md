# Slack TUI

A terminal-based Slack client with a two-panel TUI interface.

```
┌──────────┬─────────────────────────────┐
│ Channels │ #general                    │
│          │                             │
│ #general │ alice: Hey everyone!        │
│ #random  │ bob: What's up?             │
│ #dev     │                             │
│          │                             │
│ DMs      │                             │
│ @alice   │                             │
│ @bob     │                             │
│          ├─────────────────────────────┤
│          │ > Type a message...         │
└──────────┴─────────────────────────────┘
```

## Prerequisites

- Python 3.11+
- A Slack workspace where you can create apps

## Slack App Setup

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps) and click **Create New App** > **From scratch**
2. Name it (e.g. "Slack TUI") and pick your workspace

### Enable Socket Mode

3. Go to **Settings > Socket Mode** and toggle it **on**
4. Create an **App-Level Token** with the `connections:write` scope — name it anything (e.g. "socket")
5. Copy the `xapp-...` token — you'll need this later

### Add Bot Scopes

6. Go to **Features > OAuth & Permissions**
7. Under **Bot Token Scopes**, add these scopes:

| Scope | Purpose |
|-------|---------|
| `channels:read` | List public channels |
| `channels:history` | Read public channel messages |
| `groups:read` | List private channels |
| `groups:history` | Read private channel messages |
| `im:read` | List DM conversations |
| `im:history` | Read DM messages |
| `mpim:read` | List group DMs |
| `mpim:history` | Read group DM messages |
| `chat:write` | Send messages |
| `users:read` | Look up user display names |

### Subscribe to Events

8. Go to **Features > Event Subscriptions** and toggle **on**
9. Under **Subscribe to bot events**, add:
   - `message.channels`
   - `message.groups`
   - `message.im`
   - `message.mpim`

### Install the App

10. Go to **Settings > Install App** and click **Install to Workspace**
11. Authorize the permissions
12. Copy the **Bot User OAuth Token** (`xoxb-...`)

## Installation

```bash
cd slack-cli
pip install -e .
```

## Usage

```bash
slack-tui
```

On first run, you'll be prompted for your tokens:
- **Bot Token**: The `xoxb-...` token from step 12
- **App-Level Token**: The `xapp-...` token from step 5

Tokens are saved to `~/.config/slack-tui/config.toml` (permissions 0600).

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Tab` | Switch focus between sidebar and chat input |
| `Up/Down` | Navigate channels in sidebar |
| `Enter` | Select channel / Send message |
| `Ctrl+Q` | Quit |

## Configuration

Tokens are stored at `~/.config/slack-tui/config.toml`:

```toml
[tokens]
bot_token = "xoxb-..."
app_token = "xapp-..."
```

To reconfigure, delete this file and restart the app.
