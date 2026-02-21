import requests
import time
import os
import re
import sys
import random
import string
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CHECK_URL = 'https://hdmn.cloud/ru/demo/'
POST_URL  = 'https://hdmn.cloud/ru/demo/success/'

POLL_TIMEOUT_SEC = 720
POLL_INTERVAL_SEC = 20

def create_session():
    s = requests.Session()

    retry = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))

    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://hdmn.cloud/ru/demo/",
        "Origin": "https://hdmn.cloud",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })

    proxy_url = os.getenv("PROXY_URL")
    if proxy_url:
        s.proxies = {"http": proxy_url, "https": proxy_url}
        print(f"Proxy enabled: {proxy_url}")
    else:
        print("No proxy configured (set PROXY_URL env var)")

    return s


def create_email(session):
    print("Generating temporary email...")
    try:
        r = session.get(
            "https://www.1secmail.com/api/v1/?action=genRandomMailbox&count=1",
            timeout=12
        )
        r.raise_for_status()
        email = r.json()[0]
        print(f"1secmail success → {email}")
        return email
    except Exception as e:
        print(f"1secmail API failed: {e}")
        domains = [
            "1secmail.com", "1secmail.net", "1secmail.org",
            "esiix.com", "wwjmp.com", "xemaps.com", "tempmail.plus"
        ]
        local = ''.join(random.choices(string.ascii_lowercase + string.digits, k=11))
        email = f"{local}@{random.choice(domains)}"
        print(f"Fallback email: {email}")
        return email


def get_messages(session, login, domain):
    try:
        url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={login}&domain={domain}"
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
        print(f"getMessages {r.status_code}")
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
        print(f"readMessage {r.status_code}")
        return ""
    except Exception as e:
        print(f"readMessage error: {e}")
        return ""


def extract_code(body):
    if not body:
        return None
    m = re.search(r'Ваш тестовый код:\s*(\d{12,15})', body, re.IGNORECASE | re.DOTALL)
    return m.group(1) if m else None


def send_telegram(code, email):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHANNEL_ID")
    if not token or not chat_id:
        print("Telegram credentials missing")
        return

    text = (
        f"Новый демо-код\n"
        f"Email: {email}\n"
        f"Код: {code}\n"
        f"Получено: {time.strftime('%d.%m.%Y %H:%M:%S UTC')}\n"
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
            print("Message sent to Telegram")
        else:
            print(f"Telegram send failed: {r.status_code} {r.text[:300]}")
    except Exception as e:
        print(f"Telegram error: {e}")


def main():
    print("hidemyname demo code grabber")
    print("Date:", time.strftime("%Y-%m-%d %H:%M:%S UTC"))

    session = create_session()

    print("\nCreating temp email...")
    email = create_email(session)
    if "@" not in email:
        print("Email creation failed")
        return

    login, domain = email.split("@", 1)

    print("\nChecking form page...")
    try:
        r = session.get(CHECK_URL, timeout=20)
        r.raise_for_status()
        print(f"GET status: {r.status_code}  (length: {len(r.text)})")
    except Exception as e:
        print(f"GET failed: {e}")
        return

    print("\nSending POST request...")
    try:
        post_r = session.post(
            POST_URL,
            data={"demo_mail": email},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=25
        )

        print(f"POST status: {post_r.status_code}")
        print(f"Content-Type: {post_r.headers.get('Content-Type', 'unknown')}")
        print(f"Content-Length: {len(post_r.text)}")

        if len(post_r.text) < 4000:
            print("Full response body:")
            print(post_r.text)
        else:
            print("Response preview (first 4000 chars):")
            print(post_r.text[:4000])
            print("... (truncated)")

        if 'Ваш код выслан на почту' in post_r.text:
            print("\nRequest accepted — starting polling")
        else:
            print("\nNo success phrase detected")
            return
    except Exception as e:
        print(f"POST failed: {e}")
        return

    print("\nPolling inbox...")
    start = time.time()
    code = None

    time.sleep(30)  # give server time to send email

    while time.time() - start < POLL_TIMEOUT_SEC:
        msgs = get_messages(session, login, domain)
        if msgs:
            print(f"Found {len(msgs)} message(s)")
            for msg in sorted(msgs, key=lambda x: x.get('date', ''), reverse=True):
                body = read_message(session, login, domain, msg['id'])
                code = extract_code(body)
                if code:
                    print(f"\nCODE: {code}")
                    send_telegram(code, email)
                    return
        time.sleep(POLL_INTERVAL_SEC)

    print("No code received in time")
    print(f"Email: {email}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped by user")
    except Exception as e:
        print(f"Critical error: {e}")
        sys.exit(1)