"""
scraper.py — Buscador de promoções via RSS
Fontes: Pelando, Promobit, Promocoes Nerd, Cupom Válido
Busca em paralelo usando aiohttp + feedparser
"""
import asyncio
import hashlib
import re
import feedparser
import aiohttp
from typing import Dict, List, Optional, Tuple

# ─── FONTES DE PROMOÇÕES ─────────────────────────────────────────────────────
# Adicione ou remova feeds aqui. Cada fonte precisa de: name, url, emoji.
RSS_FEEDS = [
    {
        "name": "r/PromocoesOnline",
        "url": "https://www.reddit.com/r/PromocoesOnline/new.rss",
        "emoji": "🔥",
    },
    {
        "name": "r/Descontos",
        "url": "https://www.reddit.com/r/descontos/new.rss",
        "emoji": "💥",
    },
    {
        "name": "r/ofertasdobrasil",
        "url": "https://www.reddit.com/r/ofertasdobrasil/new.rss",
        "emoji": "🛒",
    },
    {
        "name": "r/eu_opshopping",
        "url": "https://www.reddit.com/r/eu_opshopping/new.rss",
        "emoji": "🎯",
    },
]

# Cabeçalho para evitar bloqueio por bot detection
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Quantos itens por feed buscar por rodada (os mais recentes)
ITEMS_PER_FEED = 10

# Timeout por requisição HTTP (segundos)
REQUEST_TIMEOUT = 15


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def generate_deal_id(url: str) -> str:
    """
    Gera um ID único para o deal a partir da URL.
    Usado para verificar duplicatas no SQLite.
    """
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def extract_price(text: str) -> Optional[str]:
    """
    Tenta extrair o preço do título ou descrição.
    Padrões suportados: 'R$ 99,99', 'por R$99', 'R$1.299'.
    """
    patterns = [
        r"R\$\s*[\d.,]+",         # R$ 99,99
        r"por\s+R\$\s*[\d.,]+",   # por R$ 99
        r"[\d.,]+\s*reais",       # 99 reais
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group().strip()
    return None


def extract_image(entry) -> Optional[str]:
    """
    Tenta extrair a URL da imagem de um entry RSS.
    Testa: media:thumbnail → enclosures → <img> na descrição HTML.
    """
    # 1. media:thumbnail (Pelando, Promobit usam isso)
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url")

    # 2. enclosures (podcasts/imagens anexadas)
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if "image" in enc.get("type", ""):
                return enc.get("href") or enc.get("url")

    # 3. primeira <img> no corpo HTML da descrição
    if hasattr(entry, "summary"):
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', entry.summary)
        if match:
            return match.group(1)

    return None


# ─── FETCH INDIVIDUAL ────────────────────────────────────────────────────────

async def fetch_feed(
    session: aiohttp.ClientSession, feed_config: Dict
) -> Tuple[List[Dict], Optional[str]]:
    """
    Busca e parseia um único feed RSS.
    Retorna: (lista de deals, mensagem de erro ou None)
    """
    deals = []
    try:
        async with session.get(
            feed_config["url"],
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        ) as response:
            if response.status != 200:
                return [], f"{feed_config['name']}: HTTP {response.status}"

            content = await response.text()

        # feedparser é síncrono — roda fora do event loop para não travar
        feed = await asyncio.get_event_loop().run_in_executor(
            None, feedparser.parse, content
        )

        for entry in feed.entries[:ITEMS_PER_FEED]:
            url = entry.get("link", "").strip()
            if not url:
                continue  # ignora entries sem URL

            title = entry.get("title", "Sem título").strip()
            description = entry.get("summary", "")

            deal = {
                "id": generate_deal_id(url),
                "title": title,
                "url": url,
                "source": feed_config["name"],
                "emoji": feed_config["emoji"],
                "price": extract_price(title + " " + description),
                "image_url": extract_image(entry),
                "description": description[:300] if description else None,
            }
            deals.append(deal)

    except asyncio.TimeoutError:
        return [], f"{feed_config['name']}: timeout após {REQUEST_TIMEOUT}s"
    except Exception as e:
        return [], f"{feed_config['name']}: {str(e)}"

    return deals, None


# ─── FETCH TODOS ─────────────────────────────────────────────────────────────

async def fetch_all_deals() -> Tuple[List[Dict], List[str]]:
    """
    Busca deals de TODAS as fontes em paralelo.
    Retorna: (todos os deals encontrados, lista de erros por fonte)
    """
    all_deals: List[Dict] = []
    errors: List[str] = []

    async with aiohttp.ClientSession() as session:
        # Executa todas as requisições ao mesmo tempo
        tasks = [fetch_feed(session, feed) for feed in RSS_FEEDS]
        results = await asyncio.gather(*tasks)

    for deals, error in results:
        if error:
            errors.append(error)
        all_deals.extend(deals)

    return all_deals, errors
