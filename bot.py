"""
bot.py — Núcleo do bot de promoções para Telegram
Responsabilidades:
  1. Buscar deals das fontes RSS (via scraper.py) a cada N minutos
  2. Filtrar duplicatas consultando o SQLite (via database.py)
  3. Postar os deals novos no canal do Telegram com foto + texto formatado
  4. Subir um servidor Flask com dashboard de monitoramento (porta $PORT)
"""
import os
# ─── Carrega o .env ANTES de qualquer outro import local ─────────────────────
# Isso garante que os.getenv() funcione corretamente em todos os módulos
from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import threading
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask, jsonify, render_template
from telegram import Bot
from telegram.error import TelegramError

from database import add_log, get_recent_deals, get_recent_logs, get_stats, init_db, is_deal_posted, save_deal
from scraper import fetch_all_deals
from ai_generator import init_gemini, generate_sales_copy

TELEGRAM_TOKEN         = os.getenv("TELEGRAM_TOKEN")          # Token do @BotFather
TELEGRAM_CHANNEL       = os.getenv("TELEGRAM_CHANNEL")        # Ex: @meucanaldeofertas
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "15"))
MAX_DEALS_PER_RUN      = int(os.getenv("MAX_DEALS_PER_RUN", "5"))
DASHBOARD_PORT         = int(os.getenv("PORT", "5000"))        # Railway usa $PORT

# ─── Logger padrão Python ────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Estado global compartilhado entre o bot e o dashboard ──────────────────
bot_state = {
    "started_at": None,    # datetime de quando o bot iniciou
    "next_check": None,    # datetime da próxima verificação agendada
    "running": False,      # True enquanto o bot está ativo
    "last_error": None,    # Último erro registrado (string ou None)
}


# ════════════════════════════════════════════════════════════════════════════
#  LÓGICA DO BOT
# ════════════════════════════════════════════════════════════════════════════

def format_message(deal: dict, sales_copy: str = None) -> str:
    """
    Monta o texto do post no Telegram usando Markdown.
    Se sales_copy for fornecida (gerada pelo Gemini), ela é incluída
    logo abaixo do título como headline de vendas.

    Exemplo de saída com IA:
        🔥 *Notebook Dell por R$ 2.499*

        Preço absurdo para um produto tão completo. Aproveita antes de acabar!

        💰 R$ 2.499
        🔗 Ver oferta
        📌 Fonte: Pelando
    """
    emoji = deal.get("emoji", "🛍️")
    lines = [f"{emoji} *{deal['title']}*", ""]

    # Headline gerada pela IA (opcional)
    if sales_copy:
        lines += [f"_{sales_copy}_", ""]

    if deal.get("price"):
        lines += [f"💰 {deal['price']}", ""]

    lines += [
        f"🔗 [Ver oferta]({deal['url']})",
        f"📌 Fonte: {deal['source']}",
    ]
    return "\n".join(lines)


async def post_deal(bot: Bot, deal: dict) -> bool:
    """
    Tenta postar um deal no canal:
      1. Chama o Gemini para gerar headline de vendas (se configurado)
      2. Com foto (send_photo) se houver image_url
      3. Fallback para só texto (send_message) se a foto falhar
    Retorna True se postou com sucesso.
    """
    # Gera headline de vendas com IA (retorna None se Gemini não estiver configurado)
    sales_copy = await generate_sales_copy(deal["title"])
    message = format_message(deal, sales_copy=sales_copy)

    # Tentativa 1: mensagem com foto
    if deal.get("image_url"):
        try:
            await bot.send_photo(
                chat_id=TELEGRAM_CHANNEL,
                photo=deal["image_url"],
                caption=message,
                parse_mode="Markdown",
            )
            return True
        except TelegramError:
            # Foto inválida ou inacessível — tenta só texto
            pass

    # Tentativa 2: só texto (com preview do link)
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHANNEL,
            text=message,
            parse_mode="Markdown",
            disable_web_page_preview=False,
        )
        return True
    except TelegramError as e:
        logger.error(f"Erro ao postar '{deal['title']}': {e}")
        add_log("ERROR", f"Erro Telegram: {e}")
        bot_state["last_error"] = str(e)
        return False


async def check_and_post_deals():
    """
    Job agendado: busca deals, filtra duplicatas e posta os novos.
    Executa a cada CHECK_INTERVAL_MINUTES minutos.
    """
    logger.info("🔍 Verificando novas promoções...")
    add_log("INFO", "Iniciando verificação de promoções")

    bot = Bot(token=TELEGRAM_TOKEN)

    try:
        # 1. Busca deals de todas as fontes RSS em paralelo
        all_deals, errors = await fetch_all_deals()

        # Registra erros de scraping (bot continua rodando mesmo com falhas parciais)
        for err in errors:
            logger.warning(err)
            add_log("WARNING", err)

        # 2. Filtra apenas os deals que ainda não foram postados
        new_deals = [d for d in all_deals if not is_deal_posted(d["id"])]

        if not new_deals:
            logger.info("✅ Nenhum deal novo no momento.")
            add_log("INFO", "Nenhum deal novo encontrado")
            return

        count = len(new_deals)
        cap = MAX_DEALS_PER_RUN
        logger.info(f"📢 {count} deals novos | postando até {cap}")
        add_log("INFO", f"{count} deals novos encontrados")

        # 3. Posta no máximo MAX_DEALS_PER_RUN por rodada (evita flood)
        posted = 0
        for deal in new_deals[:cap]:
            if await post_deal(bot, deal):
                save_deal(
                    deal_id=deal["id"],
                    title=deal["title"],
                    url=deal["url"],
                    source=deal["source"],
                    price=deal.get("price"),
                    image_url=deal.get("image_url"),
                )
                posted += 1
                await asyncio.sleep(2)  # pausa entre posts (anti-flood)

        logger.info(f"✅ {posted} deal(s) postado(s) com sucesso.")
        add_log("INFO", f"{posted} deal(s) postados")

    except Exception as e:
        logger.error(f"Erro inesperado: {e}")
        add_log("ERROR", f"Erro inesperado: {e}")
        bot_state["last_error"] = str(e)

    finally:
        # Atualiza horário da próxima verificação
        bot_state["next_check"] = datetime.now() + timedelta(
            minutes=CHECK_INTERVAL_MINUTES
        )


# ════════════════════════════════════════════════════════════════════════════
#  DASHBOARD FLASK
# ════════════════════════════════════════════════════════════════════════════

app = Flask(__name__, template_folder="templates")


@app.route("/")
def index():
    """Serve o dashboard HTML principal"""
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    """Retorna status do bot: se está rodando, próxima verificação, etc."""
    next_check = bot_state.get("next_check")
    started_at = bot_state.get("started_at")
    return jsonify({
        "running": bot_state["running"],
        "started_at": started_at.isoformat() if started_at else None,
        "next_check": next_check.isoformat() if next_check else None,
        "last_error": bot_state.get("last_error"),
        "channel": TELEGRAM_CHANNEL,
        "interval_minutes": CHECK_INTERVAL_MINUTES,
    })


@app.route("/api/stats")
def api_stats():
    """Retorna estatísticas de deals postados"""
    return jsonify(get_stats())


@app.route("/api/deals")
def api_deals():
    """Retorna os deals mais recentes postados"""
    return jsonify(get_recent_deals(limit=30))


@app.route("/api/logs")
def api_logs():
    """Retorna os logs mais recentes do sistema"""
    return jsonify(get_recent_logs(limit=50))


def run_dashboard():
    """Roda o Flask em uma thread separada (não bloqueia o event loop do bot)"""
    app.run(
        host="0.0.0.0",
        port=DASHBOARD_PORT,
        debug=False,
        use_reloader=False,   # IMPORTANTE: reloader quebra threads
    )


# ════════════════════════════════════════════════════════════════════════════
#  INICIALIZAÇÃO
# ════════════════════════════════════════════════════════════════════════════

async def main():
    """Ponto de entrada: valida configurações, inicia o scheduler e o dashboard"""

    # ── Validação das variáveis obrigatórias ──────────────────────────────
    if not TELEGRAM_TOKEN:
        raise EnvironmentError("❌ TELEGRAM_TOKEN não definido no .env")
    if not TELEGRAM_CHANNEL:
        raise EnvironmentError("❌ TELEGRAM_CHANNEL não definido no .env")

    # ── Inicializa o banco de dados ───────────────────────────────────────
    init_db()
    logger.info("✅ Banco de dados pronto.")

    # ── Inicializa o Gemini (opcional — bot funciona sem ele) ─────────────
    init_gemini()

    # ── Sobe o dashboard Flask em thread daemon ───────────────────────────
    dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
    dashboard_thread.start()
    logger.info(f"🌐 Dashboard disponível na porta {DASHBOARD_PORT}")

    # ── Configura o agendador assíncrono ──────────────────────────────────
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_and_post_deals,
        trigger="interval",
        minutes=CHECK_INTERVAL_MINUTES,
        id="check_deals",
        next_run_time=datetime.now(),  # executa imediatamente ao iniciar
    )
    scheduler.start()

    # Atualiza estado global
    bot_state["running"] = True
    bot_state["started_at"] = datetime.now()
    bot_state["next_check"] = datetime.now() + timedelta(minutes=CHECK_INTERVAL_MINUTES)

    logger.info(f"🤖 Bot rodando! Canal: {TELEGRAM_CHANNEL} | Intervalo: {CHECK_INTERVAL_MINUTES}min")
    add_log("INFO", f"Bot iniciado. Canal: {TELEGRAM_CHANNEL}")

    # ── Loop principal (mantém o processo vivo) ───────────────────────────
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot encerrado pelo usuário.")
        bot_state["running"] = False
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
