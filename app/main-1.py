"""
Webhook do WhatsApp Cloud API. Roda com:
    uvicorn app.main:app --reload
Exponha com um túnel (ngrok) durante testes, ou num servidor real em produção.
"""
import os
import httpx
from fastapi import FastAPI, Request, Response

from app import db, rule_engine

app = FastAPI()
db.init_db()

VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "troque-isto")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")


@app.get("/webhook")
def verificar(request: Request):
    """A Meta chama isso uma vez, para confirmar que o webhook é seu."""
    params = request.query_params
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    return Response(status_code=403)


@app.post("/webhook")
async def receber_mensagem(request: Request):
    payload = await request.json()
    try:
        valor = payload["entry"][0]["changes"][0]["value"]
        msg = valor["messages"][0]
        telefone = msg["from"]
        texto = msg["text"]["body"]
    except (KeyError, IndexError):
        return {"status": "ignorado"}  # status update, não é mensagem de texto

    db.buscar_cliente(telefone)  # garante que o cliente existe no banco
    resposta = rule_engine.responder(telefone, texto)

    await enviar_whatsapp(telefone, resposta)
    return {"status": "ok"}


async def enviar_whatsapp(telefone: str, texto: str):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    body = {
        "messaging_product": "whatsapp",
        "to": telefone,
        "type": "text",
        "text": {"body": texto},
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
