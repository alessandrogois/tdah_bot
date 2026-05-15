import logging
import sqlite3
from datetime import datetime, time
from zoneinfo import ZoneInfo
import re
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

from config import TOKEN, TIMEZONE, GROQ_API_KEY
from database import init_db, save_note, get_notes, save_focus, get_focus, log_water, get_water_count, salvar_mensagem, carregar_historico
from ai import ask_ai, summarize_notes
from jobs import schedule_jobs, lembrete_medicacao_retry

from medicamentos import agendar_medicamentos, med_callback
from database import salvar_medicamento, listar_medicamentos, desativar_medicamento

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TZ = ZoneInfo(TIMEZONE)


# ─── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    await update.message.reply_text(
        f"Oi, {user}! Sou seu assistente pessoal.\n\n"
        "Aqui está o que posso fazer por você:\n\n"
        "/foco [tarefa] — define sua tarefa principal do dia\n"
        "/pomo [tarefa] — inicia um Pomodoro de 25min\n"
        "/n [texto] — captura uma nota rápida\n"
        "/notas — lista suas notas do dia\n"
        "/lembrar 14h30 [texto] — cria um lembrete no horário\n"
        "/dump [texto] — organiza um monte de pensamentos\n"
        "/onde — te lembra o que estava fazendo\n"
        "/agua — registra que bebeu água\n"
        "/remedio — cadastra um novo medicamento\n"
        "/remedios — lista e gerencia seus medicamentos\n"
        "/status — resumo do seu dia\n\n"
        "Pode também me mandar uma mensagem normal que eu respondo."
        
    )


# ─── /foco ─────────────────────────────────────────────────────────────────────

async def foco(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        atual = get_focus(user_id)
        if atual:
            await update.message.reply_text(f"Seu foco atual é: *{atual}*\n\nMande /foco [tarefa] para mudar.", parse_mode="Markdown")
        else:
            await update.message.reply_text("Qual é a tarefa mais importante que você quer concluir hoje?\n\nEx: /foco Finalizar proposta do cliente")
        return

    tarefa = " ".join(context.args)
    save_focus(user_id, tarefa)
    await update.message.reply_text(
        f"Foco definido: *{tarefa}*\n\nQuando você se perder, mande /onde que eu te lembro.",
        parse_mode="Markdown"
    )


# ─── /pomo ─────────────────────────────────────────────────────────────────────

async def pomo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    duracao = 25 * 60  # 25 minutos em segundos

    tarefa = " ".join(context.args) if context.args else get_focus(user_id)
    if not tarefa:
        tarefa = "sua tarefa"

    # Salva contexto do pomodoro ativo
    context.user_data["pomo_tarefa"] = tarefa
    context.user_data["pomo_inicio"] = datetime.now(TZ).isoformat()

    await update.message.reply_text(
        f"Cronômetro iniciado — 25 minutos.\n*{tarefa}*\n\nVai lá, eu aviso quando acabar.",
        parse_mode="Markdown"
    )

    # Agenda o aviso de fim do Pomodoro
    context.job_queue.run_once(
        pomo_fim,
        when=duracao,
        chat_id=update.effective_chat.id,
        data={"tarefa": tarefa, "user_id": user_id},
        name=f"pomo_{user_id}"
    )


async def pomo_fim(context: ContextTypes.DEFAULT_TYPE):
    tarefa = context.job.data["tarefa"]
    keyboard = [
        [
            InlineKeyboardButton("Mais 25min ↻", callback_data="pomo_mais"),
            InlineKeyboardButton("Pausa 5min", callback_data="pomo_pausa"),
        ]
    ]
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=f"Pomodoro encerrado! Você trabalhou 25 minutos em *{tarefa}*.\n\nFaz uma pausa rápida — levanta, respira, bebe água.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def pomo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "pomo_mais":
        tarefa = context.user_data.get("pomo_tarefa", "sua tarefa")
        context.job_queue.run_once(
            pomo_fim,
            when=25 * 60,
            chat_id=query.message.chat_id,
            data={"tarefa": tarefa, "user_id": query.from_user.id},
            name=f"pomo_{query.from_user.id}"
        )
        await query.edit_message_text(f"Mais 25 minutos iniciados!\n*{tarefa}*\n\nVai lá.", parse_mode="Markdown")

    elif query.data == "pomo_pausa":
        context.job_queue.run_once(
            pausa_fim,
            when=5 * 60,
            chat_id=query.message.chat_id,
            data={},
            name=f"pausa_{query.from_user.id}"
        )
        await query.edit_message_text("Pausa de 5 minutos. Te aviso quando acabar.")


async def pausa_fim(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text="Pausa encerrada! Pronto para continuar?"
    )


# ─── /n (nota rápida) ──────────────────────────────────────────────────────────

async def nota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("O que você quer anotar?\n\nEx: /n ligar pra advogada essa semana")
        return

    texto = " ".join(context.args)
    save_note(user_id, texto)

    keyboard = [[InlineKeyboardButton("Lembrar amanhã cedo", callback_data=f"lembrar_nota:{texto[:50]}")]]
    await update.message.reply_text(
        f"Anotado: _{texto}_",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def nota_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("lembrar_nota:"):
        nota_texto = query.data.split(":", 1)[1]
        # Agenda lembrete para o dia seguinte às 9h
        amanha_9h = datetime.now(TZ).replace(hour=9, minute=0, second=0, microsecond=0)
        context.job_queue.run_once(
            lembrete_nota,
            when=amanha_9h,
            chat_id=query.message.chat_id,
            data={"nota": nota_texto}
        )
        await query.edit_message_text(f"Anotado: _{nota_texto}_\n\nTe lembro amanhã às 9h.", parse_mode="Markdown")


async def lembrete_nota(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=f"Lembrete de ontem: _{context.job.data['nota']}_",
        parse_mode="Markdown"
    )


# ─── /notas ────────────────────────────────────────────────────────────────────

async def notas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lista = get_notes(user_id, dias=1)
    if not lista:
        await update.message.reply_text("Nenhuma nota hoje. Use /n [texto] para capturar algo.")
        return
    texto = "Suas notas de hoje:\n\n" + "\n".join(f"• {n}" for n in lista)
    await update.message.reply_text(texto)


# ─── /dump ─────────────────────────────────────────────────────────────────────

async def dump(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Manda tudo que está na sua cabeça agora — ideias, preocupações, tarefas, qualquer coisa.\n\nEx: /dump preciso ligar pra mãe, relatório travado, quero estudar inglês, comprar café"
        )
        return

    texto = " ".join(context.args)
    await update.message.reply_text("Organizando isso pra você...")

    resposta = await ask_ai(
        f"O usuário tem TDAH e fez um dump mental. Organize de forma clara e gentil, separando em: tarefas rápidas, tarefas maiores, e ideias/desejos. Seja conciso. Dump: {texto}",
        system="Você é um assistente pessoal gentil e organizado, especializado em ajudar pessoas com TDAH. Responda sempre em português, de forma direta e sem julgamentos."
    )
    await update.message.reply_text(resposta)


# ─── /onde ─────────────────────────────────────────────────────────────────────

async def onde(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    pomo_tarefa = context.user_data.get("pomo_tarefa")
    foco_atual = get_focus(user_id)

    partes = []
    if pomo_tarefa:
        partes.append(f"Você estava em um Pomodoro: *{pomo_tarefa}*")
    if foco_atual:
        partes.append(f"Foco do dia: *{foco_atual}*")

    if partes:
        await update.message.reply_text("\n".join(partes), parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "Não tenho um contexto ativo registrado.\n\nQual é sua tarefa agora? Use /foco [tarefa] para definir."
        )


# ─── /agua ─────────────────────────────────────────────────────────────────────

async def agua(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    log_water(user_id)
    count = get_water_count(user_id)
    mensagens = [
        "Ótimo!", "Muito bem!", "Isso aí!", "Continua assim!", "Perfeito!"
    ]
    import random
    msg = random.choice(mensagens)
    await update.message.reply_text(f"{msg} Você bebeu água {count}x hoje.")


async def agua_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "agua_bebi":
        log_water(user_id)
        count = get_water_count(user_id)
        await query.edit_message_text(f"Registrado! Você bebeu água {count}x hoje.")
    elif query.data == "agua_depois":
        # Reagenda para 20 minutos
        context.job_queue.run_once(
            lembrete_agua,
            when=20 * 60,
            chat_id=query.message.chat_id,
            data={"user_id": user_id},
            name=f"agua_retry_{user_id}"
        )
        await query.edit_message_text("Ok! Te lembro em 20 minutos.")


async def lembrete_agua(context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("Bebi ✓", callback_data="agua_bebi"),
        InlineKeyboardButton("Daqui a pouco", callback_data="agua_depois"),
    ]]
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text="Lembrete: beba água agora.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ─── /status ───────────────────────────────────────────────────────────────────

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    foco_atual = get_focus(user_id)
    water = get_water_count(user_id)
    notas_hoje = get_notes(user_id, dias=1)

    linhas = [f"Resumo do seu dia — {datetime.now(TZ).strftime('%d/%m %H:%M')}\n"]
    linhas.append(f"Foco: {foco_atual or 'não definido'}")
    linhas.append(f"Água: {water}x hoje")
    linhas.append(f"Notas: {len(notas_hoje)} capturadas")

    await update.message.reply_text("\n".join(linhas))


# ─── Mensagem livre → IA ───────────────────────────────────────────────────────

async def mensagem_livre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    texto = update.message.text

    # Carrega histórico do banco
    historico = carregar_historico(user_id)

    # Adiciona mensagem nova
    historico.append({"role": "user", "content": texto})
    salvar_mensagem(user_id, "user", texto)

    resposta = await ask_ai(None, historico=historico)

    # Salva resposta do bot
    salvar_mensagem(user_id, "assistant", resposta)

    await update.message.reply_text(resposta)

async def med_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "med_tomei":
        await query.edit_message_text("Ótimo! Medicamento registrado.")

    elif query.data == "med_depois":
        context.job_queue.run_once(
            lembrete_medicacao_retry,
            when=15 * 60,
            chat_id=query.message.chat_id,
            data={},
            name=f"med_retry_{query.from_user.id}"
        )
        await query.edit_message_text("Ok! Te lembro em 15 minutos.")


async def remedio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o cadastro de um medicamento."""
    context.user_data["cadastro_med"] = {}
    await update.message.reply_text(
        "Vamos cadastrar um medicamento.\n\n"
        "Qual é o nome do medicamento?"
    )
    context.user_data["etapa_med"] = "nome"


async def meus_remedios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista medicamentos ativos."""
    user_id = update.effective_user.id
    meds = listar_medicamentos(user_id)
    if not meds:
        await update.message.reply_text("Nenhum medicamento cadastrado.\n\nUse /remedio para cadastrar.")
        return

    linhas = ["Seus medicamentos ativos:\n"]
    for m in meds:
        fim = datetime.fromisoformat(m["fim"]).replace(tzinfo=TZ)
        dias = (fim - datetime.now(TZ)).days
        linhas.append(f"*{m['nome']}*\nA cada {m['intervalo_horas']}h — {dias} dias restantes\n")

    keyboard = [[InlineKeyboardButton(f"Remover {m['nome']}", callback_data=f"med_remover:{m['id']}")] for m in meds]
    await update.message.reply_text("\n".join(linhas), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def cadastro_med_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gerencia o fluxo de cadastro passo a passo."""
    etapa = context.user_data.get("etapa_med")
    if not etapa:
        return False  # Não está em cadastro

    texto = update.message.text.strip()

    if etapa == "nome":
        context.user_data["cadastro_med"]["nome"] = texto
        context.user_data["etapa_med"] = "intervalo"
        keyboard = [[
            InlineKeyboardButton("6 em 6h", callback_data="med_intervalo:6"),
            InlineKeyboardButton("8 em 8h", callback_data="med_intervalo:8"),
            InlineKeyboardButton("12 em 12h", callback_data="med_intervalo:12"),
            InlineKeyboardButton("24h (1x/dia)", callback_data="med_intervalo:24"),
        ]]
        await update.message.reply_text(
            f"Medicamento: *{texto}*\n\nDe quantas em quantas horas?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return True

    if etapa == "horario":
        # Valida formato HH:MM
        import re
        if not re.match(r"^\d{1,2}:\d{2}$", texto):
            await update.message.reply_text("Formato inválido. Use HH:MM, por exemplo: 08:00")
            return True
        hora, minuto = map(int, texto.split(":"))
        if not (0 <= hora <= 23 and 0 <= minuto <= 59):
            await update.message.reply_text("Horário inválido. Use HH:MM, por exemplo: 08:00")
            return True
        context.user_data["cadastro_med"]["hora_inicio"] = texto
        context.user_data["etapa_med"] = "duracao"
        keyboard = [[
            InlineKeyboardButton("30 dias", callback_data="med_duracao:30"),
            InlineKeyboardButton("60 dias", callback_data="med_duracao:60"),
            InlineKeyboardButton("90 dias", callback_data="med_duracao:90"),
            InlineKeyboardButton("Contínuo", callback_data="med_duracao:3650"),
        ]]
        await update.message.reply_text(
            "Por quanto tempo?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return True

    return False


async def med_cadastro_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    acao, valor = query.data.split(":")

    if acao == "med_intervalo":
        context.user_data["cadastro_med"]["intervalo_horas"] = int(valor)
        context.user_data["etapa_med"] = "horario"
        await query.edit_message_text(
            f"Intervalo: a cada *{valor}h*\n\nQual horário da primeira dose? (ex: 08:00)",
            parse_mode="Markdown"
        )

    elif acao == "med_duracao":
        dados = context.user_data.get("cadastro_med", {})
        dados["duracao_dias"] = int(valor)
        duracao_txt = "contínuo" if int(valor) >= 3650 else f"{valor} dias"

        salvar_medicamento(
            user_id=user_id,
            nome=dados["nome"],
            hora_inicio=dados["hora_inicio"],
            intervalo_horas=dados["intervalo_horas"],
            duracao_dias=dados["duracao_dias"]
        )

        # Agenda os lembretes
        meds = listar_medicamentos(user_id)
        med = next((m for m in meds if m["nome"] == dados["nome"]), None)
        if med:
            from medicamentos import agendar_um
            agendar_um(context.application, med)

        context.user_data.pop("etapa_med", None)
        context.user_data.pop("cadastro_med", None)

        await query.edit_message_text(
            f"Medicamento cadastrado!\n\n"
            f"*{dados['nome']}*\n"
            f"A cada {dados['intervalo_horas']}h, começando às {dados['hora_inicio']}\n"
            f"Duração: {duracao_txt}",
            parse_mode="Markdown"
        )

    elif acao == "med_remover":
        desativar_medicamento(int(valor))
        await query.edit_message_text("Medicamento removido.")


async def mensagem_livre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Verifica se está em fluxo de cadastro de medicamento
    if await cadastro_med_handler(update, context):
        return

    user_id = update.effective_user.id
    texto = update.message.text
    historico = carregar_historico(user_id)
    historico.append({"role": "user", "content": texto})
    if len(historico) > 10:
        historico = historico[-10:]
    resposta = await ask_ai(None, historico=historico)
    salvar_mensagem(user_id, "assistant", resposta)
    context.user_data["historico"] = historico
    await update.message.reply_text(resposta)

# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("foco", foco))
    app.add_handler(CommandHandler("pomo", pomo))
    app.add_handler(CommandHandler("n", nota))
    app.add_handler(CommandHandler("notas", notas))
    app.add_handler(CommandHandler("dump", dump))
    app.add_handler(CommandHandler("onde", onde))
    app.add_handler(CommandHandler("agua", agua))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("lembrar", lembrar))

    # Callbacks de botões inline
    app.add_handler(CallbackQueryHandler(pomo_callback, pattern="^pomo_"))
    app.add_handler(CallbackQueryHandler(nota_callback, pattern="^lembrar_nota:"))
    app.add_handler(CallbackQueryHandler(agua_callback, pattern="^agua_"))
    app.add_handler(CallbackQueryHandler(med_callback, pattern="^med_"))
    app.add_handler(CommandHandler("remedio", remedio))
    app.add_handler(CommandHandler("remedios", meus_remedios))
    app.add_handler(CallbackQueryHandler(med_callback, pattern="^med_tomei:|^med_depois:"))
    app.add_handler(CallbackQueryHandler(med_cadastro_callback, pattern="^med_intervalo:|^med_duracao:|^med_remover:"))

    # Mensagens livres
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem_livre))

    # Agenda jobs recorrentes (água, resumo matinal, check-in noturno)
    schedule_jobs(app)


    logger.info("Bot iniciado.")
    
    import asyncio
    asyncio.get_event_loop().run_until_complete(agendar_medicamentos(app))

    app.run_polling()


async def lembrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Formatos aceitos:
      /lembrar 14h30 Tomar remédio
      /lembrar 09:00 Ligar pro banco
      /lembrar 20min Pausar o trabalho
      /lembrar amanhã 08h Reunião com cliente
    """
    if not context.args:
        await update.message.reply_text(
            "Como usar:\n"
            "/lembrar 14h30 Tomar remédio\n"
            "/lembrar 20min Pausar o trabalho\n"
            "/lembrar amanhã 08h Reunião com cliente"
        )
        return

    texto_completo = " ".join(context.args)
    agora = datetime.now(TZ)
    quando = None
    mensagem = None

    # Formato: "20min texto"
    match = re.match(r"^(\d+)min (.+)$", texto_completo)
    if match:
        minutos = int(match.group(1))
        mensagem = match.group(2)
        quando = agora + timedelta(minutes=minutos)

    # Formato: "amanhã 08h texto" ou "amanhã 08:30 texto"
    if not quando:
        match = re.match(r"^amanhã (\d{1,2})[:h]?(\d{0,2}) (.+)$", texto_completo)
        if match:
            hora = int(match.group(1))
            minuto = int(match.group(2)) if match.group(2) else 0
            mensagem = match.group(3)
            quando = (agora + timedelta(days=1)).replace(hour=hora, minute=minuto, second=0, microsecond=0)

    # Formato: "14h30 texto" ou "14:30 texto" ou "14h texto"
    if not quando:
        match = re.match(r"^(\d{1,2})[:h](\d{0,2}) (.+)$", texto_completo)
        if match:
            hora = int(match.group(1))
            minuto = int(match.group(2)) if match.group(2) else 0
            mensagem = match.group(3)
            quando = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
            # Se o horário já passou hoje, agenda para amanhã
            if quando <= agora:
                quando += timedelta(days=1)

    if not quando or not mensagem:
        await update.message.reply_text(
            "Não entendi o horário. Tenta assim:\n"
            "/lembrar 14h30 Tomar remédio\n"
            "/lembrar 20min Pausar o trabalho\n"
            "/lembrar amanhã 08h Reunião"
        )
        return

    context.job_queue.run_once(
        disparar_lembrete,
        when=quando,
        chat_id=update.effective_chat.id,
        data={"mensagem": mensagem},
        name=f"lembrete_{update.effective_user.id}_{quando.isoformat()}"
    )

    # Formata confirmação
    if (quando - agora).total_seconds() < 3600:
        quando_fmt = f"em {int((quando - agora).total_seconds() / 60)} minutos"
    elif quando.date() == agora.date():
        quando_fmt = f"hoje às {quando.strftime('%H:%M')}"
    else:
        quando_fmt = f"amanhã às {quando.strftime('%H:%M')}"

    await update.message.reply_text(f"Lembrete definido: *{mensagem}*\n{quando_fmt}.", parse_mode="Markdown")


async def disparar_lembrete(context: ContextTypes.DEFAULT_TYPE):
    mensagem = context.job.data["mensagem"]
    hora = datetime.now(TZ).hour
    saudacao = saudacao_por_horario(hora)

    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=f"{saudacao}Lembrete: *{mensagem}*",
        parse_mode="Markdown"
    )
def saudacao_por_horario(hora: int) -> str:
    if 5 <= hora < 12:
        return "Bom dia! "
    elif 12 <= hora < 18:
        return "Boa tarde! "
    elif 18 <= hora < 23:
        return "Boa noite! "
    else:
        return ""
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERRO: {e}")
        input("Pressione Enter para fechar...")