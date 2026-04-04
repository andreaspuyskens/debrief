# Debrief

A self-hosted Python CLI tool that turns your newsletter inbox into a personalized weekly digest. Debrief connects to your mailbox via IMAP, collects newsletters from a designated folder, uses the Claude API to score and summarize them based on your interest profile, and sends you a clean HTML email with only the stuff that matters to you.

## How it works

```
IMAP Fetch → HTML Cleanup → Claude API Summarization → HTML Email → SMTP Send
```

1. Connects to your mailbox via IMAP and pulls emails from a configurable folder (e.g. "Newsletters")
2. Extracts clean text from HTML email bodies, preserving meaningful links
3. Sends all newsletter content along with your interest profile to the Claude API
4. Claude scores each newsletter's relevance (high / medium / low / none) and writes concise summaries
5. Formats the output as a clean, mobile-friendly HTML email
6. Sends the digest to one or more recipients via SMTP

Newsletters that don't match your interests are listed at the bottom with a single line so you won't miss anything.

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/andreaspuyskens/debrief.git
cd debrief
```

### 2. Install dependencies

Python 3.9 or higher is required.

```bash
pip install -r requirements.txt
```

### 3. Configure your credentials

Copy the example files and fill in your details:

```bash
cp .env.example .env
cp config.example.yaml config.yaml
```

Edit `.env` with your email and API credentials:

```env
# IMAP (for reading newsletters)
IMAP_HOST=imap.mailbox.org
IMAP_PORT=993
IMAP_USER=your-email@example.com
IMAP_PASSWORD=your-app-specific-password

# SMTP (for sending the digest)
SMTP_HOST=smtp.mailbox.org
SMTP_PORT=587
SMTP_USER=your-email@example.com
SMTP_PASSWORD=your-app-specific-password

# Claude API (get a key at https://console.anthropic.com)
ANTHROPIC_API_KEY=sk-ant-...
```

> **Note:** Most email providers (Gmail, mailbox.org, Fastmail, etc.) require an app-specific password rather than your regular login password. Check your provider's documentation.

### 4. Define your interests

Edit `config.yaml` and update the `interests` list to match your focus areas. This is the heart of Debrief — Claude uses this profile to decide what's relevant to you.

```yaml
imap_folder: "Newsletters"
lookback_days: 7

digest_recipients:
  - "you@example.com"

interests:
  - "Machine learning and deep learning"
  - "Climate policy and carbon markets"
  - "Jobs and fellowships in AI research"
```

Tips for writing good interests:
- Be specific: *"CRISPR gene editing in agriculture"* beats *"biology"*
- 10–20 interests is a good range
- Group related topics for readability
- Update them as your focus shifts

### 5. Create a newsletter folder

In your email client, create a folder (e.g. "Newsletters") and set up filters/rules to route your newsletter subscriptions into it. The `imap_folder` in `config.yaml` must match the exact folder name.

## Usage

```bash
# Standard run — fetch, digest, and send
python main.py

# Dry run — generate digest and print to terminal, don't send email
python main.py --dry-run

# Force re-process all emails (ignore previously processed)
python main.py --force

# List available newsletters without generating a digest
python main.py --list-only

# Debug logging
python main.py --verbose

# Custom config path
python main.py --config /path/to/config.yaml
```

## Automate it

### macOS (launchd) — recommended

Create a file at `~/Library/LaunchAgents/com.debrief.weekly.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.debrief.weekly</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/debrief/main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/debrief</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>5</integer>
        <key>Hour</key>
        <integer>7</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/path/to/debrief/logs/launchd_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/debrief/logs/launchd_stderr.log</string>
</dict>
</plist>
```

Then load it:

```bash
launchctl load ~/Library/LaunchAgents/com.debrief.weekly.plist
```

> Your Mac needs to be awake at the scheduled time. If it's asleep, macOS will run the job when you next wake it.

### Linux (cron)

```bash
0 7 * * 5 cd /path/to/debrief && /usr/bin/python3 main.py >> logs/cron.log 2>&1
```

## Project structure

```
debrief/
├── main.py                    # CLI entry point
├── config.example.yaml        # Example config (copy to config.yaml)
├── .env.example               # Example secrets (copy to .env)
├── requirements.txt           # Python dependencies
├── src/
│   ├── fetcher.py             # IMAP connection + email retrieval
│   ├── parser.py              # HTML → clean text extraction
│   ├── digest.py              # Claude API interaction + digest generation
│   ├── mailer.py              # SMTP email sending
│   └── templates/
│       └── digest_email.html  # Jinja2 HTML email template
└── logs/                      # Run logs + processed message tracking
```

## Email provider compatibility

Debrief uses standard IMAP and SMTP protocols and should work with any provider. Tested with:

- **mailbox.org** (IMAP: port 993 SSL, SMTP: port 587 STARTTLS)

It should also work with Gmail, Fastmail, Outlook, and others — just update the host/port settings in `.env`.

## Cost

Debrief uses the Claude API, which is pay-per-use. A typical weekly digest with 10–15 newsletters costs roughly **$0.01–0.05** per run depending on newsletter length and the model used. You can monitor your usage at [console.anthropic.com](https://console.anthropic.com).

## Privacy

- Your newsletters are sent to the Anthropic API for summarization. Review [Anthropic's privacy policy](https://www.anthropic.com/privacy) if this is a concern.
- No data is stored anywhere except on your own machine (processed message IDs in `logs/`).
- Your `.env` and `config.yaml` are gitignored and never leave your machine.

## License

MIT — see [LICENSE](LICENSE).

## Author

Built by [Andreas Puyskens](https://github.com/andreaspuyskens). Powered by [Claude](https://anthropic.com).
