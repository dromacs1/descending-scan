# Descending Scan v2.0

A modern desktop OSINT & Web Reconnaissance suite built with Python and CustomTkinter. Designed for fast, structured open-source intelligence gathering, metadata inspection, and clean web search without clutter.

## Features

- **Zero-Clutter Web Search:** Smart classification and tagging for official sites, Wikipedia, Steam, code repositories, and forums, with strict filtering against `404/403` errors, Cloudflare/SmartCaptcha bot walls, and low-quality aggregators.
- **Multi-Field OSINT Form:** Run concurrent lookups across 1–7 parameters simultaneously:
  - **Username & IDs:** Checks 140+ live platforms and public APIs with strict meta-tag verification (`og:title`, `<title>`, `<h1>`) and bio extraction (`og:description`):
    - **Roblox:** Account creation date, verified badge check, and active/banned status.
    - **Steam (XML):** Lookup by username or `SteamID64` — fetches registration date, country, and VAC/Trade ban status.
    - **Discord Snowflake ID:** Offline mathematical decoding of exact account/server creation timestamps and age.
    - **GitHub & Reddit:** Account creation dates, suspension checks, and email-based commit lookups.
  - **Email:** Checks Gravatar profiles, public GitHub accounts/commits, Duolingo/Keybase registrations, and public breach indicators via XposedOrNot.
  - **Phone:** Country/carrier identification, format variations, and direct messenger links.
  - **Full Name:** Cross-platform search with automatic Cyrillic-to-Latin transliteration and cross-match dorking.
  - **IP & Domain Recon:** GeoIP/ASN lookup, OpenStreetMap coordinates, DNS resolution, `MX` records, RDAP/WHOIS, `crt.sh` subdomain enumeration, Wayback Machine snapshots, plus Shodan & VirusTotal links.
  - **MAC & Hardware:** IEEE OUI vendor lookup, LAA/randomized MAC detection, and hardware specification search.
- **Photo OCR + EXIF + Document Inspection:**
  - Built-in **Windows OCR** (EN + RU) extracts text from screenshots and automatically runs lookups on detected usernames, `@handles`, emails, and IPs.
  - Extracts image **EXIF & GPS** metadata with direct map links, plus hidden author/creation metadata from `.docx` and `.pdf` files.
- **Built-in Reader, Translator & Export:** Clean article extraction (`trafilatura`), instant translation, offline JSON archive, and one-click **HTML report export**.
- **Customizable UI:** 8 interface languages, dark/light themes, 4 background styles (including OLED Black), and 6 accent colors.

## Run from Source

```bash
git clone [https://github.com/dromacs1/DeepSearch.git](https://github.com/dromacs1/DeepSearch.git)
cd DeepSearch
pip install -r requirements.txt
python main.py
