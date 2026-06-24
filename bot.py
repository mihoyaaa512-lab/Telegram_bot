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
from urllib.parse import quote

# ====== ПРОВЕРКА ПЕРЕМЕННЫХ ======
print("🔍 Проверка переменных окружения...", flush=True)

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
print("🤖 Бот создан!", flush=True)

# ====== НАСТРОЙКИ ======
CHARACTERS = [
    {'region': 'eu', 'realm': 'howling-fjord', 'name': 'Атравлялка'}
]

DEBUG_MODE = True
characters_states = {}

# ====== ОБРАБОТКА ЗАВЕРШЕНИЯ ======
def signal_handler(signum, frame):
    print("🛑 Остановка бота...", flush=True)
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# ====== ПОЛУЧЕНИЕ ДАННЫХ ЧЕРЕЗ RAIDER.IO API ======
def extract_blizzard_data(region, realm, name):
    """Получает данные о персонаже через Raider.io API"""
    
    url = f'https://raider.io/api/v1/characters/profile'
    params = {
        'region': region,
        'realm': realm,
        'name': name,
        'fields': 'gear,raid_progression,mythic_plus_scores_by_season:current,mythic_plus_ranks'
    }
    
    try:
        print(f"\n🌐 Запрос к Raider.io API: {name} ({realm})", flush=True)
        
        response = requests.get(url, params=params, timeout=30)
        print(f"📡 Статус: {response.status_code}", flush=True)
        
        if response.status_code != 200:
            print(f"❌ Ошибка API: {response.status_code}", flush=True)
            print(f"📄 Ответ: {response.text[:500]}", flush=True)
            return None
        
        data_json = response.json()
        
        # 🔥 ПОДРОБНЫЙ ВЫВОД СТРУКТУРЫ JSON В ЛОГИ
        print(f"\n{'='*60}", flush=True)
        print(f"📋 ПОЛНАЯ СТРУКТУРА JSON ОТ RAIDER.IO:", flush=True)
        print(f"{'='*60}", flush=True)
        
        print(f" Ключи верхнего уровня: {list(data_json.keys())}", flush=True)
        
        # Основная информация
        print(f"\n👤 Основная информация:", flush=True)
        print(f"   name: {data_json.get('name')}", flush=True)
        print(f"   realm: {data_json.get('realm')}", flush=True)
        print(f"   race: {data_json.get('race')}", flush=True)
        print(f"   class: {data_json.get('class')}", flush=True)
        print(f"   active_spec_name: {data_json.get('active_spec_name')}", flush=True)
        print(f"   item_level_equipped (ILvl): {data_json.get('item_level_equipped')}", flush=True)
        print(f"   faction: {data_json.get('faction')}", flush=True)
        
        # Экипировка
        gear = data_json.get('gear', {})
        print(f"\n🎒 gear (тип: {type(gear).__name__}):", flush=True)
        if isinstance(gear, dict):
            print(f"   Ключи в gear: {list(gear.keys())}", flush=True)
            items = gear.get('items', [])
            print(f"   items тип: {type(items).__name__}, кол-во: {len(items) if isinstance(items, list) else 'N/A'}", flush=True)
            if isinstance(items, list) and items:
                print(f"   Первый предмет: {items[0]}", flush=True)
                if isinstance(items[0], dict):
                    print(f"   Ключи первого предмета: {list(items[0].keys())}", flush=True)
        
        # Mythic+ рейтинг
        mplus = data_json.get('mythic_plus_scores_by_season', [])
        print(f"\n️ mythic_plus_scores_by_season (тип: {type(mplus).__name__}, кол-во: {len(mplus) if isinstance(mplus, list) else 'N/A'}):", flush=True)
        if isinstance(mplus, list) and mplus:
            print(f"   Первый сезон: {mplus[0]}", flush=True)
            if isinstance(mplus[0], dict):
                print(f"   Ключи первого сезона: {list(mplus[0].keys())}", flush=True)
                scores = mplus[0].get('scores', {})
                print(f"   scores: {scores}", flush=True)
        
        # Рейды
        raids = data_json.get('raid_progression', {})
        print(f"\n🏰 raid_progression (тип: {type(raids).__name__}, кол-во рейдов: {len(raids) if isinstance(raids, dict) else 'N/A'}):", flush=True)
        if isinstance(raids, dict):
            for raid_name, progress in list(raids.items())[:3]:
                print(f"   Рейд {raid_name}: {progress}", flush=True)
        
        print(f"\n{'='*60}", flush=True)
        print(f"✅ КОНЕЦ СТРУКТУРЫ JSON", flush=True)
        print(f"{'='*60}\n", flush=True)
        
        # Сохраняем полный JSON для отладки
        if DEBUG_MODE:
            with open(f'debug_raiderio_{name}.json', 'w', encoding='utf-8') as f:
                json.dump(data_json, f, ensure_ascii=False, indent=2)
            print(f" Полный JSON сохранен в debug_raiderio_{name}.json", flush=True)
        
        # Формируем данные для бота
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
            'ilvl': data_json.get('item_level_equipped'),
            'faction': data_json.get('faction')
        }
        
        # 2. Экипировка
        if isinstance(gear, dict):
            items = gear.get('items', [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get('name'):
                        slot_info = item.get('slot', {})
                        slot_name = slot_info.get('name', 'unknown') if isinstance(slot_info, dict) else str(slot_info)
                        
                        data['equipment'].append({
                            'slot': slot_name,
                            'name': item.get('name'),
                            'ilvl': item.get('item_level'),
                            'quality': item.get('quality')
                        })
        
        # 3. Mythic+ рейтинг
        if isinstance(mplus, list) and mplus:
            current_season = mplus[0]
            if isinstance(current_season, dict):
                scores = current_season.get('scores', {})
                if isinstance(scores, dict):
                    data['mythic_plus'] = {
                        'score': scores.get('all'),
                        'dps_score': scores.get('dps'),
                        'healer_score': scores.get('healer'),
                        'tank_score': scores.get('tank')
                    }
        
        # 4. Прогресс рейдов
        if isinstance(raids, dict):
            for raid_name, progress in raids.items():
                if isinstance(progress, dict):
                    data['raid_progress'][raid_name] = {
                        'summary': progress.get('summary'),
                        'total_bosses': progress.get('total_bosses'),
                        'normal_bosses_killed': progress.get('normal_bosses_killed'),
                        'heroic_bosses_killed': progress.get('heroic_bosses_killed'),
                        'mythic_bosses_killed': progress.get('mythic_bosses_killed')
                    }
        
        print(f"\n✅ Данные собраны:", flush=True)
        print(f"   👤 {data['basic_info']['name']}, {data['basic_info']['active_spec']} {data['basic_info']['class']}, ILvl {data['basic_info']['ilvl']}", flush=True)
        print(f"    Экипировка: {len(data['equipment'])} предметов", flush=True)
        print(f"   🗝️ Mythic+ рейтинг: {data['mythic_plus'].get('score')}", flush=True)
        print(f"   🏰 Рейды: {len(data['raid_progress'])} штук", flush=True)
        
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

# ====== СРАВНЕНИЕ ======
def compare_states(old, new):
    changes = []
    
    # ILvl
    old_ilvl = old.get('basic_info', {}).get('ilvl')
    new_ilvl = new.get('basic_info', {}).get('ilvl')
    if old_ilvl != new_ilvl and new_ilvl:
        changes.append(f"📊 **ILvl:** {old_ilvl} → {new_ilvl}")
    
    # Экипировка
    old_equip = {e['slot']: e['name'] for e in old.get('equipment', [])}
    new_equip = {e['slot']: e['name'] for e in new.get('equipment', [])}
    
    equip_changes = []
    for slot in set(old_equip.keys()) | set(new_equip.keys()):
        if slot not in old_equip:
            equip_changes.append(f"  ➕ {slot}: {new_equip[slot]}")
        elif slot not in new_equip:
            equip_changes.append(f"  ➖ {slot}: {old_equip[slot]}")
        elif old_equip[slot] != new_equip[slot]:
            equip_changes.append(f"  🔄 {slot}: {old_equip[slot]} → {new_equip[slot]}")
    
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
        changes.append(f" **Рейды:**\n" + "\n".join(raid_changes))
    
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
            bot.send_message(
                MY_CHAT_ID,
                f"✅ Мониторинг *{name}* ({realm}) запущен!\n\n"
                f"👤 {current['basic_info']['active_spec']} {current['basic_info']['class']}\n"
                f"📊 ILvl: {current['basic_info']['ilvl']}\n"
                f"️ Mythic+: {mplus_score}",
                parse_mode='Markdown'
            )
            print(f"  ✅ Состояние сохранено", flush=True)
            continue
            
        changes = compare_states(characters_states[key], current)
        
        if changes:
            text = "\n\n".join(changes)
            bot.send_message(
                MY_CHAT_ID,
                f"🚨 **Изменения у {name}!**\n"
                f"⏰ {(datetime.now() + timedelta(hours=3)).strftime('%H:%M:%S')}\n\n{text}",
                parse_mode='Markdown'
            )
            print(f"  ⚠️ Найдены изменения!", flush=True)
        else:
            print(f"  ✓ Без изменений", flush=True)
            
        characters_states[key] = current
        save_state(region, realm, name, current)
        
    print(f"\n=== ПРОВЕРКА ЗАВЕРШЕНА ===\n", flush=True)

# ====== КОМАНДЫ ======
@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.send_message(
        message.chat.id,
        "👋 Привет! Я бот для мониторинга Blizzard WoW через Raider.io.\n\n"
        "📋 Команды:\n"
        "/check — проверить сейчас\n"
        "/monitor — автопроверка (15 мин)\n"
        "/stop — остановить"
    )

@bot.message_handler(commands=['check'])
def check_cmd(message):
    bot.reply_to(message, "🔍 Проверяю... ~5 сек.")
    check_changes()

@bot.message_handler(commands=['monitor'])
def monitor_cmd(message):
    bot.reply_to(message, "✅ Автопроверка запущена (каждые 15 мин).")
    if not hasattr(monitor_cmd, 'started'):
        schedule.every(15).minutes.do(check_changes)
        monitor_cmd.started = True

@bot.message_handler(commands=['stop'])
def stop_cmd(message):
    schedule.clear()
    bot.reply_to(message, "⏸ Автопроверка остановлена.")

# ====== ЗАПУСК ======
if __name__ == '__main__':
    print("🚀 Бот Blizzard (Raider.io API) готов!", flush=True)
    
    for char in CHARACTERS:
        key = f"{char['region']}_{char['realm']}_{char['name']}"
        state = load_state(char['region'], char['realm'], char['name'])
        if state:
            characters_states[key] = state
            
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"⚠️ Ошибка polling: {e}", flush=True)
            time.sleep(5)
