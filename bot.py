import telebot
import requests
import schedule
import time
import threading
import json
import os
from datetime import datetime
from urllib.parse import quote

# ====== НАСТРОЙКИ ======
TOKEN = '8418251202:AAGbFvhQZoZrT6HDjPBhYKnx4dp98pmik9w'
bot = telebot.TeleBot(TOKEN)

MY_CHAT_ID = '1038593672'

# СООТВЕТСТВИЕ СЕРВЕРОВ И ИХ ID
# Найдите ID для x1, x2 в DevTools (как для x3 нашли 22)
SERVER_IDS = {
    'x3': 22,
    'x1': 20,  # УТОЧНИТЕ этот номер!
    'x2': 21,  # УТОЧНИТЕ этот номер!
}

CHARACTERS = [
    {'world': 'x3', 'name': 'Марийка'},
    {'world': 'x3', 'name': 'Killershok'},
    {'world': 'x3', 'name': 'Взбешённый'},
    {'world': 'x3', 'name': 'Obnimashka'}
]

DEBUG_MODE = True

characters_states = {}
monitoring_active = False

# ====== ФУНКЦИЯ ПОЛУЧЕНИЯ ДАННЫХ ======
def extract_character_data(world, character):
    """Получает ВСЕ данные о персонаже через API"""
    
    server_id = SERVER_IDS.get(world)
    if server_id is None:
        print(f" Не найден ID для сервера {world}", flush=True)
        return None
    
    api_url = f'https://sirus.su/api/base/{server_id}/character/{quote(character)}'
    
    try:
        print(f"\n🌐 Запрос к API: {api_url}", flush=True)
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        
        response = requests.get(api_url, headers=headers, timeout=15)
        
        print(f"📡 Статус: {response.status_code}", flush=True)
        
        if response.status_code != 200:
            print(f"❌ Ошибка API: {response.status_code}", flush=True)
            return None
        
        data_json = response.json()
        
        if DEBUG_MODE:
            with open(f'debug_api_{character}.json', 'w', encoding='utf-8') as f:
                json.dump(data_json, f, ensure_ascii=False, indent=2)
            print(f"💾 JSON сохранен", flush=True)
        
        data = {
            'timestamp': datetime.now().isoformat(),
            'basic_info': {},
            'equipment': [],
            'stats': {},
            'professions': [],
            'pvp': {},
            'arena': [],
            'pve': {},
            'talents': [],
            'glyphs': [],
            'challenge': {},
            'latest_actions': []
        }
        
        # 1. Основная информация
        character_data = data_json.get('character', {})
        data['basic_info'] = {
            'name': character_data.get('name'),
            'level': character_data.get('level'),
            'class': character_data.get('className'),
            'race': character_data.get('raceName'),
            'ilvl': character_data.get('ilvl'),
            'category': character_data.get('category'),
            'achievementPoints': character_data.get('achievementPoints'),
            'guild': character_data.get('guild', {}).get('name') if character_data.get('guild') else None
        }
        
        if DEBUG_MODE:
            print(f"👤 {data['basic_info']['name']}, ур. {data['basic_info']['level']}, ILvl {data['basic_info']['ilvl']}", flush=True)
        
        # 2. Экипировка
        equipments = data_json.get('equipments', [])
        if isinstance(equipments, list):
            for item in equipments:
                if item and item.get('name'):
                    data['equipment'].append({
                        'slot': item.get('key'),
                        'name': item.get('name'),
                        'ilvl': item.get('itemLevel'),
                        'quality': item.get('quality')
                    })
        
        if DEBUG_MODE:
            print(f"🎒 Экипировка: {len(data['equipment'])} предметов", flush=True)
        
        # 3. Характеристики
        character_stats = data_json.get('character', {}).get('stats', {})
        if isinstance(character_stats, dict):
            for stat_key, value in character_stats.items():
                data['stats'][stat_key] = value
        
        if DEBUG_MODE:
            print(f"⚡ Характеристики: {len(data['stats'])} параметров", flush=True)
        
        # 4. Профессии и навыки
        professions = data_json.get('professions', [])
        if isinstance(professions, list):
            for prof in professions:
                if prof:
                    skill_data = prof.get('skill', {})
                    data['professions'].append({
                        'name': prof.get('name'),
                        'skill': skill_data.get('value') if isinstance(skill_data, dict) else skill_data,
                        'max': skill_data.get('max') if isinstance(skill_data, dict) else 0
                    })
        
        secondary_skills = data_json.get('secondarySkills', [])
        if isinstance(secondary_skills, list):
            for skill in secondary_skills:
                if skill:
                    skill_data = skill.get('skill', {})
                    data['professions'].append({
                        'name': skill.get('name'),
                        'skill': skill_data.get('value') if isinstance(skill_data, dict) else skill_data,
                        'max': skill_data.get('max') if isinstance(skill_data, dict) else 0
                    })
        
        if DEBUG_MODE:
            print(f"🔨 Профессии: {[p['name'] for p in data['professions']]}", flush=True)
        
        # 5. PvP
        pvp_data = data_json.get('pvp', {})
        if isinstance(pvp_data, dict):
            data['pvp'] = {
                'rank': pvp_data.get('rank'),
                'rating': pvp_data.get('rating'),
                'week_games': pvp_data.get('week_games'),
                'week_wins': pvp_data.get('week_wins'),
                'total_games': pvp_data.get('total_games'),
                'total_wins': pvp_data.get('total_wins')
            }
        
        # 6. Arena
        arena_data = data_json.get('arena', [])
        if isinstance(arena_data, list):
            for team in arena_data:
                if team:
                    data['arena'].append({
                        'slot': team.get('slot'),
                        'seasonGames': team.get('seasonGames'),
                        'seasonWins': team.get('seasonWins'),
                        'personalRating': team.get('personalRating')
                    })
        
        # 7. PvE (рейды)
        pve_data = data_json.get('pve', {})
        if isinstance(pve_data, dict):
            for raid_id, raid_info in pve_data.items():
                if raid_info:
                    data['pve'][raid_id] = {
                        'map_name': raid_info.get('map_name'),
                        'difficulty': raid_info.get('difficulty'),
                        'progressed': raid_info.get('progressed'),
                        'percentage': raid_info.get('percentage')
                    }
        
        # 8. Таланты (активные заклинания)
        character_talents = data_json.get('characterTalents', [])
        if isinstance(character_talents, list):
            for talent_group in character_talents:
                if isinstance(talent_group, list):
                    spells = [t.get('spell') for t in talent_group if t.get('spell')]
                    data['talents'].append(spells)
        
        # 9. Глифы
        glyphs_data = data_json.get('glyphs', [])
        if isinstance(glyphs_data, list):
            for glyph in glyphs_data:
                if glyph and glyph.get('glyphData'):
                    glyph_info = glyph.get('glyphData', {})
                    data['glyphs'].append({
                        'slot': glyph.get('glyphSlot'),
                        'name': glyph_info.get('glyph_name'),
                        'talentGroup': glyph.get('talentGroup')
                    })
        
        # 10. Мифик+ (Challenge)
        challenge_data = data_json.get('challenge', {})
        if isinstance(challenge_data, dict):
            data['challenge'] = {
                'current_score': challenge_data.get('current_score'),
                'keystone_level': challenge_data.get('keystone_level')
            }
        
        # 11. Последние действия
        try:
            actions_url = f'https://sirus.su/api/base/{world}/statistics/{quote(character)}/latest-actions'
            actions_response = requests.get(actions_url, headers=headers, timeout=10)
            
            if actions_response.status_code == 200:
                actions = actions_response.json()
                for action in actions[:15]:
                    action_type = action.get('type', 'unknown')
                    action_data = action.get('action', {})
                    datetime_str = action.get('datetime', '')
                    
                    if action_type == 'obtaineditem':
                        text = f"🎁 Получил: {action_data.get('name', 'предмет')}"
                    elif action_type == 'bosskill':
                        text = f"⚔️ Победил: {action_data.get('boss_name', 'босс')}"
                    elif action_type == 'achievement':
                        text = f"🏆 Достижение: {action_data.get('name', 'достижение')}"
                    elif action_type == 'arenamatch':
                        text = "🏟️ Арена"
                    elif action_type == 'bgmatch':
                        text = "⚔️ Поле боя"
                    else:
                        text = f"❓ {action_type}"
                    
                    data['latest_actions'].append({
                        'text': text,
                        'datetime': datetime_str,
                        'type': action_type
                    })
        except Exception as e:
            print(f"Ошибка при получении действий: {e}", flush=True)
        
        return data
        
    except Exception as e:
        print(f"❌ Общая ошибка: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return None

# ====== СОХРАНЕНИЕ/ЗАГРУЗКА ======
def get_state_file(world, character):
    return f'state_{world}_{character}.json'

def save_state(world, character, state):
    filename = get_state_file(world, character)
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def load_state(world, character):
    filename = get_state_file(world, character)
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None

# ====== СРАВНЕНИЕ ВСЕХ ДАННЫХ ======
def compare_states(old_state, new_state):
    """Сравнивает ВСЕ данные и возвращает список ВСЕХ изменений"""
    changes = []
    
    # 1. Основная информация
    old_basic = old_state.get('basic_info', {})
    new_basic = new_state.get('basic_info', {})
    
    if old_basic != new_basic:
        basic_changes = []
        for key in set(old_basic.keys()) | set(new_basic.keys()):
            old_val = old_basic.get(key)
            new_val = new_basic.get(key)
            if old_val != new_val:
                key_names = {
                    'ilvl': 'ILvl',
                    'level': 'Уровень',
                    'category': 'Категория',
                    'achievementPoints': 'Очки достижений',
                    'guild': 'Гильдия'
                }
                display_key = key_names.get(key, key)
                basic_changes.append(f"  • {display_key}: {old_val} → {new_val}")
        
        if basic_changes:
            changes.append(f"📊 **Основная информация:**\n" + "\n".join(basic_changes))
    
    # 2. Экипировка
    old_equip = {e['slot']: e['name'] for e in old_state.get('equipment', [])}
    new_equip = {e['slot']: e['name'] for e in new_state.get('equipment', [])}
    
    if old_equip != new_equip:
        equip_changes = []
        
        # Новые предметы
        for slot in new_equip:
            if slot not in old_equip:
                equip_changes.append(f"  ➕ {slot}: {new_equip[slot]}")
            elif old_equip[slot] != new_equip[slot]:
                equip_changes.append(f"  🔄 {slot}: {old_equip[slot]} → {new_equip[slot]}")
        
        # Удалённые предметы
        for slot in old_equip:
            if slot not in new_equip:
                equip_changes.append(f"  ➖ {slot}: {old_equip[slot]}")
        
        if equip_changes:
            changes.append(f" **Экипировка:**\n" + "\n".join(equip_changes[:15]))
    
    # 3. Характеристики
    old_stats = old_state.get('stats', {})
    new_stats = new_state.get('stats', {})
    
    if old_stats != new_stats:
        stat_changes = []
        stat_names = {
            'strength': 'Сила',
            'agility': 'Ловкость',
            'stamina': 'Выносливость',
            'intellect': 'Интеллект',
            'spirit': 'Дух',
            'armor': 'Броня',
            'attackPower': 'Сила атаки',
            'spellPower': 'Сила заклинаний',
            'critPct': 'Крит (%)',
            'hasteRating': 'Рейтинг скорости',
            'hitRating': 'Рейтинг меткости',
            'defenseRating': 'Рейтинг защиты'
        }
        
        for key in set(old_stats.keys()) | set(new_stats.keys()):
            old_val = old_stats.get(key)
            new_val = new_stats.get(key)
            if old_val != new_val:
                display_name = stat_names.get(key, key)
                stat_changes.append(f"  • {display_name}: {old_val} → {new_val}")
        
        if stat_changes:
            changes.append(f"⚡ **Характеристики:**\n" + "\n".join(stat_changes[:20]))
    
    # 4. Профессии
    old_prof = {p['name']: p['skill'] for p in old_state.get('professions', [])}
    new_prof = {p['name']: p['skill'] for p in new_state.get('professions', [])}
    
    if old_prof != new_prof:
        prof_changes = []
        for name in set(old_prof.keys()) | set(new_prof.keys()):
            old_val = old_prof.get(name)
            new_val = new_prof.get(name)
            if old_val != new_val:
                prof_changes.append(f"  • {name}: {old_val} → {new_val}")
        
        if prof_changes:
            changes.append(f"🔨 **Профессии/навыки:**\n" + "\n".join(prof_changes))
    
    # 5. PvP
    old_pvp = old_state.get('pvp', {})
    new_pvp = new_state.get('pvp', {})
    
    if old_pvp != new_pvp:
        pvp_changes = []
        for key in ['rating', 'rank', 'week_games', 'week_wins', 'total_games', 'total_wins']:
            old_val = old_pvp.get(key)
            new_val = new_pvp.get(key)
            if old_val != new_val:
                key_names = {
                    'rating': 'Рейтинг',
                    'rank': 'Ранг',
                    'week_games': 'Игры за неделю',
                    'week_wins': 'Победы за неделю',
                    'total_games': 'Всего игр',
                    'total_wins': 'Всего побед'
                }
                pvp_changes.append(f"  • {key_names.get(key, key)}: {old_val} → {new_val}")
        
        if pvp_changes:
            changes.append(f"⚔️ **PvP:**\n" + "\n".join(pvp_changes))
    
    # 6. Arena
    old_arena = {a['slot']: a['personalRating'] for a in old_state.get('arena', [])}
    new_arena = {a['slot']: a['personalRating'] for a in new_state.get('arena', [])}
    
    if old_arena != new_arena:
        arena_changes = []
        for slot in set(old_arena.keys()) | set(new_arena.keys()):
            old_val = old_arena.get(slot)
            new_val = new_arena.get(slot)
            if old_val != new_val:
                arena_changes.append(f"  • Арена {slot}: {old_val} → {new_val}")
        
        if arena_changes:
            changes.append(f"🏟️ **Arena:**\n" + "\n".join(arena_changes))
    
    # 7. PvE (рейды)
    old_pve = old_state.get('pve', {})
    new_pve = new_state.get('pve', {})
    
    if old_pve != new_pve:
        pve_changes = []
        for raid_id in set(old_pve.keys()) | set(new_pve.keys()):
            old_raid = old_pve.get(raid_id, {})
            new_raid = new_pve.get(raid_id, {})
            
            if old_raid.get('progressed') != new_raid.get('progressed') or old_raid.get('percentage') != new_raid.get('percentage'):
                raid_name = new_raid.get('map_name', old_raid.get('map_name', f'Рейд {raid_id}'))
                old_prog = old_raid.get('progressed', 0)
                new_prog = new_raid.get('progressed', 0)
                pve_changes.append(f"  • {raid_name}: {old_prog}/5 → {new_prog}/5")
        
        if pve_changes:
            changes.append(f"🏰 **Рейды:**\n" + "\n".join(pve_changes))
    
    # 8. Мифик+
    old_challenge = old_state.get('challenge', {})
    new_challenge = new_state.get('challenge', {})
    
    if old_challenge != new_challenge:
        challenge_changes = []
        if old_challenge.get('keystone_level') != new_challenge.get('keystone_level'):
            challenge_changes.append(f"  • Уровень ключа: {old_challenge.get('keystone_level')} → {new_challenge.get('keystone_level')}")
        if old_challenge.get('current_score') != new_challenge.get('current_score'):
            challenge_changes.append(f"  • Рейтинг: {old_challenge.get('current_score')} → {new_challenge.get('current_score')}")
        
        if challenge_changes:
            changes.append(f"🗝️ **Мифик+:**\n" + "\n".join(challenge_changes))
    
    # 9. Таланты
    old_talents = old_state.get('talents', [])
    new_talents = new_state.get('talents', [])
    
    if old_talents != new_talents:
        changes.append(f"✨ **Таланты изменены**")
    
    # 10. Глифы
    old_glyphs = {g['slot']: g['name'] for g in old_state.get('glyphs', [])}
    new_glyphs = {g['slot']: g['name'] for g in new_state.get('glyphs', [])}
    
    if old_glyphs != new_glyphs:
        glyph_changes = []
        for slot in set(old_glyphs.keys()) | set(new_glyphs.keys()):
            old_val = old_glyphs.get(slot)
            new_val = new_glyphs.get(slot)
            if old_val != new_val:
                glyph_changes.append(f"  • Слот {slot}: {old_val} → {new_val}")
        
        if glyph_changes:
            changes.append(f" **Глифы:**\n" + "\n".join(glyph_changes))
    
    # 11. Последние действия
    old_actions = [a['text'] for a in old_state.get('latest_actions', [])]
    new_actions = [a['text'] for a in new_state.get('latest_actions', [])]
    
    if old_actions != new_actions:
        new_action_set = set(new_actions) - set(old_actions)
        if new_action_set:
            changes.append(f"🎯 **Новые действия:**\n" + "\n".join([f"  • {action}" for action in list(new_action_set)[:5]]))
    
    return changes

# ====== ПРОВЕРКА ИЗМЕНЕНИЙ ======
def check_changes():
    global characters_states
    
    try:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] === НАЧАЛО ПРОВЕРКИ ===", flush=True)
        
        for char_info in CHARACTERS:
            world = char_info['world']
            character = char_info['name']
            char_key = f"{world}_{character}"
            
            print(f"\n→ Проверяю {character} ({world})...", flush=True)
            
            current_state = extract_character_data(world, character)
            
            if current_state is None:
                print(f"  ❌ Не удалось получить данные", flush=True)
                continue
            
            if char_key not in characters_states:
                characters_states[char_key] = current_state
                save_state(world, character, current_state)
                bot.send_message(MY_CHAT_ID, f"✅ Мониторинг активирован для *{character}* ({world})!", parse_mode='Markdown')
                print(f"  ✅ Первая проверка, состояние сохранено", flush=True)
                continue
            
            old_state = characters_states[char_key]
            changes = compare_states(old_state, current_state)
            
            if changes:
                changes_text = "\n\n".join(changes)
                
                if DEBUG_MODE:
                    print(f"\n   НАЙДЕНЫ ИЗМЕНЕНИЯ ({len(changes)}):", flush=True)
                    print(f"     {changes_text[:500]}...", flush=True)
                
                # Разбиваем длинные сообщения
                if len(changes_text) > 3000:
                    parts = [changes_text[i:i+3000] for i in range(0, len(changes_text), 3000)]
                    for i, part in enumerate(parts, 1):
                        bot.send_message(
                            MY_CHAT_ID,
                            f"🚨 **Изменения у {character} ({i}/{len(parts)}):**\n\n"
                            f"🌍 Сервер: {world}\n"
                            f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n\n"
                            f"{part}",
                            parse_mode='Markdown'
                        )
                else:
                    bot.send_message(
                        MY_CHAT_ID,
                        f" **Обнаружены изменения!**\n\n"
                        f"👤 Персонаж: *{character}*\n"
                        f"🌍 Сервер: {world}\n"
                        f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n\n"
                        f"{changes_text}",
                        parse_mode='Markdown'
                    )
                print(f"  ⚠️ Отправлено уведомление!", flush=True)
            else:
                print(f"  ✓ Изменений нет", flush=True)
            
            characters_states[char_key] = current_state
            save_state(world, character, current_state)
        
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] === ПРОВЕРКА ЗАВЕРШЕНА ===\n", flush=True)
        
    except Exception as e:
        print(f"Ошибка проверки: {e}", flush=True)
        import traceback
        traceback.print_exc()

# ====== КОМАНДЫ БОТА ======
@bot.message_handler(commands=['start'])
def start(message):
    print(f"📩 Команда /start от {message.chat.id}", flush=True)
    chars_list = "\n".join([f"  • {c['name']} ({c['world']})" for c in CHARACTERS])
    bot.send_message(
        message.chat.id,
        f"👋 Привет! Я бот-монитор для Sirus.su\n\n"
        f"📌 Отслеживаю:\n{chars_list}\n\n"
        f" Отслеживаются ВСЕ изменения:\n"
        f"  • Экипировка\n"
        f"  • Характеристики\n"
        f"  • Профессии и навыки\n"
        f"  • PvP и Arena рейтинг\n"
        f"  • Прогресс рейдов\n"
        f"  • Мифик+\n"
        f"  • Таланты и глифы\n"
        f"  • Последние действия\n\n"
        f" Команды:\n"
        f"/monitor — запустить\n"
        f"/stop — остановить\n"
        f"/check — проверить сейчас",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['monitor'])
def start_monitor(message):
    global monitoring_active
    print(f"📩 Команда /monitor от {message.chat.id}", flush=True)
    if str(message.chat.id) != str(MY_CHAT_ID):
        bot.reply_to(message, "⛔ Доступ запрещён!")
        return
    monitoring_active = True
    bot.reply_to(message, "✅ Мониторинг запущен! Проверка каждые 15 минут.")
    print(f"  ✅ Мониторинг включен", flush=True)

@bot.message_handler(commands=['stop'])
def stop_monitor(message):
    global monitoring_active
    print(f"📩 Команда /stop от {message.chat.id}", flush=True)
    if str(message.chat.id) != str(MY_CHAT_ID):
        bot.reply_to(message, " Доступ запрещён!")
        return
    monitoring_active = False
    bot.reply_to(message, " Мониторинг остановлен.")
    print(f"  ⏸ Мониторинг выключен", flush=True)

@bot.message_handler(commands=['check'])
def manual_check(message):
    print(f"📩 Команда /check от {message.chat.id}", flush=True)
    if str(message.chat.id) != str(MY_CHAT_ID):
        bot.reply_to(message, "⛔ Доступ запрещён!")
        return
    bot.reply_to(message, " Проверяю... Смотрите консоль!")
    print(f"  🔍 Запускаю проверку...", flush=True)
    check_changes()

# ====== ЗАПУСК ПЛАНИРОВЩИКА ======
def run_scheduler():
    schedule.every(15).minutes.do(check_changes)
    while True:
        schedule.run_pending()
        time.sleep(1)

# ====== ГЛАВНЫЙ ЗАПУСК ======
if __name__ == '__main__':
    print("🤖 Бот запущен!", flush=True)
    print(f"🔧 Режим отладки: {'ВКЛЮЧЕН' if DEBUG_MODE else 'ВЫКЛЮЧЕН'}", flush=True)
    
    for char_info in CHARACTERS:
        world = char_info['world']
        character = char_info['name']
        char_key = f"{world}_{character}"
        state = load_state(world, character)
        if state:
            characters_states[char_key] = state
            print(f"✅ Загружено состояние для {character}", flush=True)
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    print("✅ Бот готов к работе!", flush=True)
    bot.infinity_polling()