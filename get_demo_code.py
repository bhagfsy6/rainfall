import requests
import time
import os
import re
import sys
import random
import string

# ==================== CONFIG ====================
HIDEMY_CHECK_URL = 'https://hdmn.cloud/ru/demo/'
HIDEMY_POST_URL = 'https://hdmn.cloud/ru/demo/success/'
POLL_TIMEOUT_SEC = 720  # 12 minutes
POLL_INTERVAL_SEC = 15

# ==================== TEMP MAIL HELPERS ====================

def create_1secmail():
    """1secmail - no auth, best for automation"""
    try:
        r = requests.get(
            "https://www.1secmail.com/api/v1/?action=genRandomMailbox&count=1",
            timeout=12
        )
        r.raise_for_status()
        email = r.json()[0]
        print(f"[1secmail] Created: {email}")
        return email, "1secmail", None  # service name, no token needed
    except Exception as e:
        print(f"[1secmail] Failed: {e}")
        return None, None, None


def poll_1secmail(email):
    login, domain = email.split("@", 1)
    start = time.time()
    while time.time() - start < POLL_TIMEOUT_SEC:
        try:
            r = requests.get(
                f"https://www.1secmail.com/api/v1/?action=getMessages&login={login}&domain={domain}",
                timeout=10
            )
            msgs = r.json()
            if msgs:
                for msg in sorted(msgs, key=lambda x: x.get('date', ''), reverse=True):
                    mid = msg['id']
                    body_r = requests.get(
                        f"https://www.1secmail.com/api/v1/?action=readMessage&login={login}&domain={domain}&id={mid}",
                        timeout=10
                    )
                    body = body_r.json().get("textBody") or body_r.json().get("htmlBody") or ""
                    code = extract_code(body)
                    if code:
                        return code
            time.sleep(POLL_INTERVAL_SEC)
        except Exception as e:
            print(f"[1secmail poll] {e}")
            time.sleep(POLL_INTERVAL_SEC)
    return None


def create_mail_tm():
    """Mail.tm - free API with account creation"""
    try:
        domains_r = requests.get("https://api.mail.tm/domains", timeout=12)
        domains_r.raise_for_status()
        domain = domains_r.json()["hydra:member"][0]["domain"]

        local = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
        email = f"{local}@{domain}"
        password = "demo12345678"

        acc_r = requests.post(
            "https://api.mail.tm/accounts",
            json={"address": email, "password": password},
            timeout=12
        )
        if acc_r.status_code not in (201, 422):
            raise Exception(acc_r.text)

        token_r = requests.post(
            "https://api.mail.tm/token",
            json={"address": email, "password": password},
            timeout=12
        )
        token_r.raise_for_status()
        token = token_r.json()["token"]

        print(f"[Mail.tm] Created: {email}")
        return email, "mailtm", token
    except Exception as e:
        print(f"[Mail.tm] Failed: {e}")
        return None, None, None


def poll_mail_tm(token):
    headers = {"Authorization": f"Bearer {token}"}
    start = time.time()
    while time.time() - start < POLL_TIMEOUT_SEC:
        try:
            msgs_r = requests.get("https://api.mail.tm/messages", headers=headers, timeout=10)
            msgs = msgs_r.json()["hydra:member"]
            if msgs:
                for msg in sorted(msgs, key=lambda x: x.get('createdAt', ''), reverse=True):
                    msg_r = requests.get(
                        f"https://api.mail.tm/messages/{msg['@id']}",
                        headers=headers,
                        timeout=10
                    )
                    body = msg_r.json().get("text") or msg_r.json().get("intro") or msg_r.json().get("html", "")
                    code = extract_code(body)
                    if code:
                        return code
            time.sleep(POLL_INTERVAL_SEC)
        except Exception as e:
            print(f"[Mail.tm poll] {e}")
            time.sleep(POLL_INTERVAL_SEC)
    return None


def create_temp_mail_io():
    """Temp-Mail.io - simple random (unofficial but often works)"""
    try:
        # This is a common unofficial endpoint used in 2025-2026 scripts
        r = requests.get("https://api.temp-mail.io/request/domains/format/json", timeout=10)
        domains = r.json()
        domain = random.choice(domains)
        local = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        email = f"{local}{domain}"
        print(f"[Temp-Mail.io] Created: {email}")
        return email, "tempmailio", None
    except Exception as e:
        print(f"[Temp-Mail.io] Failed: {e}")
        return None, None, None


def poll_temp_mail_io(email):
    # Temp-Mail.io doesn't have reliable public polling API without hash
    # We skip deep polling here - only basic attempt (you can extend if needed)
    print("[Temp-Mail.io] Polling not fully supported - manual check recommended")
    time.sleep(POLL_TIMEOUT_SEC)
    return None  # placeholder - extend if you find a good polling method


# ==================== COMMON ====================

def extract_code(body):
    if not body:
        return None
    match = re.search(r'Ваш тестовый код:\s*(\d{12,15})', body, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else None


def send_to_telegram(code, email, service):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHANNEL_ID')
    if not token or not chat_id:
        print("⚠️ Telegram secrets missing")
        return

    text = (
        f"🆕 <b>Новый демо-код hidemyname</b>\n\n"
        f"Service: {service}\n"
        f"📧 Email: <code>{email}</code>\n"
        f"🔑 Код: <code>{code}</code>\n"
        f"⏰ Получено: {time.strftime('%d.%m.%Y %H:%M:%S UTC')}\n"
        f"✅ Работает 24 часа"
    )

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
        if r.status_code == 200:
            print("✅ Sent to Telegram")
        else:
            print(f"Telegram fail: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"Telegram error: {e}")


def try_get_demo_code():
    attempts = [
        ("1secmail", create_1secmail, poll_1secmail),
        ("mailtm", create_mail_tm, poll_mail_tm),
        ("tempmailio", create_temp_mail_io, poll_temp_mail_io),
    ]

    for name, create_func, poll_func in attempts:
        print(f"\nTrying {name}...")
        email, service, token = create_func()
        if not email:
            continue

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/132.0.0.0"}
        
        try:
            check_r = requests.get(HIDEMY_CHECK_URL, headers=headers, timeout=20)
            if 'Ваша электронная почта' not in check_r.text:
                print("Hidemy form not found - possible block")
                continue

            post_r = requests.post(
                HIDEMY_POST_URL,
                data={"demo_mail": email},
                headers=headers,
                timeout=20
            )

            if 'Ваш код выслан на почту' in post_r.text:
                print(f"✅ Request sent via {service} - waiting for email...")
                code = poll_func(token if token else email)
                if code:
                    print(f"🎉 CODE FOUND: {code}")
                    send_to_telegram(code, email, service)
                    return True
                else:
                    print("No code received")
            else:
                print(f"No success phrase in response: {post_r.text[:300]}")
        except Exception as e:
            print(f"Error with {service}: {e}")

    print("\nAll temp mail services failed.")
    return False


def main():
    print("🚀 Starting hidemyname demo code grabber")
    print("Date:", time.strftime("%Y-%m-%d %H:%M:%S UTC"))
    
    success = try_get_demo_code()
    
    if not success:
        print("Failed to get code - try running again later or check IP restrictions.")
    else:
        print("Success! Check your Telegram channel.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"Critical error: {e}")
        sys.exit(1)