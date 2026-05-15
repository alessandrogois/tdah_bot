import sqlite3
from datetime import datetime, date
from zoneinfo import ZoneInfo
from config import TIMEZONE, DB_PATH

TZ = ZoneInfo(TIMEZONE)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS focus (
                user_id INTEGER PRIMARY KEY,
                task TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS water_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                logged_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS historico (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS medicamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    hora_inicio TEXT NOT NULL,
    intervalo_horas INTEGER NOT NULL,
    duracao_dias INTEGER NOT NULL,
    inicio TEXT NOT NULL,
    fim TEXT NOT NULL,
    ativo INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS doses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    med_id INTEGER NOT NULL,
    tomado_em TEXT NOT NULL
);
        """)
    print("Banco de dados inicializado.")

# ─── Notas ─────────────────────────────────────────────────────────────────────

def save_note(user_id: int, text: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO notes (user_id, text, created_at) VALUES (?, ?, ?)",
            (user_id, text, datetime.now(TZ).isoformat())
        )


def get_notes(user_id: int, dias: int = 1) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT text FROM notes WHERE user_id = ? AND date(created_at) >= date('now', ? || ' days') ORDER BY created_at DESC",
            (user_id, f"-{dias - 1}")
        ).fetchall()
    return [r["text"] for r in rows]


# ─── Foco ──────────────────────────────────────────────────────────────────────

def save_focus(user_id: int, task: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO focus (user_id, task, updated_at) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET task=excluded.task, updated_at=excluded.updated_at",
            (user_id, task, datetime.now(TZ).isoformat())
        )


def get_focus(user_id: int) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT task FROM focus WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row["task"] if row else None


# ─── Água ──────────────────────────────────────────────────────────────────────

def log_water(user_id: int):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO water_log (user_id, logged_at) VALUES (?, ?)",
            (user_id, datetime.now(TZ).isoformat())
        )


def get_water_count(user_id: int) -> int:
    today = date.today().isoformat()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM water_log WHERE user_id = ? AND date(logged_at) = ?",
            (user_id, today)
        ).fetchone()
    return row["cnt"] if row else 0

def init_historico():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS historico (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

def salvar_mensagem(user_id: int, role: str, content: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO historico (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (user_id, role, content, datetime.now(TZ).isoformat())
        )
        # Mantém apenas as últimas 20 mensagens por usuário
        conn.execute("""
            DELETE FROM historico WHERE user_id = ? AND id NOT IN (
                SELECT id FROM historico WHERE user_id = ?
                ORDER BY id DESC LIMIT 20
            )
        """, (user_id, user_id))

def carregar_historico(user_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM historico WHERE user_id = ? ORDER BY id ASC",
            (user_id,)
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]

def salvar_medicamento(user_id: int, nome: str, hora_inicio: str, intervalo_horas: int, duracao_dias: int):
    inicio = datetime.now(TZ)
    fim = inicio + timedelta(days=duracao_dias)
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO medicamentos (user_id, nome, hora_inicio, intervalo_horas, duracao_dias, inicio, fim, ativo)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (user_id, nome, hora_inicio, intervalo_horas, duracao_dias, inicio.isoformat(), fim.isoformat()))


def listar_medicamentos(user_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM medicamentos WHERE user_id = ? AND ativo = 1 ORDER BY hora_inicio
        """, (user_id,)).fetchall()
    return [dict(r) for r in rows]


def desativar_medicamento(med_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE medicamentos SET ativo = 0 WHERE id = ?", (med_id,))


def registrar_dose(user_id: int, med_id: int):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO doses (user_id, med_id, tomado_em)
            VALUES (?, ?, ?)
        """, (user_id, med_id, datetime.now(TZ).isoformat()))