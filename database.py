"""
database.py — Módulo de banco de dados SQLite
Responsável por: salvar deals postados, evitar duplicatas, armazenar logs do sistema
"""
import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional

# Caminho do banco — pode ser sobrescrito pelo .env
DB_PATH = os.getenv("DB_PATH", "deals.db")


def get_connection() -> sqlite3.Connection:
    """Retorna uma conexão com o banco com suporte a dicionários nas linhas"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # permite acessar colunas pelo nome
    return conn


def init_db():
    """
    Cria as tabelas caso ainda não existam.
    Seguro para rodar múltiplas vezes (idempotente).
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Tabela principal: deals postados no canal
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_id     TEXT UNIQUE NOT NULL,      -- hash MD5 da URL (chave de dedup)
            title       TEXT NOT NULL,
            url         TEXT NOT NULL,
            source      TEXT NOT NULL,             -- nome da fonte: Pelando, Promobit...
            price       TEXT,                      -- preço extraído do título, se encontrado
            image_url   TEXT,                      -- URL da imagem do deal
            posted_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tabela de logs: INFO, WARNING, ERROR
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            level       TEXT NOT NULL,
            message     TEXT NOT NULL,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# ─── DEALS ──────────────────────────────────────────────────────────────────

def is_deal_posted(deal_id: str) -> bool:
    """Retorna True se o deal já foi postado antes (evita duplicata)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM deals WHERE deal_id = ?", (deal_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def save_deal(
    deal_id: str,
    title: str,
    url: str,
    source: str,
    price: Optional[str] = None,
    image_url: Optional[str] = None,
):
    """Salva um deal após ele ser postado com sucesso no Telegram"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO deals (deal_id, title, url, source, price, image_url)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (deal_id, title, url, source, price, image_url),
    )
    conn.commit()
    conn.close()


def get_recent_deals(limit: int = 30) -> List[Dict]:
    """Retorna os deals mais recentes para exibição no dashboard"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM deals ORDER BY posted_at DESC LIMIT ?", (limit,)
    )
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


# ─── LOGS ───────────────────────────────────────────────────────────────────

def add_log(level: str, message: str):
    """Registra um evento no banco. level: 'INFO', 'WARNING', 'ERROR'"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO logs (level, message) VALUES (?, ?)", (level, message)
    )
    conn.commit()
    conn.close()


def get_recent_logs(limit: int = 50) -> List[Dict]:
    """Retorna os logs mais recentes para o painel de monitoramento"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM logs ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


# ─── STATS ──────────────────────────────────────────────────────────────────

def get_stats() -> Dict:
    """
    Retorna métricas do bot para o dashboard:
    - total de deals postados
    - deals postados hoje
    - quantidade por fonte (Pelando, Promobit, etc.)
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Total geral
    cursor.execute("SELECT COUNT(*) FROM deals")
    total_deals = cursor.fetchone()[0]

    # Total do dia atual
    cursor.execute(
        "SELECT COUNT(*) FROM deals WHERE DATE(posted_at) = DATE('now')"
    )
    today_deals = cursor.fetchone()[0]

    # Breakdown por fonte
    cursor.execute(
        "SELECT source, COUNT(*) as count FROM deals GROUP BY source ORDER BY count DESC"
    )
    by_source = [{"source": row[0], "count": row[1]} for row in cursor.fetchall()]

    conn.close()
    return {
        "total": total_deals,
        "today": today_deals,
        "by_source": by_source,
    }
