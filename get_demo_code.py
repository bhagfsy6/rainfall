import requests
import time
import os
import re
import sys
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==================== SESSION WITH RETRIES & HEADERS ====================
def create_session():
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504, 403],
        allowed_methods=["GET", "POST"],
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
        "Origin": "https://temp-mail.org",
        "Referer": "https://temp-mail.org/",
    })
    return session

# ==================== TEMP-MAIL.ORG (web2 API style from your Go code) ====================
BASE_URL = "https://web2.temp-mail.org"

def create_temp_mailbox(session):
    """POST to create new mailbox → returns token & email"""
    try:
        resp = session.post(f"{BASE_URL}/mailbox", json={}, timeout=12)  # empty body as in Go
        resp.raise_for_status()
        data = resp.json()
        token = data.get("token")
        email = data.get("mailbox")
        if not token or not email:
            raise ValueError("Missing token or mailbox in response")
        print(f"✅ Created temp mailbox: {email}")
        return email, token
    except Exception as e:
        print(f"❌ Failed to create mailbox: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text[:300]}")
        sys.exit(1)


def get_messages(session, token):
    """GET list of message IDs"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = session.get(f"{BASE_URL}/messages", headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # Assuming response like {"mailbox": "...", "messages": [{"_id": "..."}, ...]}
        return data.get("messages", [])
    except Exception as e:
        print(f"❌ Failed to fetch messages list: {e}")
        return []


def read_message(session, token, msg_id):
    """GET full message by _id"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{BASE_URL}/messages/{msg_id}"
        resp = session.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # Prefer bodyHtml if available, fallback to bodyPreview or text
        return (
            data.get("bodyHtml") or
            data.get("textBody") or
            data.get("bodyPreview") or
            ""
        )
    except Exception as e:
        print(f"❌ Failed to read message {msg_id}: {e}")
        return ""


# ==================== EXTRACT CODE & SEND TO TELEGRAM (unchanged) ====================
def extract_demo_code(body):
    match = re.search(r'Ваш тестовый код:\s*(\d{12,15})', body, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else None


def send_to_telegram(code, email):
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHANNEL_ID')
    if not bot_token or not chat_id:
        print("⚠️ TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID not set in env/secrets")
        return False
    
    text = (
        f"🆕 <b>Новый демо-код hidemyname</b>\n\n"
        f"📧 Email: <code>{email}</code>\n"
        f"🔑 Код: <code>{code}</code>\n"
        f"⏰ Получено: {time.strftime('%d.%m.%Y %H:%M:%S UTC')}\n"
        f"✅ Работает 24 часа"
    )
    
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=12
        )
        if resp.status_code == 200:
            print("✅ Код отправлен в Telegram-канал")
            return True
        print(f"❌ Telegram ошибка: {resp.status_code} — {resp.text}")
        return False
    except Exception as e:
        print(f"❌ Telegram отправка провалилась: {e}")
        return False


# ==================== MAIN LOGIC ====================
def main_function():
    print("\n🚀 Запуск получения демо-кода (temp-mail.org web2 API)")
    print("⏱", time.strftime("%Y-%m-%d %H:%M:%S UTC"))
    
    session = create_session()
    
    print("🌐 Создание временного ящика...")
    email, token = create_temp_mailbox(session)
    
    print("🌐 Подключение к hidemyname...")
    check_url = 'https://hdmn.cloud/ru/demo/'
    
    try:
        resp = session.get(check_url, timeout=20)
        resp.raise_for_status()
        if 'Ваша электронная почта' not in resp.text:
            print("⚠️ Форма не найдена — возможно изменения или блокировка")
            return
        
        print("✅ Сервис доступен")
        print("📨 Отправка запроса на демо...")
        
        post_resp = session.post(
            'https://hdmn.cloud/ru/demo/success/',
            data={"demo_mail": email},
            timeout=20
        )
        post_resp.raise_for_status()
        
        if 'Ваш код выслан на почту' in post_resp.text:
            print('\n' + '✅' * 30)
            print('✅ УСПЕХ! Код отправлен на почту')
            print('📩 Ожидание письма (до 12 минут)...')
            print('✅' * 30)
            
            time.sleep(30)  # initial delay
            
            start_time = time.time()
            code_found = False
            seen_ids = set()
            
            while time.time() - start_time < 720:
                messages = get_messages(session, token)
                if messages:
                    print(f"📬 Найдено сообщений: {len(messages)}")
                    for msg in messages:
                        msg_id = msg.get("_id")
                        if not msg_id or msg_id in seen_ids:
                            continue
                        body = read_message(session, token, msg_id)
                        if not body:
                            continue
                        
                        code = extract_demo_code(body)
                        if code:
                            print(f'\n🎉 КОД ПОЛУЧЕН: {code}')
                            send_to_telegram(code, email)
                            code_found = True
                            seen_ids.add(msg_id)
                            break  # one code is enough
                        
                        seen_ids.add(msg_id)
                
                if code_found:
                    break
                
                time.sleep(15)  # poll every 15s
            
            if not code_found:
                print('⏰ Код не пришёл за 12 минут')
                print(f'Email для ручной проверки: {email}')
        
        else:
            print("❌ Ответ не содержит 'Ваш код выслан на почту'")
            print(f"Ответ сервера: {post_resp.text[:300]}...")
    
    except requests.RequestException as e:
        print(f"❌ Сетевая ошибка: {type(e).__name__}: {e}")
    except Exception as e:
        print(f"❌ Неизвестная ошибка: {e}")


if __name__ == "__main__":
    try:
        main_function()
    except KeyboardInterrupt:
        print("\n⚠️ Прервано пользователем")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        sys.exit(1)