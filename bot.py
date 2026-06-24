import telebot
import schedule
import time
import threading
import json
import os
import signal
import sys
from datetime import datetime, timedelta
from urllib.parse import quote
from playwright.sync_api import sync_playwright

# ====== НАСТРОЙКИ ======
TOKEN = os.environ.get('TOKEN', 'ВАШ_ТОКЕН')
MY_CHAT_ID = os.environ.get('MY_CHAT_ID', 'ВАШ_ID')

# Данные персонажа
REGION = 'eu'
REALM = 'howling-fjord'
CHARACTER_NAME = 'Атравлялка'

CHARACTERS = [
    {'region': REGION, 'realm': REALM, 'name': CHARACTER_NAME}
]

DEBUG_MODE = True

characters_states = {}
monitoring_active = False

# ====== ОБРАБОТКА ЗАВЕРШЕНИЯ ======
def signal_handler(signum, frame):
    print("🛑 Получен сигнал завершения", flush=True)
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# ====== ФУНКЦИЯ ПОЛУЧЕНИЯ ДАННЫХ ЧЕРЕZ PLAYWRIGHT ======
def extract_character_data(region, realm, character):
    """Получает данные о персонаже через Playwright"""
    url = f'https://worldofwarcraft.blizzard.com/{region}/character/{realm}/{quote(character)}'
    
    try:
        print(f"\n🌐 Загрузка страницы: {url}", flush=True)
        
        with sync_playwright() as p:
            # Запускаем браузер в headless режиме
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = context.new_page()
            
            # Загружаем страницу
            page.goto(url, wait_until='networkidle', timeout=60000)
            
            # Ждем загрузки контента
            page.wait_for_selector('.Character-profile', timeout=30000)
            
            # Извлекаем данные
            data = {
                'timestamp': (datetime.now() + timedelta(hours=3)).isoformat(),
                'basic_info': {},
                'equipment': [],
                'stats': {},
                'professions': [],
                'pvp': {},
                'raid_progress': {},
                'mythic_plus': {}
            }
            
            # 1. Основная информация
            try:
                name_elem = page.query_selector('.Character-profile h1')
                if name_elem:
                    data['basic_info']['name'] = name_elem.inner_text().strip()
                
                level_elem = page.query_selector('.Character-level')
                if level_elem:
                    data['basic_info']['level'] = level_elem.inner_text().strip()
                
                realm_elem = page.query_selector('.Character-realm')
                if realm_elem:
                    data['basic_info']['realm'] = realm_elem.inner_text().strip()
                
                ilvl_elem = page.query_selector('.Character-itemLevel')
                if ilvl_elem:
                    data['basic_info']['ilvl'] = ilvl_elem.inner_text().strip()
                
                if DEBUG_MODE:
                    print(f"👤 {data['basic_info'].get('name')}, ур. {data['basic_info'].get('level')}, ILvl {data['basic_info'].get('ilvl')}", flush=True)
            except Exception as e:
                print(f"⚠️ Ошибка извлечения основной информации: {e}", flush=True)
            
            # 2. Экипировка
            try:
                equipment_items = page.query_selector_all('.Character-equipment .Item')
                for item in equipment_items:
                    try:
                        name = item.query_selector('.Item-name')
                        ilvl = item.query_selector('.Item-level')
                        slot = item.query_selector('.Item-slot')
                        
                        if name:
                            data['equipment'].append({
                                'slot': slot.inner_text().strip() if slot else 'unknown',
                                'name': name.inner_text().strip(),
                                'ilvl': ilvl.inner_text().strip() if ilvl else '0'
                            })
                    except:
                        pass
                
                if DEBUG_MODE:
                    print(f"🎒 Экипировка: {len(data['equipment'])} предметов", flush=True)
            except Exception as e:
                print(f"⚠️ Ошибка извлечения экипировки: {e}", flush=True)
            
            # 3. Характеристики
            try:
                stat_items = page.query_selector_all('.Character-stats .Stat')
                for stat in stat_items:
                    try:
                        name = stat.query_selector('.Stat-name')
                        value = stat.query_selector('.Stat-value')
                        
                        if name and value:
                            data['stats'][name.inner_text().strip()] = value.inner_text().strip()
                    except:
                        pass
                
                if DEBUG_MODE:
                    print(f"⚡ Характеристики: {len(data['stats'])} параметров", flush=True)
            except Exception as e:
                print(f"⚠️ Ошибка извлечения характеристик: {e}", flush=True)
            
            # 4. Профессии
            try:
                profession_items = page.query_selector_all('.Character-professions .Profession')
                for prof in profession_items:
                    try:
                        name = prof.query_selector('.Profession-name')
                        level = prof.query_selector('.Profession-level')
                        
                        if name and level:
                            data['professions'].append({
                                'name': name.inner_text().strip(),
                                'level': level.inner_text().strip()
                            })
                    except:
                        pass
                
                if DEBUG_MODE:
                    print(f"🔨 Профессии: {len(data['professions'])} штук", flush=True)
            except Exception as e:
                print(f"⚠️ Ошибка извлечения профессий: {e}", flush=True)
            
            # 5. Mythic+ рейтинг
            try:
                mplus_elem = page.query_selector('.Character-mythicPlus .Rating-value')
                if mplus_elem:
                    data['mythic_plus']['rating'] = mplus_elem.inner_text().strip()
                
                if DEBUG_MODE:
                    print(f"🗝️ Mythic+ рейтинг: {data['mythic_plus'].get('rating', 'N/A')}", flush=True)
            except Exception as e:
                print(f"⚠️ Ошибка извлечения Mythic+: {e}", flush=True)
            
            # 6. Прогресс рейдов
            try:
                raid_items = page.query_selector_all('.Character-raids .Raid')
                for raid in raid_items:
                    try:
                        name = raid.query_selector('.Raid-name')
                        progress = raid.query_selector('.Raid-progress')
                        
                        if name and progress:
                            data['raid_progress'][name.inner_text().strip()] = progress.inner_text().strip()
                    except:
                        pass
                
                if DEBUG_MODE:
                    print(f"🏰 Рейды: {len(data['raid_progress'])} штук", flush=True)
            except Exception as e:
                print(f"⚠️ Ошибка извлечения рейдов: {e}", flush=True)
            
            # Сохраняем HTML для отладки
            if DEBUG_MODE:
                with open(f'debug_blizzard_{character}.html', 'w', encoding='utf-8') as f:
                    f.write(page.content())
                print(f"💾 HTML сохранен", flush=True)
            
            browser.close()
        
        return data
        
    except Exception as e:
        print(f"❌ Ошибка: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return None

# ====== СОХРАНЕНИЕ/ЗАГРУЗКА ======
def get_state_file(region, realm, character):
    return f'state_blizzard_{region}_{realm}_{character}.json'

def save_state(region, realm, character, state):
    with open(get_state_file(region, realm, character), 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def load_state(region, realm, character):
    filename = get_state_file(region, realm, character)
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None

# ====== СРАВНЕНИЕ ======
def compare_states(old_state, new_state):
    changes = []
    
    # Основная информация
    old_basic = old_state.get('basic_info', {})
    new_basic = new_state.get('basic_info', {})
    
    for key in ['ilvl', 'level']:
        old_val = old_basic.get(key)
        new_val = new_basic.get(key)
        if old_val != new_val:
            names = {'ilvl': 'ILvl', 'level': 'Уровень'}
            changes.append(f"📊 **{names.get(key, key)}:** {old_val} → {new_val}")
    
    # Экипировка
    old_equip = {e['slot']: e['name'] for e in old_state.get('equipment', [])}
    new_equip = {e['slot']: e['name'] for e in new_state.get('equipment', [])}
    
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
    
    # Характеристики
    old_stats = old_state.get('stats', {})
    new_stats = new_state.get('stats', {})
    
    if old_stats != new_stats:
        stat_changes = []
        for key in set(old_stats.keys()) | set(new_stats.keys()):
            if old_stats.get(key) != new_stats.get(key):
                stat_changes.append(f"  • {key}: {old_stats.get(key, 'N/A')} → {new_stats.get(key, 'N/A')}")
        
        if stat_changes:
            changes.append(f"⚡ **Характеристики:**\n" + "\n".join(stat_changes[:20]))
    
    # Профессии
    old_prof = {p['name']: p['level'] for p in old_state.get('professions', [])}
    new_prof = {p['name']: p['level'] for p in new_state.get('professions', [])}
    
    if old_prof != new_prof:
        prof_changes = []
        for name in set(old_prof.keys()) | set(new_prof.keys()):
            if old_prof.get(name) != new_prof.get(name):
                prof_changes.append(f"  • {name}: {old_prof.get(name, 'N/A')} → {new_prof.get(name, 'N/A')}")
        
        if prof_changes:
            changes.append(f"🔨 **Профессии:**\n" + "\n".join(prof_changes))
    
    # Mythic+
    old_mplus = old_state.get('mythic_plus', {})
    new_mplus = new_state.get('mythic_plus', {})
    
    if old_mplus.get('rating') != new_mplus.get('rating'):
        changes.append(f"🗝️ **Mythic+ рейтинг:** {old_mplus.get('rating', 'N/A')} → {new_mplus.get('rating', 'N/A')}")
    
    # Рейды
    old_raids = old_state.get('raid_progress', {})
    new_raids = new_state.get('raid_progress', {})
    
    if old_raids != new_raids:
        raid_changes = []
        for name in set(old_raids.keys()) | set(new_raids.keys()):
            if old_raids.get(name) != new_raids.get(name):
                raid_changes.append(f"  • {name}: {old_raids.get(name, 'N/A')} → {new_raids.get(name, 'N/A')}")
        
        if raid_changes:
            changes.append(f"🏰 **Рейды:**\n" + "\n".join(raid_changes))
    
    return changes

# ====== ПРОВЕРКА ======
def check_changes():
    global characters_states
    
    try:
        print(f"\n[{(datetime.now() + timedelta(hours=3)).strftime('%H:%M:%S')}] === НАЧАЛО ПРОВЕРКИ ===", flush=True)
        
        for char_info in CHARACTERS:
            region = char_info['region']
            realm = char_info['realm']
            character = char_info['name']
            char_key = f"{region}_{realm}_{character}"
            
            print(f"\n→ Проверяю {character} ({realm})...", flush=True)
            
            current_state = extract_character_data(region, realm, character)
            
            if current_state is None:
                print(f"  ❌ Не удалось получить данные", flush=True)
                continue
            
            if char_key not in characters_states:
                characters_states[char_key] = current_state
                save_state(region, realm, character, current_state)
                
                bot.send_message(
                    MY_CHAT_ID,
                    f"✅ Мониторинг активирован для *{character}* ({realm})!\n\n"
                    f"👤 {current_state['basic_info'].get('name')}, ур. {current_state['basic_info'].get('level')}\n"
                    f"📊 ILvl: {current_state['basic_info'].get('ilvl')}\n"
                    f"🗝️ Mythic+: {current_state['mythic_plus'].get('rating', 'N/A')}",
                    parse_mode='Markdown'
                )
                print(f"  ✅ Первая проверка, состояние сохранено", flush=True)
                continue
            
            old_state = characters_states[char_key]
            changes = compare_states(old_state, current_state)
            
            if changes:
                changes_text = "\n\n".join(changes)
                
                if DEBUG_MODE:
                    print(f"\n  🚨 НАЙДЕНЫ ИЗМЕНЕНИЯ ({len(changes)}):", flush=True)
                
                bot.send_message(
                    MY_CHAT_ID,
                    f"🚨 **Обнаружены изменения!**\n\n"
                    f"👤 Персонаж: *{character}*\n"
                    f"🌍 Сервер: {realm}\n"
                    f"⏰ {(datetime.now() + timedelta(hours=3)).strftime('%H:%M:%S')}\n\n{changes_text}",
                    parse_mode='Markdown'
                )
                print(f"  ⚠️ Отправлено уведомление!", flush=True)
            else:
                print(f"  ✓ Изменений нет", flush=True)
            
            characters_states[char_key] = current_state
            save_state(region, realm, character, current_state)
        
        print(f"\n[{(datetime.now() + timedelta(hours=3)).strftime('%H:%M:%S')}] === ПРОВЕРКА ЗАВЕРШЕНА ===\n", flush=True)
        
    except Exception as e:
        print(f"Ошибка проверки: {e}", flush=True)
        import traceback
        traceback.print_exc()

# ====== КОМАНДЫ ======
@bot.message_handler(commands=['start'])
def start(message):
    chars_list = "\n".join([f"  • {c['name']} ({c['realm']})" for c in CHARACTERS])
    bot.send_message(
        message.chat.id,
        f"👋 Привет! Я бот-монитор для Blizzard WoW\n\n"
        f"📌 Отслеживаю:\n{chars_list}\n\n"
        f"🔍 Отслеживается:\n"
        f"  • Экипировка\n"
        f"  • Характеристики\n"
        f"  • Профессии\n"
        f"  • Mythic+ рейтинг\n"
        f"  • Прогресс рейдов\n\n"
        f"📋 Команды:\n"
        f"/monitor — запустить\n"
        f"/stop — остановить\n"
        f"/check — проверить сейчас",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['monitor'])
def start_monitor(message):
    global monitoring_active
    if str(message.chat.id) != str(MY_CHAT_ID):
        bot.reply_to(message, "⛔ Доступ запрещён!")
        return
    monitoring_active = True
    bot.reply_to(message, "✅ Мониторинг запущен! Проверка каждые 15 минут.")

@bot.message_handler(commands=['stop'])
def stop_monitor(message):
    global monitoring_active
    if str(message.chat.id) != str(MY_CHAT_ID):
        bot.reply_to(message, "⛔ Доступ запрещён!")
        return
    monitoring_active = False
    bot.reply_to(message, "⏸ Мониторинг остановлен.")

@bot.message_handler(commands=['check'])
def manual_check(message):
    if str(message.chat.id) != str(MY_CHAT_ID):
        bot.reply_to(message, "⛔ Доступ запрещён!")
        return
    bot.reply_to(message, "🔍 Проверяю... Смотрите консоль!")
    check_changes()

# ====== ПЛАНИРОВЩИК ======
def run_scheduler():
    schedule.every(15).minutes.do(check_changes)
    while True:
        schedule.run_pending()
        time.sleep(1)

# ====== ЗАПУСК ======
if __name__ == '__main__':
    if not TOKEN or not MY_CHAT_ID:
        print("❌ ОШИБКА: Переменные TOKEN или MY_CHAT_ID не заданы!", flush=True)
        sys.exit(1)
    
    print("🤖 Бот запущен!", flush=True)
    print(f"🔧 Режим отладки: {'ВКЛЮЧЕН' if DEBUG_MODE else 'ВЫКЛЮЧЕН'}", flush=True)
    
    for char_info in CHARACTERS:
        region = char_info['region']
        realm = char_info['realm']
        character = char_info['name']
        char_key = f"{region}_{realm}_{character}"
        state = load_state(region, realm, character)
        if state:
            characters_states[char_key] = state
            print(f"✅ Загружено состояние для {character}", flush=True)
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    print("✅ Бот готов к работе!", flush=True)
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"⚠️ Ошибка polling: {e}", flush=True)
            time.sleep(5)
