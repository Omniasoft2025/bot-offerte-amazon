import asyncio
import logging
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

# ================================================================
# CONFIGURAZIONE
# ================================================================
TOKEN_BOT      = os.environ.get("TOKEN_BOT", "8775548158:AAFPv5SviG1OXzu9u7iFNu58q_H8Fw2hFxI")
")
ID_CANALE      = int(os.environ.get("ID_CANALE", "-1003504366148  "))
TUO_TAG_AMAZON = os.environ.get("TAG_AMAZON", "officina26-21")

FILE_INVIATI              = "prodotti_inviati.json"
MAX_OFFERTE_PER_CATEGORIA = 3
INTERVALLO_ORE            = 24
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)


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


async def scrapa_categoria(page, url: str, nome: str, inviati: set) -> list:
    log.info(f"🔍 Cerco offerte: {nome}")
    offerte = []

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_selector(".s-result-item", timeout=20_000)
        await page.mouse.wheel(0, 1500)
        await asyncio.sleep(2)
    except Exception as e:
        log.error(f"❌ Errore caricamento pagina {nome}: {e}")
        return offerte

    prodotti = await page.query_selector_all(".s-result-item[data-asin]")
    log.info(f"   Trovati {len(prodotti)} blocchi prodotto")

    skippati_asin = skippati_titolo = skippati_prezzo = 0

    for prod in prodotti:
        asin = await prod.get_attribute("data-asin")
        if not asin:
            continue
        if asin in inviati:
            skippati_asin += 1
            continue

        try:
            titolo = None
            for sel in ["h2 a span", "h2 span", ".a-size-medium", ".a-size-base-plus"]:
                el = await prod.query_selector(sel)
                if el:
                    testo = (await el.inner_text()).strip()
                    if testo:
                        titolo = testo
                        break
            if not titolo:
                skippati_titolo += 1
                continue

            prezzo = None
            for sel in [".a-price .a-offscreen", ".a-price-whole", ".a-color-price"]:
                el = await prod.query_selector(sel)
                if el:
                    testo = (await el.inner_text()).strip()
                    if testo:
                        prezzo = testo
                        break
            if not prezzo:
                skippati_prezzo += 1
                continue

            prezzo_orig = None
            for sel in [".a-price.a-text-price .a-offscreen", ".a-text-price .a-offscreen"]:
                el = await prod.query_selector(sel)
                if el:
                    testo = (await el.inner_text()).strip()
                    if testo and testo != prezzo:
                        prezzo_orig = testo
                        break

            sconto = 0
            badge = await prod.query_selector(".a-badge-text")
            if badge:
                num = "".join(filter(str.isdigit, await badge.inner_text()))
                sconto = int(num) if num else 0

            foto_el = await prod.query_selector("img.s-image")
            foto = (await foto_el.get_attribute("src")) if foto_el else ""

            rating_el = await prod.query_selector(".a-icon-alt")
            rating = (await rating_el.inner_text()).strip() if rating_el else ""

            offerte.append({
                "asin": asin,
                "titolo": titolo,
                "prezzo": prezzo,
                "prezzo_orig": prezzo_orig,
                "sconto": sconto,
                "link": f"https://www.amazon.it/dp/{asin}?tag={TUO_TAG_AMAZON}",
                "foto": foto,
                "rating": rating,
                "categoria": nome,
            })

            if len(offerte) >= MAX_OFFERTE_PER_CATEGORIA:
                break

        except Exception as e:
            log.debug(f"   Skip {asin}: {e}")
            continue

    log.info(f"   {nome}: {len(offerte)} offerte valide (skip già-inviati={skippati_asin}, no-titolo={skippati_titolo}, no-prezzo={skippati_prezzo})")
    return offerte


async def cerca_tutte_le_offerte(inviati: set) -> list:
    tutte = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="it-IT",
        )
        page = await context.new_page()

        for cat in CATEGORIE:
            offerte_cat = await scrapa_categoria(page, cat["url"], cat["nome"], inviati)
            tutte.extend(offerte_cat)
            await asyncio.sleep(3)

        await browser.close()

    tutte.sort(key=lambda x: x["sconto"], reverse=True)
    log.info(f"✅ Totale offerte trovate: {len(tutte)}")
    return tutte


def costruisci_messaggio(o: dict) -> str:
    titolo_breve = o["titolo"][:80] + ("…" if len(o["titolo"]) > 80 else "")
    righe = [f"{o['categoria']} <b>OFFERTA DEL GIORNO</b>", "", f"📦 <b>{titolo_breve}</b>", ""]

    if o.get("prezzo_orig") and o["prezzo_orig"] != o["prezzo"]:
        righe.append(f"〰️ <s>{o['prezzo_orig']}</s>")
    righe.append(f"💰 <b>{o['prezzo']}</b>")
    if o["sconto"] > 0:
        righe.append(f"🔥 Sconto: <b>-{o['sconto']}%</b>")
    if o.get("rating"):
        righe.append(f"⭐ {o['rating']}")
    righe += ["", "🚚 Spedizione Prime <b>GRATIS</b>", "", f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}"]
    return "\n".join(righe)


async def invia_offerte(offerte: list, inviati: set):
    bot = Bot(token=TOKEN_BOT)
    nuovi_inviati = set()

    for o in offerte:
        testo = costruisci_messaggio(o)
        tastiera = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 VAI ALL'OFFERTA", url=o["link"])]])

        try:
            if o.get("foto"):
                await bot.send_photo(chat_id=ID_CANALE, photo=o["foto"], caption=testo,
                                     parse_mode=ParseMode.HTML, reply_markup=tastiera)
            else:
                await bot.send_message(chat_id=ID_CANALE, text=testo,
                                       parse_mode=ParseMode.HTML, reply_markup=tastiera)
            nuovi_inviati.add(o["asin"])
            log.info(f"🚀 Postato: {o['titolo'][:50]}…")
            await asyncio.sleep(5)
        except Exception as e:
            log.error(f"⚠️ Errore Telegram per {o['asin']}: {e}")

    inviati.update(nuovi_inviati)
    salva_inviati(inviati)
    log.info(f"💾 Salvati {len(nuovi_inviati)} nuovi ASIN.")


async def main():
    log.info("=" * 55)
    log.info("🤖 Bot Offerte Amazon avviato")
    log.info("=" * 55)

    inviati = carica_inviati()
    log.info(f"📋 ASIN già inviati: {len(inviati)}")

    offerte = await cerca_tutte_le_offerte(inviati)

    if not offerte:
        log.warning("❌ Nessuna offerta trovata.")
        return

    await invia_offerte(offerte, inviati)
    log.info("✅ Esecuzione completata.")


async def loop():
    log.info(f"🔁 Modalità loop attiva — esecuzione ogni {INTERVALLO_ORE} ore")
    while True:
        try:
            await main()
        except Exception as e:
            log.error(f"❌ Errore nel loop: {e}")
        log.info(f"⏳ Prossima esecuzione tra {INTERVALLO_ORE} ore...")
        await asyncio.sleep(INTERVALLO_ORE * 3600)


if __name__ == "__main__":
    asyncio.run(loop())

