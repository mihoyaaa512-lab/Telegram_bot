import telebot
import requests
import schedule
import time
import threading
import json
import os
import signal
import sys
from datetime import datetime, timedelta

# ====== ПРОВЕРКА ПЕРЕМЕННЫХ ======
print("✅ Проверка переменных окружения...", flush=True)

TOKEN = os.environ.get('TOKEN')
MY_CHAT_ID = os.environ.get('MY_CHAT_ID')

if not TOKEN:
    print("❌ ОШИБКА: TOKEN не задан!", flush=True)
    sys.exit(1)

if not MY_CHAT_ID:
    print("❌ ОШИБКА: MY_CHAT_ID не задан!", flush=True)
    sys.exit(1)

print(f"✅ TOKEN получен (длина: {len(TOKEN)})", flush=True)
print(f"✅ MY_CHAT_ID = {MY_CHAT_ID}", flush=True)

bot = telebot.TeleBot(TOKEN, parse_mode='Markdown')
bot.delete_webhook(drop_pending_updates=True)
print("✅ Бот создан!", flush=True)

# ====== НАСТРОЙКИ ======
CHARACTERS = [
    {'region': 'eu', 'realm': 'soulflayer', 'name': 'Бусичка'},
    {'region': 'eu', 'realm': 'howling-fjord', 'name': 'Взбешённый'},
    {'region': 'eu', 'realm': 'soulflayer', 'name': 'Мерриджей'}
]

DEBUG_MODE = True
characters_states = {}
monitoring_active = False

# ====== ОБРАБОТКА ЗАВЕРШЕНИЯ ======
def signal_handler(signum, frame):
    print("🛑 Остановка бота...", flush=True)
    global monitoring_active
    monitoring_active = False
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# ====== ПОЛУЧЕНИЕ ДАННЫХ ЧЕРЕЗ RAIDER.IO ======
def extract_blizzard_data(region, realm, name):
    url = f'https://raider.io/api/v1/characters/profile'
    params = {
        'region': region,
        'realm': realm,
        'name': name,
        'fields': 'gear,raid_progression,mythic_plus_scores_by_season:current'
    }
    
    try:
        print(f"\n🌐 Запрос к Raider.io: {name} ({realm})", flush=True)
        
        response = requests.get(url, params=params, timeout=30)
        print(f"📡 Статус: {response.status_code}", flush=True)
        
        if response.status_code != 200:
            print(f"❌ Ошибка API: {response.status_code}", flush=True)
            return None
        
        data_json = response.json()
        
        if DEBUG_MODE:
            with open(f'debug_raiderio_{name}.json', 'w', encoding='utf-8') as f:
                json.dump(data_json, f, ensure_ascii=False, indent=2)
        
        data = {
            'basic_info': {},
            'equipment': [],
            'mythic_plus': {},
            'raid_progress': {}
        }
        
        # 1. Основная информация
        data['basic_info'] = {
            'name': data_json.get('name'),
            'realm': data_json.get('realm'),
            'race': data_json.get('race'),
            'class': data_json.get('class'),
            'active_spec': data_json.get('active_spec_name'),
            'faction': data_json.get('faction')
        }
        
        # 2. ILvl
        gear = data_json.get('gear', {})
        if isinstance(gear, dict):
            data['basic_info']['ilvl'] = gear.get('item_level_equipped')
        
        if DEBUG_MODE:
            print(f"👤 {data['basic_info']['name']}, {data['basic_info']['active_spec']} {data['basic_info']['class']}, ILvl {data['basic_info']['ilvl']}", flush=True)
        
        # 3. Экипировка
        if isinstance(gear, dict):
            items = gear.get('items', {})
            if isinstance(items, dict):
                for slot_name, item in items.items():
                    if isinstance(item, dict) and item.get('name'):
                        data['equipment'].append({
                            'slot': slot_name,
                            'name': item.get('name'),
                            'ilvl': item.get('item_level'),
                            'quality': item.get('item_quality')
                        })
        
        if DEBUG_MODE:
            print(f"🎒 Экипировка: {len(data['equipment'])} предметов", flush=True)
        
        # 4. Mythic+ рейтинг
        mplus_seasons = data_json.get('mythic_plus_scores_by_season', [])
        if isinstance(mplus_seasons, list) and mplus_seasons:
            current_season = mplus_seasons[0]
            if isinstance(current_season, dict):
                scores = current_season.get('scores', {})
                if isinstance(scores, dict):
                    data['mythic_plus'] = {
                        'score': scores.get('all'),
                        'dps_score': scores.get('dps'),
                        'healer_score': scores.get('healer'),
                        'tank_score': scores.get('tank')
                    }
        
        if DEBUG_MODE:
            print(f"🗝️ Mythic+ рейтинг: {data['mythic_plus'].get('score')}", flush=True)
        
        # 5. Прогресс рейдов
        raid_progression = data_json.get('raid_progression', {})
        if isinstance(raid_progression, dict):
            for raid_name, progress in raid_progression.items():
                if isinstance(progress, dict):
                    data['raid_progress'][raid_name] = {
                        'summary': progress.get('summary'),
                        'total_bosses': progress.get('total_bosses'),
                        'normal_bosses_killed': progress.get('normal_bosses_killed'),
                        'heroic_bosses_killed': progress.get('heroic_bosses_killed'),
                        'mythic_bosses_killed': progress.get('mythic_bosses_killed')
                    }
        
        if DEBUG_MODE:
            print(f"🏰 Рейды: {len(data['raid_progress'])} штук", flush=True)
        
        return data
        
    except Exception as e:
        print(f"❌ Ошибка: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return None

# ====== СОХРАНЕНИЕ/ЗАГРУЗКА ======
def get_state_file(region, realm, name):
    return f'state_blizzard_{region}_{realm}_{name}.json'

def save_state(region, realm, name, state):
    try:
        with open(get_state_file(region, realm, name), 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ Ошибка сохранения состояния: {e}", flush=True)

def load_state(region, realm, name):
    filename = get_state_file(region, realm, name)
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Ошибка загрузки состояния: {e}", flush=True)
            return None
    return None

# ====== СРАВНЕНИЕ ======
def compare_states(old, new):
    changes = []
    
    # ILvl
    old_ilvl = old.get('basic_info', {}).get('ilvl')
    new_ilvl = new.get('basic_info', {}).get('ilvl')
    if old_ilvl != new_ilvl and new_ilvl:
        changes.append(f"📊 **ILvl:** {old_ilvl} → {new_ilvl}")
    
    # Экипировка
    old_equip = {e['slot']: {'name': e['name'], 'ilvl': e.get('ilvl'), 'quality': e.get('quality')} 
                 for e in old.get('equipment', [])}
    new_equip = {e['slot']: {'name': e['name'], 'ilvl': e.get('ilvl'), 'quality': e.get('quality')} 
                 for e in new.get('equipment', [])}
    
    equip_changes = []
    for slot in set(old_equip.keys()) | set(new_equip.keys()):
        if slot not in old_equip:
            item = new_equip[slot]
            equip_changes.append(f"  ➕ {slot}: {item['name']} (ilvl {item['ilvl']})")
        elif slot not in new_equip:
            item = old_equip[slot]
            equip_changes.append(f"  ➖ {slot}: {item['name']} (ilvl {item['ilvl']})")
        else:
            old_item = old_equip[slot]
            new_item = new_equip[slot]
            
            if old_item['name'] != new_item['name']:
                equip_changes.append(f"  🔄 {slot}: {old_item['name']} (ilvl {old_item['ilvl']}) → {new_item['name']} (ilvl {new_item['ilvl']})")
            elif old_item['ilvl'] != new_item['ilvl']:
                if new_item['ilvl'] > old_item['ilvl']:
                    equip_changes.append(f"  ⬆️ {slot}: {new_item['name']} ilvl {old_item['ilvl']} → {new_item['ilvl']}")
                else:
                    equip_changes.append(f"  📉 {slot}: {new_item['name']} ilvl {old_item['ilvl']} → {new_item['ilvl']}")
            elif old_item['quality'] != new_item['quality']:
                equip_changes.append(f"  ✨ {slot}: {new_item['name']} качество {old_item['quality']} → {new_item['quality']}")
    
    if equip_changes:
        changes.append(f"🎒 **Экипировка:**\n" + "\n".join(equip_changes[:15]))
    
    # Mythic+
    old_mplus = old.get('mythic_plus', {})
    new_mplus = new.get('mythic_plus', {})
    
    if old_mplus.get('score') != new_mplus.get('score') and new_mplus.get('score'):
        changes.append(f"🗝️ **Mythic+ рейтинг:** {old_mplus.get('score', '?')} → {new_mplus['score']}")
    
    # Рейды
    old_raids = old.get('raid_progress', {})
    new_raids = new.get('raid_progress', {})
    
    raid_changes = []
    for raid in set(old_raids.keys()) | set(new_raids.keys()):
        old_summary = old_raids.get(raid, {}).get('summary', '?')
        new_summary = new_raids.get(raid, {}).get('summary', '?')
        
        if old_summary != new_summary:
            raid_changes.append(f"  • {raid}: {old_summary} → {new_summary}")
    
    if raid_changes:
        changes.append(f"🏰 **Рейды:**\n" + "\n".join(raid_changes))
    
    return changes

# ====== ПРОВЕРКА ======
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
            
            mplus_score = current.get('mythic_plus', {}).get('score', '?')
            try:
                bot.send_message(
                    MY_CHAT_ID,
                    f"✅ Мониторинг *{name}* ({realm}) запущен!\n\n"
                    f"👤 {current['basic_info']['active_spec']} {current['basic_info']['class']}\n"
                    f"💪 ILvl: {current['basic_info']['ilvl']}\n"
                    f"🗝️ Mythic+: {mplus_score}\n"
                    f"🎒 Экипировка: {len(current['equipment'])} предметов",
                    parse_mode='Markdown'
                )
            except Exception as e:
                print(f"❌ Ошибка отправки сообщения: {e}", flush=True)
            
            print(f"  ✅ Состояние сохранено", flush=True)
            continue
            
        changes = compare_states(characters_states[key], current)
        
        if changes:
            text = "\n\n".join(changes)
            try:
                bot.send_message(
                    MY_CHAT_ID,
                    f"⚠️ **Изменения у {name}!**\n"
                    f"⏰ {(datetime.now() + timedelta(hours=3)).strftime('%H:%M:%S')}\n\n{text}",
                    parse_mode='Markdown'
                )
            except Exception as e:
                print(f"❌ Ошибка отправки сообщения: {e}", flush=True)
            
            print(f"  ⚠️ Найдены изменения!", flush=True)
        else:
            print(f"  ✓ Без изменений", flush=True)
            
        characters_states[key] = current
        save_state(region, realm, name, current)
        
    print(f"\n=== ПРОВЕРКА ЗАВЕРШЕНА ===\n", flush=True)

# ====== ПОТОК ДЛЯ МОНИТОРИНГА ======
def run_scheduler():
    """Запускает планировщик в отдельном потоке"""
    global monitoring_active
    print("🔄 Планировщик запущен", flush=True)
    while monitoring_active:
        schedule.run_pending()
        time.sleep(1)
    print("⏹ Планировщик остановлен", flush=True)

# ====== КОМАНДЫ ======
@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.send_message(
        message.chat.id,
        "👋 Привет! Я бот для мониторинга Blizzard WoW через Raider.io.\n\n"
        "🔍 Отслеживается:\n"
        "  • ILvl персонажа\n"
        "  • Экипировка (замена, ilvl, качество)\n"
        "  • Mythic+ рейтинг\n"
        "  • Прогресс рейдов\n\n"
        "📋 Команды:\n"
        "/check — проверить сейчас\n"
        "/status — статус мониторинга\n"
        "/stop — остановить мониторинг\n"
        "/start_monitor — запустить мониторинг"
    )

@bot.message_handler(commands=['check'])
def check_cmd(message):
    bot.reply_to(message, "🔍 Проверяю... ~5 сек.")
    check_changes()

@bot.message_handler(commands=['status'])
def status_cmd(message):
    if monitoring_active:
        bot.reply_to(message, "✅ Мониторинг активен (каждые 15 мин)")
    else:
        bot.reply_to(message, "⏸ Мониторинг остановлен")

@bot.message_handler(commands=['start_monitor'])
def start_monitor_cmd(message):
    global monitoring_active
    
    if monitoring_active:
        bot.reply_to(message, "⚠️ Мониторинг уже запущен!")
        return
    
    monitoring_active = True
    schedule.every(15).minutes.do(check_changes)
    
    monitor_thread = threading.Thread(target=run_scheduler, daemon=True)
    monitor_thread.start()
    
    bot.reply_to(message, "✅ Мониторинг запущен (каждые 15 мин)")
    print("🔄 Мониторинг запущен по команде", flush=True)

@bot.message_handler(commands=['stop'])
def stop_cmd(message):
    global monitoring_active
    
    if not monitoring_active:
        bot.reply_to(message, "⚠️ Мониторинг не был запущен.")
        return
    
    monitoring_active = False
    schedule.clear()
    bot.reply_to(message, "⏸ Мониторинг остановлен.")
    print("⏹ Мониторинг остановлен по команде", flush=True)

# ====== ЗАПУСК ======
if __name__ == '__main__':
    print("🚀 Бот Blizzard (Raider.io API) готов!", flush=True)
    
    # Загружаем сохраненные состояния
    for char in CHARACTERS:
        key = f"{char['region']}_{char['realm']}_{char['name']}"
        state = load_state(char['region'], char['realm'], char['name'])
        if state:
            characters_states[key] = state
            print(f"✅ Загружено состояние для {char['name']}", flush=True)
    
    # АВТОМАТИЧЕСКИЙ ЗАПУСК МОНИТОРИНГА ПРИ СТАРТЕ
    print("🔄 Автоматический запуск мониторинга...", flush=True)
    monitoring_active = True
    schedule.every(15).minutes.do(check_changes)
    
    monitor_thread = threading.Thread(target=run_scheduler, daemon=True)
    monitor_thread.start()
    
    print("📡 Запускаю polling...", flush=True)
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"⚠️ Ошибка polling: {e}", flush=True)
            time.sleep(5)
