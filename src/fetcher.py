"""IMAP connection and email retrieval for newsletter fetching."""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

from imap_tools import MailBox, AND

logger = logging.getLogger(__name__)

PROCESSED_IDS_PATH = Path(__file__).parent.parent / "logs" / "processed_ids.json"
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


def load_processed_ids() -> set[str]:
    """Load previously processed message IDs from disk."""
    if PROCESSED_IDS_PATH.exists():
        with open(PROCESSED_IDS_PATH) as f:
            return set(json.load(f))
    return set()


def save_processed_ids(ids: set[str]) -> None:
    """Persist processed message IDs to disk."""
    PROCESSED_IDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROCESSED_IDS_PATH, "w") as f:
        json.dump(sorted(ids), f, indent=2)


def fetch_newsletters(
    host: str,
    port: int,
    user: str,
    password: str,
    folder: str = "Newsletters",
    lookback_days: int = 7,
    force: bool = False,
) -> list[dict]:
    """
    Connect to IMAP server and fetch emails from the configured folder.

    Returns a list of dicts with keys:
        subject, from, date, html_body, text_body, message_id
    """
    since_date = datetime.now() - timedelta(days=lookback_days)
    processed_ids = set() if force else load_processed_ids()

    emails = []
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(
                "Connecting to %s:%d (attempt %d/%d)", host, port, attempt, MAX_RETRIES
            )
            with MailBox(host, port).login(user, password, folder) as mailbox:
                criteria = AND(date_gte=since_date.date())
                for msg in mailbox.fetch(criteria, mark_seen=False):
                    if msg.uid in processed_ids:
                        logger.debug("Skipping already-processed: %s", msg.subject)
                        continue

                    emails.append(
                        {
                            "subject": msg.subject or "(no subject)",
                            "from": msg.from_ or "",
                            "date": msg.date,
                            "html_body": msg.html or "",
                            "text_body": msg.text or "",
                            "message_id": msg.uid,
                        }
                    )

            logger.info("Fetched %d new email(s) from '%s'", len(emails), folder)
            return emails

        except Exception as e:
            last_error = e
            logger.warning("Attempt %d failed: %s", attempt, e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)

    logger.error("All %d connection attempts failed", MAX_RETRIES)
    raise ConnectionError(
        f"Could not connect to {host} after {MAX_RETRIES} attempts"
    ) from last_error


def mark_as_processed(message_ids: list[str]) -> None:
    """Add message IDs to the processed set after successful digest generation."""
    existing = load_processed_ids()
    existing.update(message_ids)
    save_processed_ids(existing)
    logger.info("Marked %d message(s) as processed", len(message_ids))
