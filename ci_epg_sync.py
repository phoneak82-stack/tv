#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 CI/EPG SYNC — Генерация epg.xml по pl.m3u (универсальный)
 Запуск: GitHub Actions / VPS cron
✅ Логика: читает pl.m3u → скачивает EPG → фильтрует → сохраняет epg.xml
"""

import os, sys, re, gzip, time
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

# ==============================================================================
# ⚙️ НАСТРОЙКИ
# ==============================================================================
EPG_MIRRORS = [
    ('https://iptvx.one/EPG',        'Основной (полный, с архивом)'),
    ('https://iptvx.one/EPG7',       'Архив 7 дней'),
    ('https://iptvx.one/EPG_LITE',   'Лайт (без архива, быстрее)'),
    ('https://iptvx.one/EPG_NOARCH', 'Без архива (оптимально)')
]

# Источник по умолчанию (можно переопределить через secrets.EPG_URL)
DEFAULT_EPG_URL = 'https://iptvx.one/EPG_NOARCH'

PLAYLIST = "pl.m3u"
OUTPUT = "epg.xml"

# ==============================================================================
# 🎨 УТИЛИТЫ
# ==============================================================================
def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {level}: {msg}")

# ==============================================================================
# 📂 ЧТЕНИЕ ПЛЕЙЛИСТА
# ==============================================================================
def read_playlist(path):
    if not os.path.exists(path):
        log(f"❌ {path} не найден", "ERROR")
        sys.exit(1)
    
    valid_ids, valid_names = set(), set()
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('#EXTINF:'):
                if m := re.search(r'tvg-id="([^"]*)"', line):
                    valid_ids.add(m.group(1).lower().strip())
                if m := re.search(r',\s*(.*?)$', line):
                    name = m.group(1).strip().lower()
                    valid_names.add(name)
                    valid_names.add(name.replace(' ', ''))
    return valid_ids, valid_names

# ==============================================================================
# 🌐 ЗАГРУЗКА EPG С РЕТРАЯМИ
# ==============================================================================
def download_epg(url, retries=3):
    for attempt in range(1, retries + 1):
        try:
            log(f"📥 Попытка {attempt}/{retries}: {url[:50]}...")
            safe = urllib.parse.quote(url, safe=':/?=&#')
            req = urllib.request.Request(safe, headers={'User-Agent': 'EPG-Sync/1.0'})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                log(f"✅ Загружено: {len(data)/1024:.1f} КБ")
                return data
        except urllib.error.URLError as e:
            reason = str(e.reason).lower()
            if 'unreachable' in reason or 'network' in reason:
                if attempt < retries and attempt < len(EPG_MIRRORS):
                    next_url = EPG_MIRRORS[attempt][0]
                    log(f"⚠️ Сеть недоступна, пробуем зеркало: {next_url[:50]}...")
                    url = next_url
                    time.sleep(2)
                    continue
            elif 'timeout' in reason:
                log(f"⏳ Тайм-аут, повтор через {attempt*2}с...")
                time.sleep(attempt * 2)
                continue
            log(f"❌ Ошибка загрузки: {e.reason}", "ERROR")
        except Exception as e:
            log(f"❌ Ошибка: {e}", "ERROR")
    
    log("❌ Не удалось загрузить EPG ни с одного источника", "ERROR")
    sys.exit(1)

# ==============================================================================
# ⚡ ФИЛЬТРАЦИЯ И СОХРАНЕНИЕ
# ==============================================================================
def filter_and_save(epg_raw, valid_ids, valid_names, out_path):
    # Распаковка GZIP
    if epg_raw[:2] == b'\x1f\x8b':
        log("🗜️ Распаковка GZIP...")
        epg_raw = gzip.decompress(epg_raw)
    
    # Парсинг XML
    try:
        root = ET.fromstring(epg_raw)
    except ET.ParseError as e:
        log(f"❌ Ошибка XML: {e}", "ERROR")
        sys.exit(1)
    
    channels = root.findall('channel')
    programmes = root.findall('programme')
    
    log(f"📊 Исходный EPG: {len(channels)} каналов, {len(programmes)} программ")
    
    # Фильтрация каналов
    kept_ch, kept_ids = [], set()
    for ch in channels:
        cid = ch.get('id', '').lower().strip()
        dn = ch.find('display-name')
        txt = dn.text.lower().strip() if dn is not None and dn.text else ''
        if cid in valid_ids or txt in valid_names or txt.replace(' ','') in valid_names:
            kept_ch.append(ch)
            kept_ids.add(cid)
    
    log(f"✅ Совпало каналов: {len(kept_ch)}/{len(channels)}")
    
    # Фильтрация программ
    kept_pg = [p for p in programmes if p.get('channel', '').lower().strip() in kept_ids]
    log(f"✅ Осталось программ: {len(kept_pg)}/{len(programmes)}")
    
    # Сборка нового XML
    new_root = ET.Element(root.tag, root.attrib)
    new_root.extend(kept_ch)
    new_root.extend(kept_pg)
    
    xml_data = ET.tostring(new_root, encoding='utf-8', xml_declaration=True)
    
    # Сохранение
    with open(out_path, 'wb') as f:
        f.write(xml_data)
    
    log(f"💾 Сохранено: {out_path} ({len(xml_data)/1024:.1f} КБ)")
    return xml_data

# ==============================================================================
# 🚀 ГЛАВНЫЙ ПРОЦЕСС
# ==============================================================================
def main():
    log("🚀 Запуск CI/EPG SYNC")
    
    # Чтение плейлиста
    ids, names = read_playlist(PLAYLIST)
    log(f"📋 Плейлист: {len(ids)} ID, {len(names)} имён")
    
    # Выбор источника EPG
    epg_url = os.getenv("EPG_URL", DEFAULT_EPG_URL)
    log(f"📡 Источник EPG: {epg_url}")
    
    # Загрузка и фильтрация
    epg_raw = download_epg(epg_url)
    filter_and_save(epg_raw, ids, names, OUTPUT)
    
    log("🏁 Готово")

# ==============================================================================
# 🔐 ТОЧКА ВХОДА
# ==============================================================================
if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log("⛔ Прервано пользователем", "WARN")
        sys.exit(130)
    except Exception as e:
        log(f"❌ Критическая ошибка: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        sys.exit(1)
