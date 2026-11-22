import customtkinter as ctk
import hashlib
import json
import os
import re
import sys
import time
import threading
import webbrowser
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urlparse, quote
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import trafilatura
from PIL import Image, ImageDraw, ImageTk

try:
    from deep_translator import GoogleTranslator
    HAS_DEEP_TRANS = True
except Exception:
    HAS_DEEP_TRANS = False

NL = chr(10)
APP_NAME, AUTHOR_NAME, GITHUB_URL = "Descending Scan", "dromacs1", "https://github.com/dromacs1"
SETTINGS_FILE, SAVED_FILE, ICON_FILE = "settings.json", "saved_pages.json", "icon.ico"
UA_BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

HTTP = requests.Session()
HTTP.headers.update({"User-Agent": UA_BROWSER})


# ================= ЛОГОТИП И ИКОНКА (ГЛАЗ + МОЛНИЯ + ЩИТ) =================
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
    top_arc = _quad_bezier(lp, (cx, cy - w * 0.33), rp, 28)
    bot_arc = _quad_bezier(rp, (cx, cy + w * 0.33), lp, 28)
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


GARBAGE_DOMAINS = (
    "softonic.", "uptodown.", "malavida.", "filehippo.", "download.cnet.", "driverpack.",
    "otvet.mail.ru", "znanija.com", "rambler.ru", "msn.com", "shutterstock.", "istockphoto.",
    "alamy.", "123rf.", "dzen.ru", "yandex.ru/q", "fb.ru", "syl.ru", "autogear.ru",
    "baidu.com", "zhihu.com", "csdn.net", "weibo.com", "sohu.com", "163.com",
    "sina.com.cn", "qq.com", "bilibili.com", "360doc.com", "douban.com",
    "xvideos.", "pornhub.", "xnxx.", "xhamster.", "redtube.", "youporn.", "brazzers.",
    "chaturbate.", "bongacams.", "stripchat.", "spankbang.", "eporner.", "grannymommy.",
    "dedmazay.porn", "pornobabushki."
)

ADULT_STOP_WORDS = (
    "porn", "porno", "порно", "xvideos", "xnxx", "xhamster", "redtube", "youporn",
    "nsfw", "hentai", "хентай", "escort", "эскорт", "xxx", "sex video", "секс видео",
    "babushka porn", "granny porn", "onlyfans leak"
)

FREE_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com", "live.com",
    "icloud.com", "me.com", "mail.ru", "bk.ru", "inbox.ru", "list.ru", "internet.ru",
    "yandex.ru", "yandex.com", "ya.ru", "rambler.ru", "proton.me", "protonmail.com",
    "ukr.net", "i.ua", "meta.ua", "gmx.de", "web.de", "wp.pl", "o2.pl", "onet.pl",
    "orange.fr", "free.fr", "tutanota.com", "aol.com", "zoho.com"
}

PHONE_PREFIXES = (
    ("380", "Украина (UA)"), ("375", "Беларусь (BY)"), ("374", "Армения (AM)"),
    ("373", "Молдова (MD)"), ("372", "Эстония (EE)"), ("371", "Латвия (LV)"),
    ("370", "Литва (LT)"), ("358", "Финляндия (FI)"), ("998", "Узбекистан (UZ)"),
    ("996", "Кыргызстан (KG)"), ("995", "Грузия (GE)"), ("994", "Азербайджан (AZ)"),
    ("992", "Таджикистан (TJ)"), ("77", "Казахстан (KZ)"), ("76", "Казахстан (KZ)"),
    ("7", "Россия / Казахстан (RU/KZ)"), ("49", "Германия (DE)"), ("48", "Польша (PL)"),
    ("44", "Великобритания (UK)"), ("33", "Франция (FR)"), ("39", "Италия (IT)"),
    ("34", "Испания (ES)"), ("31", "Нидерланды (NL)"), ("90", "Турция (TR)"),
    ("1", "США / Канада (US/CA)")
)

RU_MOBILE_DEF = {
    "900": "Tele2 / Ростелеком", "901": "Tele2 / МТТ", "902": "Tele2 / МегаФон", "903": "Билайн",
    "904": "Tele2 / Мотив", "905": "Билайн", "906": "Билайн", "908": "Tele2", "909": "Билайн",
    "910": "МТС", "911": "МТС", "912": "МТС", "913": "МТС", "914": "МТС", "915": "МТС",
    "916": "МТС", "917": "МТС", "918": "МТС", "919": "МТС",
    "920": "МегаФон", "921": "МегаФон", "922": "МегаФон", "923": "МегаФон", "924": "МегаФон",
    "925": "МегаФон", "926": "МегаФон", "927": "МегаФон", "928": "МегаФон", "929": "МегаФон",
    "930": "МегаФон", "931": "МегаФон", "932": "МегаФон", "933": "МегаФон", "934": "МегаФон",
    "936": "МегаФон", "937": "МегаФон", "938": "МегаФон", "939": "МегаФон",
    "950": "Tele2", "951": "Tele2", "952": "Tele2", "953": "Tele2", "958": "Ростелеком / СберМобайл",
    "960": "Билайн", "961": "Билайн", "962": "Билайн", "963": "Билайн", "964": "Билайн",
    "965": "Билайн", "966": "Билайн", "967": "Билайн", "968": "Билайн", "969": "Билайн",
    "977": "Tele2 / Тинькофф Мобайл", "978": "МТС / Волна (Крым)",
    "980": "МТС", "981": "МТС", "982": "МТС", "983": "МТС", "984": "МТС",
    "985": "МТС", "986": "МТС", "987": "МТС", "988": "МТС", "989": "МТС",
    "991": "Tele2", "992": "Tele2", "993": "Tele2", "994": "Tele2", "995": "Yota / Тинькофф",
    "996": "Yota / СберМобайл", "999": "Yota / МегаФон"
}

KZ_MOBILE_DEF = {
    "700": "ALTEL (KZ)", "701": "Kcell / Activ (KZ)", "702": "Kcell / Activ (KZ)",
    "705": "Beeline (KZ)", "706": "ALTEL / Tele2 (KZ)", "707": "Tele2 (KZ)",
    "708": "ALTEL (KZ)", "747": "Tele2 (KZ)", "771": "Beeline (KZ)",
    "775": "Kcell / Activ (KZ)", "776": "Beeline (KZ)", "777": "Beeline (KZ)", "778": "Kcell / Activ (KZ)"
}

TRANSLIT_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya", "є": "ye", "і": "i", "ї": "yi", "ґ": "g", "ә": "a", "ң": "n", "ғ": "g",
    "ү": "u", "ұ": "u", "қ": "k", "ө": "o", "һ": "h"
}

LANG_META = {
    "ru": {"label": "Русский", "region": "ru-ru", "wiki": "ru", "steam": "russian", "q_ov": "что это обзор", "q_buy": "официальный сайт купить steam скачать цена", "q_err": "частые ошибки баги вылетает решение", "q_rev": "плюсы и минусы недостатки отзывы"},
    "en": {"label": "English", "region": "us-en", "wiki": "en", "steam": "english", "q_ov": "what is overview", "q_buy": "official website buy steam download price", "q_err": "common bugs crashes errors fix", "q_rev": "pros and cons criticism review"},
    "kk": {"label": "Қазақша", "region": "ru-ru", "wiki": "kk", "steam": "russian", "q_ov": "бұл не шолу", "q_buy": "ресми сайт сатып алу жүктеу", "q_err": "қателер багтар шешімі", "q_rev": "артықшылықтары кемшіліктері пікірлер"},
    "de": {"label": "Deutsch", "region": "de-de", "wiki": "de", "steam": "german", "q_ov": "was ist überblick", "q_buy": "offizielle seite kaufen steam download preis", "q_err": "häufige fehler bugs absturz lösung", "q_rev": "vor und nachteile kritik test"},
    "uk": {"label": "Українська", "region": "ua-uk", "wiki": "uk", "steam": "ukrainian", "q_ov": "що це огляд", "q_buy": "офіційний сайт купити steam завантажити ціна", "q_err": "часті помилки баги вилітає рішення", "q_rev": "плюси і мінуси недоліки відгуки"},
    "pl": {"label": "Polski", "region": "pl-pl", "wiki": "pl", "steam": "polish", "q_ov": "co to jest opis", "q_buy": "oficjalna strona kup steam pobierz cena", "q_err": "częste błędy bugi rozwiązanie", "q_rev": "plusy i minusy wady opinie"},
    "fr": {"label": "Français", "region": "fr-fr", "wiki": "fr", "steam": "french", "q_ov": "c est quoi aperçu", "q_buy": "site officiel acheter steam télécharger prix", "q_err": "erreurs fréquentes bugs crash solution", "q_rev": "avantages inconvénients avis critique"},
    "fi": {"label": "Suomi", "region": "fi-fi", "wiki": "fi", "steam": "finnish", "q_ov": "mikä on esittely", "q_buy": "virallinen sivu osta steam lataa hinta", "q_err": "yleiset virheet bugit ratkaisu", "q_rev": "hyvät ja huonot puolet arvostelu"},
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

EULA_TEXT_RU = """ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ (EULA) — DESCENDING SCAN
Версия 1.0 | Прокрутите до конца и внимательно прочитайте условия


1. СТАТУС ПРОГРАММНОГО ОБЕСПЕЧЕНИЯ
Программа «Descending Scan» является исключительно вспомогательным техническим инструментом для автоматизированного поиска, структурирования и чтения общедоступной информации из открытых источников сети Интернет (OSINT). Программа не предоставляет доступ к закрытым базам данных, не осуществляет взлом и работает только с публичными страницами и открытыми API.

2. ПОЛНАЯ ОТВЕТСТВЕННОСТЬ ПОЛЬЗОВАТЕЛЯ
Все действия, выполняемые с помощью «Descending Scan», включая формулировку поисковых запросов, проверку публичных профилей, сохранение материалов и любое дальнейшее использование полученных сведений, совершаются пользователем самостоятельно и исключительно под его полную юридическую, моральную и финансовую ответственность. Пользователь обязуется соблюдать законодательство своей страны и правила сторонних веб-ресурсов.

3. ОТКАЗ ОТ ОТВЕТСТВЕННОСТИ РАЗРАБОТЧИКА («КАК ЕСТЬ»)
Программное обеспечение предоставляется по принципу «КАК ЕСТЬ» (AS IS), без каких-либо явных или подразумеваемых гарантий. Автор (разработчик) программы ни при каких обстоятельствах не несёт ответственности за любой прямой, косвенный, случайный или иной ущерб, претензии третьих лиц, блокировки аккаунтов, правовые последствия или неправомерное использование программы пользователем. Всё, что пользователь делает с помощью данного инструмента, является исключительно его зоной ответственности.

4. МОДИФИКАЦИЯ, МОДДИНГ И СТОРОННИЕ СБОРКИ
Любое изменение исходного или исполняемого кода программы, декомпиляция, пересборка, создание модов, плагинов или распространение модифицированных версий осуществляется пользователями и третьими лицами на их собственный страх и риск.
Пользователь подтверждает и соглашается с тем, что:
- Разработчик не несёт никакой ответственности за работу, безопасность или последствия использования любых модифицированных (моддированных) версий программы;
- Пользователь и третьи лица не имеют и не будут выдвигать никаких претензий, исков или требований к автору оригинальной программы в связи с её моддингом, переработкой или использованием изменённых версий.

5. ПРИНЯТИЕ УСЛОВИЙ
Прокрутив данный документ до конца, поставив отметку «Я согласен» и нажав кнопку «Продолжить», вы подтверждаете, что полностью ознакомились с текстом соглашения, понимаете, что «Descending Scan» является лишь инструментом, принимаете полную ответственность за свои действия и не имеете претензий к разработчику. Если вы не согласны с любым из пунктов, закройте программу и удалите её со своего устройства."""

EULA_TEXT_EN = """END USER LICENSE AGREEMENT (EULA) — DESCENDING SCAN
Version 1.0 | Please scroll down and read carefully


1. SOFTWARE PURPOSE
"Descending Scan" is strictly a general-purpose technical tool for automated searching, structuring, and reading publicly available information from open Internet sources (OSINT). It does not access private databases or bypass authentication and interacts solely with public web pages and open APIs.

2. SOLE USER RESPONSIBILITY
All actions performed using "Descending Scan"—including search queries, public profile lookups, archiving, and any further use of retrieved information—are performed solely by the user under their full legal, ethical, and financial responsibility. You agree to comply with all applicable local and international laws and third-party terms of service.

3. DISCLAIMER OF LIABILITY ("AS IS")
This software is provided "AS IS", without warranty of any kind, express or implied. Under no circumstances shall the author/developer be held liable for any direct, indirect, incidental, or consequential damages, third-party claims, account restrictions, legal issues, or misuse of the software. Everything you do with this tool is strictly your own responsibility.

4. MODIFICATION, MODDING & THIRD-PARTY BUILDS
Any modification, modding, reverse-engineering, repacking, or creation of derivative builds is done entirely at the modifier's and user's own risk.
By continuing, you acknowledge and agree that:
- The original author holds zero liability for the safety, functionality, or consequences of any modded or altered versions;
- You waive any claims, disputes, or legal actions against the author regarding the tool, its use, or its modding.

5. ACCEPTANCE
By scrolling to the bottom of this agreement, checking the confirmation box, and clicking "Continue", you confirm that you have read and understood these terms, accept full responsibility for your actions, and hold nothing against the developer. If you do not agree, close and remove the application."""

TRANSLATIONS = {
    "ru": {
        "title": "Descending Scan — Поиск, Досье и OSINT", "nav_s": "  🔍   Поиск", "nav_a": "  💾   Сохраненное", "nav_c": "  ⚙️   Настройки", "nav_d": "  🐞   Отладка", "dark": "Темная тема",
        "hub": "Центр поиска и анализа", "m_search": "🔍 Поиск сайтов", "m_dossier": "🧠 Полное досье", "m_profile": "👤 OSINT Анкета (235+)",
        "ph_search": "Сайт, игра, новости или тема (напр.: hoi4, илон маск)...", "ph_dossier": "О чём собрать досье (суть, цена, частые ошибки, отзывы)?", "ph_profile": "Ник для проверки на 235+ площадках...",
        "lbl_nick": "Никнейм / Username", "ph_nick": "напр.: dromacs1 (235+ площадок)",
        "lbl_email": "Почта / Email", "ph_email": "напр.: user@gmail.com (Gravatar, утечки, регистрации)",
        "lbl_fio": "ФИО / Имя", "ph_fio": "напр.: Иванов Иван Иванович (соцсети, реестры, наука)",
        "lbl_phone": "Номер телефона", "ph_phone": "напр.: +79991234567 (оператор, мессенджеры, доски)",
        "form_hint": "Заполните любые известные поля (от 1 до 4) — пустые будут пропущены.",
        "go": "Запустить", "tr_cards": "🌐 Перевести выдачу", "tr_busy": "⏳ Перевод...", "tr_btn": "🌐 Перевести", "orig_btn": "🔄 Оригинал",
        "st_ready": "Выберите режим выше, введите запрос и нажмите Enter.", "st_empty": "Введите запрос!", "st_prof_empty": "Заполните хотя бы одно поле анкеты!",
        "st_scan": "Ищу «{q}» ({scope})...", "st_prof": "OSINT-анкета (235+ площадок): сканирую ({q})...",
        "st_none": "Ничего релевантного не найдено. Проверьте «🐞 Отладка».", "st_done": "Готово! Найдено {n} проверенных источников.", "st_pdone": "Анкета ({q}): {p} прямых находок и {m} упоминаний.",
        "st_err": "Ошибка: {err}", "st_dup": "Уже есть в сохраненных.", "st_saving": "Сохраняю страницу...", "st_saved": "Сохранено: {t}...",
        "saved_h": "Офлайн-архив", "set_h": "Настройки и внешний вид", "l_ui": "Язык интерфейса:", "l_scope": "Охват поиска (сайты, новости, Википедия):", "sc_reg": "Региональный", "sc_glob": "Глобальный",
        "l_accent": "Акцентный цвет кнопок:", "l_bg": "Стиль фона:", "l_depth": "Глубина проверки: {v}", "cb_gh": "Только первоисточники (GitHub, Reddit, Habr)", "cb_safe": "Безопасный поиск (скрывать 18+)",
        "l_about": "Автор и GitHub:", "btn_open_gh": "🌐 Перейти", "made_by": "Сделал dromacs1", "dbg_h": "Консоль отладки", "clear": "Очистить", "copy": "📋 Копировать", "back": "← Назад",
        "arch": "💾 В архив", "copied": "✓ Скопировано", "archived": "✓ Сохранено", "browser": "🌐 Браузер", "read": "📖 Читать", "save": "💾 Сохранить", "delete": "🗑️ Удалить",
        "b_off": "🌐 Официальный сайт", "b_wiki": "📚 Википедия", "b_steam": "🎮 Steam", "b_fan": "📖 Фандом / Вики", "b_code": "💻 Код / Git", "b_for": "💬 Форум", "b_store": "🛒 Магазин / Игры", "b_vid": "🎬 Видео",
        "b_mus": "🎵 Музыка", "b_soc": "💬 Соцсеть", "b_news": "📰 Новости", "b_art": "📄 Ресурс", "b_prof": "✅ Профиль", "b_gprof": "🎮 Игровой профиль", "b_mprof": "🎵 Музыкальный профиль", "b_repo": "📦 Проект", "b_ment": "🔎 Упоминание",
        "b_email": "📧 Почта / Утечки", "b_phone": "📱 Телефон", "b_fio": "🪪 ФИО", "b_link": "🔗 Связка",
        "r_load": "Загружаю чистый текст...", "r_fail": "Не удалось извлечь текст. Откройте в браузере.", "r_src": "Источник",
        "d_h": "ПОЛНОЕ ДОСЬЕ: {q}", "d_sub": "Собираю данные из Википедии, официальных сайтов, Steam, форумов и новостей...",
        "d1": "1. ЧТО ЭТО ТАКОЕ", "d2": "2. ОФИЦИАЛЬНЫЙ САЙТ / ГДЕ КУПИТЬ И СКАЧАТЬ", "d3": "3. ЧАСТЫЕ ОШИБКИ, БАГИ И РЕШЕНИЯ", "d4": "4. ПЛЮСЫ, МИНУСЫ И ОТЗЫВЫ", "d5": "5. СВЕЖИЕ НОВОСТИ РЕГИОНА",
        "d_done": "Готово. Нажмите «🌐 Перевести» или «💾 В архив» сверху.", "d_none": "Точных данных не найдено."
    },
    "en": {
        "title": "Descending Scan — Search, Dossier & OSINT", "nav_s": "  🔍   Search", "nav_a": "  💾   Saved", "nav_c": "  ⚙️   Settings", "nav_d": "  🐞   Debug", "dark": "Dark theme",
        "hub": "Search & Analysis Hub", "m_search": "🔍 Web Search", "m_dossier": "🧠 Full Dossier", "m_profile": "👤 OSINT Form (235+)",
        "ph_search": "Site, game, news or topic (e.g. hoi4, elon musk)...", "ph_dossier": "Topic for full dossier (overview, price, bugs, reviews)...", "ph_profile": "Username to scan 235+ platforms...",
        "lbl_nick": "Username / Nick", "ph_nick": "e.g. dromacs1 (235+ platforms)",
        "lbl_email": "Email", "ph_email": "e.g. user@gmail.com (Gravatar, leaks, checks)",
        "lbl_fio": "Full Name", "ph_fio": "e.g. John Doe (socials, registries, papers)",
        "lbl_phone": "Phone Number", "ph_phone": "e.g. +14155550199 (carrier, messengers, web)",
        "form_hint": "Fill any known fields (1 to 4) — empty ones are skipped.",
        "go": "Run", "tr_cards": "🌐 Translate results", "tr_busy": "⏳ Translating...", "tr_btn": "🌐 Translate", "orig_btn": "🔄 Original",
        "st_ready": "Pick a mode above, type your query and press Enter.", "st_empty": "Enter a query!", "st_prof_empty": "Fill at least one field in the form!",
        "st_scan": "Searching «{q}» ({scope})...", "st_prof": "OSINT form (235+ sites): scanning ({q})...",
        "st_none": "Nothing relevant found. Check «🐞 Debug».", "st_done": "Done! Found {n} verified sources.", "st_pdone": "Form ({q}): {p} direct hits and {m} mentions.",
        "st_err": "Error: {err}", "st_dup": "Already saved.", "st_saving": "Saving page...", "st_saved": "Saved: {t}...",
        "saved_h": "Offline Archive", "set_h": "Settings & Appearance", "l_ui": "Interface language:", "l_scope": "Search scope (web, news, Wikipedia):", "sc_reg": "Regional", "sc_glob": "Global",
        "l_accent": "Accent color:", "l_bg": "Background style:", "l_depth": "Search depth: {v}", "cb_gh": "Primary sources only (GitHub, Reddit, Habr)", "cb_safe": "SafeSearch (filter 18+)",
        "l_about": "Author & GitHub:", "btn_open_gh": "🌐 Open", "made_by": "Made by dromacs1", "dbg_h": "Debug Console", "clear": "Clear", "copy": "📋 Copy", "back": "← Back",
        "arch": "💾 Archive", "copied": "✓ Copied", "archived": "✓ Saved", "browser": "🌐 Browser", "read": "📖 Read", "save": "💾 Save", "delete": "🗑️ Delete",
        "b_off": "🌐 Official site", "b_wiki": "📚 Wikipedia", "b_steam": "🎮 Steam", "b_fan": "📖 Fandom / Wiki", "b_code": "💻 Code / Git", "b_for": "💬 Forum", "b_store": "🛒 Store / Games", "b_vid": "🎬 Video",
        "b_mus": "🎵 Music", "b_soc": "💬 Social", "b_news": "📰 News", "b_art": "📄 Resource", "b_prof": "✅ Profile", "b_gprof": "🎮 Gaming profile", "b_mprof": "🎵 Music profile", "b_repo": "📦 Project", "b_ment": "🔎 Mention",
        "b_email": "📧 Email / Leaks", "b_phone": "📱 Phone", "b_fio": "🪪 Full Name", "b_link": "🔗 Cross-match",
        "r_load": "Fetching clean text...", "r_fail": "Could not extract text. Open in browser.", "r_src": "Source",
        "d_h": "FULL DOSSIER: {q}", "d_sub": "Gathering data from Wikipedia, official sites, Steam, forums and news...",
        "d1": "1. OVERVIEW", "d2": "2. OFFICIAL SITE / BUY & DOWNLOAD", "d3": "3. COMMON ERRORS, BUGS & FIXES", "d4": "4. PROS, CONS & REVIEWS", "d5": "5. LATEST REGIONAL NEWS",
        "d_done": "Complete. Click «🌐 Translate» or «💾 Archive» above.", "d_none": "No exact data found."
    },
    "kk": {
        "title": "Descending Scan — Іздеу, Досье және OSINT", "nav_s": "  🔍   Іздеу", "nav_a": "  💾   Сақталған", "nav_c": "  ⚙️   Баптаулар", "nav_d": "  🐞   Отладка", "dark": "Қараңғы тақырып",
        "hub": "Іздеу және талдау орталығы", "m_search": "🔍 Сайт іздеу", "m_dossier": "🧠 Толық досье", "m_profile": "👤 OSINT Анкета (235+)",
        "ph_search": "Сайт, ойын, жаңалық немесе тақырып...", "ph_dossier": "Толық досье жинау үшін тақырып...", "ph_profile": "Ник...",
        "lbl_nick": "Никнейм / Username", "ph_nick": "мыс.: dromacs1 (235+ платформа)",
        "lbl_email": "Пошта / Email", "ph_email": "мыс.: user@gmail.com",
        "lbl_fio": "Аты-жөні (ТАӘ)", "ph_fio": "мыс.: Ахметов Асан",
        "lbl_phone": "Телефон нөмірі", "ph_phone": "мыс.: +77001234567",
        "form_hint": "Белгілі өрістерді толтырыңыз (1-ден 4-ке дейін).",
        "go": "Іске қосу", "tr_cards": "🌐 Нәтижені аудару", "tr_busy": "⏳ Аудару...", "tr_btn": "🌐 Аудару", "orig_btn": "🔄 Түпнұсқа",
        "st_ready": "Режимді таңдап, сұраныс жазып Enter басыңыз.", "st_empty": "Сұраныс енгізіңіз!", "st_prof_empty": "Кем дегенде бір өрісті толтырыңыз!",
        "st_scan": "«{q}» іздеуде ({scope})...", "st_prof": "OSINT-анкета (235+): тексеруде ({q})...",
        "st_none": "Ештеңе табылмады.", "st_done": "Дайын! {n} дереккөз табылды.", "st_pdone": "Анкета ({q}): {p} тікелей нәтиже және {m} сілтеме.",
        "st_err": "Қате: {err}", "st_dup": "Сақталған.", "st_saving": "Сақталуда...", "st_saved": "Сақталды: {t}...",
        "saved_h": "Офлайн мұрағат", "set_h": "Баптаулар және дизайн", "l_ui": "Интерфейс тілі:", "l_scope": "Іздеу аймағы:", "sc_reg": "Аймақтық", "sc_glob": "Жаһандық",
        "l_accent": "Түйме түсі:", "l_bg": "Фон стилі:", "l_depth": "Іздеу тереңдігі: {v}", "cb_gh": "Тек бастапқы көздер (GitHub, Reddit, Habr)", "cb_safe": "Қауіпсіз іздеу (18+ жасыру)",
        "l_about": "Автор және GitHub:", "btn_open_gh": "🌐 Өту", "made_by": "Жасаған dromacs1", "dbg_h": "Отладка", "clear": "Тазарту", "copy": "📋 Көшіру", "back": "← Артқа",
        "arch": "💾 Мұрағатқа", "copied": "✓ Көшірілді", "archived": "✓ Сақталды", "browser": "🌐 Браузер", "read": "📖 Оқу", "save": "💾 Сақтау", "delete": "🗑️ Жою",
        "b_off": "🌐 Ресми сайт", "b_wiki": "📚 Уикипедия", "b_steam": "🎮 Steam", "b_fan": "📖 Фандом", "b_code": "💻 Код", "b_for": "💬 Форум", "b_store": "🛒 Дүкен", "b_vid": "🎬 Бейне",
        "b_mus": "🎵 Музыка", "b_soc": "💬 Соцжелі", "b_news": "📰 Жаңалықтар", "b_art": "📄 Ресурс", "b_prof": "✅ Профиль", "b_gprof": "🎮 Ойын профилі", "b_mprof": "🎵 Музыка профилі", "b_repo": "📦 Жоба", "b_ment": "🔎 Сілтеме",
        "b_email": "📧 Пошта", "b_phone": "📱 Телефон", "b_fio": "🪪 ТАӘ", "b_link": "🔗 Байланыс",
        "r_load": "Жүктелуде...", "r_fail": "Мәтін алынбады.", "r_src": "Дереккөз",
        "d_h": "ТОЛЫҚ ДОСЬЕ: {q}", "d_sub": "Деректер жиналуда...", "d1": "1. БҰЛ НЕ", "d2": "2. РЕСМИ САЙТ / САТЫП АЛУ", "d3": "3. ҚАТЕЛЕР ЖӘНЕ ШЕШІМДЕР", "d4": "4. АРТЫҚШЫЛЫҚТАР ЖӘНЕ ПІКІРЛЕР", "d5": "5. СОҢҒЫ ЖАҢАЛЫҚТАР",
        "d_done": "Дайын.", "d_none": "Табылмады."
    },
    "de": {
        "title": "Descending Scan — Suche, Dossier & OSINT", "nav_s": "  🔍   Suche", "nav_a": "  💾   Gespeichert", "nav_c": "  ⚙️   Einstellungen", "nav_d": "  🐞   Debug", "dark": "Dunkles Design",
        "hub": "Suche & Analyse", "m_search": "🔍 Websuche", "m_dossier": "🧠 Voll-Dossier", "m_profile": "👤 OSINT-Formular (235+)",
        "ph_search": "Website, Spiel, Nachrichten oder Thema...", "ph_dossier": "Thema für vollständiges Dossier...", "ph_profile": "Benutzername...",
        "lbl_nick": "Benutzername / Nick", "ph_nick": "z.B. dromacs1 (235+ Plattformen)",
        "lbl_email": "E-Mail", "ph_email": "z.B. user@gmail.com (Gravatar, Leaks)",
        "lbl_fio": "Vollständiger Name", "ph_fio": "z.B. Max Mustermann",
        "lbl_phone": "Telefonnummer", "ph_phone": "z.B. +491701234567",
        "form_hint": "Beliebige Felder ausfüllen (1 bis 4) — leere werden übersprungen.",
        "go": "Starten", "tr_cards": "🌐 Ergebnisse übersetzen", "tr_busy": "⏳ Übersetze...", "tr_btn": "🌐 Übersetzen", "orig_btn": "🔄 Original",
        "st_ready": "Modus wählen, Begriff eingeben und Enter drücken.", "st_empty": "Suchbegriff eingeben!", "st_prof_empty": "Bitte mindestens ein Feld ausfüllen!",
        "st_scan": "Suche «{q}» ({scope})...", "st_prof": "OSINT-Formular (235+): prüfe ({q})...",
        "st_none": "Nichts Relevantes gefunden.", "st_done": "Fertig! {n} geprüfte Quellen.", "st_pdone": "Scan ({q}): {p} direkte Treffer und {m} Erwähnungen.",
        "st_err": "Fehler: {err}", "st_dup": "Bereits gespeichert.", "st_saving": "Speichere...", "st_saved": "Gespeichert: {t}...",
        "saved_h": "Offline-Archiv", "set_h": "Einstellungen & Design", "l_ui": "Oberflächensprache:", "l_scope": "Suchbereich (Web, News, Wikipedia):", "sc_reg": "Regional", "sc_glob": "Global",
        "l_accent": "Akzentfarbe:", "l_bg": "Hintergrundstil:", "l_depth": "Suchtiefe: {v}", "cb_gh": "Nur Primärquellen (GitHub, Reddit, Habr)", "cb_safe": "SafeSearch (18+ filtern)",
        "l_about": "Autor & GitHub:", "btn_open_gh": "🌐 Öffnen", "made_by": "Erstellt von dromacs1", "dbg_h": "Debug-Konsole", "clear": "Leeren", "copy": "📋 Kopieren", "back": "← Zurück",
        "arch": "💾 Archiv", "copied": "✓ Kopiert", "archived": "✓ Gespeichert", "browser": "🌐 Browser", "read": "📖 Lesen", "save": "💾 Speichern", "delete": "🗑️ Löschen",
        "b_off": "🌐 Offizielle Seite", "b_wiki": "📚 Wikipedia", "b_steam": "🎮 Steam", "b_fan": "📖 Fandom / Wiki", "b_code": "💻 Code", "b_for": "💬 Forum", "b_store": "🛒 Shop", "b_vid": "🎬 Video",
        "b_mus": "🎵 Musik", "b_soc": "💬 Soziales", "b_news": "📰 News", "b_art": "📄 Ressource", "b_prof": "✅ Profil", "b_gprof": "🎮 Gaming-Profil", "b_mprof": "🎵 Musik-Profil", "b_repo": "📦 Projekt", "b_ment": "🔎 Erwähnung",
        "b_email": "📧 E-Mail / Leaks", "b_phone": "📱 Telefon", "b_fio": "🪪 Name", "b_link": "🔗 Verknüpfung",
        "r_load": "Lade Text...", "r_fail": "Text nicht verfügbar.", "r_src": "Quelle",
        "d_h": "VOLL-DOSSIER: {q}", "d_sub": "Sammle Daten aus Wikipedia, Shops, Foren & News...", "d1": "1. ÜBERBLICK", "d2": "2. OFFIZIELLE SEITE / KAUF & DOWNLOAD", "d3": "3. FEHLER, BUGS & LÖSUNGEN", "d4": "4. VOR- & NACHTEILE, BEWERTUNGEN", "d5": "5. AKTUELLE NEWS",
        "d_done": "Fertig.", "d_none": "Keine Daten."
    },
    "uk": {
        "title": "Descending Scan — Пошук, Досьє та OSINT", "nav_s": "  🔍   Пошук", "nav_a": "  💾   Збережене", "nav_c": "  ⚙️   Налаштування", "nav_d": "  🐞   Налагодження", "dark": "Темна тема",
        "hub": "Центр пошуку та аналізу", "m_search": "🔍 Пошук сайтів", "m_dossier": "🧠 Повне досьє", "m_profile": "👤 OSINT Анкета (235+)",
        "ph_search": "Сайт, гра, новини або тема...", "ph_dossier": "Про що зібрати повне досьє?", "ph_profile": "Нік...",
        "lbl_nick": "Нікнейм / Username", "ph_nick": "напр.: dromacs1 (235+ платформ)",
        "lbl_email": "Пошта / Email", "ph_email": "напр.: user@gmail.com (Gravatar, витоки)",
        "lbl_fio": "ПІБ / Ім'я", "ph_fio": "напр.: Іваненко Іван Іванович",
        "lbl_phone": "Номер телефону", "ph_phone": "напр.: +380991234567",
        "form_hint": "Заповніть будь-які відомі поля (від 1 до 4).",
        "go": "Запустити", "tr_cards": "🌐 Перекласти видачу", "tr_busy": "⏳ Переклад...", "tr_btn": "🌐 Перекласти", "orig_btn": "🔄 Оригінал",
        "st_ready": "Оберіть режим вище, введіть запит і натисніть Enter.", "st_empty": "Введіть запит!", "st_prof_empty": "Заповніть хоча б одне поле анкети!",
        "st_scan": "Шукаю «{q}» ({scope})...", "st_prof": "OSINT-анкета (235+): сканую ({q})...",
        "st_none": "Нічого релевантного не знайдено.", "st_done": "Готово! Знайдено {n} джерел.", "st_pdone": "Анкета ({q}): {p} прямих знахідок і {m} згадок.",
        "st_err": "Помилка: {err}", "st_dup": "Вже збережено.", "st_saving": "Зберігаю...", "st_saved": "Збережено: {t}...",
        "saved_h": "Офлайн-архів", "set_h": "Налаштування та вигляд", "l_ui": "Мова інтерфейсу:", "l_scope": "Охоплення пошуку:", "sc_reg": "Регіональний", "sc_glob": "Глобальний",
        "l_accent": "Колір кнопок:", "l_bg": "Стиль фону:", "l_depth": "Глибина перевірки: {v}", "cb_gh": "Лише першоджерела (GitHub, Reddit, Habr)", "cb_safe": "Безпечний пошук (приховати 18+)",
        "l_about": "Автор і GitHub:", "btn_open_gh": "🌐 Перейти", "made_by": "Зробив dromacs1", "dbg_h": "Налагодження", "clear": "Очистити", "copy": "📋 Копіювати", "back": "← Назад",
        "arch": "💾 В архів", "copied": "✓ Скопійовано", "archived": "✓ Збережено", "browser": "🌐 Браузер", "read": "📖 Читати", "save": "💾 Зберегти", "delete": "🗑️ Видалити",
        "b_off": "🌐 Офіційний сайт", "b_wiki": "📚 Вікіпедія", "b_steam": "🎮 Steam", "b_fan": "📖 Фандом", "b_code": "💻 Код", "b_for": "💬 Форум", "b_store": "🛒 Магазин", "b_vid": "🎬 Відео",
        "b_mus": "🎵 Музика", "b_soc": "💬 Соцмережа", "b_news": "📰 Новини", "b_art": "📄 Ресурс", "b_prof": "✅ Профіль", "b_gprof": "🎮 Ігровий профіль", "b_mprof": "🎵 Музичний профіль", "b_repo": "📦 Проєкт", "b_ment": "🔎 Згадка",
        "b_email": "📧 Пошта / Витоки", "b_phone": "📱 Телефон", "b_fio": "🪪 ПІБ", "b_link": "🔗 Зв'язка",
        "r_load": "Завантажую...", "r_fail": "Не вдалося отримати текст.", "r_src": "Джерело",
        "d_h": "ПОВНЕ ДОСЬЄ: {q}", "d_sub": "Збираю дані з Вікіпедії, магазинів, форумів та новин...", "d1": "1. ЩО ЦЕ ТАКЕ", "d2": "2. ОФІЦІЙНИЙ САЙТ / КУПІВЛЯ", "d3": "3. ПОМИЛКИ, БАГИ ТА РІШЕННЯ", "d4": "4. ПЛЮСИ, МІНУСИ ТА ВІДГУКИ", "d5": "5. СВІЖІ НОВИНИ",
        "d_done": "Готово.", "d_none": "Не знайдено."
    },
    "pl": {
        "title": "Descending Scan — Wyszukiwanie, Dossier i OSINT", "nav_s": "  🔍   Szukaj", "nav_a": "  💾   Zapisane", "nav_c": "  ⚙️   Ustawienia", "nav_d": "  🐞   Debug", "dark": "Ciemny motyw",
        "hub": "Centrum wyszukiwania", "m_search": "🔍 Szukaj stron", "m_dossier": "🧠 Pełne dossier", "m_profile": "👤 Formularz OSINT (235+)",
        "ph_search": "Strona, gra, wiadomości lub temat...", "ph_dossier": "Temat pełnego raportu...", "ph_profile": "Nick...",
        "lbl_nick": "Nick / Username", "ph_nick": "np. dromacs1 (235+ platform)",
        "lbl_email": "E-mail", "ph_email": "np. user@gmail.com (Gravatar, wycieki)",
        "lbl_fio": "Imię i nazwisko", "ph_fio": "np. Jan Kowalski",
        "lbl_phone": "Numer telefonu", "ph_phone": "np. +48600123456",
        "form_hint": "Wypełnij dowolne znane pola (od 1 do 4).",
        "go": "Uruchom", "tr_cards": "🌐 Przetłumacz wyniki", "tr_busy": "⏳ Tłumaczenie...", "tr_btn": "🌐 Przetłumacz", "orig_btn": "🔄 Oryginał",
        "st_ready": "Wybierz tryb powyżej, wpisz zapytanie i naciśnij Enter.", "st_empty": "Wpisz zapytanie!", "st_prof_empty": "Wypełnij przynajmniej jedno pole!",
        "st_scan": "Szukam «{q}» ({scope})...", "st_prof": "Formularz OSINT (235+): skanuję ({q})...",
        "st_none": "Brak wyników.", "st_done": "Gotowe! Znaleziono {n} źródeł.", "st_pdone": "Skan ({q}): {p} bezpośrednich trafień i {m} wzmianek.",
        "st_err": "Błąd: {err}", "st_dup": "Już zapisano.", "st_saving": "Zapisywanie...", "st_saved": "Zapisano: {t}...",
        "saved_h": "Archiwum offline", "set_h": "Ustawienia i wygląd", "l_ui": "Język interfejsu:", "l_scope": "Zakres wyszukiwania:", "sc_reg": "Regionalny", "sc_glob": "Globalny",
        "l_accent": "Kolor akcentu:", "l_bg": "Styl tła:", "l_depth": "Głębokość: {v}", "cb_gh": "Tylko główne źródła (GitHub, Reddit, Habr)", "cb_safe": "Bezpieczne szukanie (18+)",
        "l_about": "Autor i GitHub:", "btn_open_gh": "🌐 Przejdź", "made_by": "Stworzył dromacs1", "dbg_h": "Debug", "clear": "Wyczyść", "copy": "📋 Kopiuj", "back": "← Wróć",
        "arch": "💾 Archiwum", "copied": "✓ Skopiowano", "archived": "✓ Zapisano", "browser": "🌐 Przeglądarka", "read": "📖 Czytaj", "save": "💾 Zapisz", "delete": "🗑️ Usuń",
        "b_off": "🌐 Oficjalna strona", "b_wiki": "📚 Wikipedia", "b_steam": "🎮 Steam", "b_fan": "📖 Fandom", "b_code": "💻 Kod", "b_for": "💬 Forum", "b_store": "🛒 Sklep", "b_vid": "🎬 Wideo",
        "b_mus": "🎵 Muzyka", "b_soc": "💬 Społeczność", "b_news": "📰 Wiadomości", "b_art": "📄 Zasób", "b_prof": "✅ Profil", "b_gprof": "🎮 Profil gracza", "b_mprof": "🎵 Profil muzyczny", "b_repo": "📦 Projekt", "b_ment": "🔎 Wzmianka",
        "b_email": "📧 E-mail / Wycieki", "b_phone": "📱 Telefon", "b_fio": "🪪 Imię i nazwisko", "b_link": "🔗 Powiązanie",
        "r_load": "Pobieranie...", "r_fail": "Błąd pobierania tekstu.", "r_src": "Źródło",
        "d_h": "PEŁNE DOSSIER: {q}", "d_sub": "Zbieranie danych...", "d1": "1. OPIS OGÓLNY", "d2": "2. OFICJALNA STRONA / ZAKUP", "d3": "3. BŁĘDY, BUGI I ROZWIĄZANIA", "d4": "4. PLUSY, MINUSY I OPINIE", "d5": "5. AKTUALNOŚCI",
        "d_done": "Gotowe.", "d_none": "Brak danych."
    },
    "fr": {
        "title": "Descending Scan — Recherche, Dossier & OSINT", "nav_s": "  🔍   Recherche", "nav_a": "  💾   Enregistré", "nav_c": "  ⚙️   Paramètres", "nav_d": "  🐞   Débogage", "dark": "Thème sombre",
        "hub": "Centre de recherche", "m_search": "🔍 Recherche Web", "m_dossier": "🧠 Dossier complet", "m_profile": "👤 Fiche OSINT (235+)",
        "ph_search": "Site, jeu, actualité ou sujet...", "ph_dossier": "Sujet du dossier complet...", "ph_profile": "Pseudo...",
        "lbl_nick": "Pseudo / Username", "ph_nick": "ex. dromacs1 (235+ plateformes)",
        "lbl_email": "E-mail", "ph_email": "ex. user@gmail.com (Gravatar, fuites)",
        "lbl_fio": "Nom complet", "ph_fio": "ex. Jean Dupont",
        "lbl_phone": "Téléphone", "ph_phone": "ex. +33612345678",
        "form_hint": "Remplissez les champs connus (1 à 4) — les vides sont ignorés.",
        "go": "Lancer", "tr_cards": "🌐 Traduire les résultats", "tr_busy": "⏳ Traduction...", "tr_btn": "🌐 Traduire", "orig_btn": "🔄 Original",
        "st_ready": "Choisissez un mode, tapez votre requête et appuyez sur Entrée.", "st_empty": "Entrez une requête !", "st_prof_empty": "Remplissez au moins un champ !",
        "st_scan": "Recherche «{q}» ({scope})...", "st_prof": "Fiche OSINT (235+) : analyse ({q})...",
        "st_none": "Aucun résultat pertinent.", "st_done": "Terminé ! {n} sources vérifiées.", "st_pdone": "Fiche ({q}) : {p} résultats directs et {m} mentions.",
        "st_err": "Erreur : {err}", "st_dup": "Déjà enregistré.", "st_saving": "Enregistrement...", "st_saved": "Enregistré : {t}...",
        "saved_h": "Archive hors ligne", "set_h": "Paramètres et apparence", "l_ui": "Langue de l'interface :", "l_scope": "Portée de recherche :", "sc_reg": "Régional", "sc_glob": "Global",
        "l_accent": "Couleur d'accent :", "l_bg": "Style de fond :", "l_depth": "Profondeur : {v}", "cb_gh": "Sources primaires uniquement (GitHub, Reddit, Habr)", "cb_safe": "SafeSearch (filtrer 18+)",
        "l_about": "Auteur et GitHub :", "btn_open_gh": "🌐 Ouvrir", "made_by": "Créé par dromacs1", "dbg_h": "Débogage", "clear": "Effacer", "copy": "📋 Copier", "back": "← Retour",
        "arch": "💾 Archiver", "copied": "✓ Copié", "archived": "✓ Enregistré", "browser": "🌐 Navigateur", "read": "📖 Lire", "save": "💾 Sauver", "delete": "🗑️ Supprimer",
        "b_off": "🌐 Site officiel", "b_wiki": "📚 Wikipédia", "b_steam": "🎮 Steam", "b_fan": "📖 Fandom", "b_code": "💻 Code", "b_for": "💬 Forum", "b_store": "🛒 Boutique", "b_vid": "🎬 Vidéo",
        "b_mus": "🎵 Musique", "b_soc": "💬 Social", "b_news": "📰 Actualités", "b_art": "📄 Ressource", "b_prof": "✅ Profil", "b_gprof": "🎮 Profil joueur", "b_mprof": "🎵 Profil musique", "b_repo": "📦 Projet", "b_ment": "🔎 Mention",
        "b_email": "📧 E-mail / Fuites", "b_phone": "📱 Téléphone", "b_fio": "🪪 Nom", "b_link": "🔗 Lien croisé",
        "r_load": "Extraction...", "r_fail": "Impossible d'extraire le texte.", "r_src": "Source",
        "d_h": "DOSSIER COMPLET : {q}", "d_sub": "Collecte en cours...", "d1": "1. APERÇU", "d2": "2. SITE OFFICIEL / ACHAT", "d3": "3. ERREURS, BUGS ET SOLUTIONS", "d4": "4. POINTS FORTS, FAIBLESSES ET AVIS", "d5": "5. ACTUALITÉS",
        "d_done": "Terminé.", "d_none": "Aucune donnée."
    },
    "fi": {
        "title": "Descending Scan — Haku, Raportti & OSINT", "nav_s": "  🔍   Haku", "nav_a": "  💾   Tallennetut", "nav_c": "  ⚙️   Asetukset", "nav_d": "  🐞   Vianmääritys", "dark": "Tumma teema",
        "hub": "Haku- ja analyysikeskus", "m_search": "🔍 Verkkohaku", "m_dossier": "🧠 Täysi raportti", "m_profile": "👤 OSINT-lomake (235+)",
        "ph_search": "Sivusto, peli, uutinen tai aihe...", "ph_dossier": "Aihe täyttä raporttia varten...", "ph_profile": "Nimimerkki...",
        "lbl_nick": "Nimimerkki / Username", "ph_nick": "esim. dromacs1 (235+ alustaa)",
        "lbl_email": "Sähköposti", "ph_email": "esim. user@gmail.com (Gravatar, vuodot)",
        "lbl_fio": "Koko nimi", "ph_fio": "esim. Matti Meikäläinen",
        "lbl_phone": "Puhelinnumero", "ph_phone": "esim. +358401234567",
        "form_hint": "Täytä tunnetut kentät (1–4) — tyhjät ohitetaan.",
        "go": "Suorita", "tr_cards": "🌐 Käännä tulokset", "tr_busy": "⏳ Käännetään...", "tr_btn": "🌐 Käännä", "orig_btn": "🔄 Alkuperäinen",
        "st_ready": "Valitse tila, kirjoita haku ja paina Enter.", "st_empty": "Syötä hakusana!", "st_prof_empty": "Täytä vähintään yksi kenttä!",
        "st_scan": "Haetaan «{q}» ({scope})...", "st_prof": "OSINT-lomake (235+): tarkistetaan ({q})...",
        "st_none": "Ei osuvia tuloksia.", "st_done": "Valmis! Löytyi {n} lähdettä.", "st_pdone": "Lomake ({q}): {p} suoraa osumaa ja {m} mainintaa.",
        "st_err": "Virhe: {err}", "st_dup": "Jo tallennettu.", "st_saving": "Tallennetaan...", "st_saved": "Tallennettu: {t}...",
        "saved_h": "Offline-arkisto", "set_h": "Asetukset ja ulkoasu", "l_ui": "Käyttöliittymän kieli:", "l_scope": "Haun laajuus:", "sc_reg": "Alueellinen", "sc_glob": "Globaali",
        "l_accent": "Korostusväri:", "l_bg": "Taustatyyli:", "l_depth": "Haun syvyys: {v}", "cb_gh": "Vain ensisijaiset lähteet (GitHub, Reddit, Habr)", "cb_safe": "SafeSearch (suodata 18+)",
        "l_about": "Tekijä ja GitHub:", "btn_open_gh": "🌐 Avaa", "made_by": "Tehnyt dromacs1", "dbg_h": "Vianmääritys", "clear": "Tyhjennä", "copy": "📋 Kopioi", "back": "← Takaisin",
        "arch": "💾 Arkistoi", "copied": "✓ Kopioitu", "archived": "✓ Tallennettu", "browser": "🌐 Selain", "read": "📖 Lue", "save": "💾 Tallenna", "delete": "🗑️ Poista",
        "b_off": "🌐 Virallinen sivu", "b_wiki": "📚 Wikipedia", "b_steam": "🎮 Steam", "b_fan": "📖 Fandom", "b_code": "💻 Koodi", "b_for": "💬 Foorumi", "b_store": "🛒 Kauppa", "b_vid": "🎬 Video",
        "b_mus": "🎵 Musiikki", "b_soc": "💬 Some", "b_news": "📰 Uutiset", "b_art": "📄 Lähde", "b_prof": "✅ Profiili", "b_gprof": "🎮 Peliprofiili", "b_mprof": "🎵 Musiikkiprofiili", "b_repo": "📦 Projekti", "b_ment": "🔎 Maininta",
        "b_email": "📧 Sähköposti", "b_phone": "📱 Puhelin", "b_fio": "🪪 Nimi", "b_link": "🔗 Yhteys",
        "r_load": "Ladataan...", "r_fail": "Tekstin haku epäonnistui.", "r_src": "Lähde",
        "d_h": "TÄYSI RAPORTTI: {q}", "d_sub": "Kerätään tietoja...", "d1": "1. YLEISKATSAUS", "d2": "2. VIRALLINEN SIVU / OSTO", "d3": "3. VIRHEET, BUGIT JA RATKAISUT", "d4": "4. HYVÄT, HUONOT PUOLET JA ARVOSTELUT", "d5": "5. UUTISET",
        "d_done": "Valmis.", "d_none": "Ei tietoja."
    },
}

# 215+ площадок для прямой HTML-проверки по никнейму (в дополнение к 20 прямым API = 235+ площадок)
HTML_PLATFORMS = [
    # --- Разработка, IT, Репозитории и Кибербезопасность (45) ---
    ("Codeberg", "https://codeberg.org/{q}", "b_repo", "#10B981", ("404", "page not found")),
    ("SourceForge", "https://sourceforge.net/u/{q}/profile/", "b_repo", "#F97316", ("page not found", "404")),
    ("PyPI", "https://pypi.org/user/{q}/", "b_repo", "#3B82F6", ("page not found", "404")),
    ("npm", "https://www.npmjs.com/~{q}", "b_repo", "#EF4444", ("not found", "404")),
    ("Crates.io", "https://crates.io/users/{q}", "b_repo", "#F59E0B", ("404", "not found")),
    ("RubyGems", "https://rubygems.org/profiles/{q}", "b_repo", "#EF4444", ("page not found", "404")),
    ("Packagist", "https://packagist.org/users/{q}/", "b_repo", "#F97316", ("page not found", "404")),
    ("Replit", "https://replit.com/@{q}", "b_repo", "#F97316", ("404", "not found")),
    ("CodePen", "https://codepen.io/{q}", "b_repo", "#10B981", ("404", "page not found")),
    ("Glitch", "https://glitch.com/@{q}", "b_repo", "#8B5CF6", ("page not found", "404")),
    ("Kaggle", "https://www.kaggle.com/{q}", "b_repo", "#0EA5E9", ("404", "we can't find")),
    ("Bitbucket", "https://bitbucket.org/{q}/", "b_repo", "#3B82F6", ("404", "resource not found")),
    ("LeetCode", "https://leetcode.com/u/{q}/", "b_repo", "#F59E0B", ("page not found", "404", "user does not exist")),
    ("Codeforces", "https://codeforces.com/profile/{q}", "b_repo", "#3B82F6", ("codeforces", "404")),
    ("AtCoder", "https://atcoder.jp/users/{q}", "b_repo", "#0EA5E9", ("404", "not found")),
    ("HackerRank", "https://www.hackerrank.com/profile/{q}", "b_repo", "#10B981", ("page not found", "404")),
    ("Exercism", "https://exercism.org/profiles/{q}", "b_repo", "#8B5CF6", ("page not found", "404")),
    ("Topcoder", "https://profiles.topcoder.com/{q}", "b_repo", "#0EA5E9", ("page not found", "404")),
    ("Habr", "https://habr.com/ru/users/{q}/", "b_prof", "#14B8A6", ("404", "не найдена")),
    ("Habr Career", "https://career.habr.com/{q}", "b_prof", "#14B8A6", ("404", "не найдена")),
    ("Dev.to", "https://dev.to/{q}", "b_repo", "#10B981", ("404", "page not found")),
    ("Hashnode", "https://hashnode.com/@{q}", "b_repo", "#3B82F6", ("404", "page not found")),
    ("HackerNews", "https://news.ycombinator.com/user?id={q}", "b_repo", "#F97316", ("no such user",)),
    ("Lobsters", "https://lobste.rs/~{q}", "b_repo", "#EF4444", ("404", "not found")),
    ("Launchpad", "https://launchpad.net/~{q}", "b_repo", "#F59E0B", ("page not found", "404")),
    ("Arch AUR", "https://aur.archlinux.org/account/{q}", "b_repo", "#0EA5E9", ("account details", "not found", "404")),
    ("Kali Forums", "https://forums.kali.org/u/{q}/summary", "b_repo", "#3B82F6", ("page not found", "404")),
    ("XDA Forums", "https://xdaforums.com/m/{q}/", "b_repo", "#F59E0B", ("oops! we ran into some problems", "404")),
    ("HackerOne", "https://hackerone.com/{q}", "b_repo", "#10B981", ("page not found", "404")),
    ("Bugcrowd", "https://bugcrowd.com/{q}", "b_repo", "#F97316", ("page not found", "404")),
    ("Intigriti", "https://app.intigriti.com/profile/{q}", "b_repo", "#0EA5E9", ("page not found", "404")),
    ("TryHackMe", "https://tryhackme.com/p/{q}", "b_repo", "#EF4444", ("page not found", "404")),
    ("HackTheBox", "https://app.hackthebox.com/profile/{q}", "b_repo", "#10B981", ("page not found", "404")),
    ("Root-Me", "https://www.root-me.org/{q}", "b_repo", "#10B981", ("404", "page not found")),
    ("Pastebin", "https://pastebin.com/u/{q}", "b_repo", "#3B82F6", ("not found", "404")),
    ("Gist GitHub", "https://gist.github.com/{q}", "b_repo", "#10B981", ("not found", "404")),
    ("Observable", "https://observablehq.com/@{q}", "b_repo", "#3B82F6", ("page not found", "404")),
    ("NPM RunKit", "https://runkit.com/{q}", "b_repo", "#EC4899", ("page not found", "404")),
    ("Fedora", "https://accounts.fedoraproject.org/user/{q}/", "b_repo", "#3B82F6", ("page not found", "404")),
    ("OpenStreetMap", "https://www.openstreetmap.org/user/{q}", "b_repo", "#10B981", ("does not exist", "404")),
    ("Instructables", "https://www.instructables.com/member/{q}/", "b_repo", "#F59E0B", ("page not found", "404")),
    ("Hackaday", "https://hackaday.io/{q}", "b_repo", "#10B981", ("page not found", "404")),
    ("Tindie", "https://www.tindie.com/stores/{q}/", "b_repo", "#0EA5E9", ("page not found", "404")),
    ("Arduino", "https://create.arduino.cc/projecthub/{q}", "b_repo", "#14B8A6", ("page not found", "404")),
    ("W3C", "https://www.w3.org/users/{q}", "b_repo", "#3B82F6", ("not found", "404")),

    # --- Игры, Моды, Киберспорт и Трекеры (45) ---
    ("Steam", "https://steamcommunity.com/id/{q}", "b_gprof", "#0EA5E9", ("error_ctn", "could not be found", "не может быть найден")),
    ("Trovo", "https://trovo.live/s/{q}", "b_gprof", "#10B981", ("page not found", "404")),
    ("Medal.tv", "https://medal.tv/u/{q}", "b_gprof", "#F59E0B", ("page not found", "404")),
    ("CurseForge", "https://www.curseforge.com/members/{q}", "b_gprof", "#F97316", ("page not found", "404")),
    ("NexusMods", "https://next.nexusmods.com/profile/{q}", "b_gprof", "#F97316", ("page not found", "404")),
    ("Itch.io", "https://{q}.itch.io/", "b_gprof", "#F43F5E", ("404", "couldn't find")),
    ("GameJolt", "https://gamejolt.com/@{q}", "b_gprof", "#10B981", ("page not found", "404")),
    ("Newgrounds", "https://{q}.newgrounds.com/", "b_gprof", "#F59E0B", ("404", "not found")),
    ("Kongregate", "https://www.kongregate.com/accounts/{q}", "b_gprof", "#EF4444", ("page not found", "404")),
    ("ArmorGames", "https://armorgames.com/user/{q}", "b_gprof", "#EF4444", ("page not found", "404")),
    ("Osu!", "https://osu.ppy.sh/users/{q}", "b_gprof", "#EC4899", ("user not found", "404")),
    ("PSNProfiles", "https://psnprofiles.com/{q}", "b_gprof", "#3B82F6", ("page not found", "404", "not found")),
    ("TrueAchievements", "https://www.trueachievements.com/gamer/{q}", "b_gprof", "#10B981", ("page not found", "404")),
    ("Exophase", "https://www.exophase.com/user/{q}/", "b_gprof", "#8B5CF6", ("page not found", "404")),
    ("Backloggd", "https://www.backloggd.com/u/{q}/", "b_gprof", "#EC4899", ("page not found", "404")),
    ("HowLongToBeat", "https://howlongtobeat.com/user/{q}", "b_gprof", "#3B82F6", ("page not found", "404")),
    ("RAWG", "https://rawg.io/@{q}", "b_gprof", "#10B981", ("page not found", "404")),
    ("BoardGameGeek", "https://boardgamegeek.com/user/{q}", "b_gprof", "#F97316", ("user not found", "404")),
    ("Geocaching", "https://www.geocaching.com/p/?u={q}", "b_gprof", "#10B981", ("could not be found", "404")),
    ("TruckersMP", "https://truckersmp.com/user/{q}", "b_gprof", "#EF4444", ("page not found", "404")),
    ("SpigotMC", "https://www.spigotmc.org/members/?username={q}", "b_gprof", "#F59E0B", ("requested member could not be found", "404")),
    ("PlanetMinecraft", "https://www.planetminecraft.com/member/{q}/", "b_gprof", "#10B981", ("page not found", "404")),
    ("MinecraftSkins", "https://www.minecraftskins.com/profile/{q}", "b_gprof", "#10B981", ("page not found", "404")),
    ("NameMC", "https://namemc.com/profile/{q}", "b_gprof", "#10B981", ("page not found", "404")),
    ("osu!track", "https://ameobea.me/osutrack/user/{q}/", "b_gprof", "#EC4899", ("user not found", "404")),
    ("TETR.IO", "https://ch.tetr.io/u/{q}", "b_gprof", "#8B5CF6", ("no such user", "404")),
    ("Lichess Team", "https://lichess.org/team/{q}", "b_gprof", "#10B981", ("page not found", "404")),
    ("Chess.com Club", "https://www.chess.com/club/{q}", "b_gprof", "#10B981", ("page not found", "404")),
    ("PokéCommunity", "https://www.pokecommunity.com/members/{q}/", "b_gprof", "#EF4444", ("oops! we ran into some problems", "404")),
    ("SMWCentral", "https://www.smwcentral.net/?p=profile&name={q}", "b_gprof", "#3B82F6", ("user does not exist", "404")),
    ("Doomworld", "https://www.doomworld.com/profile/{q}/", "b_gprof", "#EF4444", ("page not found", "404")),
    ("ModDB", "https://www.moddb.com/members/{q}", "b_gprof", "#EF4444", ("page not found", "404")),
    ("IndieDB", "https://www.indiedb.com/members/{q}", "b_gprof", "#0EA5E9", ("page not found", "404")),
    ("GameBanana", "https://gamebanana.com/members/{q}", "b_gprof", "#F59E0B", ("page not found", "404")),
    ("GOG.com", "https://www.gog.com/u/{q}", "b_gprof", "#8B5CF6", ("404", "not found")),
    ("PlayCanvas", "https://playcanvas.com/{q}", "b_gprof", "#F97316", ("404", "not found")),
    ("Construct", "https://www.construct.net/en/users/{q}", "b_gprof", "#14B8A6", ("404", "not found")),
    ("Scratch", "https://scratch.mit.edu/users/{q}/", "b_gprof", "#F59E0B", ("404", "whoops! our server is scratching its head")),
    ("Roblox Group", "https://www.roblox.com/groups/{q}", "b_gprof", "#0EA5E9", ("404", "not found")),
    ("Wordle / Sporcle", "https://www.sporcle.com/user/{q}/", "b_gprof", "#F97316", ("page not found", "404")),
    ("JetPunk", "https://www.jetpunk.com/users/{q}", "b_gprof", "#3B82F6", ("page not found", "404")),
    ("GeoGuessr", "https://www.geoguessr.com/user/{q}", "b_gprof", "#10B981", ("page not found", "404")),
    ("NationStates", "https://www.nationstates.net/nation={q}", "b_gprof", "#3B82F6", ("does not exist", "404")),
    ("FlightAware", "https://www.flightaware.com/user/{q}", "b_gprof", "#0EA5E9", ("page not found", "404")),
    ("RadarBox", "https://www.radarbox.com/user/{q}", "b_gprof", "#3B82F6", ("page not found", "404")),

    # --- Соцсети, Блоги, СНГ-площадки и Линк-хабы (50) ---
    ("VK", "https://vk.com/{q}", "b_prof", "#3B82F6", ("404", "не найдена", "not found", "вход", "добро пожаловать", "welcome")),
    ("OK.ru", "https://ok.ru/{q}", "b_prof", "#F97316", ("страница не найдена", "404", "not found")),
    ("Threads", "https://www.threads.net/@{q}", "b_prof", "#EC4899", ("page not found", "404", "not available")),
    ("Mastodon.social", "https://mastodon.social/@{q}", "b_prof", "#8B5CF6", ("the page you are looking for isn't here", "404")),
    ("Mastodon.online", "https://mastodon.online/@{q}", "b_prof", "#8B5CF6", ("the page you are looking for isn't here", "404")),
    ("Pinterest", "https://www.pinterest.com/{q}/", "b_prof", "#EF4444", ("user not found", "page not found")),
    ("Tumblr", "https://{q}.tumblr.com/", "b_prof", "#3B82F6", ("there's nothing here", "not found")),
    ("LiveJournal", "https://{q}.livejournal.com/", "b_prof", "#0EA5E9", ("404", "not found", "не найден")),
    ("Pikabu", "https://pikabu.ru/@{q}", "b_prof", "#10B981", ("404", "не найден")),
    ("DTF", "https://dtf.ru/u/{q}", "b_prof", "#38BDF8", ("404", "не найдена")),
    ("VC.ru", "https://vc.ru/u/{q}", "b_prof", "#38BDF8", ("404", "не найдена")),
    ("Spark.ru", "https://spark.ru/user/{q}", "b_prof", "#F59E0B", ("404", "не найдена")),
    ("Drive2", "https://www.drive2.ru/users/{q}/", "b_prof", "#EF4444", ("404", "не найдена")),
    ("Strava", "https://www.strava.com/athletes/{q}", "b_prof", "#F97316", ("page not found", "404")),
    ("Komoot", "https://www.komoot.com/user/{q}", "b_prof", "#10B981", ("page not found", "404")),
    ("AllTrails", "https://www.alltrails.com/members/{q}", "b_prof", "#10B981", ("page not found", "404")),
    ("MyAnimeList", "https://myanimelist.net/profile/{q}", "b_prof", "#3B82F6", ("404 not found", "invalid username")),
    ("AniList", "https://anilist.co/user/{q}/", "b_prof", "#0EA5E9", ("404", "not found")),
    ("Kitsu", "https://kitsu.app/users/{q}", "b_prof", "#F97316", ("404", "not found")),
    ("Anime-Planet", "https://www.anime-planet.com/users/{q}", "b_prof", "#EC4899", ("page not found", "404")),
    ("MangaDex", "https://mangadex.org/user/{q}", "b_prof", "#F97316", ("404", "not found")),
    ("Letterboxd", "https://letterboxd.com/{q}/", "b_prof", "#10B981", ("sorry, we can't find", "404")),
    ("Trakt", "https://trakt.tv/users/{q}", "b_prof", "#EF4444", ("404", "not found")),
    ("Goodreads", "https://www.goodreads.com/{q}", "b_prof", "#F59E0B", ("page not found", "404")),
    ("LiveLib", "https://www.livelib.ru/reader/{q}", "b_prof", "#3B82F6", ("404", "не найдена")),
    ("Wattpad", "https://www.wattpad.com/user/{q}", "b_prof", "#F97316", ("page not found", "404")),
    ("Ficbook", "https://ficbook.net/authors/{q}", "b_prof", "#F59E0B", ("404", "не найдена")),
    ("Author.Today", "https://author.today/u/{q}", "b_prof", "#0EA5E9", ("404", "не найдена")),
    ("Litnet", "https://litnet.com/ru/{q}", "b_prof", "#EC4899", ("404", "не найдена")),
    ("Medium", "https://medium.com/@{q}", "b_prof", "#10B981", ("404", "page not found", "out of nothing")),
    ("Substack", "https://substack.com/@{q}", "b_prof", "#F97316", ("page not found", "404")),
    ("Quora", "https://www.quora.com/profile/{q}", "b_prof", "#EF4444", ("page not found", "404")),
    ("Disqus", "https://disqus.com/by/{q}/", "b_prof", "#0EA5E9", ("page not found", "404")),
    ("About.me", "https://about.me/{q}", "b_prof", "#3B82F6", ("page not found", "404")),
    ("Linktree", "https://linktr.ee/{q}", "b_prof", "#10B981", ("page not found", "doesn't exist")),
    ("Carrd", "https://{q}.carrd.co/", "b_prof", "#8B5CF6", ("page not found", "404")),
    ("Taplink", "https://taplink.cc/{q}", "b_prof", "#0EA5E9", ("page not found", "404")),
    ("Bio.link", "https://bio.link/{q}", "b_prof", "#EC4899", ("page not found", "404")),
    ("Beacons", "https://beacons.ai/{q}", "b_prof", "#8B5CF6", ("page not found", "404")),
    ("AllMyLinks", "https://allmylinks.com/{q}", "b_prof", "#EC4899", ("page not found", "404")),
    ("Boosty", "https://boosty.to/{q}", "b_prof", "#F97316", ("page not found", "страница не найдена", "404")),
    ("Patreon", "https://www.patreon.com/{q}", "b_prof", "#F97316", ("page not found", "404")),
    ("Ko-fi", "https://ko-fi.com/{q}", "b_prof", "#0EA5E9", ("page not found", "404")),
    ("BuyMeACoffee", "https://www.buymeacoffee.com/{q}", "b_prof", "#F59E0B", ("page not found", "404")),
    ("Gumroad", "https://{q}.gumroad.com/", "b_prof", "#EC4899", ("page not found", "404")),
    ("ProductHunt", "https://www.producthunt.com/@{q}", "b_prof", "#F97316", ("page not found", "404")),
    ("Crunchbase", "https://www.crunchbase.com/person/{q}", "b_prof", "#3B82F6", ("page not found", "404")),
    ("SlideShare", "https://www.slideshare.net/{q}", "b_prof", "#0EA5E9", ("page not found", "404")),
    ("SpeakerDeck", "https://speakerdeck.com/{q}", "b_prof", "#10B981", ("page not found", "404")),
    ("GitBook", "https://{q}.gitbook.io/", "b_prof", "#3B82F6", ("page not found", "404")),

    # --- Дизайн, Арт, Фото, 3D и Видео (40) ---
    ("YouTube", "https://www.youtube.com/@{q}", "b_prof", "#EF4444", ("404 not found", "this page isn't available")),
    ("TikTok", "https://www.tiktok.com/@{q}", "b_prof", "#EC4899", ("couldn't find this account", "page not available")),
    ("Vimeo", "https://vimeo.com/{q}", "b_prof", "#0EA5E9", ("sorry, we couldn", "page not found")),
    ("Dailymotion", "https://www.dailymotion.com/{q}", "b_prof", "#3B82F6", ("page not found", "404")),
    ("Rumble", "https://rumble.com/c/{q}", "b_prof", "#10B981", ("page not found", "404")),
    ("Odysee", "https://odysee.com/@{q}", "b_prof", "#EC4899", ("channel not found", "404")),
    ("Bitchute", "https://www.bitchute.com/channel/{q}/", "b_prof", "#EF4444", ("page not found", "404")),
    ("Coub", "https://coub.com/{q}", "b_prof", "#3B82F6", ("page not found", "404")),
    ("GIPHY", "https://giphy.com/{q}", "b_prof", "#8B5CF6", ("page not found", "404")),
    ("Tenor", "https://tenor.com/users/{q}", "b_prof", "#0EA5E9", ("page not found", "404")),
    ("Behance", "https://www.behance.net/{q}", "b_prof", "#3B82F6", ("page not found", "oops")),
    ("Dribbble", "https://dribbble.com/{q}", "b_prof", "#EC4899", ("whoops", "page not found")),
    ("DeviantArt", "https://www.deviantart.com/{q}", "b_prof", "#10B981", ("404", "page not found")),
    ("ArtStation", "https://www.artstation.com/{q}", "b_prof", "#0EA5E9", ("page not found", "404")),
    ("Pixiv", "https://www.pixiv.net/en/users/{q}", "b_prof", "#0EA5E9", ("page not found", "404")),
    ("FurAffinity", "https://www.furaffinity.net/user/{q}/", "b_prof", "#F59E0B", ("system error", "cannot be found")),
    ("Sketchfab", "https://sketchfab.com/{q}", "b_prof", "#0EA5E9", ("page not found", "404")),
    ("Thingiverse", "https://www.thingiverse.com/{q}/designs", "b_prof", "#3B82F6", ("page not found", "404")),
    ("Printables", "https://www.printables.com/@{q}", "b_prof", "#F97316", ("page not found", "404")),
    ("Cults3D", "https://cults3d.com/en/users/{q}", "b_prof", "#8B5CF6", ("page not found", "404")),
    ("GrabCAD", "https://grabcad.com/{q}", "b_prof", "#EF4444", ("page not found", "404")),
    ("Unsplash", "https://unsplash.com/@{q}", "b_prof", "#10B981", ("page not found", "404")),
    ("Pexels", "https://www.pexels.com/@{q}/", "b_prof", "#10B981", ("page not found", "404")),
    ("500px", "https://500px.com/p/{q}", "b_prof", "#3B82F6", ("page not found", "404")),
    ("Flickr", "https://www.flickr.com/people/{q}/", "b_prof", "#EC4899", ("page not found", "404")),
    ("VSCO", "https://vsco.co/{q}/gallery", "b_prof", "#9CA3AF", ("page not found", "404")),
    ("EyeEm", "https://www.eyeem.com/u/{q}", "b_prof", "#10B981", ("page not found", "404")),
    ("Lomography", "https://www.lomography.com/homes/{q}", "b_prof", "#EF4444", ("page not found", "404")),
    ("GuruShots", "https://gurushots.com/{q}/photos", "b_prof", "#F59E0B", ("page not found", "404")),
    ("YouPic", "https://youpic.com/photographer/{q}/", "b_prof", "#0EA5E9", ("page not found", "404")),
    ("Ello", "https://ello.co/{q}", "b_prof", "#9CA3AF", ("page not found", "404")),
    ("Carbonmade", "https://{q}.carbonmade.com/", "b_prof", "#8B5CF6", ("page not found", "404")),
    ("Coroflot", "https://www.coroflot.com/{q}", "b_prof", "#F97316", ("page not found", "404")),
    ("Crevado", "https://{q}.crevado.com/", "b_prof", "#3B82F6", ("page not found", "404")),
    ("Portfoliobox", "https://{q}.portfoliobox.net/", "b_prof", "#10B981", ("page not found", "404")),

    # --- Музыка, Подкасты, Аудио и Фриланс/Web3 (35) ---
    ("SoundCloud", "https://soundcloud.com/{q}", "b_mprof", "#F97316", ("we can't find that user", "not found")),
    ("Last.fm", "https://www.last.fm/user/{q}", "b_mprof", "#EF4444", ("page not found", "404")),
    ("Bandcamp", "https://{q}.bandcamp.com/", "b_mprof", "#0EA5E9", ("sorry, that something isn", "not found")),
    ("Genius", "https://genius.com/{q}", "b_mprof", "#F59E0B", ("page not found", "404")),
    ("Mixcloud", "https://www.mixcloud.com/{q}/", "b_mprof", "#8B5CF6", ("page not found", "404")),
    ("Audiomack", "https://audiomack.com/{q}", "b_mprof", "#F59E0B", ("page not found", "404")),
    ("Hearthis.at", "https://hearthis.at/{q}/", "b_mprof", "#EF4444", ("page not found", "404")),
    ("ReverbNation", "https://www.reverbnation.com/{q}", "b_mprof", "#0EA5E9", ("page not found", "404")),
    ("BeatStars", "https://www.beatstars.com/{q}", "b_mprof", "#EF4444", ("page not found", "404")),
    ("Discogs", "https://www.discogs.com/user/{q}", "b_mprof", "#F59E0B", ("page not found", "404")),
    ("RateYourMusic", "https://rateyourmusic.com/~{q}", "b_mprof", "#3B82F6", ("page not found", "404")),
    ("MusicBrainz", "https://musicbrainz.org/user/{q}", "b_mprof", "#EC4899", ("editor not found", "404")),
    ("Musixmatch", "https://www.musixmatch.com/profile/{q}", "b_mprof", "#F97316", ("page not found", "404")),
    ("PromoDJ", "https://promodj.com/{q}", "b_mprof", "#0EA5E9", ("404", "не найдена")),
    ("RealMusic", "https://www.realrocks.ru/{q}/", "b_mprof", "#EF4444", ("404", "не найдена")),
    ("Podchaser", "https://www.podchaser.com/users/{q}", "b_mprof", "#8B5CF6", ("page not found", "404")),
    ("Fiverr", "https://www.fiverr.com/{q}", "b_prof", "#10B981", ("page not found", "404")),
    ("Freelancer", "https://www.freelancer.com/u/{q}", "b_prof", "#0EA5E9", ("page not found", "404")),
    ("FL.ru", "https://www.fl.ru/users/{q}/", "b_prof", "#10B981", ("404", "не найдена")),
    ("Kwork", "https://kwork.ru/user/{q}", "b_prof", "#10B981", ("404", "не найдена")),
    ("Keybase", "https://keybase.io/{q}", "b_repo", "#F97316", ("not a keybase user", "404")),
    ("OpenSea", "https://opensea.io/{q}", "b_prof", "#3B82F6", ("page not found", "404")),
    ("Rarible", "https://rarible.com/{q}", "b_prof", "#F59E0B", ("page not found", "404")),
    ("Foundation", "https://foundation.app/@{q}", "b_prof", "#9CA3AF", ("page not found", "404")),
    ("Mirror.xyz", "https://mirror.xyz/{q}", "b_prof", "#3B82F6", ("page not found", "404")),
    ("Lens", "https://hey.xyz/u/{q}", "b_prof", "#10B981", ("page not found", "404")),
    ("Farcaster", "https://warpcast.com/{q}", "b_prof", "#8B5CF6", ("page not found", "404")),
    ("Archive.org", "https://archive.org/details/@{q}", "b_prof", "#9CA3AF", ("cannot find account", "404")),
    ("Wikipedia", "https://en.wikipedia.org/wiki/User:{q}", "b_wiki", "#F59E0B", ("user account is not registered", "wikipedia does not have a user page")),
    ("RU Wikipedia", "https://ru.wikipedia.org/wiki/Участник:{q}", "b_wiki", "#F59E0B", ("не зарегистрирована", "в википедии нет страницы")),
    ("Fandom", "https://community.fandom.com/wiki/User:{q}", "b_fan", "#A855F7", ("there is currently no text in this page", "404")),
    ("Imgur", "https://imgur.com/user/{q}", "b_prof", "#10B981", ("404", "not found")),
    ("9GAG", "https://9gag.com/u/{q}", "b_prof", "#9CA3AF", ("404", "not found")),
    ("IFTTT", "https://ifttt.com/p/{q}", "b_repo", "#0EA5E9", ("page not found", "404")),
    ("Zapier", "https://zapier.com/shared/{q}", "b_repo", "#F97316", ("page not found", "404")),
]


def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(default, dict) and isinstance(data, dict):
                    merged = dict(default)
                    merged.update(data)
                    return merged
                return data
        except Exception:
            return default
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


def tr(key, **kwargs):
    text = TRANSLATIONS.get(settings.get("ui_lang", "ru"), TRANSLATIONS["en"]).get(key, TRANSLATIONS["en"].get(key, key))
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


def get_page_title(html_text):
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        return soup.title.get_text(" ", strip=True) if soup.title else ""
    except Exception:
        return ""


def parse_phone_variants(raw_phone):
    digits = re.sub(r"\D", "", raw_phone or "")
    if len(digits) < 7:
        return "", "", "", []
    country = "Неизвестный регион"
    operator = ""
    norm = digits
    if len(digits) == 11 and digits.startswith("8"):
        norm = "7" + digits[1:]
    for pref, cname in PHONE_PREFIXES:
        if norm.startswith(pref):
            country = cname
            break
    if len(norm) == 11 and norm.startswith("7"):
        def_code = norm[1:4]
        if def_code in KZ_MOBILE_DEF:
            country = "Казахстан (KZ)"
            operator = KZ_MOBILE_DEF[def_code]
        elif def_code in RU_MOBILE_DEF:
            country = "Россия (RU)"
            operator = RU_MOBILE_DEF[def_code]
    variants = [f"+{norm}", norm]
    if len(norm) == 11 and norm.startswith("7"):
        d = norm[1:]
        variants.extend([
            f"8{d}",
            f"+7 ({d[:3]}) {d[3:6]}-{d[6:8]}-{d[8:]}",
            f"8 ({d[:3]}) {d[3:6]}-{d[6:8]}-{d[8:]}",
            f"{d[:3]}-{d[3:6]}-{d[6:8]}-{d[8:]}"
        ])
    elif len(norm) == 12 and norm.startswith("380"):
        d = norm[3:]
        variants.extend([f"0{d}", f"+380 {d[:2]} {d[2:5]} {d[5:7]} {d[7:]}"])
    return norm, country, operator, list(dict.fromkeys(variants))


ctk.set_appearance_mode(settings.get("theme", "dark"))

app = ctk.CTk()
app.geometry("1200x760")
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

# ================= БОКОВОЕ МЕНЮ =================
sidebar = ctk.CTkFrame(app, width=225, corner_radius=0, fg_color=bg_c["sidebar"])
sidebar.grid(row=0, column=0, sticky="nsew")
sidebar.grid_rowconfigure(6, weight=1)

brand_row = ctk.CTkFrame(sidebar, fg_color="transparent")
brand_row.grid(row=0, column=0, padx=14, pady=22, sticky="ew")

_sidebar_pil = render_brand_logo(64, accent=acc_m, bg="#111113")
_sidebar_ctk_img = ctk.CTkImage(light_image=_sidebar_pil, dark_image=_sidebar_pil, size=(34, 34))
_icon_refs["sidebar"] = _sidebar_ctk_img

sidebar_logo_lbl = ctk.CTkLabel(brand_row, text="", image=_sidebar_ctk_img)
sidebar_logo_lbl.pack(side="left", padx=(4, 10))

brand_txt_col = ctk.CTkFrame(brand_row, fg_color="transparent")
brand_txt_col.pack(side="left", fill="x")
ctk.CTkLabel(brand_txt_col, text="DESCENDING", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(anchor="w")
ctk.CTkLabel(brand_txt_col, text="SCAN", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray", anchor="w").pack(anchor="w")


def update_sidebar_logo():
    am, _ = get_accent()
    pil_img = render_brand_logo(64, accent=am, bg="#111113")
    ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(34, 34))
    _icon_refs["sidebar"] = ctk_img
    sidebar_logo_lbl.configure(image=ctk_img)
    apply_window_icon()


ALL_PAGES = []


def switch_page(page):
    for p in ALL_PAGES:
        if p is not page:
            p.grid_remove()
    page.grid(row=0, column=0, sticky="nsew", padx=25, pady=(20, 6))
    page.tkraise()


nav_style = {
    "height": 42, "corner_radius": 8, "fg_color": "transparent",
    "text_color": ("#111827", "#E5E7EB"), "hover_color": ("#D1D5DB", "#27272A"),
    "anchor": "w", "font": ctk.CTkFont(size=14)
}

btn_nav_s = ctk.CTkButton(sidebar, text=tr("nav_s"), command=lambda: switch_page(page_search), **nav_style)
btn_nav_s.grid(row=1, column=0, padx=12, pady=4, sticky="ew")

btn_nav_a = ctk.CTkButton(sidebar, text=tr("nav_a"), command=lambda: [refresh_saved(), switch_page(page_saved)], **nav_style)
btn_nav_a.grid(row=2, column=0, padx=12, pady=4, sticky="ew")

btn_nav_c = ctk.CTkButton(sidebar, text=tr("nav_c"), command=lambda: switch_page(page_settings_wrap), **nav_style)
btn_nav_c.grid(row=3, column=0, padx=12, pady=4, sticky="ew")

btn_nav_d = ctk.CTkButton(sidebar, text=tr("nav_d"), command=lambda: switch_page(page_debug), **nav_style)
btn_nav_d.grid(row=4, column=0, padx=12, pady=4, sticky="ew")


def toggle_theme():
    new_theme = "dark" if theme_switch.get() else "light"
    ctk.set_appearance_mode(new_theme)
    settings["theme"] = new_theme
    save_json(SETTINGS_FILE, settings)


theme_switch = ctk.CTkSwitch(sidebar, text=tr("dark"), command=toggle_theme, progress_color=acc_m)
if settings.get("theme", "dark") == "dark":
    theme_switch.select()
theme_switch.grid(row=7, column=0, padx=20, pady=20, sticky="w")

# ================= ОСНОВНАЯ ОБЛАСТЬ =================
main_area = ctk.CTkFrame(app, corner_radius=0, fg_color=bg_c["main"])
main_area.grid(row=0, column=1, sticky="nsew")
main_area.grid_rowconfigure(0, weight=1)
main_area.grid_rowconfigure(1, weight=0)
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


log_debug(f"{APP_NAME} by {AUTHOR_NAME} | Platforms: {len(HTML_PLATFORMS) + 20}+ | deep-translator={'ON' if HAS_DEEP_TRANS else 'fallback'}")

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
        except Exception as e:
            log_debug(f"Translate err: {repr(e)}")
            out.append(chunk)
    return NL.join(out)


def ddgs_search(query_str, max_results=20, region="ru-ru"):
    safe = "moderate" if settings.get("safe_search", True) else "off"
    for reg in ([region] if region == "wt-wt" else [region, "wt-wt"]):
        for backend in ("auto", "html", "lite"):
            try:
                log_debug(f"DDGS [{backend} | {reg} | safe={safe}] -> '{query_str}'")
                with DDGS() as ddgs:
                    try:
                        res = list(ddgs.text(query_str, region=reg, safesearch=safe, max_results=max_results, backend=backend))
                    except TypeError:
                        res = list(ddgs.text(query_str, region=reg, max_results=max_results))
                    if res:
                        return res
            except Exception as err:
                log_debug(f"DDGS err: {repr(err)}")
                time.sleep(0.3)
    return []


def ddgs_news(query_str, max_results=5, region="ru-ru"):
    safe = "moderate" if settings.get("safe_search", True) else "off"
    try:
        with DDGS() as ddgs:
            return list(ddgs.news(query_str, region=region, safesearch=safe, max_results=max_results)) or []
    except Exception:
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
            }, headers={"User-Agent": "DescendingScan/1.0"}, timeout=7)
            if r.status_code != 200:
                continue
            pages = r.json().get("query", {}).get("pages", {})
            if pages:
                pg = next(iter(pages.values()))
                rt, ex, fu = pg.get("title", ""), pg.get("extract", "").strip(), pg.get("fullurl", "")
                en_t = rt if lang == "en" else next((ll.get("*", "") for ll in pg.get("langlinks", []) if ll.get("lang") == "en"), "")
                if rt and ex and fu:
                    blob = (rt + " " + en_t + " " + ex[:250]).lower()
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
        ok = any(t and (t in nl or nl in t) for t in (query.lower(), (en_title or "").lower()))
        if not ok and nw and qw:
            ok = len(set(nw) & set(qw)) >= min(2, len(nw))
        if not ok:
            return None
        p = top.get("price")
        p_str = f"{p['final']/100:.2f} {p.get('currency', 'USD')}" if (p and "final" in p) else "Free / Store"
        return {"title": f"{name} — Steam", "href": f"https://store.steampowered.com/app/{app_id}/", "body": f"Steam AppID: {app_id} | {p_str}"}
    except Exception:
        return None


def extract_focused_text(url, keywords, max_chars=950):
    try:
        dl = trafilatura.fetch_url(url)
        text = trafilatura.extract(dl) if dl else ""
        if not text:
            return ""
        lines = [ln.strip() for ln in text.split(NL) if len(ln.strip()) > 35]
        return NL.join([ln for ln in lines if any(kw in ln.lower() for kw in keywords)] or lines[:4])[:max_chars]
    except Exception:
        return ""


# ================= РЕЖИМ ЧТЕНИЯ + ПЕРЕВОД =================
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

    def run_tr():
        res = translate_text(cur, target_lang=target)
        app.after(0, lambda: [reader_textbox.delete("1.0", "end"), reader_textbox.insert("1.0", res), reader_state.__setitem__("translated", True), btn_r_tr.configure(state="normal", text=tr("orig_btn"))])

    threading.Thread(target=run_tr, daemon=True).start()


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
    if cached_text:
        reader_textbox.insert("1.0", header + cached_text)
        return
    if url.startswith(("osint://", "viber://", "skype:")):
        reader_textbox.insert("1.0", header + title)
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

for mk, tk_key in (("search", "m_search"), ("dossier", "m_dossier"), ("profile", "m_profile")):
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
profile_form.grid_columnconfigure(0, weight=1)
profile_form.grid_columnconfigure(1, weight=1)

lbl_f_nick = ctk.CTkLabel(profile_form, text=tr("lbl_nick"), font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
lbl_f_nick.grid(row=0, column=0, padx=(14, 7), pady=(10, 2), sticky="w")
ent_nick = ctk.CTkEntry(profile_form, placeholder_text=tr("ph_nick"), height=36, corner_radius=8, border_color=acc_m)
ent_nick.grid(row=1, column=0, padx=(14, 7), pady=(0, 8), sticky="ew")

lbl_f_email = ctk.CTkLabel(profile_form, text=tr("lbl_email"), font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
lbl_f_email.grid(row=0, column=1, padx=(7, 14), pady=(10, 2), sticky="w")
ent_email = ctk.CTkEntry(profile_form, placeholder_text=tr("ph_email"), height=36, corner_radius=8, border_color=acc_m)
ent_email.grid(row=1, column=1, padx=(7, 14), pady=(0, 8), sticky="ew")

lbl_f_fio = ctk.CTkLabel(profile_form, text=tr("lbl_fio"), font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
lbl_f_fio.grid(row=2, column=0, padx=(14, 7), pady=(2, 2), sticky="w")
ent_fio = ctk.CTkEntry(profile_form, placeholder_text=tr("ph_fio"), height=36, corner_radius=8, border_color=acc_m)
ent_fio.grid(row=3, column=0, padx=(14, 7), pady=(0, 10), sticky="ew")

lbl_f_phone = ctk.CTkLabel(profile_form, text=tr("lbl_phone"), font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
lbl_f_phone.grid(row=2, column=1, padx=(7, 14), pady=(2, 2), sticky="w")
ent_phone = ctk.CTkEntry(profile_form, placeholder_text=tr("ph_phone"), height=36, corner_radius=8, border_color=acc_m)
ent_phone.grid(row=3, column=1, padx=(7, 14), pady=(0, 10), sticky="ew")

for _ent in (ent_nick, ent_email, ent_fio, ent_phone):
    _ent.bind("<Return>", lambda e: run_active_mode())

form_actions = ctk.CTkFrame(profile_form, fg_color="transparent")
form_actions.grid(row=4, column=0, columnspan=2, padx=14, pady=(0, 12), sticky="ew")

lbl_form_hint = ctk.CTkLabel(form_actions, text=tr("form_hint"), font=ctk.CTkFont(size=11), text_color="gray", anchor="w")
lbl_form_hint.pack(side="left", fill="x", expand=True)


def clear_profile_form():
    for ent in (ent_nick, ent_email, ent_fio, ent_phone):
        ent.delete(0, "end")
    ent_nick.focus_set()


btn_prof_clear = ctk.CTkButton(form_actions, text=tr("clear"), width=95, height=36, corner_radius=8, fg_color=bg_c["inactive"], text_color=("#111827", "#E5E7EB"), command=clear_profile_form)
btn_prof_clear.pack(side="right", padx=(8, 0))

profile_go_btn = ctk.CTkButton(form_actions, text=tr("go"), width=140, height=36, corner_radius=8, fg_color=acc_m, hover_color=acc_h, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: run_active_mode())
profile_go_btn.pack(side="right")

status_row = ctk.CTkFrame(page_search, fg_color="transparent")
status_row.pack(fill="x", pady=(2, 6))

status_label = ctk.CTkLabel(status_row, text=tr("st_ready"), text_color="gray", font=ctk.CTkFont(size=12), anchor="w")
status_label.pack(side="left", fill="x", expand=True)

last_rendered_cards = []


def translate_visible_cards():
    if not last_rendered_cards:
        return
    target = settings.get("ui_lang", "ru")
    btn_tr_cards.configure(state="disabled", text=tr("tr_busy"))

    def worker():
        out = [{"title": translate_text(c["title"], target_lang=target), "url": c["url"], "desc": translate_text(c["desc"], target_lang=target), "badge": c["badge"], "badge_color": c["badge_color"], "cached": c.get("cached")} for c in last_rendered_cards]
        app.after(0, lambda: [last_rendered_cards.clear(), last_rendered_cards.extend(out), rerender_search_cards(), btn_tr_cards.configure(state="normal", text=tr("tr_cards"))])

    threading.Thread(target=worker, daemon=True).start()


btn_tr_cards = ctk.CTkButton(status_row, text=tr("tr_cards"), width=165, height=26, corner_radius=6, fg_color=bg_c["inactive"], text_color=("#111827", "#E5E7EB"), font=ctk.CTkFont(size=12), command=translate_visible_cards)
btn_tr_cards.pack(side="right")

results_box = ctk.CTkScrollableFrame(page_search, corner_radius=10, fg_color=bg_c["box"])
results_box.pack(fill="both", expand=True)


def set_search_mode(mode_key):
    global current_mode
    current_mode = mode_key
    am, ah = get_accent()
    bg_i = get_bg()["inactive"]
    for k, btn in mode_buttons.items():
        if k == current_mode:
            btn.configure(fg_color=am, hover_color=ah, text_color="#FFFFFF")
        else:
            btn.configure(fg_color=bg_i, hover_color=("#D1D5DB", "#3F3F46"), text_color=("#111827", "#E5E7EB"))

    if current_mode == "profile":
        top_bar.pack_forget()
        profile_form.pack_forget()
        profile_form.pack(fill="x", pady=(0, 8), before=status_row)
        ent_nick.focus_set()
    else:
        profile_form.pack_forget()
        top_bar.pack_forget()
        top_bar.pack(fill="x", pady=(0, 6), before=status_row)
        search_entry.configure(placeholder_text=tr(f"ph_{current_mode}"))
        search_entry.focus_set()


set_search_mode("search")


def set_busy(busy):
    state = "disabled" if busy else "normal"
    app.after(0, lambda s=state: [go_btn.configure(state=s), profile_go_btn.configure(state=s)])


def save_item(title, url, desc, cached_text=None):
    if any(i["url"] == url for i in saved_pages):
        status_label.configure(text=tr("st_dup"))
        return
    status_label.configure(text=tr("st_saving"))

    def bg():
        try:
            if cached_text or url.startswith(("dossier://", "osint://", "viber://", "skype:")):
                ft = cached_text or desc
            else:
                dl = trafilatura.fetch_url(url)
                ft = (trafilatura.extract(dl) if dl else None) or desc
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
    card = ctk.CTkFrame(parent, corner_radius=10, fg_color=bg["card"], border_width=0)
    card.pack(fill="x", pady=6, padx=6)

    hdr = ctk.CTkFrame(card, fg_color="transparent")
    hdr.pack(fill="x", padx=14, pady=(10, 4))
    ctk.CTkLabel(hdr, text=title, font=ctk.CTkFont(size=15, weight="bold"), anchor="w").pack(side="left", fill="x", expand=True)
    if badge:
        ctk.CTkLabel(hdr, text=badge, font=ctk.CTkFont(size=11, weight="bold"), text_color=badge_color).pack(side="right", padx=10)

    ctk.CTkLabel(card, text=url, font=ctk.CTkFont(size=12), text_color=am, anchor="w").pack(fill="x", padx=14)
    ctk.CTkLabel(card, text=desc, font=ctk.CTkFont(size=13), wraplength=820, justify="left", anchor="w").pack(fill="x", padx=14, pady=6)

    row = ctk.CTkFrame(card, fg_color="transparent")
    row.pack(fill="x", padx=14, pady=(4, 10))
    if not url.startswith(("dossier://", "osint://")):
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


# ================= КЛАССИФИКАТОР И АНТИ-МУСОР =================
def classify_source(url, title=""):
    dom = urlparse((url or "").lower()).netloc.replace("www.", "")
    low_t = (title or "").lower()
    if "wikipedia.org" in dom:
        return tr("b_wiki"), "#F59E0B", 40
    if "steampowered.com" in dom or "steamcommunity.com" in dom:
        return tr("b_steam"), "#0EA5E9", 72
    if any(w in dom for w in ("fandom.com", "wiki.gg", "paradoxwikis.com", "liquipedia.net", "gamepedia.com", "fextralife.com", ".wiki")) or "fandom" in low_t:
        return tr("b_fan"), "#A855F7", 65
    if any(c in dom for c in ("github.com", "gitlab.com", "bitbucket.org", "pypi.org", "npmjs.com", "huggingface.co", "docker.com")):
        return tr("b_code"), "#10B981", 74
    if any(s in dom for s in ("epicgames.com", "gog.com", "itch.io", "nexusmods.com", "curseforge.com", "modrinth.com", "roblox.com", "riotgames.com", "ea.com", "ubisoft.com", "xbox.com", "playstation.com")):
        return tr("b_store"), "#EC4899", 60
    if any(m in dom for m in ("spotify.com", "soundcloud.com", "music.yandex.", "bandcamp.com", "last.fm", "genius.com", "deezer.com", "audiomack.com")):
        return tr("b_mus"), "#F43F5E", 55
    if any(f in dom for f in ("reddit.com", "4pda.", "habr.com", "stackoverflow.com", "pikabu.ru", "dtf.ru", "stopgame.ru", "playground.ru")):
        return tr("b_for"), "#14B8A6", 55
    if any(v in dom for v in ("youtube.com", "youtu.be", "twitch.tv", "vkvideo.ru", "kick.com", "vimeo.com")):
        return tr("b_vid"), "#EF4444", 36
    if any(soc in dom for soc in ("vk.com", "t.me", "telegram.org", "x.com", "twitter.com", "instagram.com", "tiktok.com", "bsky.app", "ok.ru", "linkedin.com")):
        return tr("b_soc"), "#38BDF8", 40
    if any(n in dom for n in ("bbc.", "reuters.", "cnn.", "rbc.ru", "lenta.ru", "ria.ru", "tass.ru", "pravda.com.ua", "tengrinews.kz", "spiegel.de", "lemonde.fr", "yle.fi", "onet.pl")):
        return tr("b_news"), "#F59E0B", 42
    return tr("b_art"), "#9CA3AF", 15


def is_relevant_item(url, title, body, query, stems, raw_words):
    if is_adult_content(url, title, body):
        return False
    if not has_cjk(query) and has_cjk(title + " " + body):
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
    clean_q = {"".join(q_words)}
    if wiki_data:
        clean_q.update({"".join(extract_words(wiki_data.get("en_title", ""))), "".join(extract_words(wiki_data.get("raw_title", "")))})
    clean_q.discard("")

    non_off = ("wikipedia.org", "fandom.com", "wiki.gg", "paradoxwikis.com", "liquipedia.net", "reddit.com", "habr.com", "4pda.", "pikabu.ru", "dtf.ru", "ixbt.com", "stopgame.ru", "playground.ru", "stackoverflow.com", "apps.apple.com", "play.google.com", "bbc.", "cnn.", "rbc.ru", "lenta.ru", "ria.ru", "tass.ru", "forbes.", "youtube.com", "youtu.be", "twitch.tv")
    seen, dom_cnt, unique = set(), {}, []
    for item in ([steam_card] if steam_card else []) + list(raw_results):
        url = item.get("href", "")
        if not url:
            continue
        dom = urlparse(url.lower()).netloc.replace("www.", "")
        key = normalize_url_key(url)
        if any(b in dom for b in GARBAGE_DOMAINS) or key in seen:
            continue
        title, body = item.get("title", ""), item.get("body", "")
        if item is not steam_card and not is_relevant_item(url, title, body, query, stems, q_words):
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
        sc = (150 if base and (base in clean_q or base in all_words) else (80 if dom_hit else (65 if "steampowered.com" in dom and t_hit else (60 if t_hit and ("официальн" in title or "official" in title) else 0))))
        if len(path) == 0 or path in ("ru", "en", "de", "uk", "pl", "fr", "fi", "kk", "index.html", "home"):
            sc += 40 if dom_hit else 10
        if idx < 3 and dom_hit:
            sc += (20 - idx * 5)
        if sc > best_off:
            best_off, off_card = sc, it

    off_key = normalize_url_key(off_card.get("href", "")) if off_card else ""
    final = []
    if off_card:
        final.append((tr("b_off"), "#3B82F6", off_card))
    if wiki_card:
        final.append((tr("b_wiki"), "#F59E0B", wiki_card))

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
        for st in alpha_stems:
            sc += (16 if st in lt else 0) + (10 if st in lu else 0) + (5 if st in lb else 0)
        rest.append((sc, badge, col, it))
    rest.sort(key=lambda x: x[0], reverse=True)
    final.extend((b, c, it) for _, b, c, it in rest)
    return final


# ================= ВОРКЕРЫ: ПОИСК / ДОСЬЕ / OSINT-АНКЕТА (235+) =================
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
            if not gh_only:
                raw.extend({"title": n.get("title", ""), "href": n.get("url", ""), "body": n.get("body", "")} for n in ddgs_news(query, max_results=5, region=meta["region"]) if n.get("url"))
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


def perform_dossier(query):
    global reader_back_target, current_reader_doc
    reader_back_target = page_search
    reader_state["original"], reader_state["translated"] = "", False
    meta, scope = get_lang_meta(), settings.get("search_scope", "global")
    reg = meta["region"]
    current_reader_doc = {"title": f"{tr('m_dossier')}: {query}", "url": f"dossier://{query.lower()}", "desc": tr("d_sub")}
    out = lambda chunk: app.after(0, lambda c=chunk: [reader_textbox.insert("end", c), reader_textbox.see("end")])

    try:
        set_busy(True)
        app.after(0, lambda: [btn_r_tr.configure(text=tr("tr_btn"), state="normal"), reader_title_lbl.configure(text=f"🧠 {query}"), reader_textbox.delete("1.0", "end"), switch_page(page_reader)])
        sep = "=" * 68
        out(tr("d_h", q=query.upper()) + NL + sep + NL + tr("d_sub") + NL + NL)

        out(tr("d1") + NL + ("-" * 50) + NL)
        wiki = fetch_wikipedia(query, scope=scope)
        en_name = wiki.get("en_title", "") if wiki else ("" if has_cyrillic(query) else query)
        q_words = extract_words(query) or [query.lower().strip()]
        w_words = (extract_words(wiki.get("raw_title", "")) + extract_words(wiki.get("en_title", ""))) if wiki else []
        all_words = list(dict.fromkeys(q_words + w_words))
        stems = [w[:-1] if (len(w) > 4 and not w.isdigit()) else w for w in all_words]

        if wiki:
            out(wiki["summary"] + NL + f"{tr('r_src')}: {wiki['url']}" + NL + NL)
        else:
            ov = [it for it in ddgs_search(f"{query} {meta['q_ov']}", max_results=6, region=reg)
                  if is_relevant_item(it.get("href", ""), it.get("title", ""), it.get("body", ""), query, stems, q_words)]
            out((NL.join(f"• {it.get('title', '')}: {it.get('body', '')}" for it in ov[:3]) + NL + NL) if ov else tr("d_none") + NL + NL)
        time.sleep(0.35)

        out(tr("d2") + NL + ("-" * 50) + NL)
        steam, shown = fetch_steam_store_match(query, en_title=en_name), set()
        if steam:
            shown.add(normalize_url_key(steam["href"]))
            out(f"• {steam['title']}{NL}  {steam['href']}{NL}  {steam['body']}{NL}")
        for it in ddgs_search(f"{query} {meta['q_buy']}", max_results=8, region=reg):
            u, k = it.get("href", ""), normalize_url_key(it.get("href", ""))
            t, b = it.get("title", ""), it.get("body", "")
            if u and k not in shown and not any(g in urlparse(u.lower()).netloc for g in GARBAGE_DOMAINS) and is_relevant_item(u, t, b, query, stems, q_words):
                shown.add(k)
                out(f"• {t}{NL}  {u}{NL}  {b}{NL}")
                if len(shown) >= 5:
                    break
        out(NL if shown else tr("d_none") + NL + NL)
        time.sleep(0.35)

        out(tr("d3") + NL + ("-" * 50) + NL)
        target_name = en_name or query
        errs = ddgs_search(f'"{query}" {meta["q_err"]}', max_results=8, region=reg)
        if not errs:
            errs = ddgs_search(f"{query} {meta['q_err']}", max_results=8, region=reg)
        if scope == "global" and target_name and reg != "us-en":
            time.sleep(0.3)
            errs.extend(ddgs_search(f'"{target_name}" common bugs crashes errors fix', max_results=6, region="us-en"))
        kw = ["ошибк", "баг", "вылет", "лаг", "решен", "фикс", "crash", "error", "bug", "fix", "issue", "fehler", "błąd", "erreur", "virhe"]
        clean_e, seen_e = [], set()
        for it in errs:
            u, k = it.get("href", ""), normalize_url_key(it.get("href", ""))
            t, b = it.get("title", ""), it.get("body", "")
            if k and k not in seen_e and not any(g in urlparse(u.lower()).netloc for g in GARBAGE_DOMAINS) and is_relevant_item(u, t, b, query, stems, q_words):
                seen_e.add(k)
                clean_e.append(it)
        if clean_e:
            for it in clean_e[:5]:
                out(f"• {it.get('title', '')}{NL}  {it.get('body', '')}{NL}  {it.get('href', '')}{NL}")
            ext = 0
            for it in clean_e[:3]:
                u = it.get("href", "")
                if u and "youtube.com" not in u:
                    chunk = extract_focused_text(u, kw, max_chars=800)
                    if chunk and not is_adult_content(u, "", chunk):
                        ext += 1
                        out(f"{NL}[{urlparse(u).netloc}]:{NL}{chunk}{NL}")
                        if ext >= 2:
                            break
            out(NL)
        else:
            out(tr("d_none") + NL + NL)
        time.sleep(0.35)

        out(tr("d4") + NL + ("-" * 50) + NL)
        revs = [it for it in ddgs_search(f"{query} {meta['q_rev']}", max_results=7, region=reg)
                if not any(g in urlparse(it.get("href", "").lower()).netloc for g in GARBAGE_DOMAINS)
                and is_relevant_item(it.get("href", ""), it.get("title", ""), it.get("body", ""), query, stems, q_words)]
        out((NL.join(f"• {it.get('title', '')}{NL}  {it.get('body', '')}{NL}  {it.get('href', '')}" for it in revs[:4]) + NL + NL) if revs else tr("d_none") + NL + NL)

        out(tr("d5") + NL + ("-" * 50) + NL)
        news = [n for n in ddgs_news(query, max_results=5, region=reg) if not is_adult_content(n.get("url", ""), n.get("title", ""), n.get("body", ""))]
        out((NL.join(f"• {n.get('title', '')} ({str(n.get('date', ''))[:10]}){NL}  {n.get('url', '')}" for n in news[:4]) + NL + NL) if news else tr("d_none") + NL + NL)
        out(sep + NL + tr("d_done") + NL)
    except Exception as e:
        log_debug("DOSSIER ERR:" + NL + traceback.format_exc())
        out(NL + f"Error: {e}" + NL)
    finally:
        set_busy(False)


def check_api_profiles(nick):
    q, hits = quote(nick), []

    def api_github():
        r = HTTP.get(f"https://api.github.com/users/{q}", headers={"Accept": "application/vnd.github+json"}, timeout=6)
        if r.status_code == 200:
            u = r.json()
            hits.append((tr("b_prof"), "#10B981", {"title": f"GitHub — {u.get('name') or u.get('login', nick)} (@{u.get('login', nick)})", "href": u.get("html_url", f"https://github.com/{nick}"), "body": f"Repos: {u.get('public_repos', 0)} | Followers: {u.get('followers', 0)} | {u.get('bio') or ''}"}))
            r2 = HTTP.get(f"https://api.github.com/users/{q}/repos", params={"sort": "updated", "per_page": 5}, timeout=6)
            if r2.status_code == 200:
                for rp in r2.json():
                    hits.append((tr("b_repo"), "#3B82F6", {"title": f"GitHub Repo: {rp.get('full_name', '')} (★ {rp.get('stargazers_count', 0)} | {rp.get('language') or 'Code'})", "href": rp.get("html_url", ""), "body": rp.get("description") or "GitHub repository"}))

    def api_roblox():
        r = HTTP.post("https://users.roblox.com/v1/usernames/users", json={"usernames": [nick], "excludeBannedUsers": False}, timeout=6)
        if r.status_code == 200 and r.json().get("data"):
            u = r.json()["data"][0]
            hits.append((tr("b_gprof"), "#0EA5E9", {"title": f"Roblox — {u.get('displayName', nick)} (@{u.get('name', nick)})", "href": f"https://www.roblox.com/users/{u.get('id')}/profile", "body": f"Roblox ID: {u.get('id')}"}))

    def api_dota():
        r = HTTP.get("https://api.opendota.com/api/search", params={"q": nick}, timeout=6)
        if r.status_code == 200:
            pl, low = r.json(), nick.lower()
            exact = [p for p in pl if (p.get("personaname") or "").lower() == low]
            for p in (exact[:2] if exact else [p for p in pl if low in (p.get("personaname") or "").lower()][:1]):
                hits.append((tr("b_gprof"), "#EF4444", {"title": f"Dota 2 (Dotabuff) — {p.get('personaname', nick)}", "href": f"https://www.dotabuff.com/players/{p.get('account_id')}", "body": f"Account ID: {p.get('account_id')} | Last match: {str(p.get('last_match_time') or '?')[:10]}"}))

    def api_twitch():
        r = HTTP.get("https://api.ivr.fi/v2/twitch/user", params={"login": nick}, timeout=6)
        if r.status_code == 200 and isinstance(r.json(), list) and r.json():
            u = r.json()[0]
            hits.append((tr("b_gprof"), "#A855F7", {"title": f"Twitch — {u.get('displayName', nick)}", "href": f"https://www.twitch.tv/{u.get('login', nick)}", "body": f"Followers: {u.get('followers', 0)} | {u.get('bio') or 'Twitch'}"}))

    def api_kick():
        r = HTTP.get(f"https://kick.com/api/v1/channels/{q}", timeout=6)
        if r.status_code == 200 and r.json().get("slug"):
            d = r.json()
            hits.append((tr("b_gprof"), "#10B981", {"title": f"Kick — {d.get('slug')}", "href": f"https://kick.com/{d.get('slug')}", "body": f"Followers: {d.get('followers_count', 0)}"}))

    def api_faceit():
        r = HTTP.get(f"https://api.faceit.com/users/v1/nicknames/{q}", timeout=6)
        if r.status_code == 200 and r.json().get("payload", {}).get("nickname"):
            p = r.json()["payload"]
            hits.append((tr("b_gprof"), "#F97316", {"title": f"FACEIT — {p['nickname']}", "href": f"https://www.faceit.com/en/players/{p['nickname']}", "body": f"Country: {p.get('country', '?')} | Games: {', '.join(p.get('games', {}).keys())}"}))

    def api_minecraft():
        r = HTTP.get(f"https://api.mojang.com/users/profiles/minecraft/{q}", timeout=6)
        if r.status_code == 200 and r.text.strip():
            d = r.json()
            hits.append((tr("b_gprof"), "#10B981", {"title": f"Minecraft (Java) — {d.get('name', nick)}", "href": f"https://namemc.com/profile/{d.get('name', nick)}", "body": f"UUID: {d.get('id', '')}"}))

    def api_reddit():
        r = HTTP.get(f"https://www.reddit.com/user/{q}/about.json", headers={"User-Agent": "DescendingScan/1.0"}, timeout=6)
        if r.status_code == 200:
            d = r.json().get("data", {})
            if d and not d.get("is_suspended"):
                hits.append((tr("b_prof"), "#F97316", {"title": f"Reddit — u/{d.get('name', nick)}", "href": f"https://www.reddit.com/user/{nick}", "body": f"Karma: {d.get('total_karma', 0)}"}))

    def api_gitlab():
        r = HTTP.get("https://gitlab.com/api/v4/users", params={"username": nick}, timeout=6)
        if r.status_code == 200 and r.json():
            u = r.json()[0]
            hits.append((tr("b_repo"), "#10B981", {"title": f"GitLab — {u.get('name', nick)} (@{u.get('username', nick)})", "href": u.get("web_url", ""), "body": f"State: {u.get('state', 'active')}"}))

    def api_telegram():
        url = f"https://t.me/{q}"
        r = HTTP.get(url, timeout=6)
        if r.status_code == 200 and "tgme_page_title" in r.text:
            soup = BeautifulSoup(r.text, "html.parser")
            et, ed, ee = soup.select_one(".tgme_page_title"), soup.select_one(".tgme_page_description"), soup.select_one(".tgme_page_extra")
            if et and (ed or ee):
                hits.append((tr("b_prof"), "#0EA5E9", {"title": f"Telegram — {et.get_text(' ', strip=True)} (@{nick})", "href": url, "body": (ed.get_text(" ", strip=True) if ed else ee.get_text(" ", strip=True))}))

    def api_misc():
        checks = [
            (f"https://api.chess.com/pub/player/{q.lower()}", "Chess.com", "b_gprof", "#10B981", lambda d: (d.get("username"), d.get("url"), f"Status: {d.get('status')}")),
            (f"https://lichess.org/api/user/{q}", "Lichess", "b_gprof", "#10B981", lambda d: (d.get("username"), d.get("url"), f"Games: {d.get('count', {}).get('all', 0)}")),
            (f"https://www.speedrun.com/api/v1/users?lookup={q}", "Speedrun.com", "b_gprof", "#F59E0B", lambda d: (d["data"][0]["names"]["international"], d["data"][0]["weblink"], "Speedrunner") if d.get("data") else None),
            (f"https://shikimori.one/api/users/{q}", "Shikimori", "b_prof", "#EC4899", lambda d: (d.get("nickname"), d.get("url") or f"https://shikimori.one/{nick}", "Shikimori user") if d.get("nickname") else None),
            (f"https://api.modrinth.com/v2/user/{q}", "Modrinth", "b_gprof", "#10B981", lambda d: (d.get("username"), f"https://modrinth.com/user/{d.get('username')}", d.get("bio") or "Modrinth") if d.get("username") else None),
            (f"https://www.codewars.com/api/v1/users/{q}", "Codewars", "b_repo", "#EF4444", lambda d: (d.get("username"), f"https://www.codewars.com/users/{d.get('username')}", f"Honor: {d.get('honor', 0)}") if d.get("username") else None),
            (f"https://hub.docker.com/v2/users/{q}/", "DockerHub", "b_repo", "#0EA5E9", lambda d: (d.get("username"), f"https://hub.docker.com/u/{d.get('username')}", "DockerHub") if d.get("username") else None),
            (f"https://huggingface.co/api/users/{q}/overview", "HuggingFace", "b_repo", "#F59E0B", lambda d: (d.get("user"), f"https://huggingface.co/{d.get('user')}", f"Models: {d.get('numModels', 0)}") if d.get("user") else None),
            (f"https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor={q}.bsky.social", "Bluesky", "b_prof", "#0EA5E9", lambda d: (d.get("displayName") or d.get("handle"), f"https://bsky.app/profile/{d.get('handle')}", d.get("description") or "Bluesky") if d.get("handle") else None),
        ]
        for url, pname, bkey, col, parser in checks:
            try:
                r = HTTP.get(url, headers={"User-Agent": "DescendingScan/1.0"}, timeout=5)
                if r.status_code == 200:
                    parsed = parser(r.json())
                    if parsed and parsed[0] and parsed[1]:
                        hits.append((tr(bkey), col, {"title": f"{pname} — {parsed[0]}", "href": parsed[1], "body": str(parsed[2] or pname)}))
            except Exception:
                pass

    with ThreadPoolExecutor(max_workers=12) as pool:
        for f in as_completed([pool.submit(fn) for fn in (api_github, api_roblox, api_dota, api_twitch, api_kick, api_faceit, api_minecraft, api_reddit, api_gitlab, api_telegram, api_misc)]):
            try:
                f.result()
            except Exception:
                pass
    return hits


def check_html_platform(spec, nick):
    name, url_tpl, bkey, col, bad_markers = spec
    url = url_tpl.format(q=quote(nick))
    try:
        r = HTTP.get(url, timeout=4.5, allow_redirects=True)
        if r.status_code != 200 or any(x in r.url.lower() for x in ("/login", "/signin", "/404", "error")):
            return None
        text_low, title = r.text[:140000].lower(), get_page_title(r.text)
        t_low = title.lower()
        if any(b in t_low or b in text_low for b in bad_markers):
            return None
        if (name == "YouTube" and '"channelid"' not in text_low) or (name == "TikTok" and nick.lower() not in text_low):
            return None
        title = title if (title and len(title) >= 2) else f"{name} — {nick}"
        return (tr(bkey), col, {"title": f"{name} — {title}" if name.lower() not in t_low else title, "href": url, "body": f"{name}: {url}"})
    except Exception:
        return None


def check_email_direct(email):
    hits = []
    em = email.strip().lower()
    if "@" not in em or "." not in em.split("@")[-1]:
        return hits
    local, domain = em.split("@", 1)
    md5_h = hashlib.md5(em.encode("utf-8")).hexdigest()

    # 1. Gravatar public profile + привязанные аккаунты
    try:
        r = HTTP.get(f"https://en.gravatar.com/{md5_h}.json", timeout=6)
        if r.status_code == 200 and r.json().get("entry"):
            e = r.json()["entry"][0]
            disp = e.get("displayName") or e.get("preferredUsername") or local
            loc = e.get("currentLocation") or ""
            about = e.get("aboutMe") or ""
            accs = [a.get("url") for a in e.get("accounts", []) if a.get("url")]
            body = " | ".join(x for x in (f"Username: {e.get('preferredUsername', '')}" if e.get("preferredUsername") else "", loc, about[:140]) if x) or f"Gravatar profile ({em})"
            hits.append((tr("b_email"), "#0EA5E9", {"title": f"Gravatar — {disp} ({em})", "href": e.get("profileUrl", f"https://gravatar.com/{md5_h}"), "body": body}))
            for au in accs[:5]:
                hits.append((tr("b_link"), "#A855F7", {"title": f"Gravatar Linked Account — {urlparse(au).netloc}", "href": au, "body": f"Привязан к почте {em} через Gravatar"}))
    except Exception:
        pass

    # 2. GitHub public email match
    try:
        r = HTTP.get("https://api.github.com/search/users", params={"q": f"{em} in:email"}, headers={"Accept": "application/vnd.github+json"}, timeout=6)
        if r.status_code == 200:
            for u in r.json().get("items", [])[:3]:
                hits.append((tr("b_email"), "#10B981", {"title": f"GitHub (по email) — @{u.get('login', '')}", "href": u.get("html_url", ""), "body": f"Публичный аккаунт GitHub, связанный с {em}"}))
    except Exception:
        pass

    # 3. Duolingo public registration check by email
    try:
        r = HTTP.get("https://www.duolingo.com/2017-06-30/users", params={"email": em}, timeout=5)
        if r.status_code == 200 and r.json().get("users"):
            u = r.json()["users"][0]
            uname = u.get("username") or local
            hits.append((tr("b_email"), "#22C55E", {
                "title": f"Duolingo — аккаунт зарегистрирован ({uname})",
                "href": f"https://www.duolingo.com/profile/{quote(uname)}",
                "body": f"Почта {em} привязана к профилю Duolingo (XP: {u.get('totalXp', 0)})"
            }))
    except Exception:
        pass

    # 4. Keybase email lookup
    try:
        r = HTTP.get("https://keybase.io/_/api/1.0/user/lookup.json", params={"emails": em}, timeout=5)
        if r.status_code == 200 and r.json().get("them"):
            them = r.json()["them"]
            if isinstance(them, list) and them and them[0]:
                kb_user = them[0].get("basics", {}).get("username")
                if kb_user:
                    hits.append((tr("b_email"), "#F97316", {
                        "title": f"Keybase — @{kb_user} (найдено по email)",
                        "href": f"https://keybase.io/{kb_user}",
                        "body": f"Почта {em} привязана к профилю Keybase (@{kb_user})"
                    }))
    except Exception:
        pass

    # 5. XposedOrNot public breach check
    try:
        r = HTTP.get(f"https://api.xposedornot.com/v1/check-email/{quote(em)}", timeout=6)
        if r.status_code == 200:
            data = r.json()
            breaches = data.get("breaches")
            if isinstance(breaches, list) and breaches:
                flat = breaches[0] if isinstance(breaches[0], list) else breaches
                if flat:
                    sample = ", ".join(str(x) for x in flat[:15])
                    more = f" (+{len(flat) - 15})" if len(flat) > 15 else ""
                    hits.append((tr("b_email"), "#EF4444", {
                        "title": f"Утечки баз (XposedOrNot): найдено {len(flat)} — {em}",
                        "href": f"https://xposedornot.com/xposed#{quote(em)}",
                        "body": f"Почта засветилась в публичных утечках: {sample}{more}"
                    }))
    except Exception:
        pass

    # 6. Корпоративный домен почты
    if domain not in FREE_EMAIL_DOMAINS:
        hits.append((tr("b_email"), "#F59E0B", {
            "title": f"Корпоративный / личный домен почты: {domain}",
            "href": f"https://{domain}",
            "body": f"Почта {em} использует нестандартный домен ({domain}) — вероятно сайт компании или личный домен."
        }))

    return hits


def check_phone_direct(raw_phone):
    norm, country, operator, variants = parse_phone_variants(raw_phone)
    if not norm:
        return [], "", []
    op_line = f" | Оператор: {operator}" if operator else ""
    hits = [
        (tr("b_phone"), "#10B981", {
            "title": f"Анализ номера: +{norm} ({country}{op_line})",
            "href": f"osint://phone/{norm}",
            "body": f"Страна / код: {country}{op_line}{NL}Варианты написания: {', '.join(variants)}"
        }),
        (tr("b_phone"), "#22C55E", {
            "title": f"WhatsApp — проверить номер +{norm}",
            "href": f"https://wa.me/{norm}",
            "body": f"Прямая ссылка для проверки профиля и аватара в WhatsApp (+{norm})"
        }),
        (tr("b_phone"), "#0EA5E9", {
            "title": f"Telegram — проверить номер +{norm}",
            "href": f"https://t.me/+{norm}",
            "body": f"Прямая ссылка для открытия аккаунта Telegram по номеру +{norm}"
        }),
        (tr("b_phone"), "#8B5CF6", {
            "title": f"Viber — открыть чат по номеру +{norm}",
            "href": f"viber://chat?number=%2B{norm}",
            "body": f"Прямой вызов клиента Viber для проверки номера +{norm}"
        }),
        (tr("b_phone"), "#38BDF8", {
            "title": f"Skype — поиск профиля по номеру +{norm}",
            "href": f"skype:+{norm}?userinfo",
            "body": f"Прямой запрос карточки пользователя Skype по номеру +{norm}"
        }),
    ]
    return hits, norm, variants


def perform_profile_scan(form_data):
    try:
        set_busy(True)
        nick = form_data.get("nick", "").strip().lstrip("@")
        email = form_data.get("email", "").strip()
        fio = " ".join(form_data.get("fio", "").strip().split())
        phone = form_data.get("phone", "").strip()

        active_tags = [x for x in (nick, email, fio, phone) if x]
        summary_str = ", ".join(active_tags)[:75]
        app.after(0, lambda s=summary_str: status_label.configure(text=tr("st_prof", q=s)))
        log_debug(f"=== OSINT FORM SCAN (235+ PLATFORMS) | nick='{nick}' | email='{email}' | fio='{fio}' | phone='{phone}' ===")

        direct, mentions, seen = [], [], set()
        reg = get_lang_meta()["region"]

        def add_card(target_list, entry):
            if entry:
                url = entry[2].get("href", "")
                k = normalize_url_key(url) if not url.startswith(("osint://", "viber://", "skype:")) else url
                if k and k not in seen:
                    seen.add(k)
                    target_list.append(entry)

        # ---- ЭТАП 1: Быстрые прямые API + 215+ HTML проверок в 35 потоков ----
        phone_norm, phone_variants = "", []
        with ThreadPoolExecutor(max_workers=35) as pool:
            futs_api = []
            if nick:
                futs_api.append(pool.submit(check_api_profiles, nick))
                futs_html = [pool.submit(check_html_platform, spec, nick) for spec in HTML_PLATFORMS]
            else:
                futs_html = []

            f_email = pool.submit(check_email_direct, email) if email else None
            if phone:
                p_hits, phone_norm, phone_variants = check_phone_direct(phone)
                for ph in p_hits:
                    add_card(direct, ph)

            if f_email:
                for it in f_email.result():
                    add_card(direct, it)
            for fa in futs_api:
                for it in fa.result():
                    add_card(direct, it)
            for fh in as_completed(futs_html):
                res = fh.result()
                if res:
                    log_debug(f"FOUND: {res[2]['href']}")
                    add_card(direct, res)

        # ---- ЭТАП 2: Точечные веб-дорки по каждому заполненному полю ----
        def collect_dorks(dork_list, badge_key, badge_col, validator, region_code="wt-wt", target_list=mentions):
            for dq in dork_list:
                time.sleep(0.3)
                for it in ddgs_search(dq, max_results=10, region=region_code):
                    u = it.get("href", "")
                    t, b = it.get("title", ""), it.get("body", "")
                    k = normalize_url_key(u)
                    if not k or k in seen or any(g in urlparse(u.lower()).netloc for g in GARBAGE_DOMAINS) or is_adult_content(u, t, b):
                        continue
                    if not validator(u, t, b):
                        continue
                    bl, bc, _ = classify_source(u, t)
                    final_b, final_c = (tr(badge_key), badge_col) if badge_key in ("b_link", "b_email", "b_phone", "b_fio") else ((tr("b_ment"), "#F59E0B") if bl == tr("b_art") else (bl, bc))
                    add_card(target_list, (final_b, final_c, it))

        # 2.1 Перекрёстные связки (если заполнено >= 2 полей)
        filled_pairs = []
        if fio and nick:
            filled_pairs.append((f'"{fio}" "{nick}"', lambda u, t, b: nick.lower() in f"{u} {t} {b}".lower()))
        if fio and email:
            filled_pairs.append((f'"{fio}" "{email}"', lambda u, t, b: email.lower() in f"{u} {t} {b}".lower()))
        if nick and email:
            filled_pairs.append((f'"{nick}" "{email}"', lambda u, t, b: email.lower() in f"{u} {t} {b}".lower() or nick.lower() in f"{u} {t} {b}".lower()))
        if fio and phone_norm:
            tail = phone_norm[-7:]
            filled_pairs.append((f'"{fio}" "{phone_variants[0]}"', lambda u, t, b, tl=tail: tl in re.sub(r"\D", "", f"{u} {t} {b}")))
        for dq, val in filled_pairs:
            collect_dorks([dq], "b_link", "#A855F7", val, region_code=reg, target_list=direct)

        # 2.2 Ник — упоминания
        if nick:
            low_n = nick.lower()
            nick_dorks = [
                f'"{nick}" site:steamcommunity.com OR site:tracker.gg OR site:op.gg OR site:vk.com OR site:t.me',
                f'"{nick}" site:open.spotify.com OR site:music.yandex.ru OR site:instagram.com OR site:pastebin.com',
                f'"{nick}"'
            ]
            collect_dorks(nick_dorks, "b_ment", "#F59E0B", lambda u, t, b: low_n in f"{u} {t} {b}".lower(), region_code="wt-wt")

        # 2.3 Почта — упоминания в сети
        if email and "@" in email:
            low_e = email.lower()
            email_dorks = [
                f'"{email}"',
                f'"{email}" site:vk.com OR site:t.me OR site:github.com OR site:habr.com OR site:pastebin.com OR site:reddit.com'
            ]
            collect_dorks(email_dorks, "b_email", "#0EA5E9", lambda u, t, b: low_e in f"{u} {t} {b}".lower(), region_code="wt-wt")

        # 2.4 Телефон — упоминания, доски объявлений, справочники, соцсети
        if phone_norm:
            tail = phone_norm[-10:] if len(phone_norm) >= 10 else phone_norm[-7:]
            short_tail = phone_norm[-7:]
            phone_dorks = [f'"{phone_variants[0]}" OR "{phone_norm}"']
            if len(phone_variants) >= 4:
                phone_dorks.append(f'"{phone_variants[2]}" OR "{phone_variants[3]}"')
            phone_dorks.append(f'"{phone_variants[0]}" site:vk.com OR site:t.me OR site:avito.ru OR site:olx.kz OR site:2gis.ru OR site:zoon.ru')

            def phone_match(u, t, b):
                d_blob = re.sub(r"\D", "", f"{u} {t} {b}")
                return tail in d_blob or short_tail in d_blob

            collect_dorks(phone_dorks, "b_phone", "#22C55E", phone_match, region_code=reg)

        # 2.5 ФИО — Википедия, соцсети, фриланс, наука, открытые реестры, транслит
        if fio:
            wiki_fio = fetch_wikipedia(fio, scope="global")
            if wiki_fio:
                add_card(direct, (tr("b_wiki"), "#F59E0B", {"title": wiki_fio["title"], "href": wiki_fio["url"], "body": wiki_fio["summary"][:300]}))

            fio_words = extract_words(fio)
            fio_stems = [w[:-1] if len(w) > 4 else w for w in fio_words]
            fio_dorks = [
                f'"{fio}" site:vk.com OR site:ok.ru OR site:t.me OR site:instagram.com OR site:linkedin.com',
                f'"{fio}" site:hh.ru OR site:habr.com OR site:github.com OR site:fl.ru OR site:kwork.ru',
                f'"{fio}" site:rusprofile.ru OR site:sudact.ru OR site:cyberleninka.ru OR site:elibrary.ru',
                f'"{fio}"'
            ]
            if len(fio_words) >= 2:
                rev_pair = f"{fio_words[1]} {fio_words[0]}"
                fio_dorks.append(f'"{rev_pair}" site:vk.com OR site:linkedin.com OR site:github.com OR site:rusprofile.ru')
            if has_cyrillic(fio):
                lat = transliterate_cyrillic(fio).strip()
                if lat and lat.lower() != fio.lower():
                    fio_dorks.append(f'"{lat}"')
                    lat_stems = [w[:-1] if len(w) > 4 else w for w in extract_words(lat)]
                else:
                    lat_stems = []
            else:
                lat_stems = []

            def fio_match(u, t, b):
                blob = f"{u} {t} {b}".lower()
                need = min(2, len(fio_stems))
                cyr_hits = sum(1 for st in fio_stems if st in blob)
                lat_hits = sum(1 for st in lat_stems if st in blob) if lat_stems else 0
                return cyr_hits >= need or (lat_stems and lat_hits >= min(2, len(lat_stems)))

            collect_dorks(fio_dorks, "b_fio", "#F59E0B", fio_match, region_code=reg)

        all_cards = direct + mentions

        def render():
            last_rendered_cards.clear()
            if not all_cards:
                rerender_search_cards()
                status_label.configure(text=tr("st_none"))
                return
            last_rendered_cards.extend({
                "title": it.get("title") or summary_str,
                "url": it.get("href", ""),
                "desc": it.get("body") or "",
                "badge": b,
                "badge_color": col,
                "cached": it.get("body") if str(it.get("href", "")).startswith(("osint://", "viber://", "skype:")) else None
            } for b, col, it in all_cards)
            rerender_search_cards()
            status_label.configure(text=tr("st_pdone", q=summary_str, p=len(direct), m=len(mentions)))

        app.after(0, render)
    except Exception as e:
        log_debug("OSINT ERR:" + NL + traceback.format_exc())
        app.after(0, lambda m=str(e): status_label.configure(text=tr("st_err", err=m)))
    finally:
        set_busy(False)


def run_active_mode():
    if current_mode == "profile":
        form_data = {
            "nick": ent_nick.get().strip(),
            "email": ent_email.get().strip(),
            "fio": ent_fio.get().strip(),
            "phone": ent_phone.get().strip(),
        }
        if not any(form_data.values()):
            status_label.configure(text=tr("st_prof_empty"))
            return
        threading.Thread(target=perform_profile_scan, args=(form_data,), daemon=True).start()
        return

    q = search_entry.get().strip()
    if not q:
        status_label.configure(text=tr("st_empty"))
        return
    threading.Thread(target={"search": perform_search, "dossier": perform_dossier}[current_mode], args=(q,), daemon=True).start()


# ================= СОХРАНЕННОЕ =================
lbl_saved_h = ctk.CTkLabel(page_saved, text=tr("saved_h"), font=ctk.CTkFont(size=22, weight="bold"))
lbl_saved_h.pack(anchor="w", pady=(0, 12))
saved_box = ctk.CTkScrollableFrame(page_saved, corner_radius=10, fg_color=bg_c["box"])
saved_box.pack(fill="both", expand=True)


def refresh_saved():
    for w in saved_box.winfo_children():
        w.destroy()
    for item in reversed(saved_pages):
        create_card(saved_box, item["title"], item["url"], item["desc"], show_save=False, show_delete=True, cached_text=item.get("full_text", item["desc"]), current_page=page_saved)


# ================= НАСТРОЙКИ И КАСТОМИЗАЦИЯ =================
lbl_set_h = ctk.CTkLabel(page_settings, text=tr("set_h"), font=ctk.CTkFont(size=22, weight="bold"))
lbl_set_h.pack(anchor="w", pady=(0, 16))

lbl_l_ui = ctk.CTkLabel(page_settings, text=tr("l_ui"), font=ctk.CTkFont(size=14, weight="bold"))
lbl_l_ui.pack(anchor="w", pady=(0, 6))

lang_labels = [v["label"] for v in LANG_META.values()]
label_to_code = {v["label"]: k for k, v in LANG_META.items()}


def apply_language():
    app.title(tr("title"))
    btn_nav_s.configure(text=tr("nav_s"))
    btn_nav_a.configure(text=tr("nav_a"))
    btn_nav_c.configure(text=tr("nav_c"))
    btn_nav_d.configure(text=tr("nav_d"))
    theme_switch.configure(text=tr("dark"))
    lbl_hub.configure(text=tr("hub"))
    mode_buttons["search"].configure(text=tr("m_search"))
    mode_buttons["dossier"].configure(text=tr("m_dossier"))
    mode_buttons["profile"].configure(text=tr("m_profile"))
    search_entry.configure(placeholder_text=tr(f"ph_{current_mode}"))
    lbl_f_nick.configure(text=tr("lbl_nick"))
    ent_nick.configure(placeholder_text=tr("ph_nick"))
    lbl_f_email.configure(text=tr("lbl_email"))
    ent_email.configure(placeholder_text=tr("ph_email"))
    lbl_f_fio.configure(text=tr("lbl_fio"))
    ent_fio.configure(placeholder_text=tr("ph_fio"))
    lbl_f_phone.configure(text=tr("lbl_phone"))
    ent_phone.configure(placeholder_text=tr("ph_phone"))
    lbl_form_hint.configure(text=tr("form_hint"))
    btn_prof_clear.configure(text=tr("clear"))
    profile_go_btn.configure(text=tr("go"))
    go_btn.configure(text=tr("go"))
    btn_tr_cards.configure(text=tr("tr_cards"))
    status_label.configure(text=tr("st_ready"))
    lbl_saved_h.configure(text=tr("saved_h"))
    lbl_set_h.configure(text=tr("set_h"))
    lbl_l_ui.configure(text=tr("l_ui"))
    lbl_l_scope.configure(text=tr("l_scope"))
    scope_seg.configure(values=[tr("sc_reg"), tr("sc_glob")])
    scope_seg.set(tr("sc_reg") if settings.get("search_scope") == "regional" else tr("sc_glob"))
    lbl_l_acc.configure(text=tr("l_accent"))
    lbl_l_bg.configure(text=tr("l_bg"))
    depth_label.configure(text=tr("l_depth", v=settings.get("depth", 35)))
    gh_check.configure(text=tr("cb_gh"))
    safe_check.configure(text=tr("cb_safe"))
    lbl_l_about.configure(text=tr("l_about"))
    btn_open_gh.configure(text=tr("btn_open_gh"))
    lbl_footer_author.configure(text=tr("made_by"))
    lbl_dbg_h.configure(text=tr("dbg_h"))
    btn_dbg_clear.configure(text=tr("clear"))
    btn_dbg_copy.configure(text=tr("copy"))
    btn_r_back.configure(text=tr("back"))
    btn_r_copy.configure(text=tr("copy"))
    btn_r_save.configure(text=tr("arch"))
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
    for ent in (search_entry, ent_nick, ent_email, ent_fio, ent_phone):
        ent.configure(border_color=am)
    go_btn.configure(fg_color=am, hover_color=ah)
    profile_go_btn.configure(fg_color=am, hover_color=ah)
    btn_prof_clear.configure(fg_color=bg["inactive"])
    btn_dbg_copy.configure(fg_color=am, hover_color=ah)
    btn_r_save.configure(fg_color=am, hover_color=ah)
    ui_lang_menu.configure(fg_color=am, button_color=ah)
    scope_seg.configure(selected_color=am, selected_hover_color=ah)
    bg_seg.configure(selected_color=am, selected_hover_color=ah)
    slider.configure(button_color=am, progress_color=am)
    theme_switch.configure(progress_color=am)
    gh_check.configure(fg_color=am)
    safe_check.configure(fg_color=am)
    gh_card.configure(fg_color=bg["card"])
    lbl_gh_link.configure(text_color=am)
    btn_open_gh.configure(fg_color=am, hover_color=ah)
    btn_tr_cards.configure(fg_color=bg["inactive"])
    btn_dbg_clear.configure(fg_color=bg["inactive"])
    btn_r_back.configure(fg_color=bg["inactive"])
    btn_r_copy.configure(fg_color=bg["inactive"])
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
ctk.CTkLabel(gh_info_col, text=f"{APP_NAME} — by {AUTHOR_NAME}", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(anchor="w")
lbl_gh_link = ctk.CTkLabel(gh_info_col, text=GITHUB_URL, font=ctk.CTkFont(size=12), text_color=acc_m, anchor="w", cursor="hand2")
lbl_gh_link.pack(anchor="w", pady=(2, 0))
lbl_gh_link.bind("<Button-1>", lambda e: webbrowser.open(GITHUB_URL))

btn_open_gh = ctk.CTkButton(gh_card, text=tr("btn_open_gh"), width=120, height=36, corner_radius=8, fg_color=acc_m, hover_color=acc_h, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: webbrowser.open(GITHUB_URL))
btn_open_gh.pack(side="right", padx=16, pady=12)

switch_page(page_search)


# ================= АНИМАЦИИ, ЗАГРУЗКА И EULA =================
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
        tp = _quad_bezier((cx - ew, cy), (cx, cy - eh), (cx + ew, cy), 18)
        bp = _quad_bezier((cx + ew, cy), (cx, cy + eh), (cx - ew, cy), 18)
        canvas.create_polygon(*[c for pt in (tp + bp) for c in pt], fill="#0B0B0F", outline="")
        canvas.create_line(*[c for pt in tp for c in pt], fill="#F8FAFC", width=3.2, smooth=True)
        canvas.create_line(*[c for pt in bp for c in pt], fill="#F8FAFC", width=3.2, smooth=True)
        ir = r * 0.33 * eye_p
        if ir > 2:
            canvas.create_oval(cx - ir, cy - ir, cx + ir, cy + ir, fill="#161622", outline=accent, width=2.6)
    if bolt_p > 0.01:
        dy, sc = -(1.0 - bolt_p) * r * 0.85, 0.55 + 0.45 * bolt_p
        raw = [(0.11, -0.78), (-0.27, 0.04), (-0.01, 0.04), (-0.15, 0.78), (0.29, -0.06), (0.03, -0.06)]
        pts = [v for bx, by in raw for v in (cx + bx * r * sc, cy + by * r * sc + dy)]
        sh = [v for bx, by in raw for v in (cx + bx * r * sc + 2.5, cy + by * r * sc + dy + 2.5)]
        canvas.create_polygon(*sh, fill=accent, outline="")
        canvas.create_polygon(*pts, fill="#FFFFFF", outline="")


def run_splash_loading():
    bg_hex = "#0C0C0F"
    am, _ = get_accent()
    overlay = ctk.CTkFrame(app, fg_color=bg_hex, corner_radius=0)
    overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
    overlay.lift()
    canvas = ctk.CTkCanvas(overlay, bg=bg_hex, highlightthickness=0, bd=0)
    canvas.pack(fill="both", expand=True)
    app.update_idletasks()
    start_ts, total_dur = time.perf_counter(), 2.15

    def frame():
        if not overlay.winfo_exists():
            return
        w, h = max(canvas.winfo_width(), 900), max(canvas.winfo_height(), 600)
        cx, cy, t = w / 2, h / 2 - 14, time.perf_counter() - start_ts
        canvas.delete("all")
        p_in = _ease_out(t / 0.55)
        p_slide = _ease_io((t - 0.55) / 0.85) if t > 0.55 else 0.0
        p_load = min(1.0, t / (total_dur - 0.15))
        logo_x = cx - 178 * p_slide
        text_x = (logo_x - 190) + 258 * p_slide

        if p_slide > 0.01:
            canvas.create_text(text_x, cy - 8, text="DESCENDING SCAN", anchor="w", fill="#F8FAFC", font=("Segoe UI", 27, "bold"))
            if p_slide > 0.35:
                canvas.create_text(text_x + 2, cy + 22, text="SEARCH  •  DOSSIER  •  OSINT", anchor="w", fill="#94A3B8", font=("Segoe UI", 10, "bold"))

        canvas.create_rectangle(0, cy - 85, logo_x + 12, cy + 85, fill=bg_hex, outline="")
        _draw_animated_logo(canvas, logo_x, cy, 46, am, bg_hex, ring_p=p_in, eye_p=_ease_out((t - 0.08) / 0.45), bolt_p=_ease_out((t - 0.18) / 0.42), rot_deg=(1.0 - p_in) * 55.0)

        bx0, by = cx - 170, cy + 92
        canvas.create_line(bx0, by, bx0 + 340, by, fill="#1E1E24", width=3, capstyle="round")
        if p_load > 0.01:
            canvas.create_line(bx0, by, bx0 + 340 * p_load, by, fill=am, width=3, capstyle="round")
        canvas.create_text(cx, h - 34, text=f"By {AUTHOR_NAME}", anchor="center", fill="#64748B", font=("Segoe UI", 11, "bold"))

        if t < total_dur:
            app.after(16, frame)
        else:
            overlay.destroy()
            search_entry.focus_set()

    app.after(30, frame)


def show_eula_screen():
    bg_hex = "#0C0C0F"
    am, ah = get_accent()
    is_ru = settings.get("ui_lang", "ru") in ("ru", "uk", "kk")
    overlay = ctk.CTkFrame(app, fg_color=bg_hex, corner_radius=0)
    overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
    overlay.lift()

    card = ctk.CTkFrame(overlay, width=700, height=580, corner_radius=16, fg_color="#16161B", border_width=1, border_color="#27272A")
    card.place(relx=0.5, rely=0.5, anchor="center")
    card.pack_propagate(False)

    top_hdr = ctk.CTkFrame(card, fg_color="transparent")
    top_hdr.pack(fill="x", padx=28, pady=(22, 12))
    pil_s = render_brand_logo(64, accent=am, bg="#111113")
    ctk_s = ctk.CTkImage(light_image=pil_s, dark_image=pil_s, size=(42, 42))
    _icon_refs["eula_logo"] = ctk_s
    ctk.CTkLabel(top_hdr, text="", image=ctk_s).pack(side="left", padx=(0, 12))
    ht = ctk.CTkFrame(top_hdr, fg_color="transparent")
    ht.pack(side="left", fill="x")
    ctk.CTkLabel(ht, text="DESCENDING SCAN", font=ctk.CTkFont(size=18, weight="bold"), text_color="#F8FAFC").pack(anchor="w")
    ctk.CTkLabel(ht, text="Пользовательское соглашение (EULA)" if is_ru else "End User License Agreement (EULA)", font=ctk.CTkFont(size=12), text_color="#94A3B8").pack(anchor="w")

    eula_box = ctk.CTkTextbox(card, font=ctk.CTkFont(size=13), wrap="word", corner_radius=10, fg_color="#0F0F13", text_color="#E2E8F0", border_width=1, border_color="#27272A")
    eula_box.pack(fill="both", expand=True, padx=28, pady=(4, 10))
    eula_box.insert("1.0", EULA_TEXT_RU if is_ru else EULA_TEXT_EN)
    eula_box.configure(state="disabled")

    hint_lbl = ctk.CTkLabel(card, text="⬇ Прокрутите соглашение до самого конца, чтобы активировать галочку" if is_ru else "⬇ Scroll down to the bottom of the agreement to unlock confirmation", font=ctk.CTkFont(size=12), text_color="#F59E0B")
    hint_lbl.pack(anchor="w", padx=30, pady=(0, 8))

    unlocked = {"ok": False}
    agree_cb = ctk.CTkCheckBox(
        card, text="Я прочитал(а) соглашение, принимаю ответственность за свои действия и согласен(на) с условиями" if is_ru else "I have read the EULA, accept full responsibility for my actions, and agree to the terms",
        state="disabled", fg_color=am, hover_color=ah, text_color="#E2E8F0", font=ctk.CTkFont(size=12, weight="bold"),
        command=lambda: btn_accept.configure(state="normal" if agree_cb.get() else "disabled", fg_color=am if agree_cb.get() else "#27272A", hover_color=ah)
    )
    agree_cb.pack(anchor="w", padx=30, pady=(0, 14))

    btn_row = ctk.CTkFrame(card, fg_color="transparent")
    btn_row.pack(fill="x", padx=28, pady=(0, 22))
    ctk.CTkButton(btn_row, text="Выйти" if is_ru else "Decline & Exit", width=120, height=40, corner_radius=8, fg_color="#27272A", hover_color="#3F3F46", text_color="#E2E8F0", command=app.destroy).pack(side="left")
    btn_accept = ctk.CTkButton(btn_row, text="Я согласен — Продолжить" if is_ru else "I Agree — Continue", width=220, height=40, corner_radius=8, state="disabled", fg_color="#27272A", text_color="#FFFFFF", font=ctk.CTkFont(size=13, weight="bold"), command=lambda: [settings.__setitem__("eula_accepted", True), save_json(SETTINGS_FILE, settings), overlay.destroy(), run_splash_loading()])
    btn_accept.pack(side="right")

    def poll_scroll():
        if not overlay.winfo_exists() or unlocked["ok"]:
            return
        try:
            if eula_box._textbox.yview()[1] >= 0.96:
                unlocked["ok"] = True
                hint_lbl.configure(text="✓ Соглашение прочитано — подтвердите согласие ниже" if is_ru else "✓ Agreement reviewed — confirm below", text_color="#10B981")
                agree_cb.configure(state="normal")
                return
        except Exception:
            pass
        app.after(100, poll_scroll)

    app.after(120, poll_scroll)


def run_first_launch_intro():
    bg_hex = "#0C0C0F"
    am, _ = get_accent()
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
        rp = _ease_out(t / 0.70)
        _draw_animated_logo(canvas, cx, cy, 62, am, bg_hex, ring_p=rp, eye_p=_ease_out((t - 0.25) / 0.65), bolt_p=_ease_out((t - 0.55) / 0.55), rot_deg=(1.0 - rp) * 140.0)
        canvas.create_text(cx, h - 34, text=f"By {AUTHOR_NAME}", anchor="center", fill="#64748B", font=("Segoe UI", 11, "bold"))
        if t < 1.65:
            app.after(16, frame)
        else:
            overlay.destroy()
            show_eula_screen()

    app.after(30, frame)


app.after(20, run_first_launch_intro if not settings.get("eula_accepted", False) else run_splash_loading)
app.mainloop()
