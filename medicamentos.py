from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import TIMEZONE
from database import listar_medicamentos, desativar_medicamento, registrar_dose, salvar_medicamento

TZ = ZoneInfo(TIMEZONE)


async def agendar_medicamentos(app):
    """Agenda os lembretes de todos os medicamentos ativos."""
    from config import CHAT_ID
    meds = listar_medicamentos(CHAT_ID)
    for med in meds:
        agendar_um(app, med)


def agendar_um(app, med: dict):
    from config import CHAT_ID
    agora = datetime.now(TZ)
    fim = datetime.fromisoformat(med["fim"]).replace(tzinfo=TZ)

    if agora > fim:
        desativar_medicamento(med["id"])
        return

    # Calcula próximo horário com base na hora_inicio e intervalo
    hora, minuto = map(int, med["hora_inicio"].split(":"))
    proximo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)

    # Avança pelos intervalos até achar o próximo no futuro
    while proximo <= agora:
        proximo += timedelta(hours=med["intervalo_horas"])

    # Não agenda se já passou do fim do tratamento
    if proximo > fim:
        return

    job_name = f"med_{med['id']}_{proximo.isoformat()}"

    app.job_queue.run_once(
        disparar_med,
        when=proximo,
        chat_id=CHAT_ID,
        data={"med": med},
        name=job_name
    )


async def disparar_med(context):
    from config import CHAT_ID
    med = context.job.data["med"]
    agora = datetime.now(TZ)
    fim = datetime.fromisoformat(med["fim"]).replace(tzinfo=TZ)

    keyboard = [[
        InlineKeyboardButton("Tomei ✓", callback_data=f"med_tomei:{med['id']}"),
        InlineKeyboardButton("15 minutos", callback_data=f"med_depois:{med['id']}"),
    ]]

    dias_restantes = (fim - agora).days
    texto = (
        f"Hora do medicamento!\n"
        f"*{med['nome']}*\n\n"
        f"Tratamento: {dias_restantes} dias restantes"
    )

    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=texto,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

    # Reagenda para o próximo horário
    agendar_um(context.application, med)


async def med_callback(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    acao, med_id = query.data.split(":")
    med_id = int(med_id)

    if acao == "med_tomei":
        registrar_dose(user_id, med_id)
        await query.edit_message_text("Registrado! Dose confirmada.")

    elif acao == "med_depois":
        # Reenviar em 15 minutos
        meds = listar_medicamentos(user_id)
        med = next((m for m in meds if m["id"] == med_id), None)
        if med:
            context.job_queue.run_once(
                disparar_med,
                when=15 * 60,
                chat_id=query.message.chat_id,
                data={"med": med},
                name=f"med_retry_{med_id}"
            )
        await query.edit_message_text("Ok! Te lembro em 15 minutos.")