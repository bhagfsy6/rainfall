import requests
import time
import os
import re
import sys
import random
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==================== SESSION SETUP ====================
def create_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504, 403])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    })
    return session

# ==================== 1SECMAIL TEMP EMAIL ====================
def get_random_email(session):
    try:
        resp = session.get(
            "https://www.1secmail.com/api/v1/?action=genRandomMailbox&count=1",
            timeout=15
        )
        resp.raise_for_status()
        emails = resp.json()
        if emails and "@" in emails[0]:
            email = emails[0]
            print(f"✅ Generated: {email}")
            return email
        raise ValueError("No valid email returned")
    except Exception as e:
        print(f"❌ genRandomMailbox failed: {e}")
        # Fallback random
        domains = ["1secmail.com", "1secmail.net", "esiix.com", "wwjmp.com", "1secmail.org"]
        local = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=10))
        email = f"{local}@{random.choice(domains)}"
        print(f"⚠️ Using fallback: {email}")
        return email


def split_email(email):
    return email.split("@", 1)


def get_messages(session, login, domain):
    try:
        url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={login}&domain={domain}"
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        print(f"getMessages HTTP {resp.status_code}")
        return []
    except Exception as e:
        print(f"getMessages error: {e}")
        return []


def read_message(session, login, domain, msg_id):
    try:
        url = f"https://www.1secmail.com/api/v1/?action=readMessage&login={login}&domain={domain}&id={msg_id}"
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("textBody") or data.get("htmlBody") or data.get("body", "")
        print(f"readMessage HTTP {resp.status_code}")
        return ""
    except Exception as e:
        print(f"readMessage error: {e}")
        return ""


# ==================== CODE EXTRACTION & TELEGRAM ====================
def extract_demo_code(body):
    match = re.search(r'Ваш тестовый код:\s*(\d{12,15})', body, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else None


def send_to_telegram(code, email):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHANNEL_ID')
    if not token or not chat_id:
        print("⚠️ Telegram vars missing")
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
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=12
        )
        if resp.status_code == 200:
            print("✅ Отправлено в Telegram")
            return True
        print(f"Telegram fail: {resp.status_code} {resp.text}")
        return False
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


# ==================== MAIN ====================
def main_function():
    print("\n🚀 Получение демо-кода (1secmail API)")
    print("⏱", time.strftime("%Y-%m-%d %H:%M:%S UTC"))
    
    session = create_session()
    
    print("🌐 Создание временного email...")
    email = get_random_email(session)
    login, domain = split_email(email)
    
    print("🌐 Проверка hidemyname...")
    check_url = 'https://hdmn.cloud/ru/demo/'
    
    try:
        resp = session.get(check_url, timeout=20)
        resp.raise_for_status()
        if 'Ваша электронная почта' not in resp.text:
            print("⚠️ Форма не найдена (блокировка/изменения?)")
            return
        
        print("✅ Сервис OK")
        print("📨 Отправка запроса...")
        
        post_resp = session.post(
            'https://hdmn.cloud/ru/demo/success/',
            data={"demo_mail": email},
            timeout=20
        )
        post_resp.raise_for_status()
        
        if 'Ваш код выслан на почту' in post_resp.text:
            print('\n' + '✅' * 30)
            print('✅ Запрос успешен — ждём письмо (до 12 мин)')
            print('✅' * 30)
            
            time.sleep(30)
            
            start = time.time()
            found = False
            seen = set()
            
            while time.time() - start < 720:
                msgs = get_messages(session, login, domain)
                if msgs:
                    print(f"📬 Сообщений: {len(msgs)}")
                    for msg in sorted(msgs, key=lambda x: x.get('date', ''), reverse=True):
                        mid = msg.get('id')
                        if mid in seen:
                            continue
                        body = read_message(session, login, domain, mid)
                        code = extract_demo_code(body)
                        if code:
                            print(f'\n🎉 КОД: {code}')
                            send_to_telegram(code, email)
                            found = True
                            break
                        seen.add(mid)
                if found:
                    break
                time.sleep(20)
            
            if not found:
                print('⏰ Не пришло за 12 мин')
                print(f'Проверь: {email}')
        else:
            print("❌ Нет 'Ваш код выслан' в ответе")
            print(f"Ответ: {post_resp.text[:300]}...")
    
    except requests.RequestException as e:
        print(f"❌ Сеть ошибка: {type(e).__name__} {e}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")


if __name__ == "__main__":
    try:
        main_function()
    except KeyboardInterrupt:
        print("\n⚠️ Прервано")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        sys.exit(1)