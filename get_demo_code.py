import requests
import time
import os
import re
import sys

# ==================== ВРЕМЕННЫЙ EMAIL (1SecMail API - без ключей, полностью бесплатный) ====================
def get_random_email():
    """Генерирует случайный временный email через публичный API 1secmail.com"""
    try:
        resp = requests.get(
            "https://www.1secmail.com/api/v1/?action=genRandomMailbox&count=1",
            timeout=10
        )
        if resp.status_code == 200:
            email = resp.json()[0]
            print(f"✅ Сгенерирован временный email: {email}")
            return email
        else:
            raise Exception(f"HTTP {resp.status_code}")
    except Exception as e:
        print(f"❌ Не удалось создать временный email: {e}")
        sys.exit(1)


def split_email(email):
    login, domain = email.split('@')
    return login, domain


def get_messages(login, domain):
    """Получает список писем в ящике"""
    try:
        url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={login}&domain={domain}"
        resp = requests.get(url, timeout=10)
        return resp.json() if resp.status_code == 200 else []
    except:
        return []


def read_message(login, domain, msg_id):
    """Читает полное письмо"""
    try:
        url = f"https://www.1secmail.com/api/v1/?action=readMessage&login={login}&domain={domain}&id={msg_id}"
        resp = requests.get(url, timeout=10)
        return resp.json() if resp.status_code == 200 else {}
    except:
        return {}


def extract_demo_code(body):
    """Извлекает только цифры кода из письма"""
    # Ищем "Ваш тестовый код: 34241999578662"
    match = re.search(r'Ваш тестовый код:\s*(\d{12,15})', body, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1)
    return None


def send_to_telegram(code, email):
    """Отправляет код в ваш Telegram-канал"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHANNEL_ID')
    
    if not token or not chat_id:
        print("⚠️ TELEGRAM_BOT_TOKEN или TELEGRAM_CHANNEL_ID не заданы в окружении")
        return False
    
    text = (
        f"🆕 <b>Новый демо-код hidemyname</b>\n\n"
        f"📧 Email: <code>{email}</code>\n"
        f"🔑 Код: <code>{code}</code>\n"
        f"⏰ Получено: {time.strftime('%d.%m.%Y %H:%M:%S')}\n\n"
        f"✅ Работает 24 часа"
    )
    
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=10
        )
        if resp.status_code == 200:
            print("✅ Код успешно отправлен в Telegram-канал")
            return True
        else:
            print(f"❌ Ошибка Telegram: {resp.status_code} — {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Не удалось отправить в Telegram: {e}")
        return False


# ==================== ОСНОВНАЯ ЛОГИКА (расширенная оригинальная функция) ====================
def main_function():
    print("\n🚀 Запуск автоматического получения демо-кода (GitHub Actions)")
    print("🌐 Создание временного email...")

    email = get_random_email()
    login, domain = split_email(email)

    print("🌐 Подключение к hidemyname...")
    check_url = 'https://hdmn.cloud/ru/demo/'

    try:
        response = requests.get(check_url, timeout=15)
        
        if response.status_code != 200:
            print(f'⚠️ Ошибка сервиса: HTTP {response.status_code}')
            return

        if 'Ваша электронная почта' not in response.text:
            print('⚠️\033[1;31m Отключитесь от среды выполнения и удалите её\033[0m')
            return

        print("✅ Сервис доступен")
        print("📨 Отправка запроса на демо-код...")

        post_response = requests.post(
            'https://hdmn.cloud/ru/demo/success/',
            data={"demo_mail": email},
            timeout=15
        )

        if 'Ваш код выслан на почту' in post_response.text:
            print('\n' + '✅' * 25)
            print('✅\033[1;32m УСПЕХ! Код отправлен на почту!\033[0m')
            print('📩 Ожидание письма (максимум 10 минут)...')
            print('✅' * 25)

            # === ПОЛЛИНГ ЯЩИКА ===
            print("⏳ Проверяем почту каждые 15 секунд...")
            start_time = time.time()
            code_found = False

            while time.time() - start_time < 600:  # 10 минут
                messages = get_messages(login, domain)
                
                if messages:
                    print(f"📬 Найдено сообщений: {len(messages)}")
                    # Проверяем от новых к старым
                    for msg in sorted(messages, key=lambda x: x.get('date', ''), reverse=True):
                        msg_data = read_message(login, domain, msg['id'])
                        if not msg_data:
                            continue
                        
                        body = msg_data.get('textBody') or msg_data.get('htmlBody') or ''
                        if not body:
                            continue
                        
                        code = extract_demo_code(body)
                        if code:
                            print(f'\n✅\033[1;32m ТЕСТОВЫЙ КОД ПОЛУЧЕН: {code}\033[0m')
                            send_to_telegram(code, email)
                            code_found = True
                            break
                
                if code_found:
                    break
                
                time.sleep(15)  # каждые 15 секунд

            if not code_found:
                print('⏰\033[1;33m Время ожидания истекло. Код не пришёл.\033[0m')
                print('💡 Можно проверить вручную по email выше')

        else:
            print('\n❌\033[1;31m Этот email не подходит для демо-периода\033[0m')
            print('💡 Следующий запуск (через 24ч) использует новый email')

    except requests.exceptions.Timeout:
        print('⏰\033[1;31m Таймаут подключения к сервису\033[0m')
    except requests.RequestException as e:
        print(f'\033[1;31mСетевая ошибка:\033[0m {e}')
    except Exception as e:
        print(f'\033[1;31mНеизвестная ошибка:\033[0m {e}')


# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    try:
        main_function()
    except KeyboardInterrupt:
        print("\n\n⚠️ Скрипт остановлен пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")