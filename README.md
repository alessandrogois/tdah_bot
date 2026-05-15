# Bot Telegram — Assistente Pessoal para TDAH

Assistente pessoal no Telegram com lembretes de água, Pomodoro, captura rápida de notas e IA conversacional com contexto.

## Funcionalidades

| Comando | O que faz |
|---|---|
| `/foco [tarefa]` | Define a tarefa principal do dia |
| `/pomo [tarefa]` | Inicia Pomodoro de 25min |
| `/n [texto]` | Captura uma nota rápida |
| `/notas` | Lista notas do dia |
| `/dump [texto]` | Joga pensamentos e a IA organiza |
| `/onde` | Lembra o que você estava fazendo |
| `/agua` | Registra que bebeu água |
| `/status` | Resumo do dia |

**Automático:**
- 08h00 — Resumo matinal com clima e foco
- A cada ~90min — Lembrete de água com botões inline
- 13h e 19h30 — Lembretes de refeição
- 21h30 — Check-in noturno

---

## Instalação local

### 1. Pré-requisitos
- Python 3.11+
- Conta no Telegram
- Chave da API Anthropic (console.anthropic.com)

### 2. Criar o bot no Telegram
1. Abra o Telegram e procure @BotFather
2. Mande `/newbot`
3. Escolha nome e username (ex: `meu_assistente_bot`)
4. Copie o **token** que ele enviar

### 3. Descobrir seu chat_id
1. Abra o Telegram e procure @userinfobot
2. Mande `/start` — ele retorna seu `id`
3. Copie esse número

### 4. Instalar dependências

```bash
git clone <seu-repositorio>
cd tdah_bot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Configurar variáveis

```bash
cp .env.example .env
```

Edite o `.env` com seus valores:

```
TELEGRAM_TOKEN=seu_token_aqui
ANTHROPIC_API_KEY=sk-ant-...
CHAT_ID=123456789
TIMEZONE=America/Sao_Paulo
```

### 6. Rodar

```bash
python bot.py
```

Mande `/start` no Telegram para testar.

---

## Deploy no Railway (gratuito)

1. Crie conta em [railway.app](https://railway.app)
2. Conecte seu repositório GitHub
3. Em **Variables**, adicione as 4 variáveis do `.env`
4. O deploy é automático a cada push

O bot ficará online 24/7 sem custo para uso pessoal.

---

## Estrutura do projeto

```
tdah_bot/
├── bot.py          # Handlers principais e entry point
├── database.py     # SQLite — notas, foco, água
├── ai.py           # Integração com Claude (Anthropic)
├── jobs.py         # Jobs agendados (água, resumo, check-in)
├── config.py       # Variáveis de ambiente
├── requirements.txt
└── .env.example
```

---

## Personalização rápida

**Mudar horário dos lembretes de água** — em `jobs.py`, ajuste o range do loop ou os horários fixos.

**Mudar tom da IA** — em `ai.py`, edite o `SYSTEM_PROMPT`.

**Adicionar lembrete de medicação** — em `jobs.py`, adicione um `run_daily` com o horário certo e botão de confirmação igual ao da água.
