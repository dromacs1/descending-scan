import customtkinter as ctk
from tkinter import filedialog
import hashlib
import html as html_lib
import json
import os
import re
import socket
import subprocess
import sys
import time
import threading
import webbrowser
import traceback
import zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urlparse, quote
import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import trafilatura
from PIL import Image, ImageDraw, ImageTk, ExifTags

try:
    from deep_translator import GoogleTranslator
    HAS_DEEP_TRANS = True
except Exception:
    HAS_DEEP_TRANS = False

try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except Exception:
    HAS_PYPDF = False

NL = chr(10)
APP_NAME, AUTHOR_NAME, GITHUB_URL = "Descending Scan", "dromacs1", "https://github.com/dromacs1"
SETTINGS_FILE, SAVED_FILE, ICON_FILE = "settings.json", "saved_pages.json", "icon.ico"
UA_BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

HTTP = requests.Session()
HTTP.headers.update({"User-Agent": UA_BROWSER, "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"})
_adapter = HTTPAdapter(pool_connections=64, pool_maxsize=64)
HTTP.mount("http://", _adapter)
HTTP.mount("https://", _adapter)


# ================= ЛОГОТИП И ИКОНКА =================
def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _quad_bezier(p0, p1, p2, steps=24):
    return [((1 - i / steps) ** 2 * p0[0] + 2 * (1 - i / steps) * (i / steps) * p1[0] + (i / steps) ** 2 * p2[0],
             (1 - i / steps) ** 2 * p0[1] + 2 * (1 - i / steps) * (i / steps) * p1[1] + (i / steps) ** 2 * p2[1])
            for i in range(steps + 1)]


def render_brand_logo(size=256, accent="#6366F1", bg="#111113"):
    w = size * 4
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    acc_rgb, bg_rgb = _hex_to_rgb(accent), _hex_to_rgb(bg)
    cx, cy, pad = w / 2, w / 2, w * 0.04
    draw.rounded_rectangle([pad, pad, w - pad, w - pad], radius=w * 0.23, fill=bg_rgb + (255,), outline=(44, 44, 52, 255), width=max(2, int(w * 0.016)))
    ro, rw = w * 0.38, max(3, int(w * 0.028))
    draw.arc([cx - ro, cy - ro, cx + ro, cy + ro], start=205, end=335, fill=acc_rgb + (255,), width=rw)
    draw.arc([cx - ro, cy - ro, cx + ro, cy + ro], start=25, end=155, fill=acc_rgb + (255,), width=rw)
    rs = w * 0.31
    draw.arc([cx - rs, cy - rs, cx + rs, cy + rs], start=218, end=322, fill=(248, 250, 252, 110), width=max(2, int(w * 0.015)))
    lp, rp = (cx - w * 0.30, cy), (cx + w * 0.30, cy)
    top_arc, bot_arc = _quad_bezier(lp, (cx, cy - w * 0.33), rp, 28), _quad_bezier(rp, (cx, cy + w * 0.33), lp, 28)
    draw.polygon(top_arc + bot_arc, fill=(10, 10, 14, 255))
    ew = max(3, int(w * 0.032))
    draw.line(top_arc, fill=(241, 245, 249, 255), width=ew, joint="curve")
    draw.line(bot_arc, fill=(241, 245, 249, 255), width=ew, joint="curve")
    ri = w * 0.125
    draw.ellipse([cx - ri, cy - ri, cx + ri, cy + ri], fill=acc_rgb + (55,), outline=acc_rgb + (255,), width=max(2, int(w * 0.024)))
    bolt = [(cx + w * 0.045, cy - w * 0.295), (cx - w * 0.105, cy + w * 0.015), (cx - w * 0.005, cy + w * 0.015),
            (cx - w * 0.055, cy + w * 0.295), (cx + w * 0.115, cy - w * 0.025), (cx + w * 0.012, cy - w * 0.025)]
    draw.polygon([(x + w * 0.012, y + w * 0.012) for x, y in bolt], fill=acc_rgb + (180,))
    draw.polygon(bolt, fill=(255, 255, 255, 255))
    return img.resize((size, size), Image.LANCZOS)


def ensure_icon_file(path=ICON_FILE, accent="#6366F1"):
    try:
        render_brand_logo(256, accent=accent, bg="#111113").save(
            path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        )
        return True
    except Exception:
        return False


if "--make-icon" in sys.argv:
    ensure_icon_file(ICON_FILE)
    print("icon.ico created.")
    sys.exit(0)


# ================= БАЗЫ, АНТИ-404 / АНТИ-КАПЧА И ЯЗЫКИ =================
GARBAGE_DOMAINS = (
    "softonic.", "uptodown.", "malavida.", "filehippo.", "download.cnet.", "driverpack.",
    "otvet.mail.ru", "znanija.com", "rambler.ru", "msn.com", "shutterstock.", "istockphoto.",
    "alamy.", "123rf.", "dzen.ru", "yandex.ru/q", "fb.ru", "syl.ru", "autogear.ru",
    "baidu.com", "zhihu.com", "csdn.net", "weibo.com", "sohu.com", "163.com",
    "sina.com.cn", "qq.com", "bilibili.com", "360doc.com", "douban.com",
    "xvideos.", "pornhub.", "xnxx.", "xhamster.", "redtube.", "youporn.", "brazzers.",
    "chaturbate.", "bongacams.", "stripchat.", "spankbang.", "eporner.",
    "ria.ru", "tass.ru", "lenta.ru", "rbc.ru", "gazeta.ru", "kp.ru", "aif.ru", "iz.ru", "rt.com"
)

ADULT_STOP_WORDS = (
    "porn", "porno", "порно", "xvideos", "xnxx", "xhamster", "redtube", "youporn",
    "nsfw", "hentai", "хентай", "escort", "эскорт", "xxx", "sex video", "секс видео", "onlyfans leak"
)

BOT_WALLS = (
    "just a moment", "attention required", "cloudflare", "cf-challenge", "challenge-platform",
    "ddos-guard", "verify you are human", "are you a robot", "checking your browser",
    "smartcaptcha", "вы не робот", "подтвердите, что вы не робот", "пожалуйста, пройдите проверку",
    "enable javascript and cookies", "access denied", "bot protection", "security check", "captcha"
)

JUNK_TITLES = (
    "404", "403 forbidden", "502 bad gateway", "503 service", "page not found", "not found",
    "error 404", "ошибка 404", "страница не найдена", "не найдена", "не найден",
    "доступ запрещен", "вход", "авторизация", "sign in", "log in", "login", "suspended"
)

DEFAULT_404 = (
    "404 not found", "page not found", "user not found", "profile not found", "account not found",
    "does not exist", "doesn't exist", "isn't available", "couldn't find", "we can't find",
    "страница не найдена", "пользователь не найден", "такой страницы нет", "аккаунт удален"
)

OCR_STOP = {
    "roblox", "health", "menu", "chat", "play", "settings", "leave", "resume", "reset", "character",
    "players", "leaderboard", "team", "score", "level", "vip", "fps", "ping", "shop", "store",
    "inventory", "friends", "home", "back", "next", "cancel", "close", "open", "join", "server",
    "loading", "game", "games", "avatar", "profile", "online", "offline", "send", "message",
    "discord", "telegram", "steam", "windows", "search", "file", "edit", "view", "help", "youtube",
    "mute", "unmute", "report", "block", "follow", "followers", "following", "about", "groups", "people"
}

FREE_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com", "live.com",
    "icloud.com", "me.com", "mail.ru", "bk.ru", "inbox.ru", "list.ru", "internet.ru",
    "yandex.ru", "yandex.com", "ya.ru", "rambler.ru", "proton.me", "protonmail.com",
    "ukr.net", "i.ua", "meta.ua", "gmx.de", "web.de", "wp.pl", "o2.pl", "onet.pl",
    "orange.fr", "free.fr", "tutanota.com", "aol.com", "zoho.com"
}

PHONE_PREFIXES = (
    ("380", "Украина"), ("375", "Беларусь"), ("374", "Армения"), ("373", "Молдова"),
    ("372", "Эстония"), ("371", "Латвия"), ("370", "Литва"), ("358", "Финляндия"),
    ("998", "Узбекистан"), ("996", "Кыргызстан"), ("995", "Грузия"), ("994", "Азербайджан"),
    ("992", "Таджикистан"), ("77", "Казахстан"), ("76", "Казахстан"), ("7", "Россия / Казахстан"),
    ("49", "Германия"), ("48", "Польша"), ("44", "Великобритания"), ("33", "Франция"),
    ("39", "Италия"), ("34", "Испания"), ("31", "Нидерланды"), ("90", "Турция"), ("1", "США / Канада")
)

RU_MOBILE_DEF = {
    **{str(k): "МТС" for k in (*range(910, 920), *range(980, 990))},
    **{str(k): "МегаФон" for k in (*range(920, 935), *range(936, 940))},
    **{str(k): "Билайн" for k in (903, 905, 906, 909, *range(960, 970))},
    **{str(k): "Tele2" for k in (900, 901, 902, 904, 908, 950, 951, 952, 953, 977, 991, 992, 993, 994)},
    "958": "Ростелеком / Сбер", "978": "МТС / Волна", "995": "Yota / Т-Мобайл", "996": "Yota / Сбер", "999": "Yota / МегаФон"
}

KZ_MOBILE_DEF = {
    "700": "ALTEL", "701": "Kcell/Activ", "702": "Kcell/Activ", "705": "Beeline", "706": "ALTEL/Tele2",
    "707": "Tele2", "708": "ALTEL", "747": "Tele2", "771": "Beeline", "775": "Kcell/Activ", "776": "Beeline", "777": "Beeline", "778": "Kcell/Activ"
}

TRANSLIT_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya", "є": "ye", "і": "i", "ї": "yi", "ґ": "g", "ә": "a", "ң": "n", "ғ": "g", "ү": "u", "ұ": "u", "қ": "k", "ө": "o", "һ": "h"
}

LANG_META = {
    "ru": {"label": "Русский", "region": "ru-ru", "wiki": "ru", "steam": "russian"},
    "en": {"label": "English", "region": "us-en", "wiki": "en", "steam": "english"},
    "kk": {"label": "Қазақша", "region": "ru-ru", "wiki": "kk", "steam": "russian"},
    "de": {"label": "Deutsch", "region": "de-de", "wiki": "de", "steam": "german"},
    "uk": {"label": "Українська", "region": "ua-uk", "wiki": "uk", "steam": "ukrainian"},
    "pl": {"label": "Polski", "region": "pl-pl", "wiki": "pl", "steam": "polish"},
    "fr": {"label": "Français", "region": "fr-fr", "wiki": "fr", "steam": "french"},
    "fi": {"label": "Suomi", "region": "fi-fi", "wiki": "fi", "steam": "finnish"},
}

ACCENTS = {
    "indigo": ("#6366F1", "#4F46E5", "Indigo"), "emerald": ("#10B981", "#059669", "Emerald"),
    "sky": ("#0EA5E9", "#0284C7", "Sky"), "amber": ("#F59E0B", "#D97706", "Amber"),
    "rose": ("#F43F5E", "#E11D48", "Rose"), "violet": ("#8B5CF6", "#7C3AED", "Violet"),
}

BG_STYLES = {
    "classic": {"label": "Classic", "sidebar": ("#E5E7EB", "#111113"), "main": ("#FFFFFF", "#18181B"), "box": ("#F3F4F6", "#111113"), "card": ("#FFFFFF", "#1E1E22"), "inactive": ("#E5E7EB", "#27272A")},
    "oled": {"label": "OLED Black", "sidebar": ("#E5E7EB", "#000000"), "main": ("#FFFFFF", "#050505"), "box": ("#F3F4F6", "#0A0A0A"), "card": ("#FFFFFF", "#141416"), "inactive": ("#E5E7EB", "#1C1C1F")},
    "midnight": {"label": "Midnight", "sidebar": ("#E2E8F0", "#0B1120"), "main": ("#F8FAFC", "#0F172A"), "box": ("#E2E8F0", "#0B1120"), "card": ("#FFFFFF", "#1E293B"), "inactive": ("#CBD5E1", "#1E293B")},
    "graphite": {"label": "Graphite", "sidebar": ("#E7E5E4", "#171615"), "main": ("#FAFAF9", "#1F1E1C"), "box": ("#E7E5E4", "#171615"), "card": ("#FFFFFF", "#292724"), "inactive": ("#D6D3D1", "#2E2B28")},
}

EULA_TEXT_RU = """ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ (EULA) — DESCENDING SCAN v2.0
Прокрутите до конца и внимательно прочитайте условия

1. СТАТУС ПО
Программа «Descending Scan» — технический инструмент для автоматизированного поиска и анализа общедоступных данных из открытых источников (OSINT) и публичных API.

2. ОТВЕТСТВЕННОСТЬ ПОЛЬЗОВАТЕЛЯ
Все действия совершаются пользователем самостоятельно под его полную юридическую и моральную ответственность с соблюдением законодательства.

3. ОТКАЗ ОТ ОТВЕТСТВЕННОСТИ («КАК ЕСТЬ»)
ПО предоставляется «КАК ЕСТЬ» (AS IS) без каких-либо гарантий. Автор не несёт ответственности за ущерб или последствия использования.

4. МОДИФИКАЦИИ
Любые модификации и сторонние сборки используются исключительно на свой риск.

5. ПРИНЯТИЕ УСЛОВИЙ
Прокрутив документ до конца и подтвердив согласие, вы принимаете все пункты выше."""

EULA_TEXT_EN = """END USER LICENSE AGREEMENT (EULA) — DESCENDING SCAN v2.0
Please scroll down and read carefully

1. SOFTWARE PURPOSE
"Descending Scan" is an OSINT tool for searching and analyzing publicly available data from open sources and public APIs only.

2. USER RESPONSIBILITY
All actions performed with this tool are under the user's sole legal and ethical responsibility.

3. DISCLAIMER ("AS IS")
Provided "AS IS", without warranty of any kind. The author holds zero liability for misuse or damages.

4. MODIFICATIONS
Any modded or third-party builds are used strictly at your own risk.

5. ACCEPTANCE
By scrolling to the bottom and confirming below, you agree to these terms."""

TR_EN = {
    "title": "Descending Scan — OSINT & Recon Hub", "nav_s": "  🔍   Search", "nav_a": "  💾   Saved", "nav_c": "  ⚙️   Settings", "nav_d": "  🐞   Debug", "dark": "Dark theme",
    "hub": "Search & OSINT Hub", "m_search": "🔍 Web Search", "m_profile": "👁️ OSINT Scan",
    "ph_search": "Site, game or topic (404 / captcha / news trash filtered)...",
    "lbl_nick": "Nick / SteamID64 / Discord ID", "ph_nick": "e.g. dromacs1 or 18-digit Discord/Steam ID",
    "lbl_email": "Email", "ph_email": "e.g. user@gmail.com (Gravatar, commits, leaks)",
    "lbl_fio": "Full Name", "ph_fio": "e.g. John Doe (socials, registries)",
    "lbl_phone": "Phone Number", "ph_phone": "e.g. +14155550199 (carrier, messengers)",
    "lbl_ip": "IP / Domain", "ph_ip": "e.g. 8.8.8.8 or github.com (GeoIP, crt.sh, DNS)",
    "lbl_hw": "MAC / Hardware", "ph_hw": "e.g. A4:5E:60:11:22:33 or device model",
    "btn_photo": "📷 Photo / File (OCR+EXIF)", "photo_none": "No photo/file selected",
    "go": "Run", "tr_cards": "🌐 Translate", "exp_html": "📄 HTML", "tr_busy": "⏳ Translating...", "tr_btn": "🌐 Translate", "orig_btn": "🔄 Original",
    "st_ready": "Pick a mode above, enter data and press Enter.", "st_empty": "Enter a query!", "st_prof_empty": "Fill at least one field or pick a photo/file!",
    "st_scan": "Searching «{q}» ({scope})...", "st_prof": "OSINT scan: checking ({q})...",
    "st_none": "Nothing verified found (404/captcha filtered).", "st_done": "Done! {n} clean verified sources.", "st_pdone": "Done ({q}): {p} verified hits, {m} mentions.",
    "st_err": "Error: {err}", "st_dup": "Already saved.", "st_saving": "Saving...", "st_saved": "Saved: {t}...", "st_exp": "HTML report opened: {f}",
    "saved_h": "Offline Archive", "set_h": "Settings & Appearance", "l_ui": "Interface language:", "l_scope": "Search scope:", "sc_reg": "Regional", "sc_glob": "Global",
    "l_accent": "Accent color:", "l_bg": "Background style:", "l_depth": "Search depth: {v}", "cb_gh": "Primary sources only (GitHub, Reddit, Habr)", "cb_safe": "SafeSearch (filter 18+)",
    "l_about": "Author & GitHub:", "btn_open_gh": "🌐 Open", "made_by": "Made by dromacs1", "dbg_h": "Debug Console", "clear": "Clear", "copy": "📋 Copy", "back": "← Back",
    "arch": "💾 Archive", "copied": "✓ Copied", "archived": "✓ Saved", "browser": "🌐 Browser", "read": "📖 Read", "save": "💾 Save", "delete": "🗑️ Delete",
    "b_off": "⭐ Official", "b_wiki": "📚 Wikipedia", "b_steam": "🎮 Steam", "b_fan": "📖 Wiki / Fandom", "b_code": "💻 Code / Git", "b_for": "💬 Forum", "b_store": "🛒 Store", "b_vid": "🎬 Video",
    "b_mus": "🎵 Music", "b_soc": "💬 Social", "b_art": "📄 Site", "b_api": "✅ API Verified", "b_html": "🌐 Profile", "b_gprof": "🎮 Gaming API", "b_mprof": "🎵 Music",
    "b_repo": "📦 Project", "b_ment": "🔎 Mention", "b_email": "📧 Email", "b_alert": "🚨 Alert / Ban", "b_phone": "📱 Phone", "b_fio": "🪪 Name", "b_link": "🔗 Cross-Match",
    "b_ip": "🌍 IP / Domain", "b_sub": "📡 Subdomains / DNS", "b_wayback": "🕰️ Wayback", "b_hw": "🖥️ Hardware / MAC", "b_photo": "📍 EXIF / GPS", "b_ocr": "🔤 OCR Auto-Recon",
    "b_doc": "📄 Doc Meta", "b_disc": "❄️ Discord ID",
    "r_load": "Fetching clean text...", "r_fail": "Could not extract text. Open in browser.", "r_src": "Source"
}

TR_RU = {
    **TR_EN,
    "title": "Descending Scan — Поиск и OSINT-комбайн", "nav_s": "  🔍   Поиск", "nav_a": "  💾   Сохраненное", "nav_c": "  ⚙️   Настройки", "nav_d": "  🐞   Отладка", "dark": "Темная тема",
    "hub": "Центр поиска и OSINT", "m_search": "🔍 Поиск сайтов", "m_profile": "👁️ OSINT Анкета",
    "ph_search": "Сайт, игра или тема (без новостей, 404 и капч)...",
    "lbl_nick": "Ник / SteamID64 / Discord ID", "ph_nick": "напр.: dromacs1 или 18-значный Discord/Steam ID",
    "lbl_email": "Почта / Email", "ph_email": "напр.: user@gmail.com (Gravatar, коммиты, утечки)",
    "lbl_fio": "ФИО / Имя", "ph_fio": "напр.: Иванов Иван Иванович",
    "lbl_phone": "Номер телефона", "ph_phone": "напр.: +79991234567 (оператор, мессенджеры)",
    "lbl_ip": "IP / Домен", "ph_ip": "напр.: 8.8.8.8 или github.com (GeoIP, crt.sh, DNS)",
    "lbl_hw": "MAC / Железо", "ph_hw": "напр.: A4:5E:60:11:22:33 или модель железа",
    "btn_photo": "📷 Фото / Файл (OCR+EXIF)", "photo_none": "Фото или файл не выбран",
    "go": "Запустить", "tr_cards": "🌐 Перевести", "exp_html": "📄 HTML", "tr_busy": "⏳ Перевод...", "tr_btn": "🌐 Перевести", "orig_btn": "🔄 Оригинал",
    "st_ready": "Выберите режим, введите данные и нажмите Enter.", "st_empty": "Введите запрос!", "st_prof_empty": "Заполните хотя бы одно поле или выберите фото/файл!",
    "st_scan": "Ищу «{q}» ({scope})...", "st_prof": "OSINT-скан: проверяю ({q})...",
    "st_none": "Подтвержденных данных не найдено (404/капчи отсеяны).", "st_done": "Готово! {n} чистых проверенных источников.", "st_pdone": "Готово ({q}): {p} подтвержденных и {m} упоминаний.",
    "st_err": "Ошибка: {err}", "st_dup": "Уже есть в сохраненных.", "st_saving": "Сохраняю...", "st_saved": "Сохранено: {t}...", "st_exp": "Отчет открыт: {f}",
    "saved_h": "Офлайн-архив", "set_h": "Настройки и внешний вид", "l_ui": "Язык интерфейса:", "l_scope": "Охват поиска:", "sc_reg": "Региональный", "sc_glob": "Глобальный",
    "l_accent": "Акцентный цвет кнопок:", "l_bg": "Стиль фона:", "l_depth": "Глубина проверки: {v}", "cb_gh": "Только первоисточники (GitHub, Reddit, Habr)", "cb_safe": "Безопасный поиск (скрывать 18+)",
    "l_about": "Автор и GitHub:", "btn_open_gh": "🌐 Перейти", "made_by": "Сделал dromacs1", "dbg_h": "Консоль отладки", "clear": "Очистить", "copy": "📋 Копировать", "back": "← Назад",
    "arch": "💾 В архив", "copied": "✓ Скопировано", "archived": "✓ Сохранено", "browser": "🌐 Браузер", "read": "📖 Читать", "save": "💾 Сохранить", "delete": "🗑️ Удалить",
    "b_off": "⭐ Официальный", "b_wiki": "📚 Википедия", "b_steam": "🎮 Steam", "b_fan": "📖 Фандом / Вики", "b_code": "💻 Код / Git", "b_for": "💬 Форум", "b_store": "🛒 Магазин", "b_vid": "🎬 Видео",
    "b_mus": "🎵 Музыка", "b_soc": "💬 Соцсеть", "b_art": "📄 Сайт", "b_api": "✅ API Подтвержден", "b_html": "🌐 Профиль", "b_gprof": "🎮 Игровой API", "b_mprof": "🎵 Музыка",
    "b_repo": "📦 Проект", "b_ment": "🔎 Упоминание", "b_email": "📧 Почта", "b_alert": "🚨 Утечка / Бан", "b_phone": "📱 Телефон", "b_fio": "🪪 ФИО", "b_link": "🔗 Связка",
    "b_ip": "🌍 IP / Домен", "b_sub": "📡 Поддомены / DNS", "b_wayback": "🕰️ Архив", "b_hw": "🖥️ Железо / MAC", "b_photo": "📍 EXIF / GPS", "b_ocr": "🔤 OCR Автопробив",
    "b_doc": "📄 Метаданные", "b_disc": "❄️ Discord ID",
    "r_load": "Загружаю чистый текст...", "r_fail": "Не удалось извлечь текст. Откройте в браузере.", "r_src": "Источник"
}

TRANSLATIONS = {
    "ru": TR_RU, "en": TR_EN,
    "uk": {**TR_RU, "nav_s": "  🔍   Пошук", "nav_a": "  💾   Збережене", "nav_c": "  ⚙️   Налаштування", "nav_d": "  🐞   Налагодження", "hub": "Центр пошуку та OSINT", "m_search": "🔍 Пошук сайтів", "m_profile": "👁️ OSINT Анкета", "go": "Запустити", "saved_h": "Офлайн-архів", "set_h": "Налаштування", "clear": "Очистити", "back": "← Назад", "read": "📖 Читати", "save": "💾 Зберегти", "delete": "🗑️ Видалити", "made_by": "Зробив dromacs1"},
    "kk": {**TR_RU, "nav_s": "  🔍   Іздеу", "nav_a": "  💾   Сақталған", "nav_c": "  ⚙️   Баптаулар", "hub": "Іздеу және OSINT", "m_search": "🔍 Сайт іздеу", "go": "Іске қосу", "saved_h": "Офлайн мұрағат", "set_h": "Баптаулар", "clear": "Тазарту", "back": "← Артқа", "read": "📖 Оқу", "save": "💾 Сақтау", "delete": "🗑️ Жою", "made_by": "Жасаған dromacs1"},
    "de": {**TR_EN, "nav_s": "  🔍   Suche", "nav_a": "  💾   Gespeichert", "nav_c": "  ⚙️   Einstellungen", "dark": "Dunkles Design", "m_search": "🔍 Websuche", "go": "Starten", "saved_h": "Offline-Archiv", "set_h": "Einstellungen", "clear": "Leeren", "back": "← Zurück", "read": "📖 Lesen", "save": "💾 Speichern", "delete": "🗑️ Löschen", "made_by": "Erstellt von dromacs1"},
    "pl": {**TR_EN, "nav_s": "  🔍   Szukaj", "nav_a": "  💾   Zapisane", "nav_c": "  ⚙️   Ustawienia", "dark": "Ciemny motyw", "m_search": "🔍 Szukaj stron", "go": "Uruchom", "saved_h": "Archiwum offline", "set_h": "Ustawienia", "clear": "Wyczyść", "back": "← Wróć", "read": "📖 Czytaj", "save": "💾 Zapisz", "delete": "🗑️ Usuń", "made_by": "Stworzył dromacs1"},
    "fr": {**TR_EN, "nav_s": "  🔍   Recherche", "nav_a": "  💾   Enregistré", "nav_c": "  ⚙️   Paramètres", "dark": "Thème sombre", "m_search": "🔍 Recherche Web", "go": "Lancer", "saved_h": "Archive hors ligne", "set_h": "Paramètres", "clear": "Effacer", "back": "← Retour", "read": "📖 Lire", "save": "💾 Sauver", "delete": "🗑️ Supprimer", "made_by": "Créé par dromacs1"},
    "fi": {**TR_EN, "nav_s": "  🔍   Haku", "nav_a": "  💾   Tallennetut", "nav_c": "  ⚙️   Asetukset", "dark": "Tumma teema", "m_search": "🔍 Verkkohaku", "go": "Suorita", "saved_h": "Offline-arkisto", "set_h": "Asetukset", "clear": "Tyhjennä", "back": "← Takaisin", "read": "📖 Lue", "save": "💾 Tallenna", "delete": "🗑️ Poista", "made_by": "Tehnyt dromacs1"},
}

# Живые площадки с высоким сигналом (без мертвых и вечных капч)
HTML_PLATFORMS = [
    ("Codeberg", "https://codeberg.org/{q}", "b_repo", "#10B981"), ("SourceForge", "https://sourceforge.net/u/{q}/profile/", "b_repo", "#F97316"),
    ("PyPI", "https://pypi.org/user/{q}/", "b_repo", "#3B82F6"), ("npm", "https://www.npmjs.com/~{q}", "b_repo", "#EF4444"),
    ("Crates.io", "https://crates.io/users/{q}", "b_repo", "#F59E0B"), ("RubyGems", "https://rubygems.org/profiles/{q}", "b_repo", "#EF4444"),
    ("Replit", "https://replit.com/@{q}", "b_repo", "#F97316"), ("CodePen", "https://codepen.io/{q}", "b_repo", "#10B981"),
    ("Kaggle", "https://www.kaggle.com/{q}", "b_repo", "#0EA5E9"), ("Bitbucket", "https://bitbucket.org/{q}/", "b_repo", "#3B82F6"),
    ("LeetCode", "https://leetcode.com/u/{q}/", "b_repo", "#F59E0B"), ("AtCoder", "https://atcoder.jp/users/{q}", "b_repo", "#0EA5E9"),
    ("HackerRank", "https://www.hackerrank.com/profile/{q}", "b_repo", "#10B981"), ("Exercism", "https://exercism.org/profiles/{q}", "b_repo", "#8B5CF6"),
    ("Habr", "https://habr.com/ru/users/{q}/", "b_html", "#14B8A6"), ("Habr Career", "https://career.habr.com/{q}", "b_html", "#14B8A6"),
    ("Dev.to", "https://dev.to/{q}", "b_repo", "#10B981"), ("Hashnode", "https://hashnode.com/@{q}", "b_repo", "#3B82F6"),
    ("HackerNews", "https://news.ycombinator.com/user?id={q}", "b_repo", "#F97316", ("no such user",)), ("Lobsters", "https://lobste.rs/~{q}", "b_repo", "#EF4444"),
    ("Launchpad", "https://launchpad.net/~{q}", "b_repo", "#F59E0B"), ("Arch AUR", "https://aur.archlinux.org/account/{q}", "b_repo", "#0EA5E9"),
    ("HackerOne", "https://hackerone.com/{q}", "b_repo", "#10B981"), ("TryHackMe", "https://tryhackme.com/p/{q}", "b_repo", "#EF4444"),
    ("Pastebin", "https://pastebin.com/u/{q}", "b_repo", "#3B82F6"), ("Gist GitHub", "https://gist.github.com/{q}", "b_repo", "#10B981"),
    ("OpenStreetMap", "https://www.openstreetmap.org/user/{q}", "b_repo", "#10B981"), ("Hackaday", "https://hackaday.io/{q}", "b_repo", "#10B981"),
    ("Keybase", "https://keybase.io/{q}", "b_repo", "#F97316", ("not a keybase user",)),
    ("Trovo", "https://trovo.live/s/{q}", "b_gprof", "#10B981"), ("Medal.tv", "https://medal.tv/u/{q}", "b_gprof", "#F59E0B"),
    ("CurseForge", "https://www.curseforge.com/members/{q}", "b_gprof", "#F97316"), ("NexusMods", "https://next.nexusmods.com/profile/{q}", "b_gprof", "#F97316"),
    ("Itch.io", "https://{q}.itch.io/", "b_gprof", "#F43F5E"), ("GameJolt", "https://gamejolt.com/@{q}", "b_gprof", "#10B981"),
    ("Newgrounds", "https://{q}.newgrounds.com/", "b_gprof", "#F59E0B"), ("Osu!", "https://osu.ppy.sh/users/{q}", "b_gprof", "#EC4899"),
    ("PSNProfiles", "https://psnprofiles.com/{q}", "b_gprof", "#3B82F6"), ("Exophase", "https://www.exophase.com/user/{q}/", "b_gprof", "#8B5CF6"),
    ("Backloggd", "https://www.backloggd.com/u/{q}/", "b_gprof", "#EC4899"), ("HowLongToBeat", "https://howlongtobeat.com/user/{q}", "b_gprof", "#3B82F6"),
    ("RAWG", "https://rawg.io/@{q}", "b_gprof", "#10B981"), ("BoardGameGeek", "https://boardgamegeek.com/user/{q}", "b_gprof", "#F97316"),
    ("TruckersMP", "https://truckersmp.com/user/{q}", "b_gprof", "#EF4444"), ("PlanetMinecraft", "https://www.planetminecraft.com/member/{q}/", "b_gprof", "#10B981"),
    ("NameMC", "https://namemc.com/profile/{q}", "b_gprof", "#10B981"), ("TETR.IO", "https://ch.tetr.io/u/{q}", "b_gprof", "#8B5CF6", ("no such user",)),
    ("ModDB", "https://www.moddb.com/members/{q}", "b_gprof", "#EF4444"), ("GameBanana", "https://gamebanana.com/members/{q}", "b_gprof", "#F59E0B"),
    ("GOG.com", "https://www.gog.com/u/{q}", "b_gprof", "#8B5CF6"), ("Scratch", "https://scratch.mit.edu/users/{q}/", "b_gprof", "#F59E0B", ("scratching its head",)),
    ("GeoGuessr", "https://www.geoguessr.com/user/{q}", "b_gprof", "#10B981"), ("NationStates", "https://www.nationstates.net/nation={q}", "b_gprof", "#3B82F6"),
    ("VK", "https://vk.com/{q}", "b_html", "#3B82F6", ("добро пожаловать",)), ("OK.ru", "https://ok.ru/{q}", "b_html", "#F97316"),
    ("Mastodon.social", "https://mastodon.social/@{q}", "b_html", "#8B5CF6", ("isn't here",)), ("Pinterest", "https://www.pinterest.com/{q}/", "b_html", "#EF4444"),
    ("Tumblr", "https://{q}.tumblr.com/", "b_html", "#3B82F6", ("there's nothing here",)), ("LiveJournal", "https://{q}.livejournal.com/", "b_html", "#0EA5E9"),
    ("Pikabu", "https://pikabu.ru/@{q}", "b_html", "#10B981"), ("DTF", "https://dtf.ru/u/{q}", "b_html", "#38BDF8"),
    ("VC.ru", "https://vc.ru/u/{q}", "b_html", "#38BDF8"), ("Drive2", "https://www.drive2.ru/users/{q}/", "b_html", "#EF4444"),
    ("Strava", "https://www.strava.com/athletes/{q}", "b_html", "#F97316"), ("MyAnimeList", "https://myanimelist.net/profile/{q}", "b_html", "#3B82F6", ("invalid username",)),
    ("AniList", "https://anilist.co/user/{q}/", "b_html", "#0EA5E9"), ("Kitsu", "https://kitsu.app/users/{q}", "b_html", "#F97316"),
    ("Letterboxd", "https://letterboxd.com/{q}/", "b_html", "#10B981"), ("Trakt", "https://trakt.tv/users/{q}", "b_html", "#EF4444"),
    ("Goodreads", "https://www.goodreads.com/{q}", "b_html", "#F59E0B"), ("LiveLib", "https://www.livelib.ru/reader/{q}", "b_html", "#3B82F6"),
    ("Wattpad", "https://www.wattpad.com/user/{q}", "b_html", "#F97316"), ("Ficbook", "https://ficbook.net/authors/{q}", "b_html", "#F59E0B"),
    ("Author.Today", "https://author.today/u/{q}", "b_html", "#0EA5E9"), ("Medium", "https://medium.com/@{q}", "b_html", "#10B981", ("out of nothing",)),
    ("Substack", "https://substack.com/@{q}", "b_html", "#F97316"), ("Disqus", "https://disqus.com/by/{q}/", "b_html", "#0EA5E9"),
    ("About.me", "https://about.me/{q}", "b_html", "#3B82F6"), ("Linktree", "https://linktr.ee/{q}", "b_html", "#10B981"),
    ("Carrd", "https://{q}.carrd.co/", "b_html", "#8B5CF6"), ("Taplink", "https://taplink.cc/{q}", "b_html", "#0EA5E9"),
    ("Bio.link", "https://bio.link/{q}", "b_html", "#EC4899"), ("Boosty", "https://boosty.to/{q}", "b_html", "#F97316"),
    ("Patreon", "https://www.patreon.com/{q}", "b_html", "#F97316"), ("Ko-fi", "https://ko-fi.com/{q}", "b_html", "#0EA5E9"),
    ("BuyMeACoffee", "https://www.buymeacoffee.com/{q}", "b_html", "#F59E0B"), ("Gumroad", "https://{q}.gumroad.com/", "b_html", "#EC4899"),
    ("ProductHunt", "https://www.producthunt.com/@{q}", "b_html", "#F97316"), ("YouTube", "https://www.youtube.com/@{q}", "b_html", "#EF4444"),
    ("Vimeo", "https://vimeo.com/{q}", "b_html", "#0EA5E9", ("sorry, we couldn",)), ("Rumble", "https://rumble.com/c/{q}", "b_html", "#10B981"),
    ("Odysee", "https://odysee.com/@{q}", "b_html", "#EC4899"), ("Coub", "https://coub.com/{q}", "b_html", "#3B82F6"),
    ("Behance", "https://www.behance.net/{q}", "b_html", "#3B82F6", ("oops",)), ("Dribbble", "https://dribbble.com/{q}", "b_html", "#EC4899", ("whoops",)),
    ("DeviantArt", "https://www.deviantart.com/{q}", "b_html", "#10B981"), ("ArtStation", "https://www.artstation.com/{q}", "b_html", "#0EA5E9"),
    ("Sketchfab", "https://sketchfab.com/{q}", "b_html", "#0EA5E9"), ("Thingiverse", "https://www.thingiverse.com/{q}/designs", "b_html", "#3B82F6"),
    ("Printables", "https://www.printables.com/@{q}", "b_html", "#F97316"), ("Unsplash", "https://unsplash.com/@{q}", "b_html", "#10B981"),
    ("Flickr", "https://www.flickr.com/people/{q}/", "b_html", "#EC4899"), ("VSCO", "https://vsco.co/{q}/gallery", "b_html", "#9CA3AF"),
    ("SoundCloud", "https://soundcloud.com/{q}", "b_mprof", "#F97316", ("can't find that user",)), ("Last.fm", "https://www.last.fm/user/{q}", "b_mprof", "#EF4444"),
    ("Bandcamp", "https://{q}.bandcamp.com/", "b_mprof", "#0EA5E9", ("sorry, that something isn",)), ("Genius", "https://genius.com/{q}", "b_mprof", "#F59E0B"),
    ("Mixcloud", "https://www.mixcloud.com/{q}/", "b_mprof", "#8B5CF6"), ("Discogs", "https://www.discogs.com/user/{q}", "b_mprof", "#F59E0B"),
    ("PromoDJ", "https://promodj.com/{q}", "b_mprof", "#0EA5E9"), ("Freelancer", "https://www.freelancer.com/u/{q}", "b_html", "#0EA5E9"),
    ("FL.ru", "https://www.fl.ru/users/{q}/", "b_html", "#10B981"), ("Kwork", "https://kwork.ru/user/{q}", "b_html", "#10B981"),
    ("Mirror.xyz", "https://mirror.xyz/{q}", "b_html", "#3B82F6"), ("Farcaster", "https://warpcast.com/{q}", "b_html", "#8B5CF6"),
    ("Archive.org", "https://archive.org/details/@{q}", "b_html", "#9CA3AF", ("cannot find account",)), ("Imgur", "https://imgur.com/user/{q}", "b_html", "#10B981"),
    ("Wikipedia", "https://en.wikipedia.org/wiki/User:{q}", "b_wiki", "#F59E0B", ("not registered", "does not have a user page")),
    ("RU Wikipedia", "https://ru.wikipedia.org/wiki/Участник:{q}", "b_wiki", "#F59E0B", ("не зарегистрирована", "нет страницы")),
    ("Fandom", "https://community.fandom.com/wiki/User:{q}", "b_fan", "#A855F7", ("no text in this page",)),
]


# ================= УТИЛИТЫ =================
def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {**default, **data} if isinstance(default, dict) and isinstance(data, dict) else data
        except Exception:
            pass
    return default


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


settings = load_json(SETTINGS_FILE, {
    "theme": "dark", "depth": 35, "github_only": False, "safe_search": True,
    "ui_lang": "ru", "search_scope": "global", "accent": "indigo", "bg_style": "classic", "eula_accepted": False
})
saved_pages = load_json(SAVED_FILE, [])
current_mode = "search"
selected_photo = {"path": ""}


def tr(key, **kwargs):
    text = TRANSLATIONS.get(settings.get("ui_lang", "ru"), TR_EN).get(key, TR_EN.get(key, key))
    return text.format(**kwargs) if kwargs else text


def get_lang_meta():
    return LANG_META.get(settings.get("ui_lang", "ru"), LANG_META["en"])


def get_accent():
    v = ACCENTS.get(settings.get("accent", "indigo"), ACCENTS["indigo"])
    return v[0], v[1]


def get_bg():
    return BG_STYLES.get(settings.get("bg_style", "classic"), BG_STYLES["classic"])


def has_cjk(text):
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]", text or ""))


def has_cyrillic(text):
    return bool(re.search(r"[а-яА-ЯёЁәіңғүұқөһєіїґ]", text or "", re.IGNORECASE))


def transliterate_cyrillic(text):
    return "".join(TRANSLIT_MAP.get(ch.lower(), ch) for ch in (text or ""))


def extract_words(text):
    return [w.lower() for w in re.findall(r"[^\W_]+", text or "", re.UNICODE) if len(w) >= 2]


def normalize_url_key(url):
    try:
        p = urlparse((url or "").lower().strip())
        return f"{p.netloc.replace('www.', '')}{p.path.rstrip('/')}"
    except Exception:
        return (url or "").lower().strip()


def is_adult_content(url="", title="", body=""):
    if not settings.get("safe_search", True):
        return False
    blob = f"{url} {title} {body}".lower()
    return any(sw in blob for sw in ADULT_STOP_WORDS)


def is_junk_page(url="", title="", body=""):
    tl, bl, ul = (title or "").lower().strip(), (body or "").lower(), (url or "").lower()
    if any(m in tl for m in JUNK_TITLES):
        return True
    if any(m in tl or m in bl for m in BOT_WALLS):
        return True
    if any(x in ul for x in ("/404", "/captcha", "/challenge", "cdn-cgi/l/chk")):
        return True
    return False


def parse_html_meta(html_text):
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        h1 = soup.h1.get_text(" ", strip=True) if soup.h1 else ""
        og_t = (soup.find("meta", property="og:title") or {}).get("content", "") or ""
        og_d = (soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"}) or {}).get("content", "") or ""
        og_u = (soup.find("meta", property="og:url") or {}).get("content", "") or ""
        can = (soup.find("link", rel="canonical") or {}).get("href", "") or ""
        return title.strip(), h1.strip(), og_t.strip(), og_d.strip(), og_u.strip(), can.strip()
    except Exception:
        return "", "", "", "", "", ""


def parse_phone_variants(raw_phone):
    digits = re.sub(r"\D", "", raw_phone or "")
    if len(digits) < 7:
        return "", "", "", []
    country, operator, norm = "Неизвестный регион", "", ("7" + digits[1:] if len(digits) == 11 and digits.startswith("8") else digits)
    for pref, cname in PHONE_PREFIXES:
        if norm.startswith(pref):
            country = cname
            break
    if len(norm) == 11 and norm.startswith("7"):
        dc = norm[1:4]
        if dc in KZ_MOBILE_DEF:
            country, operator = "Казахстан", KZ_MOBILE_DEF[dc]
        elif dc in RU_MOBILE_DEF:
            country, operator = "Россия", RU_MOBILE_DEF[dc]
    variants = [f"+{norm}", norm]
    if len(norm) == 11 and norm.startswith("7"):
        d = norm[1:]
        variants.extend([f"8{d}", f"+7 ({d[:3]}) {d[3:6]}-{d[6:8]}-{d[8:]}", f"8 ({d[:3]}) {d[3:6]}-{d[6:8]}-{d[8:]}"])
    elif len(norm) == 12 and norm.startswith("380"):
        d = norm[3:]
        variants.extend([f"0{d}", f"+380 {d[:2]} {d[2:5]} {d[5:7]} {d[7:]}"])
    return norm, country, operator, list(dict.fromkeys(variants))


# ================= ОКНО И НАВИГАЦИЯ =================
ctk.set_appearance_mode(settings.get("theme", "dark"))
app = ctk.CTk()
app.geometry("1240x790")
app.title(tr("title"))
app.grid_columnconfigure(1, weight=1)
app.grid_rowconfigure(0, weight=1)

acc_m, acc_h = get_accent()
bg_c = get_bg()
_icon_refs = {}


def apply_window_icon():
    am, _ = get_accent()
    try:
        tk_ico = ImageTk.PhotoImage(render_brand_logo(64, accent=am, bg="#111113"))
        _icon_refs["win"] = tk_ico
        app.wm_iconphoto(True, tk_ico)
        if not os.path.exists(ICON_FILE):
            ensure_icon_file(ICON_FILE, accent=am)
        if os.path.exists(ICON_FILE):
            app.iconbitmap(ICON_FILE)
    except Exception:
        pass


apply_window_icon()
app.after(260, apply_window_icon)

sidebar = ctk.CTkFrame(app, width=225, corner_radius=0, fg_color=bg_c["sidebar"])
sidebar.grid(row=0, column=0, sticky="nsew")
sidebar.grid_rowconfigure(6, weight=1)

brand_row = ctk.CTkFrame(sidebar, fg_color="transparent")
brand_row.grid(row=0, column=0, padx=14, pady=22, sticky="ew")
_sidebar_pil = render_brand_logo(64, accent=acc_m, bg="#111113")
_icon_refs["sidebar"] = ctk.CTkImage(light_image=_sidebar_pil, dark_image=_sidebar_pil, size=(34, 34))
sidebar_logo_lbl = ctk.CTkLabel(brand_row, text="", image=_icon_refs["sidebar"])
sidebar_logo_lbl.pack(side="left", padx=(4, 10))
brand_txt_col = ctk.CTkFrame(brand_row, fg_color="transparent")
brand_txt_col.pack(side="left", fill="x")
ctk.CTkLabel(brand_txt_col, text="DESCENDING", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(anchor="w")
ctk.CTkLabel(brand_txt_col, text="SCAN v2.0", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray", anchor="w").pack(anchor="w")


def update_sidebar_logo():
    am, _ = get_accent()
    pil = render_brand_logo(64, accent=am, bg="#111113")
    _icon_refs["sidebar"] = ctk.CTkImage(light_image=pil, dark_image=pil, size=(34, 34))
    sidebar_logo_lbl.configure(image=_icon_refs["sidebar"])
    apply_window_icon()


ALL_PAGES = []


def switch_page(page):
    for p in ALL_PAGES:
        if p is not page:
            p.grid_remove()
    page.grid(row=0, column=0, sticky="nsew", padx=25, pady=(20, 6))
    page.tkraise()


nav_style = {"height": 42, "corner_radius": 8, "fg_color": "transparent", "text_color": ("#111827", "#E5E7EB"), "hover_color": ("#D1D5DB", "#27272A"), "anchor": "w", "font": ctk.CTkFont(size=14)}
btn_nav_s = ctk.CTkButton(sidebar, text=tr("nav_s"), command=lambda: switch_page(page_search), **nav_style)
btn_nav_s.grid(row=1, column=0, padx=12, pady=4, sticky="ew")
btn_nav_a = ctk.CTkButton(sidebar, text=tr("nav_a"), command=lambda: [refresh_saved(), switch_page(page_saved)], **nav_style)
btn_nav_a.grid(row=2, column=0, padx=12, pady=4, sticky="ew")
btn_nav_c = ctk.CTkButton(sidebar, text=tr("nav_c"), command=lambda: switch_page(page_settings_wrap), **nav_style)
btn_nav_c.grid(row=3, column=0, padx=12, pady=4, sticky="ew")
btn_nav_d = ctk.CTkButton(sidebar, text=tr("nav_d"), command=lambda: switch_page(page_debug), **nav_style)
btn_nav_d.grid(row=4, column=0, padx=12, pady=4, sticky="ew")


def toggle_theme():
    t = "dark" if theme_switch.get() else "light"
    ctk.set_appearance_mode(t)
    settings["theme"] = t
    save_json(SETTINGS_FILE, settings)


theme_switch = ctk.CTkSwitch(sidebar, text=tr("dark"), command=toggle_theme, progress_color=acc_m)
if settings.get("theme", "dark") == "dark":
    theme_switch.select()
theme_switch.grid(row=7, column=0, padx=20, pady=20, sticky="w")

main_area = ctk.CTkFrame(app, corner_radius=0, fg_color=bg_c["main"])
main_area.grid(row=0, column=1, sticky="nsew")
main_area.grid_rowconfigure(0, weight=1)
main_area.grid_columnconfigure(0, weight=1)

page_search = ctk.CTkFrame(main_area, fg_color="transparent")
page_saved = ctk.CTkFrame(main_area, fg_color="transparent")
page_settings_wrap = ctk.CTkFrame(main_area, fg_color="transparent")
page_settings = ctk.CTkScrollableFrame(page_settings_wrap, fg_color=bg_c["main"])
page_settings.pack(fill="both", expand=True)
page_reader = ctk.CTkFrame(main_area, fg_color="transparent")
page_debug = ctk.CTkFrame(main_area, fg_color="transparent")

ALL_PAGES.extend((page_search, page_saved, page_settings_wrap, page_reader, page_debug))
for p in ALL_PAGES:
    p.grid(row=0, column=0, sticky="nsew", padx=25, pady=(20, 6))
    p.grid_remove()

footer_bar = ctk.CTkFrame(main_area, fg_color="transparent", height=22)
footer_bar.grid(row=1, column=0, sticky="ew", padx=25, pady=(0, 8))
lbl_footer_author = ctk.CTkLabel(footer_bar, text=tr("made_by"), font=ctk.CTkFont(size=11), text_color="gray", cursor="hand2")
lbl_footer_author.pack(side="right")
lbl_footer_author.bind("<Button-1>", lambda e: webbrowser.open(GITHUB_URL))

# ================= ОТЛАДКА =================
debug_top = ctk.CTkFrame(page_debug, fg_color="transparent")
debug_top.pack(fill="x", pady=(0, 12))
lbl_dbg_h = ctk.CTkLabel(debug_top, text=tr("dbg_h"), font=ctk.CTkFont(size=22, weight="bold"))
lbl_dbg_h.pack(side="left")
btn_dbg_clear = ctk.CTkButton(debug_top, text=tr("clear"), width=90, height=32, corner_radius=8, fg_color=bg_c["inactive"], text_color=("#111827", "#E5E7EB"), command=lambda: debug_textbox.delete("1.0", "end"))
btn_dbg_clear.pack(side="right", padx=(8, 0))
btn_dbg_copy = ctk.CTkButton(debug_top, text=tr("copy"), width=130, height=32, corner_radius=8, fg_color=acc_m, hover_color=acc_h, command=lambda: [app.clipboard_clear(), app.clipboard_append(debug_textbox.get("1.0", "end")), log_debug("Logs copied.")])
btn_dbg_copy.pack(side="right")
debug_textbox = ctk.CTkTextbox(page_debug, font=ctk.CTkFont(family="Consolas", size=12), wrap="word", corner_radius=10)
debug_textbox.pack(fill="both", expand=True)


def log_debug(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}" + NL
    app.after(0, lambda l=line: [debug_textbox.insert("end", l), debug_textbox.see("end")])


log_debug(f"{APP_NAME} v2.0 | Live platforms: {len(HTML_PLATFORMS) + 22}+ | WinOCR={'ON' if os.name == 'nt' else 'OFF'} | PDF={'ON' if HAS_PYPDF else 'DOCX-only'}")


# ================= ПЕРЕВОДЧИК И СЕТЕВЫЕ API =================
def translate_text(text, target_lang="ru"):
    if not text or not text.strip():
        return text
    chunks, buf = [], ""
    for line in text.split(NL):
        if len(buf) + len(line) + 1 > 1400 and buf:
            chunks.append(buf)
            buf = line
        else:
            buf = (buf + NL + line) if buf else line
    if buf:
        chunks.append(buf)
    out = []
    for chunk in chunks:
        st = chunk.strip()
        if not st or set(st) <= {"=", "-", " "} or st.startswith(("http://", "https://")):
            out.append(chunk)
            continue
        try:
            if HAS_DEEP_TRANS:
                out.append(GoogleTranslator(source="auto", target=target_lang).translate(chunk) or chunk)
            else:
                r = HTTP.get("https://translate.googleapis.com/translate_a/single", params={"client": "gtx", "sl": "auto", "tl": target_lang, "dt": "t", "q": chunk}, timeout=8)
                out.append("".join(p[0] for p in r.json()[0] if p and p[0]) if r.status_code == 200 else chunk)
        except Exception:
            out.append(chunk)
    return NL.join(out)


def ddgs_search(query_str, max_results=20, region="ru-ru", fast=False):
    safe = "moderate" if settings.get("safe_search", True) else "off"
    regs = [region] if (fast or region == "wt-wt") else [region, "wt-wt"]
    for reg in regs:
        for backend in (("auto", "html") if fast else ("auto", "html", "lite")):
            try:
                log_debug(f"DDGS [{backend} | {reg}] -> '{query_str}'")
                with DDGS() as ddgs:
                    try:
                        res = list(ddgs.text(query_str, region=reg, safesearch=safe, max_results=max_results, backend=backend))
                    except TypeError:
                        res = list(ddgs.text(query_str, region=reg, max_results=max_results))
                    if res:
                        return res
            except Exception as err:
                log_debug(f"DDGS err: {repr(err)}")
                if not fast:
                    time.sleep(0.25)
    return []


def fetch_wikipedia(query, scope="global"):
    pref = get_lang_meta()["wiki"]
    langs = (pref,) if scope == "regional" else tuple(dict.fromkeys((pref, "en", "ru")))
    alpha_q = [w for w in extract_words(query) if not w.isdigit()]
    for lang in langs:
        try:
            r = HTTP.get(f"https://{lang}.wikipedia.org/w/api.php", params={
                "action": "query", "format": "json", "generator": "search", "gsrsearch": query, "gsrlimit": 1,
                "prop": "extracts|info|langlinks", "inprop": "url", "exintro": 1, "explaintext": 1, "redirects": 1, "lllang": "en"
            }, headers={"User-Agent": "DescendingScan/2.0"}, timeout=7)
            if r.status_code != 200:
                continue
            pages = r.json().get("query", {}).get("pages", {})
            if pages:
                pg = next(iter(pages.values()))
                rt, ex, fu = pg.get("title", ""), pg.get("extract", "").strip(), pg.get("fullurl", "")
                en_t = rt if lang == "en" else next((ll.get("*", "") for ll in pg.get("langlinks", []) if ll.get("lang") == "en"), "")
                if rt and ex and fu:
                    blob = f"{rt} {en_t} {ex[:250]}".lower()
                    if alpha_q and not any((w[:-1] if len(w) > 4 else w) in blob for w in alpha_q):
                        continue
                    return {"lang": lang, "raw_title": rt, "en_title": en_t, "title": f"{rt} — Wikipedia ({lang.upper()})", "url": fu, "summary": ex}
        except Exception:
            pass
    return None


def fetch_steam_store_match(query, en_title=""):
    try:
        r = HTTP.get("https://store.steampowered.com/api/storesearch/", params={"term": en_title or query, "l": get_lang_meta()["steam"], "cc": "us"}, timeout=5)
        items = r.json().get("items", []) if r.status_code == 200 else []
        if not items:
            return None
        top = items[0]
        name, app_id = top.get("name", ""), top.get("id")
        if not name or not app_id:
            return None
        nl, nw, qw = name.lower(), extract_words(name.lower()), extract_words(query) + extract_words(en_title)
        if not any(t and (t in nl or nl in t) for t in (query.lower(), (en_title or "").lower())) and not (nw and qw and len(set(nw) & set(qw)) >= min(2, len(nw))):
            return None
        p = top.get("price")
        p_str = f"{p['final']/100:.2f} {p.get('currency', 'USD')}" if (p and "final" in p) else "Free / Store"
        return {"title": f"{name} — Steam", "href": f"https://store.steampowered.com/app/{app_id}/", "body": f"Steam AppID: {app_id} | {p_str}"}
    except Exception:
        return None


# ================= ЧИТАЛКА =================
reader_top = ctk.CTkFrame(page_reader, fg_color="transparent")
reader_top.pack(fill="x", pady=(0, 10))
reader_back_target = page_search
current_reader_doc = {"title": "", "url": "", "desc": ""}
reader_state = {"original": "", "translated": False}

btn_r_back = ctk.CTkButton(reader_top, text=tr("back"), width=85, height=34, corner_radius=8, fg_color=bg_c["inactive"], text_color=("#111827", "#E5E7EB"), command=lambda: switch_page(reader_back_target))
btn_r_back.pack(side="left")
reader_title_lbl = ctk.CTkLabel(reader_top, text="...", font=ctk.CTkFont(size=15, weight="bold"), anchor="w")
reader_title_lbl.pack(side="left", padx=12, fill="x", expand=True)


def toggle_reader_translate():
    if reader_state["translated"]:
        reader_textbox.delete("1.0", "end")
        reader_textbox.insert("1.0", reader_state["original"])
        reader_state["translated"] = False
        btn_r_tr.configure(text=tr("tr_btn"))
        return
    cur = reader_textbox.get("1.0", "end").strip()
    if not cur:
        return
    reader_state["original"] = cur
    target = settings.get("ui_lang", "ru")
    btn_r_tr.configure(state="disabled", text=tr("tr_busy"))
    threading.Thread(target=lambda: app.after(0, lambda res=translate_text(cur, target): [reader_textbox.delete("1.0", "end"), reader_textbox.insert("1.0", res), reader_state.__setitem__("translated", True), btn_r_tr.configure(state="normal", text=tr("orig_btn"))]), daemon=True).start()


def copy_reader_text():
    app.clipboard_clear()
    app.clipboard_append(reader_textbox.get("1.0", "end"))
    btn_r_copy.configure(text=tr("copied"))
    app.after(1500, lambda: btn_r_copy.configure(text=tr("copy")))


def save_current_reader():
    text = reader_textbox.get("1.0", "end").strip()
    if not text or not current_reader_doc["url"]:
        return
    global saved_pages
    saved_pages = [i for i in saved_pages if i["url"] != current_reader_doc["url"]]
    saved_pages.append({"title": current_reader_doc["title"], "url": current_reader_doc["url"], "desc": current_reader_doc["desc"], "full_text": text})
    save_json(SAVED_FILE, saved_pages)
    btn_r_save.configure(text=tr("archived"))
    app.after(1500, lambda: btn_r_save.configure(text=tr("arch")))


btn_r_copy = ctk.CTkButton(reader_top, text=tr("copy"), width=108, height=34, corner_radius=8, fg_color=bg_c["inactive"], text_color=("#111827", "#E5E7EB"), command=copy_reader_text)
btn_r_copy.pack(side="right", padx=(5, 0))
btn_r_save = ctk.CTkButton(reader_top, text=tr("arch"), width=105, height=34, corner_radius=8, fg_color=acc_m, hover_color=acc_h, command=save_current_reader)
btn_r_save.pack(side="right", padx=5)
btn_r_tr = ctk.CTkButton(reader_top, text=tr("tr_btn"), width=120, height=34, corner_radius=8, fg_color="#0EA5E9", hover_color="#0284C7", command=toggle_reader_translate)
btn_r_tr.pack(side="right", padx=5)
reader_textbox = ctk.CTkTextbox(page_reader, font=ctk.CTkFont(size=14), wrap="word", corner_radius=10)
reader_textbox.pack(fill="both", expand=True)


def open_reader(title, url, from_page, cached_text=None):
    global reader_back_target, current_reader_doc
    reader_back_target = from_page
    reader_state["original"], reader_state["translated"] = "", False
    btn_r_tr.configure(text=tr("tr_btn"), state="normal")
    current_reader_doc = {"title": title, "url": url, "desc": f"{tr('r_src')}: {url}"}
    reader_title_lbl.configure(text=title[:58])
    reader_textbox.delete("1.0", "end")
    switch_page(page_reader)
    header = f"{tr('r_src')}: {url}" + NL + ("=" * 60) + NL + NL
    if cached_text or url.startswith(("osint://", "viber://", "skype:")):
        reader_textbox.insert("1.0", header + (cached_text or title))
        return
    reader_textbox.insert("1.0", tr("r_load"))

    def worker():
        try:
            dl = trafilatura.fetch_url(url)
            txt = (trafilatura.extract(dl) if dl else None) or tr("r_fail")
            app.after(0, lambda t=txt: [reader_textbox.delete("1.0", "end"), reader_textbox.insert("1.0", header + t)])
        except Exception as e:
            app.after(0, lambda m=str(e): reader_textbox.insert("end", NL + NL + f"Error: {m}"))

    threading.Thread(target=worker, daemon=True).start()


# ================= ЦЕНТР ПОИСКА И OSINT-АНКЕТА =================
lbl_hub = ctk.CTkLabel(page_search, text=tr("hub"), font=ctk.CTkFont(size=22, weight="bold"))
lbl_hub.pack(anchor="w", pady=(0, 8))

mode_bar = ctk.CTkFrame(page_search, fg_color="transparent")
mode_bar.pack(fill="x", pady=(0, 10))
mode_buttons = {}
for mk, tk_key in (("search", "m_search"), ("profile", "m_profile")):
    b = ctk.CTkButton(mode_bar, text=tr(tk_key), height=38, corner_radius=8, font=ctk.CTkFont(size=13, weight="bold"), command=lambda k=mk: set_search_mode(k))
    b.pack(side="left", padx=(0, 8))
    mode_buttons[mk] = b

top_bar = ctk.CTkFrame(page_search, fg_color="transparent")
top_bar.pack(fill="x", pady=(0, 6))
search_entry = ctk.CTkEntry(top_bar, placeholder_text=tr("ph_search"), height=44, corner_radius=10, border_color=acc_m)
search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
search_entry.bind("<Return>", lambda e: run_active_mode())
go_btn = ctk.CTkButton(top_bar, text=tr("go"), width=130, height=44, corner_radius=10, fg_color=acc_m, hover_color=acc_h, font=ctk.CTkFont(size=14, weight="bold"), command=lambda: run_active_mode())
go_btn.pack(side="right")

profile_form = ctk.CTkFrame(page_search, corner_radius=12, fg_color=bg_c["card"])
for col_i in (0, 1, 2):
    profile_form.grid_columnconfigure(col_i, weight=1)

form_labels, form_entries = {}, {}
for key, r_idx, c_idx in (("nick", 0, 0), ("email", 0, 1), ("fio", 0, 2), ("phone", 2, 0), ("ip", 2, 1), ("hw", 2, 2)):
    lbl = ctk.CTkLabel(profile_form, text=tr(f"lbl_{key}"), font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
    lbl.grid(row=r_idx, column=c_idx, padx=10, pady=(8, 2), sticky="w")
    ent = ctk.CTkEntry(profile_form, placeholder_text=tr(f"ph_{key}"), height=34, corner_radius=8, border_color=acc_m)
    ent.grid(row=r_idx + 1, column=c_idx, padx=10, pady=(0, 6), sticky="ew")
    ent.bind("<Return>", lambda e: run_active_mode())
    form_labels[key], form_entries[key] = lbl, ent

form_actions = ctk.CTkFrame(profile_form, fg_color="transparent")
form_actions.grid(row=4, column=0, columnspan=3, padx=10, pady=(4, 10), sticky="ew")


def pick_photo_file():
    path = filedialog.askopenfilename(title="Select Photo or Document", filetypes=[("Images & Docs", "*.jpg *.jpeg *.png *.webp *.bmp *.tiff *.docx *.pdf"), ("All files", "*.*")])
    if path:
        selected_photo["path"] = path
        lbl_photo_name.configure(text=f"📎 {os.path.basename(path)[:42]}", text_color="#10B981")


btn_pick_photo = ctk.CTkButton(form_actions, text=tr("btn_photo"), width=205, height=34, corner_radius=8, fg_color=bg_c["inactive"], text_color=("#111827", "#E5E7EB"), command=pick_photo_file)
btn_pick_photo.pack(side="left")
lbl_photo_name = ctk.CTkLabel(form_actions, text=tr("photo_none"), font=ctk.CTkFont(size=11), text_color="gray", anchor="w")
lbl_photo_name.pack(side="left", padx=10, fill="x", expand=True)


def clear_profile_form():
    for ent in form_entries.values():
        ent.delete(0, "end")
    selected_photo["path"] = ""
    lbl_photo_name.configure(text=tr("photo_none"), text_color="gray")
    form_entries["nick"].focus_set()


btn_prof_clear = ctk.CTkButton(form_actions, text=tr("clear"), width=90, height=34, corner_radius=8, fg_color=bg_c["inactive"], text_color=("#111827", "#E5E7EB"), command=clear_profile_form)
btn_prof_clear.pack(side="right", padx=(8, 0))
profile_go_btn = ctk.CTkButton(form_actions, text=tr("go"), width=135, height=34, corner_radius=8, fg_color=acc_m, hover_color=acc_h, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: run_active_mode())
profile_go_btn.pack(side="right")

status_row = ctk.CTkFrame(page_search, fg_color="transparent")
status_row.pack(fill="x", pady=(2, 6))
status_label = ctk.CTkLabel(status_row, text=tr("st_ready"), text_color="gray", font=ctk.CTkFont(size=12), anchor="w")
status_label.pack(side="left", fill="x", expand=True)

last_rendered_cards = []


def export_html_report():
    if not last_rendered_cards:
        return
    fname = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    rows = []
    for c in last_rendered_cards:
        u = html_lib.escape(c["url"])
        link = f'<a href="{u}" target="_blank">{u}</a>' if c["url"].startswith("http") else f'<span>{u}</span>'
        rows.append(f'<div class="card"><div class="hdr"><b>{html_lib.escape(c["title"])}</b><span class="badge" style="color:{c["badge_color"]}">{html_lib.escape(c["badge"])}</span></div><div class="url">{link}</div><p>{html_lib.escape(c["desc"]).replace(NL, "<br>")}</p></div>')
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>{APP_NAME} Report</title><style>
    body{{background:#0d0d10;color:#e5e7eb;font-family:Segoe UI,sans-serif;max-width:960px;margin:30px auto;padding:0 16px}}
    .card{{background:#18181d;border:1px solid #27272f;border-radius:10px;padding:14px 18px;margin:10px 0}}
    .hdr{{display:flex;justify-content:space-between;gap:12px;font-size:15px}}.badge{{font-size:12px;font-weight:700}}
    .url{{margin:4px 0 8px;font-size:12px;word-break:break-all}}a{{color:#818cf8;text-decoration:none}}p{{margin:0;color:#cbd5e1;font-size:13px;line-height:1.45}}
    </style></head><body><h2>{APP_NAME} — Report ({datetime.now().strftime('%Y-%m-%d %H:%M')})</h2>{"".join(rows)}</body></html>"""
    with open(fname, "w", encoding="utf-8") as f:
        f.write(doc)
    webbrowser.open(f"file://{os.path.abspath(fname)}")
    status_label.configure(text=tr("st_exp", f=fname))


def translate_visible_cards():
    if not last_rendered_cards:
        return
    target = settings.get("ui_lang", "ru")
    btn_tr_cards.configure(state="disabled", text=tr("tr_busy"))
    snap = list(last_rendered_cards)

    def worker():
        out = [{**c, "title": translate_text(c["title"], target), "desc": translate_text(c["desc"], target)} for c in snap]
        app.after(0, lambda: [last_rendered_cards.clear(), last_rendered_cards.extend(out), rerender_search_cards(), btn_tr_cards.configure(state="normal", text=tr("tr_cards"))])

    threading.Thread(target=worker, daemon=True).start()


btn_exp_html = ctk.CTkButton(status_row, text=tr("exp_html"), width=90, height=26, corner_radius=6, fg_color=bg_c["inactive"], text_color=("#111827", "#E5E7EB"), font=ctk.CTkFont(size=12), command=export_html_report)
btn_exp_html.pack(side="right", padx=(6, 0))
btn_tr_cards = ctk.CTkButton(status_row, text=tr("tr_cards"), width=130, height=26, corner_radius=6, fg_color=bg_c["inactive"], text_color=("#111827", "#E5E7EB"), font=ctk.CTkFont(size=12), command=translate_visible_cards)
btn_tr_cards.pack(side="right")

results_box = ctk.CTkScrollableFrame(page_search, corner_radius=10, fg_color=bg_c["box"])
results_box.pack(fill="both", expand=True)


def set_search_mode(mode_key):
    global current_mode
    current_mode = mode_key
    am, ah = get_accent()
    bg_i = get_bg()["inactive"]
    for k, btn in mode_buttons.items():
        btn.configure(fg_color=am if k == current_mode else bg_i, hover_color=ah if k == current_mode else ("#D1D5DB", "#3F3F46"), text_color="#FFFFFF" if k == current_mode else ("#111827", "#E5E7EB"))
    if current_mode == "profile":
        top_bar.pack_forget()
        profile_form.pack_forget()
        profile_form.pack(fill="x", pady=(0, 8), before=status_row)
        form_entries["nick"].focus_set()
    else:
        profile_form.pack_forget()
        top_bar.pack_forget()
        top_bar.pack(fill="x", pady=(0, 6), before=status_row)
        search_entry.configure(placeholder_text=tr("ph_search"))
        search_entry.focus_set()


set_search_mode("search")


def set_busy(busy):
    s = "disabled" if busy else "normal"
    app.after(0, lambda st=s: [go_btn.configure(state=st), profile_go_btn.configure(state=st)])


def save_item(title, url, desc, cached_text=None):
    if any(i["url"] == url for i in saved_pages):
        status_label.configure(text=tr("st_dup"))
        return
    status_label.configure(text=tr("st_saving"))

    def bg():
        try:
            ft = (cached_text or desc) if (cached_text or url.startswith(("osint://", "viber://", "skype:"))) else ((trafilatura.extract(trafilatura.fetch_url(url)) if url else None) or desc)
            saved_pages.append({"title": title, "url": url, "desc": desc, "full_text": ft})
            save_json(SAVED_FILE, saved_pages)
            app.after(0, lambda t=title: status_label.configure(text=tr("st_saved", t=t[:45])))
        except Exception as e:
            app.after(0, lambda m=str(e): status_label.configure(text=tr("st_err", err=m)))

    threading.Thread(target=bg, daemon=True).start()


def delete_saved(url):
    global saved_pages
    saved_pages = [i for i in saved_pages if i["url"] != url]
    save_json(SAVED_FILE, saved_pages)
    refresh_saved()


def create_card(parent, title, url, desc, badge="", badge_color="#10B981", show_save=True, show_delete=False, cached_text=None, current_page=page_search):
    am, ah = get_accent()
    bg = get_bg()
    card = ctk.CTkFrame(parent, corner_radius=10, fg_color=bg["card"])
    card.pack(fill="x", pady=6, padx=6)
    hdr = ctk.CTkFrame(card, fg_color="transparent")
    hdr.pack(fill="x", padx=14, pady=(10, 4))
    ctk.CTkLabel(hdr, text=title, font=ctk.CTkFont(size=15, weight="bold"), anchor="w").pack(side="left", fill="x", expand=True)
    if badge:
        ctk.CTkLabel(hdr, text=badge, font=ctk.CTkFont(size=11, weight="bold"), text_color=badge_color).pack(side="right", padx=10)
    ctk.CTkLabel(card, text=url, font=ctk.CTkFont(size=12), text_color=am, anchor="w").pack(fill="x", padx=14)
    ctk.CTkLabel(card, text=desc, font=ctk.CTkFont(size=13), wraplength=860, justify="left", anchor="w").pack(fill="x", padx=14, pady=6)
    row = ctk.CTkFrame(card, fg_color="transparent")
    row.pack(fill="x", padx=14, pady=(4, 10))
    if not url.startswith("osint://"):
        ctk.CTkButton(row, text=tr("browser"), width=95, height=28, corner_radius=6, fg_color=bg["inactive"], text_color=("#111827", "#E5E7EB"), command=lambda u=url: webbrowser.open(u)).pack(side="right", padx=5)
    ctk.CTkButton(row, text=tr("read"), width=95, height=28, corner_radius=6, fg_color=bg["inactive"], text_color=("#111827", "#E5E7EB"), command=lambda t=title, u=url, p=current_page, c=cached_text or (desc if url.startswith(("osint://", "viber://", "skype:")) else None): open_reader(t, u, p, c)).pack(side="right", padx=5)
    if show_save:
        ctk.CTkButton(row, text=tr("save"), width=105, height=28, corner_radius=6, fg_color=am, hover_color=ah, command=lambda t=title, u=url, d=desc, c=cached_text: save_item(t, u, d, c)).pack(side="right", padx=5)
    if show_delete:
        ctk.CTkButton(row, text=tr("delete"), width=95, height=28, corner_radius=6, fg_color="#DC2626", hover_color="#B91C1C", command=lambda u=url: delete_saved(u)).pack(side="right", padx=5)


def rerender_search_cards():
    for w in results_box.winfo_children():
        w.destroy()
    for c in last_rendered_cards:
        create_card(results_box, c["title"], c["url"], c["desc"], badge=c["badge"], badge_color=c["badge_color"], cached_text=c.get("cached"), current_page=page_search)


# ================= КЛАССИФИКАТОР И ЧИСТЫЙ ПОИСК САЙТОВ =================
def classify_source(url, title=""):
    dom, low_t = urlparse((url or "").lower()).netloc.replace("www.", ""), (title or "").lower()
    rules = [
        (("wikipedia.org",), "b_wiki", "#F59E0B", 40),
        (("steampowered.com", "steamcommunity.com"), "b_steam", "#0EA5E9", 72),
        (("fandom.com", "wiki.gg", "paradoxwikis.com", "liquipedia.net", "gamepedia.com", "fextralife.com", ".wiki"), "b_fan", "#A855F7", 65),
        (("github.com", "gitlab.com", "bitbucket.org", "pypi.org", "npmjs.com", "huggingface.co", "docker.com"), "b_code", "#10B981", 74),
        (("epicgames.com", "gog.com", "itch.io", "nexusmods.com", "curseforge.com", "modrinth.com", "roblox.com", "riotgames.com"), "b_store", "#EC4899", 60),
        (("spotify.com", "soundcloud.com", "music.yandex.", "bandcamp.com", "last.fm", "genius.com"), "b_mus", "#F43F5E", 55),
        (("reddit.com", "4pda.", "habr.com", "stackoverflow.com", "pikabu.ru", "dtf.ru", "stopgame.ru", "playground.ru"), "b_for", "#14B8A6", 55),
        (("youtube.com", "youtu.be", "twitch.tv", "vkvideo.ru", "kick.com", "vimeo.com"), "b_vid", "#EF4444", 36),
        (("vk.com", "t.me", "telegram.org", "x.com", "twitter.com", "instagram.com", "tiktok.com", "bsky.app", "ok.ru", "linkedin.com"), "b_soc", "#38BDF8", 40),
    ]
    for doms, bk, col, sc in rules:
        if any(d in dom for d in doms) or (bk == "b_fan" and "fandom" in low_t):
            return tr(bk), col, sc
    return tr("b_art"), "#9CA3AF", 15


def is_relevant_item(url, title, body, query, stems, raw_words):
    if is_adult_content(url, title, body) or is_junk_page(url, title, body) or (not has_cjk(query) and has_cjk(title + " " + body)):
        return False
    blob = f"{url} {title} {body}".lower()
    alpha = [s for s in stems if not s.isdigit()]
    return any(st in blob for st in alpha) if alpha else any(re.search(rf"(?<!\d){re.escape(w)}(?!\d)", blob) for w in raw_words)


def sort_and_tag_results(raw_results, query, wiki_data=None, steam_card=None):
    q_words = extract_words(query) or [query.lower().strip()]
    w_words = (extract_words(wiki_data.get("raw_title", "")) + extract_words(wiki_data.get("en_title", ""))) if wiki_data else []
    all_words = list(dict.fromkeys(q_words + w_words))
    stems = [w[:-1] if (len(w) > 4 and not w.isdigit()) else w for w in all_words]
    alpha_stems = [s for s in stems if not s.isdigit()] or stems
    clean_q = {"".join(q_words)} | ({"".join(extract_words(wiki_data.get("en_title", ""))), "".join(extract_words(wiki_data.get("raw_title", "")))} if wiki_data else set())
    clean_q.discard("")

    non_off = ("wikipedia.org", "fandom.com", "wiki.gg", "reddit.com", "habr.com", "4pda.", "pikabu.ru", "dtf.ru", "stackoverflow.com", "youtube.com", "youtu.be", "twitch.tv")
    seen, dom_cnt, unique = set(), {}, []
    for item in ([steam_card] if steam_card else []) + list(raw_results):
        url = item.get("href", "")
        if not url:
            continue
        dom, key = urlparse(url.lower()).netloc.replace("www.", ""), normalize_url_key(url)
        if any(b in dom for b in GARBAGE_DOMAINS) or key in seen:
            continue
        if item is not steam_card and not is_relevant_item(url, item.get("title", ""), item.get("body", ""), query, stems, q_words):
            continue
        if dom_cnt.get(dom, 0) >= (3 if any(k in dom for k in ("github.com", "steampowered.com", "reddit.com")) else 2):
            continue
        seen.add(key)
        dom_cnt[dom] = dom_cnt.get(dom, 0) + 1
        unique.append(item)

    wiki_card = {"title": wiki_data["title"], "href": wiki_data["url"], "body": wiki_data["summary"][:330] + ("..." if len(wiki_data["summary"]) > 330 else "")} if wiki_data else next((it for it in unique if "wikipedia.org" in urlparse(it.get("href", "").lower()).netloc), None)
    wiki_key = normalize_url_key(wiki_card.get("href", "")) if wiki_card else ""

    off_card, best_off = None, 55
    for idx, it in enumerate(unique):
        url = it.get("href", "")
        if normalize_url_key(url) == wiki_key:
            continue
        p = urlparse(url.lower())
        dom, path = p.netloc.replace("www.", ""), p.path.strip("/")
        base, title = (dom.split(".")[0] if dom else ""), it.get("title", "").lower()
        if any(d in dom for d in non_off) and not (base and (base in all_words or base in clean_q)):
            continue
        dom_hit = any(w in dom for w in all_words if not w.isdigit()) or (base in clean_q)
        t_hit = any(st in title for st in alpha_stems)
        if not (dom_hit or t_hit):
            continue
        sc = 150 if base in clean_q or base in all_words else (80 if dom_hit else (65 if "steampowered.com" in dom and t_hit else (60 if t_hit and ("официальн" in title or "official" in title) else 0)))
        sc += (40 if dom_hit else 10) if (not path or path in ("ru", "en", "de", "uk", "pl", "fr", "fi", "kk", "index.html", "home")) else 0
        sc += (20 - idx * 5) if (idx < 3 and dom_hit) else 0
        if sc > best_off:
            best_off, off_card = sc, it

    off_key = normalize_url_key(off_card.get("href", "")) if off_card else ""
    final = ([(tr("b_off"), "#3B82F6", off_card)] if off_card else []) + ([(tr("b_wiki"), "#F59E0B", wiki_card)] if wiki_card else [])
    rest, ui_lang = [], settings.get("ui_lang", "ru")
    for it in unique:
        url = it.get("href", "")
        key = normalize_url_key(url)
        if key in (off_key, wiki_key) or ("wikipedia.org" in urlparse(url.lower()).netloc and wiki_card):
            continue
        title, body = it.get("title", ""), it.get("body", "")
        badge, col, sc = classify_source(url, title)
        if ui_lang in ("ru", "uk", "kk") and has_cyrillic(title + " " + body):
            sc += 18
        lt, lb, lu = title.lower(), body.lower(), url.lower()
        sc += sum((16 if st in lt else 0) + (10 if st in lu else 0) + (5 if st in lb else 0) for st in alpha_stems)
        rest.append((sc, badge, col, it))
    rest.sort(key=lambda x: x[0], reverse=True)
    return final + [(b, c, it) for _, b, c, it in rest]


def perform_search(query):
    try:
        set_busy(True)
        gh_only, depth, scope, meta = settings.get("github_only", False), settings.get("depth", 35), settings.get("search_scope", "global"), get_lang_meta()
        app.after(0, lambda q=query, s=tr("sc_reg") if scope == "regional" else tr("sc_glob"): status_label.configure(text=tr("st_scan", q=q, scope=s)))
        wiki = None if gh_only else fetch_wikipedia(query, scope=scope)
        en_name = wiki.get("en_title", "") if wiki else ""
        steam = None if gh_only else fetch_steam_store_match(query, en_title=en_name)
        wrap = lambda q: f"{q} site:github.com OR site:reddit.com OR site:habr.com" if gh_only else q
        raw = []
        if scope == "regional":
            raw.extend(ddgs_search(wrap(query), max_results=depth, region=meta["region"]))
        else:
            half = max(16, int(depth * 0.6))
            raw.extend(ddgs_search(wrap(query), max_results=half, region=meta["region"]))
            en_q = en_name if (has_cyrillic(query) and en_name) else ("" if has_cyrillic(query) else query)
            if en_q and meta["region"] != "us-en":
                time.sleep(0.3)
                raw.extend(ddgs_search(wrap(en_q), max_results=max(12, depth - half), region="us-en"))

        ordered = sort_and_tag_results(raw, query, wiki_data=wiki, steam_card=steam)

        def render(items=ordered):
            last_rendered_cards.clear()
            if not items:
                rerender_search_cards()
                status_label.configure(text=tr("st_none"))
                return
            last_rendered_cards.extend({"title": it.get("title") or "Untitled", "url": it.get("href", ""), "desc": it.get("body") or "", "badge": b, "badge_color": col} for b, col, it in items)
            rerender_search_cards()
            status_label.configure(text=tr("st_done", n=len(items)))

        app.after(0, render)
    except Exception as e:
        log_debug("SEARCH ERR:" + NL + traceback.format_exc())
        app.after(0, lambda m=str(e): status_label.configure(text=tr("st_err", err=m)))
    finally:
        set_busy(False)


# ================= OSINT МОДУЛИ v2.0 (ДАТЫ, БАНЫ, SNOWFLAKE, STEAM XML, OCR) =================
def fetch_roblox_full(usernames, source_tag=""):
    hits = []
    try:
        r = HTTP.post("https://users.roblox.com/v1/usernames/users", json={"usernames": usernames[:25], "excludeBannedUsers": False}, timeout=6)
        if r.status_code != 200:
            return hits
        for u in r.json().get("data", []):
            uid, uname, disp = u.get("id"), u.get("name", ""), u.get("displayName", "")
            created, banned, bio, ver = "?", False, "", False
            try:
                r2 = HTTP.get(f"https://users.roblox.com/v1/users/{uid}", timeout=5)
                if r2.status_code == 200:
                    d2 = r2.json()
                    created = str(d2.get("created", "?"))[:10]
                    banned = bool(d2.get("isBanned", False))
                    ver = bool(d2.get("hasVerifiedBadge", False))
                    bio = (d2.get("description") or "").strip()[:160]
            except Exception:
                pass
            st_txt = "🚨 БАН" if banned else "✅ Активен"
            ver_txt = " ☑️Verified" if ver else ""
            src_txt = f" | {source_tag}" if source_tag else ""
            body = f"ID: {uid} | Создан: {created} | Статус: {st_txt}{ver_txt}{src_txt}" + (f"{NL}О себе: {bio}" if bio else "")
            hits.append((tr("b_alert") if banned else tr("b_gprof"), "#EF4444" if banned else "#0EA5E9", {
                "title": f"Roblox — {disp or uname} (@{uname}){' [BANNED]' if banned else ''}",
                "href": f"https://www.roblox.com/users/{uid}/profile",
                "body": body
            }))
    except Exception:
        pass
    return hits


def check_steam_xml(target):
    is_id64 = bool(re.fullmatch(r"7656119\d{10}", target))
    url = f"https://steamcommunity.com/profiles/{target}/?xml=1" if is_id64 else f"https://steamcommunity.com/id/{quote(target)}/?xml=1"
    try:
        r = HTTP.get(url, timeout=6)
        if r.status_code != 200 or "<steamID64>" not in r.text:
            return None
        root = ET.fromstring(r.content)
        g = lambda tag: (root.findtext(tag) or "").strip()
        sid64, sname = g("steamID64"), g("steamID") or target
        if not sid64:
            return None
        created = g("memberSince") or "скрыта"
        vac, trade = g("vacBanned") == "1", g("tradeBanState")
        loc, state = g("location"), g("onlineState")
        banned = vac or (trade and trade.lower() != "none")
        ban_txt = f"🚨 VAC={int(vac)}, Trade={trade}" if banned else "✅ Чист (без VAC)"
        body = f"SteamID64: {sid64} | Создан: {created} | {ban_txt}" + (f" | {loc}" if loc else "") + (f" | {state}" if state else "")
        return (tr("b_alert") if banned else tr("b_steam"), "#EF4444" if banned else "#0EA5E9", {
            "title": f"Steam — {sname}" + (" [VAC/BAN]" if banned else ""),
            "href": f"https://steamcommunity.com/profiles/{sid64}",
            "body": body
        })
    except Exception:
        return None


def decode_discord_snowflake(raw_id):
    if not re.fullmatch(r"\d{17,20}", raw_id) or raw_id.startswith("7656119"):
        return None
    try:
        ms = (int(raw_id) >> 22) + 1420070400000
        dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
        if dt.year < 2015 or dt.year > 2030:
            return None
        age = (datetime.now(timezone.utc) - dt).days
        return (tr("b_disc"), "#8B5CF6", {
            "title": f"Discord Snowflake ID: {raw_id}",
            "href": f"https://discord.com/users/{raw_id}",
            "body": f"Точная дата создания: {dt.strftime('%Y-%m-%d %H:%M:%S')} UTC{NL}Возраст аккаунта/сервера: {age} дн."
        })
    except Exception:
        return None


def check_api_profiles(nick):
    q, hits = quote(nick), []
    disc = decode_discord_snowflake(nick)
    if disc:
        hits.append(disc)

    def api_github():
        r = HTTP.get(f"https://api.github.com/users/{q}", headers={"Accept": "application/vnd.github+json"}, timeout=6)
        if r.status_code == 200:
            u = r.json()
            created = str(u.get("created_at") or "?")[:10]
            loc = f" | {u['location']}" if u.get("location") else ""
            hits.append((tr("b_api"), "#10B981", {"title": f"GitHub — {u.get('name') or u.get('login', nick)} (@{u.get('login', nick)})", "href": u.get("html_url", f"https://github.com/{nick}"), "body": f"Создан: {created} | Repos: {u.get('public_repos', 0)} | Followers: {u.get('followers', 0)}{loc} | {u.get('bio') or ''}"}))
            r2 = HTTP.get(f"https://api.github.com/users/{q}/repos", params={"sort": "updated", "per_page": 4}, timeout=6)
            if r2.status_code == 200:
                for rp in r2.json():
                    hits.append((tr("b_repo"), "#3B82F6", {"title": f"GitHub Repo: {rp.get('full_name', '')} (★ {rp.get('stargazers_count', 0)} | {rp.get('language') or 'Code'})", "href": rp.get("html_url", ""), "body": rp.get("description") or "GitHub repository"}))

    def api_roblox():
        hits.extend(fetch_roblox_full([nick]))

    def api_steam():
        st = check_steam_xml(nick)
        if st:
            hits.append(st)

    def api_reddit():
        r = HTTP.get(f"https://www.reddit.com/user/{q}/about.json", headers={"User-Agent": "DescendingScan/2.0"}, timeout=6)
        if r.status_code == 200:
            d = r.json().get("data", {})
            if d.get("name"):
                susp = bool(d.get("is_suspended"))
                c_utc = d.get("created_utc")
                c_str = datetime.fromtimestamp(c_utc, tz=timezone.utc).strftime("%Y-%m-%d") if c_utc else "?"
                hits.append((tr("b_alert") if susp else tr("b_api"), "#EF4444" if susp else "#F97316", {
                    "title": f"Reddit — u/{d['name']}" + (" [SUSPENDED]" if susp else ""),
                    "href": f"https://www.reddit.com/user/{d['name']}",
                    "body": f"Создан: {c_str} | Статус: {'🚨 Заблокирован' if susp else '✅ Активен'} | Karma: {d.get('total_karma', 0)}"
                }))

    def api_dota():
        r = HTTP.get("https://api.opendota.com/api/search", params={"q": nick}, timeout=6)
        if r.status_code == 200:
            pl, low = r.json(), nick.lower()
            exact = [p for p in pl if (p.get("personaname") or "").lower() == low]
            for p in (exact[:2] if exact else [p for p in pl if low in (p.get("personaname") or "").lower()][:1]):
                hits.append((tr("b_gprof"), "#EF4444", {"title": f"Dota 2 — {p.get('personaname', nick)}", "href": f"https://www.dotabuff.com/players/{p.get('account_id')}", "body": f"Account ID: {p.get('account_id')} | Last match: {str(p.get('last_match_time') or '?')[:10]}"}))

    def api_telegram():
        url = f"https://t.me/{q}"
        r = HTTP.get(url, timeout=6)
        if r.status_code == 200 and "tgme_page_title" in r.text:
            soup = BeautifulSoup(r.text, "html.parser")
            et, ed, ee = soup.select_one(".tgme_page_title"), soup.select_one(".tgme_page_description"), soup.select_one(".tgme_page_extra")
            if et and (ed or ee):
                hits.append((tr("b_api"), "#0EA5E9", {"title": f"Telegram — {et.get_text(' ', strip=True)} (@{nick})", "href": url, "body": (ed.get_text(" ", strip=True) if ed else ee.get_text(" ", strip=True))}))

    def api_misc():
        checks = [
            (f"https://api.ivr.fi/v2/twitch/user?login={q}", "Twitch", "b_gprof", "#A855F7", lambda d: (d[0].get("displayName"), f"https://www.twitch.tv/{d[0].get('login')}", f"Создан: {str(d[0].get('createdAt','?'))[:10]} | Followers: {d[0].get('followers', 0)} | {'🚨 BAN' if d[0].get('banned') else '✅ OK'}") if isinstance(d, list) and d else None),
            (f"https://kick.com/api/v1/channels/{q}", "Kick", "b_gprof", "#10B981", lambda d: (d.get("slug"), f"https://kick.com/{d.get('slug')}", f"Followers: {d.get('followers_count', 0)}") if d.get("slug") else None),
            (f"https://api.faceit.com/users/v1/nicknames/{q}", "FACEIT", "b_gprof", "#F97316", lambda d: (d["payload"]["nickname"], f"https://www.faceit.com/en/players/{d['payload']['nickname']}", f"Country: {d['payload'].get('country', '?')}") if d.get("payload", {}).get("nickname") else None),
            (f"https://api.mojang.com/users/profiles/minecraft/{q}", "Minecraft", "b_gprof", "#10B981", lambda d: (d.get("name"), f"https://namemc.com/profile/{d.get('name')}", f"UUID: {d.get('id')}") if d.get("id") else None),
            (f"https://gitlab.com/api/v4/users?username={q}", "GitLab", "b_repo", "#10B981", lambda d: (d[0].get("name") or d[0].get("username"), d[0].get("web_url"), f"State: {d[0].get('state')}") if isinstance(d, list) and d else None),
            (f"https://api.chess.com/pub/player/{q.lower()}", "Chess.com", "b_gprof", "#10B981", lambda d: (d.get("username"), d.get("url"), f"Status: {d.get('status')}")),
            (f"https://lichess.org/api/user/{q}", "Lichess", "b_gprof", "#10B981", lambda d: (d.get("username"), d.get("url"), f"Games: {d.get('count', {}).get('all', 0)}")),
            (f"https://www.speedrun.com/api/v1/users?lookup={q}", "Speedrun.com", "b_gprof", "#F59E0B", lambda d: (d["data"][0]["names"]["international"], d["data"][0]["weblink"], f"Joined: {str(d['data'][0].get('signup','?'))[:10]}") if d.get("data") else None),
            (f"https://shikimori.one/api/users/{q}", "Shikimori", "b_api", "#EC4899", lambda d: (d.get("nickname"), d.get("url") or f"https://shikimori.one/{nick}", "Shikimori") if d.get("nickname") else None),
            (f"https://api.modrinth.com/v2/user/{q}", "Modrinth", "b_gprof", "#10B981", lambda d: (d.get("username"), f"https://modrinth.com/user/{d.get('username')}", f"Created: {str(d.get('created','?'))[:10]} | {d.get('bio') or 'Modrinth'}") if d.get("username") else None),
            (f"https://www.codewars.com/api/v1/users/{q}", "Codewars", "b_repo", "#EF4444", lambda d: (d.get("username"), f"https://www.codewars.com/users/{d.get('username')}", f"Honor: {d.get('honor', 0)}") if d.get("username") else None),
            (f"https://hub.docker.com/v2/users/{q}/", "DockerHub", "b_repo", "#0EA5E9", lambda d: (d.get("username"), f"https://hub.docker.com/u/{d.get('username')}", f"Joined: {str(d.get('date_joined','?'))[:10]}") if d.get("username") else None),
            (f"https://huggingface.co/api/users/{q}/overview", "HuggingFace", "b_repo", "#F59E0B", lambda d: (d.get("user"), f"https://huggingface.co/{d.get('user')}", f"Models: {d.get('numModels', 0)}") if d.get("user") else None),
            (f"https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor={q}.bsky.social", "Bluesky", "b_api", "#0EA5E9", lambda d: (d.get("displayName") or d.get("handle"), f"https://bsky.app/profile/{d.get('handle')}", d.get("description") or "Bluesky") if d.get("handle") else None),
        ]
        for url, pname, bkey, col, parser in checks:
            try:
                r = HTTP.get(url, headers={"User-Agent": "DescendingScan/2.0"}, timeout=5)
                if r.status_code == 200 and r.text.strip():
                    parsed = parser(r.json())
                    if parsed and parsed[0] and parsed[1]:
                        hits.append((tr(bkey), col, {"title": f"{pname} — {parsed[0]}", "href": parsed[1], "body": str(parsed[2] or pname)}))
            except Exception:
                pass

    with ThreadPoolExecutor(max_workers=10) as pool:
        for f in as_completed([pool.submit(fn) for fn in (api_github, api_roblox, api_steam, api_reddit, api_dota, api_telegram, api_misc)]):
            try:
                f.result()
            except Exception:
                pass
    return hits


def check_html_platform(spec, nick):
    name, url_tpl, bkey, col = spec[:4]
    bad_markers = DEFAULT_404 + (spec[4] if len(spec) > 4 else ())
    url = url_tpl.format(q=quote(nick))
    try:
        r = HTTP.get(url, timeout=3.8, allow_redirects=True)
        if r.status_code != 200:
            return None
        final_u = r.url.lower()
        if any(x in final_u for x in ("/login", "/signin", "/auth", "/404", "/captcha", "error", "not-found")):
            return None
        # Редирект на корень сайта при запросе пути — верный признак заглушки
        if urlparse(url).path.strip("/") and not urlparse(r.url).path.strip("/"):
            return None
        raw_html = r.text[:120000]
        if len(raw_html) < 900:
            return None
        text_low = raw_html.lower()
        if any(bw in text_low for bw in BOT_WALLS):
            return None
        title, h1, og_t, og_d, og_u, can = parse_html_meta(raw_html)
        t_low = (og_t or title).lower()
        if not t_low or is_junk_page(r.url, t_low, og_d) or any(b in t_low or b in text_low for b in bad_markers):
            return None
        # Строгая верификация: ник обязан подтверждаться в метаданных/заголовке/URL
        n_low = nick.lower()
        n_alnum = re.sub(r"[^a-z0-9а-яё]", "", n_low)
        meta_blob = f"{title} {h1} {og_t} {og_u} {can}".lower()
        if name == "YouTube" and '"channelid"' not in text_low:
            return None
        is_sub = "{q}." in url_tpl
        if not is_sub and n_low not in meta_blob and (len(n_alnum) < 3 or n_alnum not in re.sub(r"[^a-z0-9а-яё]", "", meta_blob)):
            return None
        disp_title = og_t or title or f"{name} — {nick}"
        if name.lower() not in disp_title.lower():
            disp_title = f"{name} — {disp_title}"
        desc = og_d[:240] if (og_d and not is_junk_page("", "", og_d)) else f"Подтвержденный профиль на {name}"
        return (tr(bkey), col, {"title": disp_title[:110], "href": r.url, "body": desc})
    except Exception:
        return None


def check_email_direct(email):
    hits = []
    em = email.strip().lower()
    if "@" not in em or "." not in em.split("@")[-1]:
        return hits
    local, domain = em.split("@", 1)
    md5_h = hashlib.md5(em.encode("utf-8")).hexdigest()
    try:
        r = HTTP.get(f"https://en.gravatar.com/{md5_h}.json", timeout=6)
        if r.status_code == 200 and r.json().get("entry"):
            e = r.json()["entry"][0]
            disp = e.get("displayName") or e.get("preferredUsername") or local
            body = " | ".join(x for x in (e.get("preferredUsername", ""), e.get("currentLocation", ""), (e.get("aboutMe") or "")[:140]) if x) or f"Gravatar ({em})"
            hits.append((tr("b_email"), "#0EA5E9", {"title": f"Gravatar — {disp} ({em})", "href": e.get("profileUrl", f"https://gravatar.com/{md5_h}"), "body": body}))
            for a in e.get("accounts", [])[:5]:
                if a.get("url"):
                    hits.append((tr("b_link"), "#A855F7", {"title": f"Gravatar Linked — {urlparse(a['url']).netloc}", "href": a["url"], "body": f"Привязан к {em}"}))
    except Exception:
        pass
    try:
        r = HTTP.get("https://api.github.com/search/users", params={"q": f"{em} in:email"}, headers={"Accept": "application/vnd.github+json"}, timeout=6)
        if r.status_code == 200:
            for u in r.json().get("items", [])[:3]:
                hits.append((tr("b_email"), "#10B981", {"title": f"GitHub (профиль по email) — @{u.get('login', '')}", "href": u.get("html_url", ""), "body": f"Аккаунт GitHub для {em}"}))
    except Exception:
        pass
    try:
        r = HTTP.get("https://api.github.com/search/commits", params={"q": f"author-email:{em}", "per_page": 3}, headers={"Accept": "application/vnd.github.cloak-preview+json"}, timeout=6)
        if r.status_code == 200 and r.json().get("items"):
            for cm in r.json()["items"][:2]:
                repo = cm.get("repository", {}).get("full_name", "")
                aname = cm.get("commit", {}).get("author", {}).get("name", "")
                adate = str(cm.get("commit", {}).get("author", {}).get("date", ""))[:10]
                hits.append((tr("b_link"), "#A855F7", {"title": f"GitHub Коммит (найден по email) — {repo}", "href": cm.get("html_url", ""), "body": f"Автор в git: {aname} ({em}) | Дата: {adate}"}))
    except Exception:
        pass
    try:
        r = HTTP.get("https://www.duolingo.com/2017-06-30/users", params={"email": em}, timeout=5)
        if r.status_code == 200 and r.json().get("users"):
            u = r.json()["users"][0]
            un = u.get("username") or local
            hits.append((tr("b_email"), "#22C55E", {"title": f"Duolingo — {un}", "href": f"https://www.duolingo.com/profile/{quote(un)}", "body": f"Зарегистрирован в Duolingo (XP: {u.get('totalXp', 0)})"}))
    except Exception:
        pass
    try:
        r = HTTP.get("https://keybase.io/_/api/1.0/user/lookup.json", params={"emails": em}, timeout=5)
        them = r.json().get("them") if r.status_code == 200 else None
        if isinstance(them, list) and them and them[0] and them[0].get("basics", {}).get("username"):
            ku = them[0]["basics"]["username"]
            hits.append((tr("b_email"), "#F97316", {"title": f"Keybase — @{ku}", "href": f"https://keybase.io/{ku}", "body": f"Почта {em} привязана к Keybase"}))
    except Exception:
        pass
    try:
        r = HTTP.get(f"https://api.xposedornot.com/v1/check-email/{quote(em)}", timeout=6)
        if r.status_code == 200 and isinstance(r.json().get("breaches"), list) and r.json()["breaches"]:
            b = r.json()["breaches"]
            flat = b[0] if isinstance(b[0], list) else b
            if flat:
                hits.append((tr("b_alert"), "#EF4444", {"title": f"🚨 Утечки (XposedOrNot): {len(flat)} — {em}", "href": f"https://xposedornot.com/xposed#{quote(em)}", "body": "Базы: " + ", ".join(str(x) for x in flat[:15]) + (f" (+{len(flat) - 15})" if len(flat) > 15 else "")}))
    except Exception:
        pass
    if domain not in FREE_EMAIL_DOMAINS:
        hits.append((tr("b_email"), "#F59E0B", {"title": f"Корпоративный / личный домен: {domain}", "href": f"https://{domain}", "body": f"Почта {em} на нестандартном домене."}))
    return hits


def check_phone_direct(raw_phone):
    norm, country, operator, variants = parse_phone_variants(raw_phone)
    if not norm:
        return [], "", []
    op_line = f" | Оператор: {operator}" if operator else ""
    hits = [
        (tr("b_phone"), "#10B981", {"title": f"Анализ номера: +{norm} ({country}{op_line})", "href": f"osint://phone/{norm}", "body": f"Страна: {country}{op_line}{NL}Форматы: {', '.join(variants)}"}),
        (tr("b_phone"), "#22C55E", {"title": f"WhatsApp — +{norm}", "href": f"https://wa.me/{norm}", "body": f"Проверка профиля WhatsApp (+{norm})"}),
        (tr("b_phone"), "#0EA5E9", {"title": f"Telegram — +{norm}", "href": f"https://t.me/+{norm}", "body": f"Проверка аккаунта Telegram (+{norm})"}),
        (tr("b_phone"), "#8B5CF6", {"title": f"Viber — +{norm}", "href": f"viber://chat?number=%2B{norm}", "body": f"Открыть чат Viber (+{norm})"}),
    ]
    return hits, norm, variants


def check_ip_domain(raw_target):
    hits = []
    target = re.sub(r"^https?://", "", (raw_target or "").strip()).split("/")[0].split(":")[0].strip()
    if not target:
        return hits
    is_ip = bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", target) or ":" in target)
    ip_addr = target
    if not is_ip:
        try:
            ip_addr = socket.gethostbyname(target)
            hits.append((tr("b_ip"), "#0EA5E9", {"title": f"DNS Резолв: {target} → {ip_addr}", "href": f"https://{target}", "body": f"Домен {target} указывает на IPv4: {ip_addr}"}))
        except Exception:
            ip_addr = ""
        try:
            r = HTTP.get(f"https://rdap.org/domain/{quote(target)}", timeout=6)
            if r.status_code == 200:
                d = r.json()
                ev = {e.get("eventAction"): str(e.get("eventDate", ""))[:10] for e in d.get("events", [])}
                ns = ", ".join(n.get("ldhName", "") for n in d.get("nameservers", [])[:4] if n.get("ldhName"))
                hits.append((tr("b_ip"), "#F59E0B", {"title": f"WHOIS / RDAP: {target}", "href": f"https://who.is/whois/{quote(target)}", "body": f"Статус: {', '.join(d.get('status', [])[:3])}{NL}Создан: {ev.get('registration', '?')} | Истекает: {ev.get('expiration', '?')}{NL}NS: {ns}"}))
        except Exception:
            pass
        try:
            mx_r = HTTP.get("https://dns.google/resolve", params={"name": target, "type": "MX"}, timeout=5)
            mx_list = [a.get("data", "") for a in mx_r.json().get("Answer", [])][:4] if mx_r.status_code == 200 else []
            if mx_list:
                hits.append((tr("b_sub"), "#14B8A6", {"title": f"DNS MX (почта домена): {target}", "href": f"osint://dns/{target}", "body": "Почтовые серверы: " + " | ".join(mx_list)}))
        except Exception:
            pass
        try:
            cr = HTTP.get(f"https://crt.sh/?q=%.{quote(target)}&output=json", timeout=7)
            if cr.status_code == 200:
                subs = sorted({s.strip().lower() for row in cr.json() for s in str(row.get("name_value", "")).splitlines() if "*" not in s and target.lower() in s.lower()})
                if subs:
                    hits.append((tr("b_sub"), "#A855F7", {"title": f"Поддомены (crt.sh): найдено {len(subs)} — {target}", "href": f"https://crt.sh/?q=%.{quote(target)}", "body": ", ".join(subs[:25]) + (f" (+{len(subs)-25})" if len(subs) > 25 else "")}))
        except Exception:
            pass
        try:
            wb = HTTP.get("http://archive.org/wayback/available", params={"url": target}, timeout=5)
            snap = wb.json().get("archived_snapshots", {}).get("closest", {}) if wb.status_code == 200 else {}
            if snap.get("available") and snap.get("url"):
                ts = str(snap.get("timestamp", ""))
                dt_s = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}" if len(ts) >= 8 else ts
                hits.append((tr("b_wayback"), "#F59E0B", {"title": f"Wayback Machine: архив {target} ({dt_s})", "href": snap["url"], "body": f"Сохраненная копия сайта в интернет-архиве ({dt_s})"}))
        except Exception:
            pass
    if ip_addr:
        try:
            r = HTTP.get(f"https://ipwho.is/{quote(ip_addr)}", timeout=6)
            if r.status_code == 200 and r.json().get("success", False):
                g = r.json()
                conn, lat, lon = g.get("connection") or {}, g.get("latitude"), g.get("longitude")
                body = f"Страна: {g.get('country','?')} ({g.get('country_code','')}) | Регион: {g.get('region','?')} | Город: {g.get('city','?')}{NL}Провайдер: {conn.get('isp','?')} | Org: {conn.get('org','?')} | ASN: AS{conn.get('asn','?')}{NL}Координаты: {lat}, {lon}"
                hits.append((tr("b_ip"), "#10B981", {"title": f"GeoIP / ASN: {ip_addr} — {g.get('country','')}, {g.get('city','')}", "href": f"osint://ip/{ip_addr}", "body": body}))
                if lat is not None and lon is not None:
                    hits.append((tr("b_ip"), "#3B82F6", {"title": f"Карта провайдера: {lat}, {lon}", "href": f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=12/{lat}/{lon}", "body": f"Локация узла {conn.get('isp', ip_addr)} на OpenStreetMap"}))
        except Exception:
            pass
        hits.append((tr("b_ip"), "#A855F7", {"title": f"Shodan — порты и сервисы ({ip_addr})", "href": f"https://www.shodan.io/host/{ip_addr}", "body": f"Открытые порты и баннеры по {ip_addr}"}))
        hits.append((tr("b_ip"), "#EF4444", {"title": f"VirusTotal — репутация ({target})", "href": f"https://www.virustotal.com/gui/{'ip-address' if is_ip else 'domain'}/{quote(target)}", "body": "Проверка репутации и связанных доменов"}))
    return hits


def check_mac_hardware(raw_hw):
    hits, hw = [], (raw_hw or "").strip()
    if not hw:
        return hits, False
    clean_hex = re.sub(r"[^0-9a-fA-F]", "", hw)
    is_mac = bool(re.match(r"^([0-9a-fA-F]{2}[:-]){2,5}[0-9a-fA-F]{2}$", hw) or (len(clean_hex) in (6, 12) and re.fullmatch(r"[0-9a-fA-F]+", clean_hex)))
    if is_mac:
        oui = ":".join(clean_hex[i:i + 2].upper() for i in range(0, min(len(clean_hex), 12), 2))
        vendor = "Не найден в базе IEEE OUI"
        try:
            r = HTTP.get(f"https://api.macvendors.com/{quote(oui)}", timeout=6)
            if r.status_code == 200 and r.text.strip():
                vendor = r.text.strip()
        except Exception:
            pass
        laa = "Локальный / рандомизированный (Wi-Fi Privacy / VM)" if (int(clean_hex[:2], 16) & 2) else "Глобальный заводской (IEEE OUI)"
        hits.append((tr("b_hw"), "#10B981", {"title": f"MAC / Железо: {oui} → {vendor}", "href": f"osint://mac/{oui}", "body": f"Производитель: {vendor}{NL}Тип: {laa}{NL}OUI: {oui[:8]}"}))
        hits.append((tr("b_hw"), "#3B82F6", {"title": f"MacLookup — {oui[:8]}", "href": f"https://maclookup.app/search/result?mac={quote(oui)}", "body": f"Подробная карточка {vendor}"}))
    else:
        hits.append((tr("b_hw"), "#F59E0B", {"title": f"Железо / модель: {hw}", "href": f"osint://hw/{quote(hw)}", "body": f"Веб-поиск спецификаций и драйверов для «{hw}»."}))
    return hits, is_mac


def _dms_to_deg(dms, ref):
    try:
        d, m, s = [float(x) for x in dms]
        val = d + m / 60.0 + s / 3600.0
        return -val if ref in ("S", "W") else val
    except Exception:
        return None


def _win_ocr_image(path):
    if os.name != "nt" or not os.path.exists(path):
        return []
    ps_script = r"""
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $ErrorActionPreference = 'Stop'
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    [void][Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
    [void][Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics,ContentType=WindowsRuntime]
    [void][Windows.Media.Ocr.OcrEngine,Windows.Media,ContentType=WindowsRuntime]
    function Await($WinRtTask, $ResultType) {
        $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0].MakeGenericMethod($ResultType)
        $netTask = $asTask.Invoke($null, @($WinRtTask))
        $netTask.Wait(-1) | Out-Null
        return $netTask.Result
    }
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($env:OCR_IMG)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage((New-Object Windows.Globalization.Language("en-US"))) }
    $res = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    foreach ($line in $res.Lines) { Write-Output $line.Text }
    """
    try:
        env = {**os.environ, "OCR_IMG": os.path.abspath(path)}
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                           capture_output=True, text=True, encoding="utf-8", errors="ignore", env=env, timeout=18, creationflags=flags)
        return [ln.strip() for ln in (p.stdout or "").splitlines() if ln.strip()]
    except Exception as e:
        log_debug(f"WinOCR ERR: {repr(e)}")
        return []


def inspect_photo_or_doc(path):
    hits = []
    if not path or not os.path.exists(path):
        return hits
    fname, ext = os.path.basename(path), os.path.splitext(path)[1].lower()

    # --- 1. Документы DOCX / PDF ---
    if ext == ".docx":
        try:
            with zipfile.ZipFile(path) as zf:
                lines = [f"Документ Word: {fname} ({os.path.getsize(path)//1024} КБ)"]
                if "docProps/core.xml" in zf.namelist():
                    root = ET.fromstring(zf.read("docProps/core.xml"))
                    for el in root:
                        tag = el.tag.split("}")[-1]
                        if el.text and el.text.strip():
                            lines.append(f"{tag}: {el.text.strip()}")
                hits.append((tr("b_doc"), "#10B981", {"title": f"Метаданные DOCX: {fname}", "href": f"osint://doc/{quote(fname)}", "body": NL.join(lines)}))
        except Exception as e:
            hits.append((tr("b_doc"), "#EF4444", {"title": f"Ошибка DOCX: {fname}", "href": f"osint://doc/{quote(fname)}", "body": str(e)}))
        return hits

    if ext == ".pdf":
        if not HAS_PYPDF:
            hits.append((tr("b_doc"), "#F59E0B", {"title": f"PDF: {fname}", "href": f"osint://doc/{quote(fname)}", "body": "Для чтения метаданных PDF выполните: pip install pypdf"}))
            return hits
        try:
            meta = PdfReader(path).metadata or {}
            lines = [f"PDF: {fname} ({os.path.getsize(path)//1024} КБ)"] + [f"{str(k).lstrip('/')}: {v}" for k, v in meta.items() if v]
            hits.append((tr("b_doc"), "#10B981", {"title": f"Метаданные PDF: {fname}", "href": f"osint://doc/{quote(fname)}", "body": NL.join(lines)}))
        except Exception as e:
            hits.append((tr("b_doc"), "#EF4444", {"title": f"Ошибка PDF: {fname}", "href": f"osint://doc/{quote(fname)}", "body": str(e)}))
        return hits

    # --- 2. EXIF + GPS ---
    try:
        with Image.open(path) as img:
            lines = [f"Файл: {fname} | {os.path.getsize(path)//1024} КБ | {img.width}x{img.height} ({img.format})"]
            exif_raw = img.getexif() or {}
            if hasattr(img, "_getexif") and img._getexif():
                exif_raw = {**exif_raw, **img._getexif()}
            tags = {ExifTags.TAGS.get(k, k): v for k, v in exif_raw.items()}
            for label, tk in (("Камера", "Make"), ("Модель", "Model"), ("Софт", "Software"), ("Дата съёмки", "DateTimeOriginal"), ("Изменён", "DateTime"), ("Объектив", "LensModel")):
                if tags.get(tk):
                    lines.append(f"{label}: {str(tags[tk]).strip()}")
            gps = tags.get("GPSInfo")
            if isinstance(gps, dict):
                g = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps.items()}
                lat, lon = _dms_to_deg(g.get("GPSLatitude"), g.get("GPSLatitudeRef")), _dms_to_deg(g.get("GPSLongitude"), g.get("GPSLongitudeRef"))
                if lat is not None and lon is not None:
                    lines.append(f"GPS: {lat:.6f}, {lon:.6f}")
                    hits.append((tr("b_photo"), "#EF4444", {"title": f"📍 GPS найден в фото! ({lat:.5f}, {lon:.5f})", "href": f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}", "body": f"Точка съёмки {fname} на OpenStreetMap"}))
            if len(lines) == 1:
                lines.append("EXIF-метаданные отсутствуют или были очищены.")
            hits.append((tr("b_photo"), "#10B981", {"title": f"EXIF Анализ фото: {fname}", "href": f"osint://exif/{quote(fname)}", "body": NL.join(lines)}))
    except Exception as e:
        hits.append((tr("b_photo"), "#EF4444", {"title": f"Ошибка фото: {fname}", "href": f"osint://exif/{quote(fname)}", "body": str(e)}))

    # --- 3. Системный Windows OCR + автопробив всего, что видно на фото ---
    ocr_lines = _win_ocr_image(path)
    if ocr_lines:
        ocr_blob = NL.join(ocr_lines)
        hits.append((tr("b_ocr"), "#F59E0B", {"title": f"🔤 OCR: считано {len(ocr_lines)} строк с «{fname}»", "href": f"osint://ocr/{quote(fname)}", "body": " | ".join(ocr_lines)[:750]}))

        # 3.1 Автопробив почт со скриншота
        for em in list(dict.fromkeys(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", ocr_blob)))[:2]:
            hits.extend(check_email_direct(em))

        # 3.2 Автопробив IP со скриншота
        for ip in list(dict.fromkeys(re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", ocr_blob)))[:2]:
            if not ip.startswith(("127.", "192.168.", "10.", "0.")):
                hits.extend(check_ip_domain(ip)[:2])

        # 3.3 Автопробив @тегов (Telegram / GitHub)
        for handle in list(dict.fromkeys(re.findall(r"@([A-Za-z0-9_]{3,25})", ocr_blob)))[:4]:
            if handle.lower() not in OCR_STOP:
                r = HTTP.get(f"https://t.me/{quote(handle)}", timeout=4)
                if r.status_code == 200 and "tgme_page_title" in r.text:
                    soup = BeautifulSoup(r.text, "html.parser")
                    et = soup.select_one(".tgme_page_title")
                    ed = soup.select_one(".tgme_page_description") or soup.select_one(".tgme_page_extra")
                    if et and ed:
                        hits.append((tr("b_ocr"), "#0EA5E9", {"title": f"Telegram (с фото) — {et.get_text(' ', strip=True)} (@{handle})", "href": f"https://t.me/{handle}", "body": ed.get_text(" ", strip=True)}))

        # 3.4 Автопробив кандидатов на игровые ники в Roblox API (с датами и банами!)
        cands = []
        for chunk in ocr_lines:
            for tok in re.findall(r"[A-Za-z0-9_]{3,20}", chunk.lstrip("@")):
                if tok.lower() not in OCR_STOP and not tok.isdigit() and tok not in cands:
                    cands.append(tok)
        if cands:
            hits.extend(fetch_roblox_full(cands, source_tag=f"найден OCR на {fname}"))

    hits.extend([
        (tr("b_photo"), "#0EA5E9", {"title": "Яндекс Картинки — поиск по фото / лицу", "href": "https://yandex.ru/images/search?rpt=imageview", "body": f"Загрузите «{fname}» для визуального поиска похожих фото и профилей."}),
        (tr("b_photo"), "#3B82F6", {"title": "Google Lens — визуальный поиск", "href": "https://lens.google.com/", "body": f"Перетащите «{fname}» в Google Lens для поиска объектов и локаций."}),
        (tr("b_photo"), "#8B5CF6", {"title": "TinEye — поиск первоисточника", "href": "https://tineye.com/", "body": f"Поиск точных копий «{fname}» в сети."}),
    ])
    return hits


def perform_profile_scan(form_data):
    try:
        set_busy(True)
        nick = form_data["nick"].lstrip("@")
        email, fio, phone, ip_dom, hw, photo = form_data["email"], " ".join(form_data["fio"].split()), form_data["phone"], form_data["ip"], form_data["hw"], form_data["photo"]
        tags = [x for x in (nick, email, fio, phone, ip_dom, hw, os.path.basename(photo) if photo else "") if x]
        summary_str = ", ".join(tags)[:75]

        app.after(0, lambda s=summary_str: [last_rendered_cards.clear(), rerender_search_cards(), status_label.configure(text=tr("st_prof", q=s))])
        log_debug(f"=== OSINT v2.0 SCAN | {summary_str} ===")

        direct, mentions, seen, lock = [], [], set(), threading.Lock()
        reg = get_lang_meta()["region"]

        def add_card(target_list, entry):
            if not entry:
                return
            url = entry[2].get("href", "")
            k = normalize_url_key(url) if not url.startswith(("osint://", "viber://", "skype:")) else url
            if not k:
                return
            with lock:
                if k in seen:
                    return
                seen.add(k)
                target_list.append(entry)
            b, col, it = entry
            card = {"title": it.get("title") or summary_str, "url": url, "desc": it.get("body") or "", "badge": b, "badge_color": col, "cached": it.get("body") if url.startswith(("osint://", "viber://", "skype:")) else None}
            app.after(0, lambda c=card: [last_rendered_cards.append(c), create_card(results_box, c["title"], c["url"], c["desc"], badge=c["badge"], badge_color=c["badge_color"], cached_text=c["cached"], current_page=page_search), status_label.configure(text=f"{tr('st_prof', q=summary_str)} [{len(last_rendered_cards)}]")])

        phone_norm, phone_variants, hw_is_mac = "", [], False
        is_pure_id = bool(re.fullmatch(r"\d{16,20}", nick))
        with ThreadPoolExecutor(max_workers=40) as pool:
            f_api = pool.submit(check_api_profiles, nick) if nick else None
            f_html = [pool.submit(check_html_platform, spec, nick) for spec in HTML_PLATFORMS] if (nick and not is_pure_id) else []
            f_email = pool.submit(check_email_direct, email) if email else None
            f_ip = pool.submit(check_ip_domain, ip_dom) if ip_dom else None
            f_hw = pool.submit(check_mac_hardware, hw) if hw else None
            f_photo = pool.submit(inspect_photo_or_doc, photo) if photo else None

            if phone:
                p_hits, phone_norm, phone_variants = check_phone_direct(phone)
                for it in p_hits:
                    add_card(direct, it)
            for fut in (f_photo, f_ip, f_email, f_api):
                if fut:
                    for it in fut.result():
                        add_card(direct, it)
            if f_hw:
                hw_hits, hw_is_mac = f_hw.result()
                for it in hw_hits:
                    add_card(direct, it)
            for fh in as_completed(f_html):
                res = fh.result()
                if res:
                    add_card(direct, res)

        dork_tasks = []
        if fio and nick:
            dork_tasks.append((f'"{fio}" "{nick}"', "b_link", "#A855F7", lambda u, t, b: nick.lower() in f"{u} {t} {b}".lower(), reg, direct))
        if fio and email:
            dork_tasks.append((f'"{fio}" "{email}"', "b_link", "#A855F7", lambda u, t, b: email.lower() in f"{u} {t} {b}".lower(), reg, direct))
        if nick and email:
            dork_tasks.append((f'"{nick}" "{email}"', "b_link", "#A855F7", lambda u, t, b: email.lower() in f"{u} {t} {b}".lower() or nick.lower() in f"{u} {t} {b}".lower(), reg, direct))
        if nick and not is_pure_id:
            ln = nick.lower()
            dork_tasks.append((f'"{nick}" site:steamcommunity.com OR site:tracker.gg OR site:vk.com OR site:t.me OR site:pastebin.com', "b_ment", "#F59E0B", lambda u, t, b, x=ln: x in f"{u} {t} {b}".lower(), "wt-wt", mentions))
        if email and "@" in email:
            le = email.lower()
            dork_tasks.append((f'"{email}"', "b_email", "#0EA5E9", lambda u, t, b, x=le: x in f"{u} {t} {b}".lower(), "wt-wt", mentions))
        if phone_norm:
            tl = phone_norm[-7:]
            dork_tasks.append((f'"{phone_variants[0]}" OR "{phone_norm}"', "b_phone", "#22C55E", lambda u, t, b, x=tl: x in re.sub(r"\D", "", f"{u} {t} {b}"), reg, mentions))
        if hw and not hw_is_mac:
            lh = hw.lower()
            dork_tasks.append((f'"{hw}" specs OR driver OR motherboard OR datasheet', "b_hw", "#F59E0B", lambda u, t, b, x=lh: any(w in f"{u} {t} {b}".lower() for w in extract_words(x)), "wt-wt", mentions))
        if fio:
            wf = fetch_wikipedia(fio, scope="global")
            if wf:
                add_card(direct, (tr("b_wiki"), "#F59E0B", {"title": wf["title"], "href": wf["url"], "body": wf["summary"][:300]}))
            fs = [w[:-1] if len(w) > 4 else w for w in extract_words(fio)]
            lat = transliterate_cyrillic(fio).strip() if has_cyrillic(fio) else ""
            ls = [w[:-1] if len(w) > 4 else w for w in extract_words(lat)] if (lat and lat.lower() != fio.lower()) else []
            v_fio = lambda u, t, b, a=fs, c=ls: sum(1 for s in a if s in f"{u} {t} {b}".lower()) >= min(2, len(a)) or (bool(c) and sum(1 for s in c if s in f"{u} {t} {b}".lower()) >= min(2, len(c)))
            dork_tasks.append((f'"{fio}" site:vk.com OR site:ok.ru OR site:t.me OR site:linkedin.com OR site:rusprofile.ru', "b_fio", "#F59E0B", v_fio, reg, mentions))

        def run_dork(task):
            dq, bk, bc, val, rcode, tlist = task
            for it in ddgs_search(dq, max_results=6, region=rcode, fast=True):
                u, t, b = it.get("href", ""), it.get("title", ""), it.get("body", "")
                if not u or any(g in urlparse(u.lower()).netloc for g in GARBAGE_DOMAINS) or is_adult_content(u, t, b) or is_junk_page(u, t, b) or not val(u, t, b):
                    continue
                bl, bcol, _ = classify_source(u, t)
                fb, fc = (tr(bk), bc) if bk in ("b_link", "b_email", "b_phone", "b_fio", "b_hw") else ((tr("b_ment"), "#F59E0B") if bl == tr("b_art") else (bl, bcol))
                add_card(tlist, (fb, fc, it))

        if dork_tasks:
            with ThreadPoolExecutor(max_workers=5) as dpool:
                list(dpool.map(run_dork, dork_tasks))

        app.after(0, lambda: status_label.configure(text=tr("st_none") if not last_rendered_cards else tr("st_pdone", q=summary_str, p=len(direct), m=len(mentions))))
    except Exception as e:
        log_debug("OSINT ERR:" + NL + traceback.format_exc())
        app.after(0, lambda m=str(e): status_label.configure(text=tr("st_err", err=m)))
    finally:
        set_busy(False)


def run_active_mode():
    if current_mode == "profile":
        fd = {k: ent.get().strip() for k, ent in form_entries.items()}
        fd["photo"] = selected_photo["path"]
        if not any(fd.values()):
            status_label.configure(text=tr("st_prof_empty"))
            return
        threading.Thread(target=perform_profile_scan, args=(fd,), daemon=True).start()
        return
    q = search_entry.get().strip()
    if not q:
        status_label.configure(text=tr("st_empty"))
        return
    threading.Thread(target=perform_search, args=(q,), daemon=True).start()


# ================= СОХРАНЕННОЕ И НАСТРОЙКИ =================
lbl_saved_h = ctk.CTkLabel(page_saved, text=tr("saved_h"), font=ctk.CTkFont(size=22, weight="bold"))
lbl_saved_h.pack(anchor="w", pady=(0, 12))
saved_box = ctk.CTkScrollableFrame(page_saved, corner_radius=10, fg_color=bg_c["box"])
saved_box.pack(fill="both", expand=True)


def refresh_saved():
    for w in saved_box.winfo_children():
        w.destroy()
    for item in reversed(saved_pages):
        create_card(saved_box, item["title"], item["url"], item["desc"], show_save=False, show_delete=True, cached_text=item.get("full_text", item["desc"]), current_page=page_saved)


lbl_set_h = ctk.CTkLabel(page_settings, text=tr("set_h"), font=ctk.CTkFont(size=22, weight="bold"))
lbl_set_h.pack(anchor="w", pady=(0, 16))
lbl_l_ui = ctk.CTkLabel(page_settings, text=tr("l_ui"), font=ctk.CTkFont(size=14, weight="bold"))
lbl_l_ui.pack(anchor="w", pady=(0, 6))
lang_labels = [v["label"] for v in LANG_META.values()]
label_to_code = {v["label"]: k for k, v in LANG_META.items()}


def apply_language():
    app.title(tr("title"))
    for w, k in ((btn_nav_s, "nav_s"), (btn_nav_a, "nav_a"), (btn_nav_c, "nav_c"), (btn_nav_d, "nav_d"), (theme_switch, "dark"), (lbl_hub, "hub"),
                 (mode_buttons["search"], "m_search"), (mode_buttons["profile"], "m_profile"), (btn_pick_photo, "btn_photo"),
                 (btn_prof_clear, "clear"), (profile_go_btn, "go"), (go_btn, "go"), (btn_tr_cards, "tr_cards"), (btn_exp_html, "exp_html"),
                 (status_label, "st_ready"), (lbl_saved_h, "saved_h"), (lbl_set_h, "set_h"), (lbl_l_ui, "l_ui"), (lbl_l_scope, "l_scope"),
                 (lbl_l_acc, "l_accent"), (lbl_l_bg, "l_bg"), (gh_check, "cb_gh"), (safe_check, "cb_safe"), (lbl_l_about, "l_about"),
                 (btn_open_gh, "btn_open_gh"), (lbl_footer_author, "made_by"), (lbl_dbg_h, "dbg_h"), (btn_dbg_clear, "clear"),
                 (btn_dbg_copy, "copy"), (btn_r_back, "back"), (btn_r_copy, "copy"), (btn_r_save, "arch")):
        w.configure(text=tr(k))
    search_entry.configure(placeholder_text=tr("ph_search"))
    for k in form_labels:
        form_labels[k].configure(text=tr(f"lbl_{k}"))
        form_entries[k].configure(placeholder_text=tr(f"ph_{k}"))
    if not selected_photo["path"]:
        lbl_photo_name.configure(text=tr("photo_none"))
    scope_seg.configure(values=[tr("sc_reg"), tr("sc_glob")])
    scope_seg.set(tr("sc_reg") if settings.get("search_scope") == "regional" else tr("sc_glob"))
    depth_label.configure(text=tr("l_depth", v=settings.get("depth", 35)))
    btn_r_tr.configure(text=tr("orig_btn") if reader_state["translated"] else tr("tr_btn"))
    refresh_saved()


ui_lang_menu = ctk.CTkOptionMenu(page_settings, values=lang_labels, command=lambda v: [settings.__setitem__("ui_lang", label_to_code.get(v, "ru")), save_json(SETTINGS_FILE, settings), apply_language()], fg_color=acc_m, button_color=acc_h, width=220, height=36)
ui_lang_menu.set(get_lang_meta()["label"])
ui_lang_menu.pack(anchor="w", pady=(0, 16))

lbl_l_scope = ctk.CTkLabel(page_settings, text=tr("l_scope"), font=ctk.CTkFont(size=14, weight="bold"))
lbl_l_scope.pack(anchor="w", pady=(0, 6))
scope_seg = ctk.CTkSegmentedButton(page_settings, values=[tr("sc_reg"), tr("sc_glob")], command=lambda v: [settings.__setitem__("search_scope", "regional" if v == tr("sc_reg") else "global"), save_json(SETTINGS_FILE, settings)], selected_color=acc_m, selected_hover_color=acc_h, height=36)
scope_seg.set(tr("sc_reg") if settings.get("search_scope") == "regional" else tr("sc_glob"))
scope_seg.pack(anchor="w", pady=(0, 16))

lbl_l_acc = ctk.CTkLabel(page_settings, text=tr("l_accent"), font=ctk.CTkFont(size=14, weight="bold"))
lbl_l_acc.pack(anchor="w", pady=(0, 6))
acc_row = ctk.CTkFrame(page_settings, fg_color="transparent")
acc_row.pack(anchor="w", pady=(0, 16))


def apply_theme_colors():
    am, ah = get_accent()
    bg = get_bg()
    sidebar.configure(fg_color=bg["sidebar"])
    main_area.configure(fg_color=bg["main"])
    page_settings.configure(fg_color=bg["main"])
    results_box.configure(fg_color=bg["box"])
    saved_box.configure(fg_color=bg["box"])
    profile_form.configure(fg_color=bg["card"])
    gh_card.configure(fg_color=bg["card"])
    for ent in (search_entry, *form_entries.values()):
        ent.configure(border_color=am)
    for b in (go_btn, profile_go_btn, btn_dbg_copy, btn_r_save, btn_open_gh):
        b.configure(fg_color=am, hover_color=ah)
    for b in (btn_prof_clear, btn_pick_photo, btn_tr_cards, btn_exp_html, btn_dbg_clear, btn_r_back, btn_r_copy):
        b.configure(fg_color=bg["inactive"])
    ui_lang_menu.configure(fg_color=am, button_color=ah)
    scope_seg.configure(selected_color=am, selected_hover_color=ah)
    bg_seg.configure(selected_color=am, selected_hover_color=ah)
    slider.configure(button_color=am, progress_color=am)
    theme_switch.configure(progress_color=am)
    gh_check.configure(fg_color=am)
    safe_check.configure(fg_color=am)
    lbl_gh_link.configure(text_color=am)
    update_sidebar_logo()
    set_search_mode(current_mode)
    rerender_search_cards()
    refresh_saved()


for ak, (c1, c2, cname) in ACCENTS.items():
    ctk.CTkButton(acc_row, text=cname, width=82, height=32, corner_radius=8, fg_color=c1, hover_color=c2, text_color="#FFFFFF", command=lambda k=ak: [settings.__setitem__("accent", k), save_json(SETTINGS_FILE, settings), apply_theme_colors()]).pack(side="left", padx=(0, 6))

lbl_l_bg = ctk.CTkLabel(page_settings, text=tr("l_bg"), font=ctk.CTkFont(size=14, weight="bold"))
lbl_l_bg.pack(anchor="w", pady=(0, 6))
bg_label_to_key = {v["label"]: k for k, v in BG_STYLES.items()}
bg_seg = ctk.CTkSegmentedButton(page_settings, values=list(bg_label_to_key.keys()), command=lambda v: [settings.__setitem__("bg_style", bg_label_to_key.get(v, "classic")), save_json(SETTINGS_FILE, settings), apply_theme_colors()], selected_color=acc_m, selected_hover_color=acc_h, height=36)
bg_seg.set(get_bg()["label"])
bg_seg.pack(anchor="w", pady=(0, 18))

depth_label = ctk.CTkLabel(page_settings, text=tr("l_depth", v=settings.get("depth", 35)), font=ctk.CTkFont(size=14, weight="bold"))
depth_label.pack(anchor="w")
slider = ctk.CTkSlider(page_settings, from_=10, to=150, number_of_steps=14, command=lambda val: [depth_label.configure(text=tr("l_depth", v=int(val))), settings.__setitem__("depth", int(val)), save_json(SETTINGS_FILE, settings)], button_color=acc_m, progress_color=acc_m)
slider.set(settings.get("depth", 35))
slider.pack(fill="x", pady=(10, 16))

gh_check = ctk.CTkCheckBox(page_settings, text=tr("cb_gh"), command=lambda: [settings.__setitem__("github_only", bool(gh_check.get())), save_json(SETTINGS_FILE, settings)], fg_color=acc_m)
if settings.get("github_only"):
    gh_check.select()
gh_check.pack(anchor="w", pady=5)

safe_check = ctk.CTkCheckBox(page_settings, text=tr("cb_safe"), command=lambda: [settings.__setitem__("safe_search", bool(safe_check.get())), save_json(SETTINGS_FILE, settings)], fg_color=acc_m)
if settings.get("safe_search", True):
    safe_check.select()
safe_check.pack(anchor="w", pady=5)

lbl_l_about = ctk.CTkLabel(page_settings, text=tr("l_about"), font=ctk.CTkFont(size=14, weight="bold"))
lbl_l_about.pack(anchor="w", pady=(22, 8))
gh_card = ctk.CTkFrame(page_settings, corner_radius=10, fg_color=bg_c["card"])
gh_card.pack(fill="x", pady=(0, 14))
gh_info_col = ctk.CTkFrame(gh_card, fg_color="transparent")
gh_info_col.pack(side="left", padx=16, pady=12, fill="x", expand=True)
ctk.CTkLabel(gh_info_col, text=f"{APP_NAME} v2.0 — by {AUTHOR_NAME}", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(anchor="w")
lbl_gh_link = ctk.CTkLabel(gh_info_col, text=GITHUB_URL, font=ctk.CTkFont(size=12), text_color=acc_m, anchor="w", cursor="hand2")
lbl_gh_link.pack(anchor="w", pady=(2, 0))
lbl_gh_link.bind("<Button-1>", lambda e: webbrowser.open(GITHUB_URL))
btn_open_gh = ctk.CTkButton(gh_card, text=tr("btn_open_gh"), width=120, height=36, corner_radius=8, fg_color=acc_m, hover_color=acc_h, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: webbrowser.open(GITHUB_URL))
btn_open_gh.pack(side="right", padx=16, pady=12)

switch_page(page_search)


# ================= АНИМАЦИИ И EULA =================
def _ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _ease_io(t):
    t = max(0.0, min(1.0, t))
    return 4 * t * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 3) / 2


def _draw_animated_logo(canvas, cx, cy, r, accent, bg_hex, ring_p=1.0, eye_p=1.0, bolt_p=1.0, rot_deg=0.0):
    br = r * 1.15
    canvas.create_oval(cx - br, cy - br, cx + br, cy + br, fill=bg_hex, outline="")
    if ring_p > 0.01:
        ext, ro, rs = 132.0 * ring_p, r * 1.02, r * 0.84
        canvas.create_arc(cx - ro, cy - ro, cx + ro, cy + ro, start=24 + rot_deg, extent=ext, style="arc", outline=accent, width=3.5)
        canvas.create_arc(cx - ro, cy - ro, cx + ro, cy + ro, start=204 + rot_deg, extent=ext, style="arc", outline=accent, width=3.5)
        canvas.create_arc(cx - rs, cy - rs, cx + rs, cy + rs, start=40 - rot_deg * 0.6, extent=100 * ring_p, style="arc", outline="#475569", width=1.8)
    if eye_p > 0.01:
        ew, eh = r * 0.80 * min(1.0, eye_p * 1.35), r * 0.88 * eye_p
        tp, bp = _quad_bezier((cx - ew, cy), (cx, cy - eh), (cx + ew, cy), 18), _quad_bezier((cx + ew, cy), (cx, cy + eh), (cx - ew, cy), 18)
        canvas.create_polygon(*[c for pt in (tp + bp) for c in pt], fill="#0B0B0F", outline="")
        canvas.create_line(*[c for pt in tp for c in pt], fill="#F8FAFC", width=3.2, smooth=True)
        canvas.create_line(*[c for pt in bp for c in pt], fill="#F8FAFC", width=3.2, smooth=True)
        ir = r * 0.33 * eye_p
        if ir > 2:
            canvas.create_oval(cx - ir, cy - ir, cx + ir, cy + ir, fill="#161622", outline=accent, width=2.6)
    if bolt_p > 0.01:
        dy, sc = -(1.0 - bolt_p) * r * 0.85, 0.55 + 0.45 * bolt_p
        raw = [(0.11, -0.78), (-0.27, 0.04), (-0.01, 0.04), (-0.15, 0.78), (0.29, -0.06), (0.03, -0.06)]
        canvas.create_polygon(*[v for bx, by in raw for v in (cx + bx * r * sc + 2.5, cy + by * r * sc + dy + 2.5)], fill=accent, outline="")
        canvas.create_polygon(*[v for bx, by in raw for v in (cx + bx * r * sc, cy + by * r * sc + dy)], fill="#FFFFFF", outline="")


def run_splash_loading():
    bg_hex, am = "#0C0C0F", get_accent()[0]
    overlay = ctk.CTkFrame(app, fg_color=bg_hex, corner_radius=0)
    overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
    overlay.lift()
    canvas = ctk.CTkCanvas(overlay, bg=bg_hex, highlightthickness=0, bd=0)
    canvas.pack(fill="both", expand=True)
    app.update_idletasks()
    start_ts, total_dur = time.perf_counter(), 1.9

    def frame():
        if not overlay.winfo_exists():
            return
        w, h = max(canvas.winfo_width(), 900), max(canvas.winfo_height(), 600)
        cx, cy, t = w / 2, h / 2 - 14, time.perf_counter() - start_ts
        canvas.delete("all")
        p_in, p_slide, p_load = _ease_out(t / 0.5), (_ease_io((t - 0.5) / 0.75) if t > 0.5 else 0.0), min(1.0, t / (total_dur - 0.15))
        logo_x, text_x = cx - 178 * p_slide, (cx - 178 * p_slide - 190) + 258 * p_slide
        if p_slide > 0.01:
            canvas.create_text(text_x, cy - 8, text="DESCENDING SCAN", anchor="w", fill="#F8FAFC", font=("Segoe UI", 27, "bold"))
            if p_slide > 0.35:
                canvas.create_text(text_x + 2, cy + 22, text="OSINT  •  OCR  •  RECON v2.0", anchor="w", fill="#94A3B8", font=("Segoe UI", 10, "bold"))
        canvas.create_rectangle(0, cy - 85, logo_x + 12, cy + 85, fill=bg_hex, outline="")
        _draw_animated_logo(canvas, logo_x, cy, 46, am, bg_hex, ring_p=p_in, eye_p=_ease_out((t - 0.08) / 0.42), bolt_p=_ease_out((t - 0.16) / 0.4), rot_deg=(1.0 - p_in) * 55.0)
        bx0, by = cx - 170, cy + 92
        canvas.create_line(bx0, by, bx0 + 340, by, fill="#1E1E24", width=3, capstyle="round")
        if p_load > 0.01:
            canvas.create_line(bx0, by, bx0 + 340 * p_load, by, fill=am, width=3, capstyle="round")
        canvas.create_text(cx, h - 34, text=f"By {AUTHOR_NAME}", anchor="center", fill="#64748B", font=("Segoe UI", 11, "bold"))
        app.after(16, frame) if t < total_dur else (overlay.destroy(), search_entry.focus_set())

    app.after(30, frame)


def show_eula_screen():
    bg_hex, (am, ah) = "#0C0C0F", get_accent()
    is_ru = settings.get("ui_lang", "ru") in ("ru", "uk", "kk")
    overlay = ctk.CTkFrame(app, fg_color=bg_hex, corner_radius=0)
    overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
    overlay.lift()
    card = ctk.CTkFrame(overlay, width=680, height=540, corner_radius=16, fg_color="#16161B", border_width=1, border_color="#27272A")
    card.place(relx=0.5, rely=0.5, anchor="center")
    card.pack_propagate(False)

    top_hdr = ctk.CTkFrame(card, fg_color="transparent")
    top_hdr.pack(fill="x", padx=28, pady=(20, 10))
    pil_s = render_brand_logo(64, accent=am, bg="#111113")
    _icon_refs["eula_logo"] = ctk.CTkImage(light_image=pil_s, dark_image=pil_s, size=(42, 42))
    ctk.CTkLabel(top_hdr, text="", image=_icon_refs["eula_logo"]).pack(side="left", padx=(0, 12))
    ht = ctk.CTkFrame(top_hdr, fg_color="transparent")
    ht.pack(side="left", fill="x")
    ctk.CTkLabel(ht, text="DESCENDING SCAN", font=ctk.CTkFont(size=18, weight="bold"), text_color="#F8FAFC").pack(anchor="w")
    ctk.CTkLabel(ht, text="Пользовательское соглашение (EULA)" if is_ru else "End User License Agreement (EULA)", font=ctk.CTkFont(size=12), text_color="#94A3B8").pack(anchor="w")

    eula_box = ctk.CTkTextbox(card, font=ctk.CTkFont(size=13), wrap="word", corner_radius=10, fg_color="#0F0F13", text_color="#E2E8F0", border_width=1, border_color="#27272A")
    eula_box.pack(fill="both", expand=True, padx=28, pady=(4, 10))
    eula_box.insert("1.0", EULA_TEXT_RU if is_ru else EULA_TEXT_EN)
    eula_box.configure(state="disabled")

    hint_lbl = ctk.CTkLabel(card, text="⬇ Прокрутите соглашение до конца" if is_ru else "⬇ Scroll down to unlock", font=ctk.CTkFont(size=12), text_color="#F59E0B")
    hint_lbl.pack(anchor="w", padx=30, pady=(0, 8))

    unlocked = {"ok": False}
    agree_cb = ctk.CTkCheckBox(card, text="Я прочитал(а) соглашение и согласен(на) с условиями" if is_ru else "I have read and agree to the EULA", state="disabled", fg_color=am, hover_color=ah, text_color="#E2E8F0", font=ctk.CTkFont(size=12, weight="bold"),
                               command=lambda: btn_accept.configure(state="normal" if agree_cb.get() else "disabled", fg_color=am if agree_cb.get() else "#27272A", hover_color=ah))
    agree_cb.pack(anchor="w", padx=30, pady=(0, 14))

    btn_row = ctk.CTkFrame(card, fg_color="transparent")
    btn_row.pack(fill="x", padx=28, pady=(0, 20))
    ctk.CTkButton(btn_row, text="Выйти" if is_ru else "Exit", width=120, height=40, corner_radius=8, fg_color="#27272A", hover_color="#3F3F46", text_color="#E2E8F0", command=app.destroy).pack(side="left")
    btn_accept = ctk.CTkButton(btn_row, text="Продолжить" if is_ru else "Continue", width=200, height=40, corner_radius=8, state="disabled", fg_color="#27272A", text_color="#FFFFFF", font=ctk.CTkFont(size=13, weight="bold"),
                               command=lambda: [settings.__setitem__("eula_accepted", True), save_json(SETTINGS_FILE, settings), overlay.destroy(), run_splash_loading()])
    btn_accept.pack(side="right")

    def poll_scroll():
        if not overlay.winfo_exists() or unlocked["ok"]:
            return
        try:
            if eula_box._textbox.yview()[1] >= 0.96:
                unlocked["ok"] = True
                hint_lbl.configure(text="✓ Соглашение прочитано" if is_ru else "✓ Agreement reviewed", text_color="#10B981")
                agree_cb.configure(state="normal")
                return
        except Exception:
            pass
        app.after(100, poll_scroll)

    app.after(120, poll_scroll)


def run_first_launch_intro():
    bg_hex, am = "#0C0C0F", get_accent()[0]
    overlay = ctk.CTkFrame(app, fg_color=bg_hex, corner_radius=0)
    overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
    overlay.lift()
    canvas = ctk.CTkCanvas(overlay, bg=bg_hex, highlightthickness=0, bd=0)
    canvas.pack(fill="both", expand=True)
    app.update_idletasks()
    start_ts = time.perf_counter()

    def frame():
        if not overlay.winfo_exists():
            return
        w, h = max(canvas.winfo_width(), 900), max(canvas.winfo_height(), 600)
        cx, cy, t = w / 2, h / 2, time.perf_counter() - start_ts
        canvas.delete("all")
        rp = _ease_out(t / 0.7)
        _draw_animated_logo(canvas, cx, cy, 62, am, bg_hex, ring_p=rp, eye_p=_ease_out((t - 0.25) / 0.6), bolt_p=_ease_out((t - 0.5) / 0.5), rot_deg=(1.0 - rp) * 140.0)
        canvas.create_text(cx, h - 34, text=f"By {AUTHOR_NAME}", anchor="center", fill="#64748B", font=("Segoe UI", 11, "bold"))
        app.after(16, frame) if t < 1.5 else (overlay.destroy(), show_eula_screen())

    app.after(30, frame)


app.after(20, run_first_launch_intro if not settings.get("eula_accepted", False) else run_splash_loading)
app.mainloop()
