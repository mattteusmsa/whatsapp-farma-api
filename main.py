import os, re
import httpx
from fastapi import FastAPI, Request, HTTPException
from supabase import create_client, Client
from groq import GroqClient
from dotenv import load_dotenv

load_dotenv()  # carrega variáveis de .env

# — Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# — Groq
groq = GroqClient(api_key=os.getenv("GROQ_API_KEY"))

# — Waha
WAHA_BASE_URL = os.getenv("WAHA_BASE_URL")
WAHA_API_KEY   = os.getenv("WAHA_API_KEY")
WAHA_PHONE_ID  = os.getenv("WAHA_PHONE_ID")

app = FastAPI()

async def classify_intent(text: str) -> str:
    prompt = f"""Você é um assistente de farmácia. Classifique este texto em:
- consulta_preco
- info_endereco
- info_horario
- info_entrega
- outro

Texto: "{text}"
Intent:"""
    resp = groq.chat.completions.create(
        model="mixtral-8x7b-32768",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=10
    )
    return resp.choices[0].message.content.strip().lower()

async def send_waha_message(to: str, body: str):
    url = f"{WAHA_BASE_URL}/v1/messages"
    headers = {
        "Authorization": f"Bearer {WAHA_API_KEY}",
        "Content-Type":    "application/json"
    }
    payload = {
        "phone_id": WAHA_PHONE_ID,
        "to":       to,
        "type":     "text",
        "text":     {"body": body}
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    try:
        sender = data["from"]
        text   = data["message"]["text"].strip()
    except KeyError:
        raise HTTPException(400, "Formato inválido")

    intent = await classify_intent(text)

    # lógica de resposta
    if intent == "consulta_preco":
        nome = text.lower()
        res  = supabase.table("produtos").select("valor").eq("nome", nome).maybe_single().execute()
        if res.data:
            resp = f"💊 Preço de *{nome}*: R$ {res.data['valor']:.2f}"
        else:
            resp = f"❌ Não encontrei o produto *{nome}*."
    elif intent in ("info_endereco","info_horario","info_entrega"):
        info = supabase.table("info_farma").select("*").single().execute().data
        if intent=="info_endereco": resp = f"🏥 Endereço: {info['endereco']}"
        if intent=="info_horario":  resp = f"🕒 Horário: {info['horario']}"
        if intent=="info_entrega":  resp = f"🚚 Entrega? {'Sim' if info['entrega'] else 'Não'}"
    else:
        resp = (
            "🤖 Olá! Posso ajudar com:\n"
            "- preço de produto (ex: 'dipirona')\n"
            "- nosso endereço\n"
            "- horário de funcionamento\n"
            "- entrega"
        )

    await send_waha_message(sender, resp)
    return {"status":"ok"}

if __name__=="__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT",8000)))
