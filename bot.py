import telebot
import os
import sys
import time
import threading
import schedule
import json
import re
from datetime import datetime, timedelta
from urllib.parse import quote
from playwright.sync_api import sync_playwright

# ====== 1. ПОЛУЧЕНИЕ ПЕРЕМЕННЫХ И СОЗДАНИЕ БОТА ======
print("🔍 Проверка переменных окружения...", flush=True)

TOKEN = os.environ.get('TOKEN')
MY_CHAT_ID = os.environ.get('MY_CHAT_ID')

if not TOKEN:
    print("❌ ОШИБКА: Переменная TOKEN не задана в Railway!", flush=True)
    print(" Зайдите в Railway -> Variables и добавьте TOKEN", flush=True)
    sys.exit(1)

if not MY_CHAT_ID:
    print("❌ ОШИБКА: Переменная MY_CHAT_ID не задана в Railway!", flush=True)
    sys.exit(1)

print(f"✅ TOKEN получен (длина: {len(TOKEN)})", flush=True)
print(f"✅ MY_CHAT_ID = {MY_CHAT_ID}", flush=True)

# ВАЖНО: Создаем объект бота ЗДЕСЬ, до всех декораторов
bot = telebot.TeleBot(TOKEN, parse_mode='Markdown')
print("🤖 Объект бота успешно создан!", flush=True)

# ====== 2. НАСТРОЙКИ ПЕРСОНАЖЕЙ ======
CHARACTERS = [
    {'region': 'eu', 'realm': 'howling-fjord', 'name': 'Атравлялка'}
]

DEBUG_MODE = True
characters_states = {}

# ====== 3. ОБРАБОТКА ЗАВЕРШЕНИЯ ======
def signal_handler(signum, frame):
    print(" Остановка бота...", flush=True)
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# ====== 4. ФУНКЦИЯ ПОЛУЧЕНИЯ ДАННЫХ (PLAYWRIGHT) ======
def extract_blizzard_data(region, realm, name):
    """Заходит на страницу Blizzard и вытаскивает данные"""
    url = f'https://worldofwarcraft.blizzard.com/{region}/character/{realm}/{quote(name)}'
    
    data = {
        'ilvl': None,
        'stats': {},
        'mythic_plus': None,
        'raid_progress': {}
    }
    
    try:
        print(f"\n🌐 Загружаю {name} ({realm}) через браузер...", flush=True)
        
        with sync_playwright() as p:
            # Запускаем браузер с флагами для Railway/Docker
            browser = p.chromium.launch(
                headless=True, 
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            page = browser.new_page()
            page.set_default_timeout(30000)
            
            # Переходим на страницу
            page.goto(url, wait_until='domcontentloaded')
            # Ждем загрузки динамического контента
            page.wait_for_timeout(8000) 
            
            # Получаем весь HTML
            page_text = page.content()
            browser.close()
            
        # --- ПАРСИНГ ЧЕРЕЗ РЕГУЛЯРНЫЕ ВЫРАЖЕНИЯ ---
        
        # 1. Item Level (ILvl)
        ilvl_match = re.search(r'Item Level\s*<[^>]*>(\d+)', page_text)
        if ilvl_match:
            data['ilvl'] = ilvl_match.group(1)
        else:
            ilvl_match = re.search(r'(\d{3})\s*Item Level', page_text)
            if ilvl_match:
                data['ilvl'] = ilvl_match.group(1)
                
        if DEBUG_MODE: print(f"📊 ILvl: {data['ilvl']}", flush=True)
        
        # 2. Характеристики
        stats_to_find = {
            'Intellect': 'Интеллект',
            'Stamina': 'Выносливость', 
            'Critical Strike': 'Крит. удар',
            'Haste': 'Скорость',
            'Mastery': 'Искусность',
            'Versatility': 'Универсальность'
        }
        
        for eng_name, ru_name in stats_to_find.items():
            pattern = rf'{eng_name}[^<]*<[^>]*>([\d,]+\.?\d*)%?'
            match = re.search(pattern, page_text)
            if match:
                val = match.group(1).replace(',', '')
                data['stats'][ru_name] = val
            else:
                pattern2 = rf'{eng_name}\D+?(\d{2,})'
                match2 = re.search(pattern2, page_text)
                if match2:
                    data['stats'][ru_name] = match2.group(1)
                    
        if DEBUG_MODE: print(f"⚡ Статы: {data['stats']}", flush=True)
        
        # 3. Mythic+ Rating
        mplus_match = re.search(r'Mythic\+ Rating\D+?([\d.]+)', page_text)
        if mplus_match:
            data['mythic_plus'] = mplus_match.group(1)
            
        if DEBUG_MODE: print(f"🗝️ Mythic+: {data['mythic_plus']}", flush=True)
        
        # 4. Прогресс рейдов
        raid_matches = re.findall(r'([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?)\s+(\d+/\d+)', page_text)
        for raid_name, progress in raid_matches:
            if len(raid_name) > 5 and '/' in progress:
                data['raid_progress'][raid_name] = progress
                
        if DEBUG_MODE: print(f" Рейды: {data['raid_progress']}", flush=True)
        
        return data
        
    except Exception as e:
        print(f"❌ Ошибка при загрузке страницы: {e}", flush=True)
        return None

# ====== 5. СОХРАНЕНИЕ/ЗАГРУЗКА СОСТОЯНИЯ ======
def get_state_file(region, realm, name):
    return f'state_blizzard_{region}_{realm}_{name}.json'

def save_state(region, realm, name, state):
    with open(get_state_file(region, realm, name), 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def load_state(region, realm, name):
    filename = get_state_file(region, realm, name)
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None

# ====== 6. СРАВНЕНИЕ СОСТОЯНИЙ ======
def compare_states(old, new):
    changes = []
    
    if old.get('ilvl') != new.get('ilvl') and new.get('ilvl'):
        changes.append(f"📊 **ILvl:** {old.get('ilvl', '?')} → {new['ilvl']}")
        
    if old.get('stats') != new.get('stats'):
        stat_changes = []
        for stat in new.get('stats', {}):
            old_val = old.get('stats', {}).get(stat, '?')
            new_val = new['stats'][stat]
            if old_val != new_val:
                stat_changes.append(f"  • {stat}: {old_val} → {new_val}")
        if stat_changes:
            changes.append(f" **Характеристики:**\n" + "\n".join(stat_changes))
            
    if old.get('mythic_plus') != new.get('mythic_plus') and new.get('mythic_plus'):
        changes.append(f"🗝️ **Mythic+ Рейтинг:** {old.get('mythic_plus', '?')} → {new['mythic_plus']}")
        
    if old.get('raid_progress') != new.get('raid_progress'):
        raid_changes = []
        for raid, prog in new.get('raid_progress', {}).items():
            old_prog = old.get('raid_progress', {}).get(raid, '?')
            if old_prog != prog:
                raid_changes.append(f"  • {raid}: {old_prog} → {prog}")
        if raid_changes:
            changes.append(f"🏰 **Рейды:**\n" + "\n".join(raid_changes))
            
    return changes

# ====== 7. ПРОВЕРКА ИЗМЕНЕНИЙ ======
def check_changes():
    global characters_states
    
    print(f"\n[{(datetime.now() + timedelta(hours=3)).strftime('%H:%M:%S')}] === НАЧАЛО ПРОВЕРКИ ===", flush=True)
    
    for char in CHARACTERS:
        region, realm, name = char['region'], char['realm'], char['name']
        key = f"{region}_{realm}_{name}"
        
        print(f"\n→ Проверяю {name}...", flush=True)
        
        current = extract_blizzard_data(region, realm, name)
        if not current:
            print(f"  ❌ Не удалось получить данные", flush=True)
            continue
            
        if key not in characters_states:
            characters_states[key] = current
            save_state(region, realm, name, current)
            
            bot.send_message(MY_CHAT_ID, f"✅ Мониторинг *{name}* ({realm}) запущен!\n\n ILvl: {current.get('ilvl', '?')}\n🗝️ Mythic+: {current.get('mythic_plus', '?')}", parse_mode='Markdown')
            print(f"  ✅ Состояние сохранено", flush=True)
            continue
            
        changes = compare_states(characters_states[key], current)
        
        if changes:
            text = "\n\n".join(changes)
            bot.send_message(MY_CHAT_ID, f"🚨 **Изменения у {name}!**\n {(datetime.now() + timedelta(hours=3)).strftime('%H:%M:%S')}\n\n{text}", parse_mode='Markdown')
            print(f"  ⚠️ Найдены изменения!", flush=True)
        else:
            print(f"  ✓ Без изменений", flush=True)
            
        characters_states[key] = current
        save_state(region, realm, name, current)
        
    print(f"\n=== ПРОВЕРКА ЗАВЕРШЕНА ===\n", flush=True)

# ====== 8. КОМАНДЫ БОТА ======
@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.send_message(message.chat.id, "👋 Привет! Я бот для мониторинга Blizzard WoW.\n\nКоманды:\n/check — проверить сейчас\n/monitor — запустить автопроверку (каждые 15 мин)\n/stop — остановить")

@bot.message_handler(commands=['check'])
def check_cmd(message):
    bot.reply_to(message, "🔍 Запускаю браузер и проверяю... Это займет ~15 секунд.")
    check_changes()

@bot.message_handler(commands=['monitor'])
def monitor_cmd(message):
    bot.reply_to(message, "✅ Автопроверка запущена (каждые 15 минут).")
    if not hasattr(monitor_cmd, 'started'):
        schedule.every(15).minutes.do(check_changes)
        monitor_cmd.started = True

@bot.message_handler(commands=['stop'])
def stop_cmd(message):
    schedule.clear()
    bot.reply_to(message, "⏸ Автопроверка остановлена.")

# ====== 9. ЗАПУСК ======
if __name__ == '__main__':
    print("🚀 Бот Blizzard готов к работе!", flush=True)
    
    # Загружаем старые состояния
    for char in CHARACTERS:
        key = f"{char['region']}_{char['realm']}_{char['name']}"
        state = load_state(char['region'], char['realm'], char['name'])
        if state:
            characters_states[key] = state
            
    # Запускаем polling
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"️ Ошибка polling: {e}", flush=True)
            time.sleep(5)
