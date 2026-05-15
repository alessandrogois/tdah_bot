from datetime import time
from zoneinfo import ZoneInfo
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

from config import TIMEZONE, CHAT_ID
from database import get_focus, get_water_count, get_notes

TZ = ZoneInfo(TIMEZONE)

def is_fim_de_semana() -> bool:
    """Retorna True se hoje é sábado (5) ou domingo (6)."""
    return datetime.now(TZ).weekday() in (5, 6)

def schedule_jobs(app: Application):
    jq = app.job_queue

    # Resumo matinal — 08h00
    jq.run_daily(resumo_matinal, time=time(8, 0, tzinfo=TZ), name="resumo_matinal")

    # Lembretes de água — a cada 90 minutos, entre 8h e 22h
    for hora in range(8, 22):
        if hora % 2 == 0:  # 8h, 10h, 12h, 14h, 16h, 18h, 20h
            jq.run_daily(lembrete_agua_job, time=time(hora, 30, tzinfo=TZ), name=f"agua_{hora}")

    # Lembrete de refeição — 13h e 19h30
    jq.run_daily(lembrete_almoco, time=time(13, 0, tzinfo=TZ), name="almoco")
    jq.run_daily(lembrete_jantar, time=time(19, 30, tzinfo=TZ), name="jantar")

    # Check-in noturno — 21h30
    jq.run_daily(checkin_noturno, time=time(21, 30, tzinfo=TZ), name="checkin_noturno")

# Lembrete de medicação — ajuste o horário aqui
    jq.run_daily(lembrete_medicacao, time=time(8, 0, tzinfo=TZ), name="medicacao")
# ─── Resumo matinal ────────────────────────────────────────────────────────────

async def resumo_matinal(context):
    if is_fim_de_semana():
        return

    from datetime import datetime
    import httpx

    dia = datetime.now(TZ).strftime("%A, %d/%m")
    dias_pt = {
        "Monday": "Segunda", "Tuesday": "Terça", "Wednesday": "Quarta",
        "Thursday": "Quinta", "Friday": "Sexta", "Saturday": "Sábado", "Sunday": "Domingo"
    }
    for en, pt in dias_pt.items():
        dia = dia.replace(en, pt)

    foco = get_focus(CHAT_ID) or "ainda não definido"

    # Clima simples via wttr.in (sem chave de API)
    clima = ""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("https://wttr.in/?format=%C+%t", headers={"Accept-Language": "pt"})
            clima = f"\nClima: {r.text.strip()}"
    except Exception:
        pass

    texto = (
        f"Bom dia! Hoje é {dia}.{clima}\n\n"
        f"Foco de hoje: *{foco}*\n\n"
        "Pronto para começar? Use /foco [tarefa] para definir sua prioridade."
    )
    await context.bot.send_message(chat_id=CHAT_ID, text=texto, parse_mode="Markdown")


# ─── Lembretes de água ─────────────────────────────────────────────────────────

async def lembrete_agua_job(context):
    keyboard = [[
        InlineKeyboardButton("Bebi ✓", callback_data="agua_bebi"),
        InlineKeyboardButton("Daqui a pouco", callback_data="agua_depois"),
    ]]
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text="Lembrete: beba água agora.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ─── Refeições ─────────────────────────────────────────────────────────────────

async def lembrete_almoco(context):
    if is_fim_de_semana():
        return
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text="Hora do almoço! Já parou para comer?"
    )


async def lembrete_jantar(context):
    if is_fim_de_semana():
        return
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text="Hora do jantar. Não pule essa refeição."
    )


# ─── Check-in noturno ──────────────────────────────────────────────────────────

async def checkin_noturno(context):
    if is_fim_de_semana():
        return
    water_count = get_water_count(CHAT_ID)
    notes = get_notes(CHAT_ID)
    
    texto = (
        f"Check-in noturno 🌙\n\n"
        f"Água bebida hoje: {water_count} copos\n"
        f"Anotações: {notes or 'nenhuma'}\n\n"
        "Durma bem! 💤"
    )
    await context.bot.send_message(chat_id=CHAT_ID, text=texto, parse_mode="Markdown")


async def resumo_matinal(context):
    if is_fim_de_semana():
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text="Bom dia! Hoje é fim de semana — descanse, sem agenda. Só água e medicação no radar."
        )
        return
    from datetime import datetime
    import httpx

    dia = datetime.now(TZ).strftime("%A, %d/%m")
    dias_pt = {
        "Monday": "Segunda", "Tuesday": "Terça", "Wednesday": "Quarta",
        "Thursday": "Quinta", "Friday": "Sexta", "Saturday": "Sábado", "Sunday": "Domingo"
    }
    for en, pt in dias_pt.items():
        dia = dia.replace(en, pt)

    foco = get_focus(CHAT_ID)

    clima = ""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("https://wttr.in/?format=%C+%t", headers={"Accept-Language": "pt"})
            clima = f"\nClima: {r.text.strip()}"
    except Exception:
        pass

    hora = datetime.now(TZ).hour
    saudacao = "Bom dia! ☀️ " if hora < 12 else "Boa tarde! " if hora < 18 else "Boa noite! "

    texto = (
        f"{saudacao}Hoje é {dia}.{clima}\n\n"
        f"Foco de hoje: *{foco or 'não definido'}*\n\n"
        "Use /foco [tarefa] para definir sua prioridade."
    )
    await context.bot.send_message(chat_id=CHAT_ID, text=texto, parse_mode="Markdown")

async def lembrete_medicacao(context):
    keyboard = [[
        InlineKeyboardButton("Tomei ✓", callback_data="med_tomei"),
        InlineKeyboardButton("Lembrar em 15min", callback_data="med_depois"),
    ]]
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text="Hora do medicamento! Já tomou hoje?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def lembrete_medicacao_retry(context):
    keyboard = [[
        InlineKeyboardButton("Tomei ✓", callback_data="med_tomei"),
        InlineKeyboardButton("Lembrar em 15min", callback_data="med_depois"),
    ]]
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text="Lembrete: você ainda não confirmou o medicamento.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )