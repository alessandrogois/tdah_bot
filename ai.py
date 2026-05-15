from groq import AsyncGroq
from config import GROQ_API_KEY

client = AsyncGroq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """Você é um assistente pessoal gentil e direto, feito para uma pessoa com TDAH.
Respostas curtas. Sem julgamentos. Máx 4 linhas. Responda sempre em português."""

async def ask_ai(prompt, system=None, historico=None):
    messages = historico if historico else [{"role": "user", "content": prompt}]
    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system or SYSTEM_PROMPT}] + messages,
            max_tokens=600
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Não consegui processar agora. Tente de novo. ({e})"


async def summarize_notes(notes: list[str]) -> str:
    if not notes:
        return "Nenhuma nota para resumir."
    texto = "\n".join(f"- {n}" for n in notes)
    return await ask_ai(
        f"Resuma essas notas do dia de forma útil e organizada, em até 5 linhas:\n{texto}"
    )