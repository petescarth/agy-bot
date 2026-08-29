# 🤖 Antigravity (`agy`) Telegram Bot Bridge

An advanced, production-ready Telegram Bot bridge for controlling your headless or remote **Google Antigravity (`agy`) CLI** agent from any device.

---

## 🌟 Why this Bridge is Powerful

A basic subprocess runner fails in headless production because agent workflows require continuous context, long execution streams, cancelability, and workspace navigation. This bot provides a complete remote engineering terminal over Telegram:

| Feature | Naive Script | Antigravity Telegram Bridge |
|---|---|---|
| **Multi-turn Context** | ❌ Lost every message | ✅ Persists via `--conversation <UUID>` |
| **Execution Feedback** | ❌ Silent 60s freeze | ✅ Real-time status stream & tool badges |
| **Cancellation** | ❌ Can't stop runaway task | ✅ Instant `/stop` and `[🛑 Cancel]` button |
| **Workspace Navigation** | ❌ Hardcoded directory | ✅ `/cd`, `/pwd`, `/ls`, `/git` commands |
| **Model & Effort Switching**| ❌ Hardcoded flags | ✅ Interactive picker (`/model`, `/effort`) |
| **Output Length Limits** | ❌ Crashes on >4096 chars | ✅ Smart chunking + `.md` doc attachments |
| **Media & File Ingestion** | ❌ Text-only | ✅ Photo & Document auto-download to workspace |
| **Session Browser** | ❌ None | ✅ Paginated `/sessions` list with 1-tap resume |
| **Daemonization** | ❌ Manual tmux loop | ✅ Production `systemd` service template |

---

## 🚀 Quickstart Guide

### 1. Telegram Bot Setup
1. Message [@BotFather](https://t.me/BotFather) on Telegram and send `/newbot`.
2. Choose a Name and Username for your bot (e.g., `MyAgyAgentBot`).
3. Copy the **API Token** (e.g., `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`).
4. Message [@userinfobot](https://t.me/userinfobot) to get your numerical **Telegram User ID** (e.g., `123456789`).

### 2. Environment Configuration
Copy `.env.example` to `.env` and configure your credentials:
```bash
cp .env.example .env
```
Edit `.env`:
```env
TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN_FROM_BOTFATHER"
ALLOWED_USER_IDS="YOUR_TELEGRAM_USER_ID"
DEFAULT_WORKING_DIR="/home/pete/share/code/agy_bot"
DEFAULT_MODEL="gemini-3.7-flash-high"
DEFAULT_EFFORT="high"
DEFAULT_MODE="accept-edits"
DEFAULT_AUTO_APPROVE="true"
```

### 3. Install Dependencies
```bash
/home/pete/miniforge3/bin/pip install -r requirements.txt
```

### 4. Run the Bot
```bash
/home/pete/miniforge3/bin/python main.py
```

---

## 🎮 Command Reference

### Prompting & Execution
- **Text Message**: Simply type and send any prompt. The bot initiates or continues your active `agy` conversation.
- **File Upload**: Send any file or script. It is automatically saved into your active workspace and passed to the agent with your caption.
- **Image Upload**: Send a diagram or screenshot to instruct the agent to inspect it.
- `/stop` or `/cancel`: Immediately terminates the active `agy` subprocess and releases locks.

### Session Management
- `/new` (or `/clear`): Resets conversation context to start a fresh agent session.
- `/status`: Opens the interactive Control Dashboard with live stats, token counts, and fast setting toggles.
- `/sessions`: Displays a paginated list of previous conversations discovered from `~/.gemini/antigravity-cli/brain/` with 1-tap resume buttons.
- `/resume <conversation_id>`: Resumes a specific past session by UUID.

### Workspace & File Operations
- `/cd <path>`: Changes the current working directory for the agent (supports absolute and relative paths).
- `/pwd`: Shows the current active workspace directory.
- `/ls [path]`: Lists files and directories in the current or specified path.
- `/git`: Displays current Git branch, modified files status, and the most recent commit.

### Agent Settings & Model Tuning
- `/model`: Opens an interactive inline keyboard to select models (Gemini 3.7 Flash, Claude Sonnet 4.6 Thinking, Claude Opus, GPT-OSS 120B).
- `/effort [low|medium|high]`: Adjusts the reasoning effort level.
- `/mode [accept-edits|plan]`: Switches between write mode (`accept-edits`) and read-only analysis mode (`plan`).
- `/perms`: Toggles automatic tool permissions (`--dangerously-skip-permissions`).
- `/help`: Displays the in-chat quick reference guide.

---

## 🖥️ Running as a Background Systemd Service

To keep your bot running 24/7 and survive server reboots:

1. Copy the unit file into your system systemd directory:
   ```bash
   sudo cp agy-bot.service /etc/systemd/system/agy-bot.service
   ```
2. Reload systemd daemon:
   ```bash
   sudo systemctl daemon-reload
   ```
3. Enable and start the service:
   ```bash
   sudo systemctl enable agy-bot
   sudo systemctl start agy-bot
   ```
4. Check status & logs:
   ```bash
   sudo systemctl status agy-bot
   journalctl -u agy-bot -f
   ```

---

## 🔒 Security Best Practices
- **Never expose your bot without `ALLOWED_USER_IDS`**: Setting this ensures unauthorized Telegram users cannot message your bot or execute commands on your host.
- **Auto-Approve vs Plan Mode**: For sensitive repositories or unvetted tasks, switch to `/mode plan` or disable auto-approval via `/perms`.
