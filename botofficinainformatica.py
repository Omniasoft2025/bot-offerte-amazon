import requests
import logging
import json
import os
import time
import random
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
import asyncio

# ================================================================
# CONFIGURAZIONE — modifica questi valori
# ================================================================
TOKEN_BOT      =  "8775548158:AAFPv5SviG1OXzu9u7iFNu58q_H8Fw2hFxI"      # Token del tuo bot Telegram
ID_CANALE      = -1003504366148                           # ID del canale Telegram
TUO_TAG_AMAZON = "officina26-21"                 # Tag affiliazione Amazon

FILE_INVIATI            = "prodotti_inviati.json"
MAX_OFFERTE_PER_CATEGORIA = 3
# ================================================================

CATEGORIE = [
    {
        "nome": "💻 Laptop & PC",
        "url": "https://www.amazon.it/s?k=laptop+notebook&rh=p_n_deal_type%3A26901223031&s=price-asc-rank",
    },
    {
        "nome": "🖥️ Monitor",
        "url": "https://www.amazon.it/s?k=monitor+pc&rh=p_n_deal_type%3A26901223031&s=price-asc-rank",
    },
    {
        "nome": "⌨️ Tastiere & Mouse",
        "url": "https://www.amazon.it/s?k=tastiera+mouse+pc&rh=p_n_deal_type%3A26901223031&s=price-asc-rank",
    },
    {
        "nome": "🖨️ Stampanti & Accessori",
        "url": "https://www.amazon.it/s?k=stampante+accessori+pc&rh=p_n_deal_type%3A26901223031&s=price-asc-rank",
    },
    {
        "nome": "💾 Storage & RAM",
        "url": "https://www.amazon.it/s?k=SSD+hard+disk+RAM&rh=p_n_deal_type%3A26901223031&s=price-asc-rank",
    },
    {
        "nome": "🔌 Componenti PC",
        "url": "https://www.amazon.it/s?k=scheda+grafica+processore+CPU&rh=p_n_deal_type%3A26901223031&s=price-asc-rank",
    },
]

# Lista di User-Agent realistici — viene scelto uno a caso ad ogni richiesta
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot_offerte.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ----------------------------------------------------------------
# GESTIONE PRODOTTI GIÀ INVIATI
# ----------------------------------------------------------------

def carica_inviati() -> set:
    if os.path.exists(FILE_INVIATI):
        try:
            with open(FILE_INVIATI, "r") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def salva_inviati(inviati: set):
    with open(FILE_INVIATI, "w") as f:
        json.dump(list(inviati), f)


# ----------------------------------------------------------------
# SCRAPING CON REQUESTS + BEAUTIFULSOUP
# ----------------------------------------------------------------

def get_headers() -> dict:
    """Genera header HTTP realistici con user-agent casuale."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
        "Referer": "https://www.amazon.it/",
    }


def estrai_testo(soup_el) -> str:
    """Estrae il testo pulito da un elemento BeautifulSoup."""
    return soup_el.get_text(strip=True) if soup_el else ""


def scrapa_categoria(url: str, nome: str, inviati: set) -> list:
    """Scarica la pagina e analizza i prodotti con BeautifulSoup."""
    log.info(f"🔍 Cerco offerte: {nome}")
    offerte = []

    try:
        session = requests.Session()
        risposta = session.get(url, headers=get_headers(), timeout=20)
        risposta.raise_for_status()
    except requests.RequestException as e:
        log.error(f"❌ Errore richiesta HTTP per {nome}: {e}")
        return offerte

    soup = BeautifulSoup(risposta.text, "html.parser")

    # Controlla se Amazon ha mostrato un CAPTCHA
    if "Type the characters you see in this image" in risposta.text or "captcha" in risposta.text.lower():
        log.warning(f"⚠️  CAPTCHA rilevato per {nome} — skip categoria")
        return offerte

    prodotti = soup.select(".s-result-item[data-asin]")
    log.info(f"   Trovati {len(prodotti)} blocchi prodotto")

    skippati_asin = 0
    skippati_titolo = 0
    skippati_prezzo = 0

    for prod in prodotti:
        asin = prod.get("data-asin", "").strip()
        if not asin:
            continue
        if asin in inviati:
            skippati_asin += 1
            continue

        # --- Titolo ---
        titolo = None
        for sel in ["h2 a span", "h2 span", ".a-size-medium", ".a-size-base-plus"]:
            el = prod.select_one(sel)
            if el:
                testo = estrai_testo(el)
                if testo:
                    titolo = testo
                    break
        if not titolo:
            skippati_titolo += 1
            continue

        # --- Prezzo ---
        prezzo = None
        for sel in [".a-price .a-offscreen", ".a-price-whole", ".a-color-price"]:
            el = prod.select_one(sel)
            if el:
                testo = estrai_testo(el)
                if testo:
                    prezzo = testo
                    break
        if not prezzo:
            skippati_prezzo += 1
            continue

        # --- Prezzo originale barrato ---
        prezzo_orig = None
        for sel in [".a-price.a-text-price .a-offscreen", ".a-text-price .a-offscreen"]:
            el = prod.select_one(sel)
            if el:
                testo = estrai_testo(el)
                if testo and testo != prezzo:
                    prezzo_orig = testo
                    break

        # --- Sconto % ---
        sconto = 0
        badge = prod.select_one(".a-badge-text")
        if badge:
            num = "".join(filter(str.isdigit, estrai_testo(badge)))
            sconto = int(num) if num else 0

        # --- Foto ---
        foto_el = prod.select_one("img.s-image")
        foto = foto_el.get("src", "") if foto_el else ""

        # --- Rating ---
        rating_el = prod.select_one(".a-icon-alt")
        rating = estrai_testo(rating_el)

        link_affiliato = f"https://www.amazon.it/dp/{asin}?tag={TUO_TAG_AMAZON}"

        offerte.append({
            "asin": asin,
            "titolo": titolo,
            "prezzo": prezzo,
            "prezzo_orig": prezzo_orig,
            "sconto": sconto,
            "link": link_affiliato,
            "foto": foto,
            "rating": rating,
            "categoria": nome,
        })

        if len(offerte) >= MAX_OFFERTE_PER_CATEGORIA:
            break

    log.info(
        f"   {nome}: {len(offerte)} offerte valide "
        f"(skip già-inviati={skippati_asin}, no-titolo={skippati_titolo}, no-prezzo={skippati_prezzo})"
    )
    return offerte


def cerca_tutte_le_offerte(inviati: set) -> list:
    tutte = []
    for cat in CATEGORIE:
        offerte_cat = scrapa_categoria(cat["url"], cat["nome"], inviati)
        tutte.extend(offerte_cat)
        # Pausa casuale tra categorie per sembrare un utente reale
        time.sleep(random.uniform(3, 7))

    tutte.sort(key=lambda x: x["sconto"], reverse=True)
    log.info(f"✅ Totale offerte trovate: {len(tutte)}")
    return tutte


# ----------------------------------------------------------------
# INVIO TELEGRAM
# ----------------------------------------------------------------

def costruisci_messaggio(o: dict) -> str:
    titolo_breve = o["titolo"][:80] + ("…" if len(o["titolo"]) > 80 else "")

    righe = [
        f"{o['categoria']} <b>OFFERTA DEL GIORNO</b>",
        "",
        f"📦 <b>{titolo_breve}</b>",
        "",
    ]

    if o.get("prezzo_orig") and o["prezzo_orig"] != o["prezzo"]:
        righe.append(f"〰️ <s>{o['prezzo_orig']}</s>")

    righe.append(f"💰 <b>{o['prezzo']}</b>")

    if o["sconto"] > 0:
        righe.append(f"🔥 Sconto: <b>-{o['sconto']}%</b>")

    if o.get("rating"):
        righe.append(f"⭐ {o['rating']}")

    righe += [
        "",
        "🚚 Spedizione Prime <b>GRATIS</b>",
        "",
        f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}",
    ]

    return "\n".join(righe)


async def invia_offerte(offerte: list, inviati: set):
    bot = Bot(token=TOKEN_BOT)
    nuovi_inviati = set()

    for o in offerte:
        testo = costruisci_messaggio(o)
        tastiera = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🛒 VAI ALL'OFFERTA", url=o["link"])]]
        )

        try:
            if o.get("foto"):
                await bot.send_photo(
                    chat_id=ID_CANALE,
                    photo=o["foto"],
                    caption=testo,
                    parse_mode=ParseMode.HTML,
                    reply_markup=tastiera,
                )
            else:
                await bot.send_message(
                    chat_id=ID_CANALE,
                    text=testo,
                    parse_mode=ParseMode.HTML,
                    reply_markup=tastiera,
                    disable_web_page_preview=False,
                )

            nuovi_inviati.add(o["asin"])
            log.info(f"🚀 Postato: {o['titolo'][:50]}…")
            await asyncio.sleep(5)

        except Exception as e:
            log.error(f"⚠️  Errore invio Telegram per {o['asin']}: {e}")

    inviati.update(nuovi_inviati)
    salva_inviati(inviati)
    log.info(f"💾 Salvati {len(nuovi_inviati)} nuovi ASIN nel registro.")


# ----------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------

async def main():
    log.info("=" * 55)
    log.info("🤖 Bot Offerte Amazon avviato")
    log.info("=" * 55)

    inviati = carica_inviati()
    log.info(f"📋 ASIN già inviati nel registro: {len(inviati)}")

    offerte = cerca_tutte_le_offerte(inviati)

    if not offerte:
        log.warning("❌ Nessuna offerta trovata. Amazon potrebbe aver mostrato un CAPTCHA.")
        return

    await invia_offerte(offerte, inviati)
    log.info("✅ Esecuzione completata.")


INTERVALLO_ORE = 24 # Ogni quante ore cercare nuove offerte
async def loop():
    log.info("🔁 Modalità loop attiva — esecuzione ogni {} ore".format(INTERVALLO_ORE))
    while True:
        try:
            await main()
        except Exception as e:
            log.error(f"❌ Errore nel loop principale: {e}")
        log.info(f"⏳ Prossima esecuzione tra {INTERVALLO_ORE} ore...")
        await asyncio.sleep(INTERVALLO_ORE * 3600)

if __name__ == "__main__":
    asyncio.run(loop())
