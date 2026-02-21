import requests
import time
import os
import re
import sys
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==================== SESSION WITH RETRIES & BROWSER MIMIC ====================
def create_session():
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        "Origin": "https://temp-mail.org",
        "Referer": "https://temp-mail.org/",
        "Connection": "keep-alive",
    })
    return session

# ==================== TEMP-MAIL.ORG (web2 unofficial API – exact from your Go) ====================
BASE_URL = "https://web2.temp-mail.org"

def create_temp_mailbox(session):
    print("→ POST /mailbox ...")
    try:
        # Pre-warm: GET main page (mimic user visiting site)
        session.get("https://temp-mail.org/en/", timeout=10)
        
        resp = session.post(
            f"{BASE_URL}/mailbox",
            json={},  # empty body like in Go
            timeout=30  # longer timeout in case it's slow
        )
        print(f"← Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"Body preview: {resp.text[:400]}")
            resp.raise_for_status()
        
        data = resp.json()
        token = data.get("token")
        email = data.get("mailbox")
        
        if not token or not email:
            raise ValueError("Missing 'token' or 'mailbox' in JSON")
        
        print(f"✅ Mailbox created: {email}")
        return email, token
    
    except requests.Timeout:
        print("⏰ TIMEOUT on /mailbox – endpoint may be blocking or extremely slow")
        raise
    except requests.RequestException as e:
        print(f"Network/Request error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Status: {e.response.status_code}")
            print(f"Body: {e.response.text[:600]}")
        raise
    except ValueError as ve:
        print(f"JSON/Format error: {ve}")
        print(f"Raw response: {resp.text if 'resp' in locals() else 'No response'}")
        raise


def get_messages(session, token):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = session.get(f"{BASE_URL}/messages", headers=headers, timeout=10)
        if resp.status_code != 200:
            print(f"/messages HTTP {resp.status_code} - {resp.text[:200]}")
            return []
        data = resp.json()
        return data.get("messages", [])
    except Exception as e:
        print(f"get_messages failed: {e}")
        return []


def read_message(session, token, msg_id):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{BASE_URL}/messages/{msg_id}"
        resp = session.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            print(f"read {msg_id} HTTP {resp.status_code}")
            return ""
        data = resp.json()
        return data.get("bodyHtml") or data.get("bodyPreview") or ""
    except Exception as e:
        print(f"read_message {msg_id} error: {e}")
        return ""


# ==================== CODE & TELEGRAM (same as before) ====================
def extract_demo_code(body):
    match = re.search(r'Ваш тестовый код:\s*(\d{12,15})', body, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1)
    return None


def send_to_telegram(code, email):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHANNEL_ID')
    if not token or not chat_id:
        print("⚠️ Telegram secrets missing")
        return False
    
    text = f"🆕 Новый демо-код\nEmail: {email}\nКод: {code}\n⏰ {time.strftime('%d.%m.%Y %H:%M:%S')}"
    
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
        if resp.status_code == 200:
            print("✅ Sent to channel")
            return True
        print(f"Telegram fail: {resp.text}")
        return False
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


# ==================== MAIN FLOW ====================
def main_function():
    print("\n🚀 Запуск (temp-mail.org web2 API)")
    print("⏱", time.strftime("%Y-%m-%d %H:%M:%S UTC"))
    
    session = create_session()
    
    print("🌐 Создание временного ящика...")
    try:
        email, token = create_temp_mailbox(session)
    except Exception as e:
        print(f"Creation completely failed: {e}")
        return
    
    print("🌐 Подключение к hidemyname...")
    check_url = 'https://hdmn.cloud/ru/demo/'
    
    try:
        resp = session.get(check_url, timeout=20)
        resp.raise_for_status()
        if 'Ваша электронная почта' not in resp.text:
            print("⚠️ Форма не найдена")
            return
        
        print("✅ Сервис доступен")
        print("📨 Отправка запроса...")
        
        post_resp = session.post(
            'https://hdmn.cloud/ru/demo/success/',
            data={"demo_mail": email},
            timeout=20
        )
        post_resp.raise_for_status()
        
        if 'Ваш код выслан на почту' in post_resp.text:
            print('\n✅' * 8 + " Код запрошен – ждём 12 мин " + '✅' * 8)
            
            time.sleep(30)
            
            start_time = time.time()
            code_found = False
            seen_ids = set()
            
            while time.time() - start_time < 720:
                messages = get_messages(session, token)
                if messages:
                    print(f"📬 {len(messages)} сообщений")
                    for msg in messages:
                        msg_id = msg.get("_id")
                        if not msg_id or msg_id in seen_ids:
                            continue
                        body = read_message(session, token, msg_id)
                        code = extract_demo_code(body)
                        if code:
                            print(f"🎉 КОД: {code}")
                            send_to_telegram(code, email)
                            code_found = True
                            break
                        seen_ids.add(msg_id)
                if code_found:
                    break
                time.sleep(20)
            
            if not code_found:
                print("⏰ Код не пришёл")
                print(f"Email: {email}")
        else:
            print("❌ Нет фразы о коде в ответе")
            print(post_resp.text)
    
    except Exception as e:
        print(f"Ошибка в hidemyname части: {e}")


if __name__ == "__main__":
    try:
        main_function()
    except KeyboardInterrupt:
        print("\nПрервано")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        sys.exit(1)