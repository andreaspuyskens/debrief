"""Claude API interaction for digest generation."""

import json
import logging
import time

import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a personal newsletter curator. The user receives many newsletters and wants a weekly digest tailored to their interests.

## User's Current Interests
{interests_list}

## Your Task
1. Read each newsletter provided below.
2. For each newsletter, assess its relevance to the user's interests.
3. Produce a digest in the following JSON structure:

{{
  "highlights_intro": "2-3 sentence overview of this week's most interesting findings",
  "sections": [
    {{
      "newsletter_name": "Name / Subject",
      "sender": "sender@example.com",
      "relevance": "high|medium|low|none",
      "summary": "150-300 word summary for relevant newsletters, or a single sentence noting no relevant content for irrelevant ones",
      "key_links": [{{"text": "link text", "url": "https://..."}}]
    }}
  ]
}}

## Rules
- Be concise and information-dense. No filler.
- Preserve important links (research papers, tools, events).
- For irrelevant newsletters, write exactly one sentence: "[Newsletter Name] did not contain content matching your current interests this week."
- Order sections by relevance: high first, then medium, then low, then none.
- Stay within {max_words} words total.
- Write in English.
- Use a professional but approachable tone.
- Respond with ONLY the JSON object, no markdown fences or extra text."""

MAX_RETRIES = 3
INITIAL_BACKOFF = 5  # seconds


def _build_user_message(parsed_emails: list[dict]) -> str:
    """Build the user message containing all newsletter content."""
    parts = []
    for i, email in enumerate(parsed_emails, 1):
        parts.append(
            f"--- Newsletter {i} ---\n"
            f"Subject: {email['subject']}\n"
            f"From: {email['from']}\n"
            f"Date: {email['date']}\n\n"
            f"{email['clean_text']}\n"
        )
        if email.get("links"):
            links_text = "\n".join(
                f"  - [{l['text']}]({l['url']})" for l in email["links"][:10]
            )
            parts.append(f"\nKey links:\n{links_text}\n")
    return "\n\n".join(parts)


def generate_digest(
    parsed_emails: list[dict],
    interests: list[str],
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
    max_words: int = 4500,
) -> dict:
    """
    Send newsletter content to Claude API and return structured digest.

    Returns:
        dict with keys: highlights_intro, sections (list of dicts)
    """
    if not parsed_emails:
        logger.warning("No emails to digest")
        return {"highlights_intro": "No newsletters to process this week.", "sections": []}

    interests_list = "\n".join(f"- {interest}" for interest in interests)
    system = SYSTEM_PROMPT.format(interests_list=interests_list, max_words=max_words)
    user_message = _build_user_message(parsed_emails)

    client = anthropic.Anthropic(api_key=api_key)

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(
                "Calling Claude API (attempt %d/%d, model=%s)", attempt, MAX_RETRIES, model
            )
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )

            raw_text = response.content[0].text
            usage = response.usage
            logger.info(
                "API response: %d input tokens, %d output tokens",
                usage.input_tokens,
                usage.output_tokens,
            )

            # Parse JSON response — strip markdown fences if present
            text = raw_text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            digest = json.loads(text)

            # Sort sections by relevance
            relevance_order = {"high": 0, "medium": 1, "low": 2, "none": 3}
            digest["sections"].sort(
                key=lambda s: relevance_order.get(s.get("relevance", "none"), 4)
            )

            return digest

        except anthropic.RateLimitError as e:
            last_error = e
            backoff = INITIAL_BACKOFF * (2 ** (attempt - 1))
            logger.warning("Rate limited, retrying in %ds: %s", backoff, e)
            time.sleep(backoff)

        except anthropic.APIError as e:
            last_error = e
            backoff = INITIAL_BACKOFF * (2 ** (attempt - 1))
            logger.warning("API error, retrying in %ds: %s", backoff, e)
            time.sleep(backoff)

        except json.JSONDecodeError as e:
            logger.error("Failed to parse Claude response as JSON: %s", e)
            logger.debug("Raw response: %s", raw_text[:500])
            raise ValueError(f"Claude returned invalid JSON: {e}") from e

    raise RuntimeError(
        f"Claude API failed after {MAX_RETRIES} attempts"
    ) from last_error
