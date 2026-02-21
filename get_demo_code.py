import requests
import time
import os
import re
import sys
import random
import string
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==================== CONFIG ====================
HIDEMY_CHECK_URL = 'https://hdmn.cloud/ru/demo/'
HIDEMY_POST_URL  = 'https://hdmn.cloud/ru/demo/success/'
POLL_TIMEOUT_SEC = 720          # 12 minutes
POLL_INTERVAL_SEC = 20

# ==================== SESSION WITH RETRIES ====================
def create_session():
    s = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://hdmn.cloud/ru/demo/",
        "Connection": "keep-alive",
    })
    return s

# ==================== TEMP EMAIL – 1SECMAIL ====================
def create_email(session):
    print("Trying to generate email via 1secmail API...")
    try:
        r = session.get(
            "https://www.1secmail.com/api/v1/?action=genRandomMailbox&count=1",
            timeout=12
        )
        r.raise_for_status()
        email = r.json()[0]
        print(f"Success: {email}")
        return email
    except Exception as e:
        print(f"1secmail API failed: {e}")
        # Fallback – random email on known domains
        domains = [
            "1secmail.com", "1secmail.net", "1secmail.org",
            "esiix.com", "wwjmp.com", "xemaps.com", "tempmail.plus"
        ]
        local = ''.join(random.choices(string.ascii_lowercase + string.digits, k=11))
        email = f"{local}@{random.choice(domains)}"
        print(f"Using fallback email: {email}")
        return email


def get_messages(session, login, domain):
    try:
        url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={login}&domain={domain}"
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
        print(f"getMessages → {r.status_code}")
        return []
    except Exception as e:
        print(f"getMessages error: {e}")
        return []


def read_message(session, login, domain, msg_id):
    try:
        url = f"https://www.1secmail.com/api/v1/?action=readMessage&login={login}&domain={domain}&id={msg_id}"
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("textBody") or data.get("htmlBody") or data.get("body", "")
        print(f"readMessage → {r.status_code}")
        return ""
    except Exception as e:
        print(f"readMessage error: {e}")
        return ""


# ==================== CODE EXTRACTION ====================
def extract_code(body):
    if not body:
        return None
    m = re.search(r'Ваш тестовый код:\s*(\d{12,15})', body, re.IGNORECASE | re.DOTALL)
    return m.group(1) if m else None


# ==================== TELEGRAM ====================
def send_telegram(code, email):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHANNEL_ID")
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID not set")
        return False

    text = (
        f"🆕 Новый демо-код\n\n"
        f"Email: <code>{email}</code>\n"
        f"Код: <code>{code}</code>\n"
        f"Время: {time.strftime('%d.%m.%Y %H:%M:%S UTC')}\n"
        f"Действует 24 часа"
    )

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=10
        )
        if r.status_code == 200:
            print("→ Sent to Telegram")
            return True
        print(f"Telegram failed: {r.status_code} {r.text[:200]}")
        return False
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


# ==================== MAIN LOGIC ====================
def main():
    print("\n🚀 hidemyname demo code grabber")
    print("Date:", time.strftime("%Y-%m-%d %H:%M:%S UTC"))

    session = create_session()

    print("\n1. Creating temporary email...")
    email = create_email(session)
    if "@" not in email:
        print("Email creation failed completely → exit")
        return

    login, domain = email.split("@", 1)

    print("\n2. Checking hidemyname page...")
    try:
        r = session.get(HIDEMY_CHECK_URL, timeout=20)
        r.raise_for_status()
        if 'Ваша электронная почта' not in r.text:
            print("Warning: expected form phrase not found → possible change or block")
    except Exception as e:
        print(f"Cannot reach hidemy check page: {e}")
        return

    print("\n3. Sending demo request...")
    try:
        post_r = session.post(
            HIDEMY_POST_URL,
            data={"demo_mail": email},
            timeout=25
        )
        post_r.raise_for_status()

        print(f"POST status: {post_r.status_code}")
        print("POST body preview (first 400 chars):")
        print(post_r.text[:400] + "..." if len(post_r.text) > 400 else post_r.text)

        if 'Ваш код выслан на почту' in post_r.text:
            print("\n✅ Request accepted – waiting for email (up to 12 min)")
        else:
            print("\n⚠️ No success message in response → probably blocked or form changed")
            return
    except Exception as e:
        print(f"POST request failed: {e}")
        return

    # Polling
    print("\n4. Polling inbox every ~20 seconds...")
    start_time = time.time()
    code = None

    while time.time() - start_time < POLL_TIMEOUT_SEC:
        msgs = get_messages(session, login, domain)
        if msgs:
            print(f"Found {len(msgs)} message(s)")
            for msg in sorted(msgs, key=lambda x: x.get('date', ''), reverse=True):
                body = read_message(session, login, domain, msg['id'])
                code = extract_code(body)
                if code:
                    print(f"\n🎉 CODE FOUND: {code}")
                    send_telegram(code, email)
                    return
        time.sleep(POLL_INTERVAL_SEC)

    print("\n⏰ No code received within time limit")
    print(f"You can check manually: {email}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"\nCritical error: {e}")
        sys.exit(1)