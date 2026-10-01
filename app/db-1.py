"""
Camada de dados do agente. Usa SQLite (arquivo local) para começar.
Troque por Postgres/Google Calendar quando for para produção séria.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = "salao.db"

SERVICOS = {
    "corte": {"nome": "Corte feminino", "minutos": 45, "preco": 80},
    "escova": {"nome": "Escova", "minutos": 40, "preco": 60},
    "coloracao": {"nome": "Coloração", "minutos": 150, "preco": 220},
    "masculino": {"nome": "Corte masculino", "minutos": 30, "preco": 50},
}

PROFISSIONAIS = ["Marina", "Rafael"]

# Horário de funcionamento (simplificado: mesmo todo dia)
ABERTURA, FECHAMENTO = "09:00", "19:00"


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                telefone TEXT PRIMARY KEY,
                nome TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agendamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telefone TEXT,
                servico TEXT,
                profissional TEXT,
                inicio TEXT,   -- ISO 8601
                fim TEXT,      -- ISO 8601
                status TEXT DEFAULT 'confirmado'  -- confirmado | cancelado
            )
        """)


def buscar_cliente(telefone: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM clientes WHERE telefone = ?", (telefone,)
        ).fetchone()
        if row:
            return dict(row)
        conn.execute("INSERT INTO clientes (telefone, nome) VALUES (?, ?)", (telefone, None))
        return {"telefone": telefone, "nome": None}


def salvar_nome_cliente(telefone: str, nome: str):
    with get_db() as conn:
        conn.execute("UPDATE clientes SET nome = ? WHERE telefone = ?", (nome, telefone))


def listar_agendamentos_futuros(telefone: str):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM agendamentos
               WHERE telefone = ? AND status = 'confirmado' AND inicio > ?
               ORDER BY inicio ASC""",
            (telefone, datetime.now().isoformat()),
        ).fetchall()
        return [dict(r) for r in rows]


def horarios_ocupados(profissional: str, dia_iso: str):
    """dia_iso: 'YYYY-MM-DD'. Retorna [(inicio, fim), ...] já ocupados naquele dia."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT inicio, fim FROM agendamentos
               WHERE profissional = ? AND status = 'confirmado' AND inicio LIKE ?""",
            (profissional, f"{dia_iso}%"),
        ).fetchall()
        return [(r["inicio"], r["fim"]) for r in rows]


def criar_agendamento(telefone, servico, profissional, inicio_iso, fim_iso):
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO agendamentos (telefone, servico, profissional, inicio, fim)
               VALUES (?, ?, ?, ?, ?)""",
            (telefone, servico, profissional, inicio_iso, fim_iso),
        )
        return cur.lastrowid


def cancelar_agendamento(agendamento_id: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE agendamentos SET status = 'cancelado' WHERE id = ?", (agendamento_id,)
        )
