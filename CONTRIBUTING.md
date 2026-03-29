# Contributing to Slack TUI

Thank you for your interest in contributing. This guide covers the workflow for reporting bugs, proposing features, and submitting code changes.

## Reporting Bugs

Open a GitHub issue with the following information:

- **What happened** -- Describe the bug clearly. Include any error messages or unexpected behavior.
- **Steps to reproduce** -- Provide the minimal steps needed to trigger the issue.
- **Expected behavior** -- What you expected to happen instead.
- **Environment** -- Python version, OS, terminal emulator, and Textual version (`pip show textual`).
- **Logs** -- Check `~/.cache/slack-tui/slack-tui.log` for relevant error output. Set `SLACK_TUI_LOG_LEVEL=DEBUG` to capture more detail.

## Feature Requests

Open a GitHub issue with:

- A clear description of the feature and the problem it solves.
- Any relevant Slack API endpoints or Textual capabilities involved.
- Whether you are willing to implement it yourself.

Keep in mind that this project aims to stay lean. Features that add significant complexity or heavy dependencies may be declined.

## Development Setup

```bash
# Clone and set up the dev environment
git clone https://github.com/your-username/slack-tui.git
cd slack-tui
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

You will need a Slack workspace with a test app configured. See the [README](README.md#slack-app-setup) for token setup instructions. For development, it is recommended to use a personal or test workspace rather than a production one.

Set your tokens via environment variables so you do not accidentally commit them:

```bash
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_APP_TOKEN="xapp-..."
```

Run the app:

```bash
slack-tui
# or
python -m slack_tui
```

Enable debug logging to see API calls and event processing:

```bash
SLACK_TUI_LOG_LEVEL=DEBUG slack-tui
```

Logs are written to `~/.cache/slack-tui/slack-tui.log`.

## Making Changes

### Workflow

1. **Fork** the repository and clone your fork.
2. **Create a branch** from `main` for your change:
   ```bash
   git checkout -b my-feature
   ```
3. **Make your changes.** Keep commits focused and write clear commit messages.
4. **Test manually** by running the app against a real Slack workspace. Verify that existing features still work.
5. **Push** your branch and open a **Pull Request** against `main`.

### Code Style

- Follow the existing code patterns. The codebase uses standard Python conventions with type hints throughout.
- Use `dataclass` for data models (see `models.py`).
- Use `async`/`await` for all Slack API calls. The `SlackClient` class handles rate limiting automatically via `_rate_limit_retry`.
- Keep widget classes focused. Each widget in `widgets/` handles one concern.
- Use Textual's message-passing pattern (post `TextualMessage` subclasses) for communication between widgets and the app.
- Avoid adding new dependencies unless they are essential. If a feature can be implemented with the standard library or existing dependencies, prefer that.

### Project Structure

| Directory | Purpose |
|-----------|---------|
| `slack_tui/` | Main package |
| `slack_tui/widgets/` | Textual widget classes (sidebar, messages, input, autocomplete) |
| `slack_tui/screens/` | Modal screens (auth dialog) |
| `slack_tui/models.py` | Shared dataclasses |
| `slack_tui/slack_client.py` | All Slack API interaction |
| `slack_tui/cache.py` | Disk cache read/write |

### Testing

There is no automated test suite yet. When submitting changes:

- Run the app and verify your change works end-to-end against a real Slack workspace.
- Test keyboard navigation (Tab between panels, arrow keys, Enter to select).
- Test edge cases: empty channels, long messages, channels with many members, rate limiting.
- If your change affects the sidebar, verify collapsing/expanding categories, unread indicators, and presence dots.
- If your change affects message rendering, verify emoji conversion, link detection, image placeholders, and thread indicators.

If you would like to contribute a test suite, that would be a welcome addition.

### Commit Messages

- Use the imperative mood ("Add feature" not "Added feature").
- Keep the first line under 72 characters.
- Reference issue numbers where applicable (e.g., "Fix sidebar crash on empty channel list (#42)").

## Pull Request Guidelines

- Keep PRs focused. One feature or fix per PR.
- Describe what the PR does and why. Include screenshots or terminal recordings for UI changes.
- Make sure the app starts and runs without errors before submitting.
- Be responsive to review feedback.

## Code of Conduct

Be respectful and constructive. We are all here to build something useful.

- Be welcoming to newcomers.
- Assume good intent.
- Give and accept constructive feedback gracefully.
- Focus on what is best for the project and its users.

Harassment, personal attacks, and unconstructive negativity are not tolerated.
