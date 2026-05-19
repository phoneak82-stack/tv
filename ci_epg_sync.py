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

# ⚙️ Настройки
EPG_URL = os.getenv("EPG_URL", "https://iptvx.one/EPG_NOARCH")
PLAYLIST = "pl.m3u"
OUTPUT = "epg.xml"

def log(msg, level="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {level}: {msg}")

def read_playlist(path):
    if not os.path.exists(path):
        log(f"❌ {path} не найден", "ERROR"); sys.exit(1)
    ids, names = set(), set()
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('#EXTINF:'):
                if m := re.search(r'tvg-id="([^"]*)"', line): ids.add(m.group(1).lower().strip())
                if m := re.search(r',\s*(.*?)$', line):
                    n = m.group(1).strip().lower()
                    names.add(n); names.add(n.replace(' ',''))
    return ids, names

def download_epg(url, retries=3):
    for i in range(1, retries+1):
        try:
            log(f"Загрузка EPG (попытка {i})...")
            req = urllib.request.Request(urllib.parse.quote(url, safe=':/?=&#'), headers={'User-Agent': 'EPG-Sync/1.0'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:
            if i < retries: time.sleep(2**i)
            else: log(f"❌ Не удалось загрузить EPG: {e}", "ERROR"); sys.exit(1)
    return b""

def filter_and_save(epg_raw, valid_ids, valid_names, out_path):
    if epg_raw[:2] == b'\x1f\x8b': epg_raw = gzip.decompress(epg_raw)
    try: root = ET.fromstring(epg_raw)
    except ET.ParseError as e: log(f"❌ Ошибка XML: {e}", "ERROR"); sys.exit(1)

    channels, programmes = root.findall('channel'), root.findall('programme')
    kept_ch, kept_ids = [], set()

    log(f"Фильтрация: {len(channels)} каналов, {len(programmes)} программ...")
    for ch in channels:
        cid = ch.get('id', '').lower().strip()
        dn = ch.find('display-name')
        txt = dn.text.lower().strip() if dn is not None and dn.text else ''
        if cid in valid_ids or txt in valid_names or txt.replace(' ','') in valid_names:
            kept_ch.append(ch); kept_ids.add(cid)

    kept_pg = [p for p in programmes if p.get('channel','').lower().strip() in kept_ids]

    new_root = ET.Element(root.tag, root.attrib)
    new_root.extend(kept_ch); new_root.extend(kept_pg)
    xml_data = ET.tostring(new_root, encoding='utf-8', xml_declaration=True)
    with open(out_path, 'wb') as f: f.write(xml_data)
    log(f"✅ Сохранено: {out_path} ({len(xml_data)/1024:.1f} КБ)")

def main():
    log("🚀 Запуск генерации EPG")
    ids, names = read_playlist(PLAYLIST)
    log(f"Плейлист: {len(ids)} ID, {len(names)} имён")
    epg_raw = download_epg(EPG_URL)
    filter_and_save(epg_raw, ids, names, OUTPUT)
    log("🏁 Готово")

if __name__ == '__main__':
    try: main()
    except KeyboardInterrupt: sys.exit(130)
    except Exception as e: log(f"❌ Критическая ошибка: {e}", "ERROR"); sys.exit(1)
