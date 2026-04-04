"""Debrief — Personal newsletter digest CLI."""

__version__ = "0.1.0"

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.fetcher import fetch_newsletters, mark_as_processed
from src.parser import parse_email
from src.digest import generate_digest
from src.mailer import render_digest, send_digest

LOG_DIR = Path(__file__).parent / "logs"


def setup_logging(verbose: bool = False) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(LOG_DIR / "digest.log"),
        ],
    )


def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Debrief — Newsletter digest generator")
    parser.add_argument("--dry-run", action="store_true", help="Generate digest but don't send email; output to stdout")
    parser.add_argument("--force", action="store_true", help="Re-process all emails (ignore processed IDs)")
    parser.add_argument("--list-only", action="store_true", help="Only list available newsletters, don't generate digest")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("--version", action="version", version=f"debrief {__version__}")
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger("debrief")

    load_dotenv(override=True)
    config = load_config(args.config)

    # Fetch
    logger.info("Fetching newsletters from '%s'", config["imap_folder"])
    try:
        emails = fetch_newsletters(
            host=os.getenv("IMAP_HOST"),
            port=int(os.getenv("IMAP_PORT", "993")),
            user=os.getenv("IMAP_USER"),
            password=os.getenv("IMAP_PASSWORD"),
            folder=config["imap_folder"],
            lookback_days=config.get("lookback_days", 7),
            force=args.force,
        )
    except ConnectionError as e:
        logger.error("Failed to fetch emails: %s", e)
        sys.exit(1)

    if not emails:
        logger.info("No new newsletters found.")
        print("No new newsletters found.")
        return

    # List only
    if args.list_only:
        print(f"Found {len(emails)} newsletter(s):\n")
        for e in emails:
            print(f"  [{e['date']}] {e['from']}")
            print(f"    {e['subject']}")
            print()
        return

    # Parse
    logger.info("Parsing %d email(s)", len(emails))
    parsed = [parse_email(e) for e in emails]
    total_words = sum(p["word_count"] for p in parsed)
    logger.info("Total words across newsletters: %d", total_words)

    # Generate digest
    logger.info("Generating digest via Claude API")
    try:
        digest = generate_digest(
            parsed_emails=parsed,
            interests=config["interests"],
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            model=config.get("claude_model", "claude-sonnet-4-20250514"),
            max_words=config.get("digest_max_words", 4500),
        )
    except (ValueError, RuntimeError) as e:
        logger.error("Digest generation failed: %s", e)
        sys.exit(1)

    # Render
    html, plain_text = render_digest(digest)

    if args.dry_run:
        print(plain_text)
        logger.info("Dry run complete — email not sent")
    else:
        # Send
        logger.info("Sending digest email")
        try:
            recipients = config.get("digest_recipients", config.get("digest_recipient", []))
            if isinstance(recipients, str):
                recipients = [recipients]
            send_digest(
                html=html,
                plain_text=plain_text,
                smtp_host=os.getenv("SMTP_HOST"),
                smtp_port=int(os.getenv("SMTP_PORT", "587")),
                smtp_user=os.getenv("SMTP_USER"),
                smtp_password=os.getenv("SMTP_PASSWORD"),
                recipients=recipients,
                sender_name=config.get("digest_sender_name", "Newsletter Digest"),
            )
            print(f"Digest sent to {', '.join(recipients)}")
        except Exception as e:
            logger.error("Failed to send digest: %s", e)
            sys.exit(1)

    # Mark as processed
    message_ids = [e["message_id"] for e in emails]
    mark_as_processed(message_ids)


if __name__ == "__main__":
    main()
