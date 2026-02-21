import requests
import time
import os
import re
import sys

# ==================== TEMP-MAIL.ORG (web2 unofficial API – plain requests) ====================
BASE_URL = "https://web2.temp-mail.org"

def create_temp_mailbox():
    url = f"{BASE_URL}/mailbox"
    print(f"→ POST {url}")
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "PostmanRuntime/7.49.1",  # your working curl UA
    }
    
    print("Headers:", headers)
    
    try:
        resp = requests.post(
            url,
            json={},  # empty body
            headers=headers,
            timeout=60
        )
        
        print(f"← Status: {resp.status_code}")
        print("Response headers:", dict(resp.headers))
        print("Body preview:", resp.text[:600] if resp.text else "<empty body>")
        
        resp.raise_for_status()
        
        data = resp.json()
        token = data.get("token")
        email = data.get("mailbox")
        
        if not token or not email:
            raise ValueError("No 'token' or 'mailbox' in response JSON")
        
        print(f"✅ Created: {email} (token starts with {token[:15]}...)")
        return email, token
    
    except requests.Timeout:
        print("!!! TIMEOUT (60s) – likely IP blocked or endpoint dead")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"!!! Request error: {e}")
        if 'response' in locals() and resp is not None:
            print(f"Status: {resp.status_code}")
            print(f"Body: {resp.text[:800] if resp.text else '<no body>'}")
        sys.exit(1)
    except ValueError as ve:
        print(f"!!! JSON error: {ve}")
        if 'resp' in locals():
            print(f"Raw body: {resp.text}")
        sys.exit(1)


def get_messages(token):
    url = f"{BASE_URL}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "PostmanRuntime/7.49.1",
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"/messages → {resp.status_code} {resp.text[:200]}")
            return []
        data = resp.json()
        return data.get("messages", [])
    except Exception as e:
        print(f"get_messages error: {e}")
        return []


def read_message(token, msg_id):
    url = f"{BASE_URL}/messages/{msg_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "PostmanRuntime/7.49.1",
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"read {msg_id} → {resp.status_code}")
            return ""
        data = resp.json()
        return data.get("bodyHtml") or data.get("bodyPreview") or data.get("textBody") or ""
    except Exception as e:
        print(f"read_message error: {e}")
        return ""


# ==================== CODE EXTRACTION & TELEGRAM ====================
def extract_demo_code(body):
    match = re.search(r'Ваш тестовый код:\s*(\d{12,15})', body, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else None


def send_to_telegram(code, email):
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHANNEL_ID')
    if not bot_token or not chat_id:
        print("⚠️ Telegram env vars missing")
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
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=15
        )
        if resp.status_code == 200:
            print("✅ Отправлено в Telegram")
            return True
        print(f"Telegram fail: {resp.status_code} — {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


# ==================== MAIN ====================
def main_function():
    print("\n🚀 Запуск (temp-mail.org web2 API – no session)")
    print("⏱", time.strftime("%Y-%m-%d %H:%M:%S UTC"))
    
    print("🌐 Создание временного ящика...")
    email, token = create_temp_mailbox()
    
    print("🌐 Подключение к hidemyname...")
    check_url = 'https://hdmn.cloud/ru/demo/'
    
    try:
        headers_check = {"User-Agent": "PostmanRuntime/7.49.1"}
        resp = requests.get(check_url, headers=headers_check, timeout=20)
        resp.raise_for_status()
        
        if 'Ваша электронная почта' not in resp.text:
            print("⚠️ Форма не найдена — возможно блок или изменения")
            return
        
        print("✅ Сервис доступен")
        print("📨 Отправка запроса...")
        
        headers_post = {"User-Agent": "PostmanRuntime/7.49.1"}
        post_resp = requests.post(
            'https://hdmn.cloud/ru/demo/success/',
            data={"demo_mail": email},
            headers=headers_post,
            timeout=20
        )
        post_resp.raise_for_status()
        
        if 'Ваш код выслан на почту' in post_resp.text:
            print('\n' + '✅' * 30)
            print('✅ Код запрошен — ждём письмо (до 12 мин)')
            print('✅' * 30)
            
            time.sleep(30)
            
            start_time = time.time()
            code_found = False
            seen_ids = set()
            
            while time.time() - start_time < 720:
                messages = get_messages(token)
                if messages:
                    print(f"📬 Найдено сообщений: {len(messages)}")
                    for msg in messages:
                        msg_id = msg.get("_id")
                        if not msg_id or msg_id in seen_ids:
                            continue
                        body = read_message(token, msg_id)
                        if not body:
                            continue
                        code = extract_demo_code(body)
                        if code:
                            print(f'\n🎉 КОД ПОЛУЧЕН: {code}')
                            send_to_telegram(code, email)
                            code_found = True
                            break
                        seen_ids.add(msg_id)
                
                if code_found:
                    break
                
                time.sleep(15)
            
            if not code_found:
                print('⏰ Письмо не пришло за 12 мин')
                print(f'Email для проверки: {email}')
        
        else:
            print('\n❌ Нет "Ваш код выслан на почту"')
            print(f"Ответ: {post_resp.text[:400]}...")
    
    except Exception as e:
        print(f"Ошибка: {e}")


if __name__ == "__main__":
    try:
        main_function()
    except KeyboardInterrupt:
        print("\n⚠️ Прервано")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        sys.exit(1)