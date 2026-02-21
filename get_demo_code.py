import requests
import time
import os
import re
import sys
import random
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==================== SESSION WITH RETRIES & HEADERS ====================
def create_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
    })
    return session

# ==================== TEMP EMAIL — 1SECMAIL (free, no key) ====================
def get_random_email(session):
    try:
        # Try to get random mailbox
        resp = session.get(
            "https://www.1secmail.com/api/v1/?action=genRandomMailbox&count=1",
            timeout=12
        )
        resp.raise_for_status()
        data = resp.json()
        if data and isinstance(data, list) and "@" in data[0]:
            email = data[0]
            print(f"✅ Generated temp email: {email}")
            return email
        else:
            raise ValueError("Unexpected response format")
    except Exception as e:
        print(f"genRandomMailbox failed: {e}")
        # Fallback: manual random + known good domains
        domains = ["1secmail.com", "1secmail.net", "1secmail.org", "esiix.com", "wwjmp.com"]
        local = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=10))
        email = f"{local}@{random.choice(domains)}"
        print(f"⚠️ Fallback email: {email}")
        return email


def get_messages_1sec(session, login, domain):
    try:
        url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={login}&domain={domain}"
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return []
    except:
        return []


def read_message_1sec(session, login, domain, msg_id):
    try:
        url = f"https://www.1secmail.com/api/v1/?action=readMessage&login={login}&domain={domain}&id={msg_id}"
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("textBody") or data.get("body") or data.get("htmlBody", "")
        return ""
    except:
        return ""


# ==================== OTHER FUNCTIONS (unchanged) ====================
def extract_demo_code(body):
    match = re.search(r'Ваш тестовый код:\s*(\d{12,15})', body, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else None


def send_to_telegram(code, email):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHANNEL_ID')
    if not token or not chat_id:
        print("⚠️ Missing Telegram env vars")
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
            print("✅ Sent to Telegram")
            return True
        print(f"Telegram fail: {resp.status_code} — {resp.text}")
        return False
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


# ==================== MAIN LOGIC ====================
def main_function():
    print("\n🚀 Автоматическое получение демо-кода")
    print("⏱ Дата:", time.strftime("%Y-%m-%d %H:%M:%S UTC"))
    
    session = create_session()
    
    print("🌐 Создание временного email...")
    email = get_random_email(session)
    if "@" not in email:
        print("❌ Email generation failed completely")
        return
    
    login, domain = email.split("@", 1)
    
    print("🌐 Проверка hidemyname...")
    check_url = 'https://hdmn.cloud/ru/demo/'
    try:
        resp = session.get(check_url, timeout=20)
        resp.raise_for_status()
        if 'Ваша электронная почта' not in resp.text:
            print("⚠️ Форма не найдена — возможно блокировка или изменения на сайте")
            return
        print("✅ Сервис доступен")
        
        print("📨 Запрос демо-кода...")
        post_resp = session.post(
            'https://hdmn.cloud/ru/demo/success/',
            data={"demo_mail": email},
            timeout=20
        )
        post_resp.raise_for_status()
        
        if 'Ваш код выслан на почту' in post_resp.text:
            print('\n' + '✅' * 30)
            print('✅ Код запрошен — ждём письмо (до 12 мин)')
            print('✅' * 30)
            
            time.sleep(30)  # initial wait
            
            start = time.time()
            found = False
            while time.time() - start < 720:
                msgs = get_messages_1sec(session, login, domain)
                if msgs:
                    print(f"📬 Сообщений: {len(msgs)}")
                    for msg in sorted(msgs, key=lambda x: x.get('date', ''), reverse=True):
                        body = read_message_1sec(session, login, domain, msg['id'])
                        code = extract_demo_code(body)
                        if code:
                            print(f'\n🎉 КОД: {code}')
                            send_to_telegram(code, email)
                            found = True
                            break
                if found:
                    break
                time.sleep(20)
            
            if not found:
                print('⏰ Код не пришёл за 12 мин')
                print(f'Проверь вручную: {email}')
        else:
            print("❌ Не 'Ваш код выслан' в ответе")
            print(f"Ответ: {post_resp.text[:200]}...")
    
    except requests.RequestException as e:
        print(f"❌ Ошибка сети с hidemyname: {type(e).__name__}: {e}")
    except Exception as e:
        print(f"❌ Неизвестная ошибка: {e}")


if __name__ == "__main__":
    try:
        main_function()
    except KeyboardInterrupt:
        print("\n⚠️ Прервано")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        sys.exit(1)