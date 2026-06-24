import os
import base64
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from email.utils import parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
BASE_DIR = os.path.dirname(__file__)
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")

USER_EMAIL = "marquesadv@marquesss.com.br"


def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def list_threads(service, max_results: int = 200, unread_only: bool = True) -> List[Dict]:
    """List inbox threads, newest first. By default returns only unread threads."""
    labels = ["INBOX", "UNREAD"] if unread_only else ["INBOX"]
    results = []
    page_token = None
    while len(results) < max_results:
        params = {
            "userId": "me",
            "labelIds": labels,
            "maxResults": min(100, max_results - len(results)),
        }
        if page_token:
            params["pageToken"] = page_token
        resp = service.users().threads().list(**params).execute()
        results.extend(resp.get("threads", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results


def get_thread_detail(service, thread_id: str) -> Dict[str, Any]:
    """Fetch a thread with metadata only (no full body) to save quota."""
    return (
        service.users()
        .threads()
        .get(userId="me", id=thread_id, format="metadata",
             metadataHeaders=["From", "To", "Subject", "Date", "Reply-To"])
        .execute()
    )


def is_thread_unread(thread: Dict[str, Any]) -> bool:
    """Check if any message in the thread has the UNREAD label."""
    for msg in thread.get("messages", []):
        if "UNREAD" in msg.get("labelIds", []):
            return True
    return False


def _header_value(headers: List[Dict], name: str) -> str:
    name_lower = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name_lower:
            return h.get("value", "")
    return ""


def parse_thread(thread: Dict, my_email: str = USER_EMAIL) -> Optional[Dict[str, Any]]:
    """
    Extract a compact summary from a thread object.
    Returns None if the thread has no messages.
    """
    messages = thread.get("messages", [])
    if not messages:
        return None

    first_msg = messages[0]
    last_msg = messages[-1]

    def get_headers(msg):
        return msg.get("payload", {}).get("headers", [])

    subject = _header_value(get_headers(first_msg), "Subject") or "(sem assunto)"
    sender = _header_value(get_headers(first_msg), "From")

    # Determine if the last message was sent by us
    last_sender = _header_value(get_headers(last_msg), "From")
    we_replied = my_email.lower() in last_sender.lower()

    # Parse date of last message
    last_date_str = _header_value(get_headers(last_msg), "Date")
    try:
        last_date = parsedate_to_datetime(last_date_str)
        if last_date.tzinfo is None:
            last_date = last_date.replace(tzinfo=timezone.utc)
    except Exception:
        last_date = datetime.now(timezone.utc)

    now = datetime.now(timezone.utc)
    hours_since_last = (now - last_date).total_seconds() / 3600

    # Extract snippet from last message
    snippet = last_msg.get("snippet", "")

    # Extract sender name/email cleanly
    sender_clean = re.sub(r"<.*?>", "", sender).strip().strip('"')
    if not sender_clean:
        sender_clean = sender

    return {
        "thread_id": thread["id"],
        "history_id": thread.get("historyId", ""),
        "subject": subject,
        "sender": sender_clean,
        "sender_raw": sender,
        "message_count": len(messages),
        "we_replied": we_replied,
        "unread": is_thread_unread(thread),
        "hours_since_last": round(hours_since_last, 1),
        "last_date": last_date.isoformat(),
        "snippet": snippet[:300],
    }
