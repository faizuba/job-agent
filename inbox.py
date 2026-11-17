"""
inbox.py — how the agent reaches your email.

Two interchangeable classes with the SAME methods:
  FakeInbox   reads sample_data/fake_inbox.json  (practice mode, no Google setup)
  GmailInbox  talks to your real Gmail through the Gmail API

Because both have search() / read() / create_draft(), the agent code doesn't care
which one it's using. This "same interface, swappable backend" trick is worth
remembering. It's how you test agents safely before pointing them at real data.
"""

import base64
import json
import os
from datetime import date, datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path

MAX_BODY_CHARS = 3000   # long emails waste tokens (= money); the model rarely needs more


# ----------------------------------------------------------------------------
# Practice inbox
# ----------------------------------------------------------------------------
class FakeInbox:
    def __init__(self, path="sample_data/fake_inbox.json", drafts_dir="drafts"):
        raw = json.loads(Path(path).read_text())
        today = date.today()
        self.emails = []
        for e in raw:
            # Dates are stored as "days_ago" so the sample stays realistic whenever you run it.
            e = dict(e)
            e["date"] = (today - timedelta(days=e.pop("days_ago"))).isoformat()
            self.emails.append(e)
        self.drafts_dir = Path(drafts_dir)

    def search(self, query: str, max_results: int = 20, newer_than_days: int | None = None):
        # Very simple stand-in for Gmail search: match any plain word in subject/body.
        words = [w.lower() for w in query.split() if ":" not in w and w.upper() != "OR"]
        cutoff = (date.today() - timedelta(days=newer_than_days)).isoformat() if newer_than_days else None
        hits = []
        for e in self.emails:
            if cutoff and e["date"] < cutoff:
                continue
            text = (e["subject"] + " " + e["body"]).lower()
            if not words or any(w in text for w in words):
                hits.append(_summary(e))
        return hits[:max_results]

    def read(self, email_id: str) -> dict:
        for e in self.emails:
            if e["id"] == email_id:
                return {**_summary(e), "body": e["body"][:MAX_BODY_CHARS]}
        raise KeyError(f"No email with id {email_id}")

    def create_draft(self, to: str, subject: str, body: str) -> dict:
        # Practice mode: drafts are saved as text files you can open.
        self.drafts_dir.mkdir(exist_ok=True)
        name = f"draft_{datetime.now():%Y%m%d_%H%M%S}_{len(list(self.drafts_dir.iterdir()))}.txt"
        path = self.drafts_dir / name
        path.write_text(f"To: {to}\nSubject: {subject}\n\n{body}\n")
        return {"saved_to": str(path)}


def _summary(e: dict) -> dict:
    return {"id": e["id"], "from": e["from"], "subject": e["subject"],
            "date": e["date"], "snippet": e["body"][:160]}


# ----------------------------------------------------------------------------
# Real Gmail
# ----------------------------------------------------------------------------
# readonly = read mail. compose = create drafts. The code below never SENDS anything;
# drafts wait in your Gmail Drafts folder for you to review.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]


class GmailInbox:
    def __init__(self, credentials_file="credentials.json", token_file="token.json"):
        # Imported here so practice mode works without the Google libraries installed.
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if os.path.exists(token_file):
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # First run: opens your browser so you can approve access.
                flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
            Path(token_file).write_text(creds.to_json())
        self.service = build("gmail", "v1", credentials=creds)

    def search(self, query: str, max_results: int = 20, newer_than_days: int | None = None):
        if newer_than_days:
            query = f"{query} newer_than:{newer_than_days}d"
        resp = self.service.users().messages().list(
            userId="me", q=query, maxResults=max_results).execute()
        results = []
        for m in resp.get("messages", []):
            msg = self.service.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"]).execute()
            h = _headers(msg)
            results.append({"id": m["id"], "from": h.get("From", ""), "subject": h.get("Subject", ""),
                             "date": _iso_date(msg), "snippet": msg.get("snippet", "")})
        return results

    def read(self, email_id: str) -> dict:
        msg = self.service.users().messages().get(userId="me", id=email_id, format="full").execute()
        h = _headers(msg)
        return {"id": email_id, "from": h.get("From", ""), "subject": h.get("Subject", ""),
                "date": _iso_date(msg), "body": _plain_text(msg["payload"])[:MAX_BODY_CHARS]}

    def create_draft(self, to: str, subject: str, body: str) -> dict:
        mime = MIMEText(body)
        mime["to"], mime["subject"] = to, subject
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        draft = self.service.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}).execute()
        return {"gmail_draft_id": draft["id"], "note": "Saved in Gmail Drafts. Not sent."}


def _headers(msg) -> dict:
    return {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}


def _iso_date(msg) -> str:
    return datetime.fromtimestamp(int(msg["internalDate"]) / 1000).date().isoformat()


def _plain_text(payload) -> str:
    """Emails are trees of parts (text, HTML, attachments). Find the plain-text part."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "replace")
    for part in payload.get("parts", []) or []:
        text = _plain_text(part)
        if text:
            return text
    return ""
