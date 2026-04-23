"""
ai_generator.py — Geração de copy de vendas com Google Gemini
Usa a REST API diretamente via aiohttp (sem SDK — compatível com Python 3.14+)
Documentação: https://ai.google.dev/gemini-api/docs/quickstart
"""
import logging
import os
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# ─── Configuração ─────────────────────────────────────────────────────────────

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)

_gemini_enabled = False
_gemini_api_key = None  # lido dentro de init_gemini() para garantir que o .env já foi carregado


def init_gemini():
    """
    Habilita o Gemini se a chave estiver configurada.
    Lê a variável aqui (não no topo do módulo) para garantir que
    load_dotenv() já foi chamado antes.
    """
    global _gemini_enabled, _gemini_api_key

    _gemini_api_key = os.getenv("GEMINI_API_KEY")

    if not _gemini_api_key:
        logger.warning(
            "⚠️  GEMINI_API_KEY não configurada — bot vai postar sem headline de IA."
        )
        return

    _gemini_enabled = True
    logger.info("✅ Gemini configurado (REST API).")


# ─── Prompt ───────────────────────────────────────────────────────────────────

PROMPT_TEMPLATE = """Você é um copywriter especialista em canais de promoções brasileiros no Telegram.
Seu objetivo é criar frases que façam as pessoas clicarem AGORA.

Produto em promoção: {title}

Regras:
- Máximo 2 linhas
- Tom urgente e informal ("corre!", "só hoje!", "tá barato demais!")
- Mencione o benefício principal ou a oportunidade de economia
- NÃO use emojis (já são adicionados pelo bot)
- Retorne APENAS a frase, sem aspas, sem explicações

Exemplos de saídas boas:
- "Tá ridiculamente barato esse produto! Corre antes de acabar o estoque."
- "Essa promoção não vai durar. Perfeito pra quem tava esperando baixar o preço."
- "Melhor preço do ano nisso aqui. Aproveita enquanto tem!"

Agora crie a frase para o produto acima:"""


# ─── Geração de copy ───────────────────────────────────────────────────────────

async def generate_sales_copy(title: str) -> Optional[str]:
    """
    Gera uma headline de vendas para o produto usando a REST API do Gemini.
    Retorna None silenciosamente se a IA estiver desabilitada ou der erro.
    """
    if not _gemini_enabled:
        return None

    payload = {
        "contents": [
            {
                "parts": [{"text": PROMPT_TEMPLATE.format(title=title)}]
            }
        ]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{GEMINI_URL}?key={_gemini_api_key}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status != 200:
                    logger.warning(f"Gemini retornou HTTP {response.status}")
                    return None

                data = await response.json()
                copy = (
                    data["candidates"][0]["content"]["parts"][0]["text"].strip()
                )

                # Sanidade: ignora se vier muito longo
                if len(copy) > 300:
                    logger.warning("Gemini retornou texto muito longo, ignorando.")
                    return None

                return copy

    except Exception as e:
        # Falha silenciosa — o deal ainda é postado, só sem a headline de IA
        logger.warning(f"Gemini falhou para '{title}': {e}")
        return None
