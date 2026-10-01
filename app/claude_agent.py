"""
Aqui é onde a IA de verdade entra. O Claude decide o que dizer e quando
chamar uma ferramenta; a ferramenta em si (tools.py) é código comum,
sem inventar nada.
"""
import json
import os
from anthropic import Anthropic
from app import tools

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """Você é a assistente virtual do Salão Lúmen. Fale em português \
do Brasil, de forma simpática e curta (1-3 frases), com no máximo um emoji.

Regras:
1. Descubra: serviço, profissional (opcional) e dia.
2. Sempre chame consultar_disponibilidade antes de oferecer horário. Nunca invente.
3. Ofereça no máximo 3 opções de horário.
4. Antes de confirmar, repita serviço, profissional, dia, hora e valor.
5. Só chame criar_agendamento depois que o cliente confirmar.
6. Cancelamento com erro "cancelamento_tardio": explique a política e chame chamar_humano.
7. Preços fora de tabela, promoções, reclamações: chame chamar_humano.
8. Nunca invente serviços, profissionais ou preços fora do que as ferramentas retornam."""

TOOL_DEFS = [
    {
        "name": "consultar_disponibilidade",
        "description": "Busca horários livres de verdade na agenda.",
        "input_schema": {
            "type": "object",
            "properties": {
                "servico": {"type": "string", "enum": list(tools.db.SERVICOS)},
                "profissional": {"type": "string", "description": "Nome ou 'qualquer'"},
                "dia": {"type": "string", "description": "'hoje', 'amanha' ou YYYY-MM-DD"},
            },
            "required": ["servico", "profissional", "dia"],
        },
    },
    {
        "name": "criar_agendamento",
        "description": "Grava o agendamento depois que o cliente confirmou.",
        "input_schema": {
            "type": "object",
            "properties": {
                "servico": {"type": "string"},
                "profissional": {"type": "string"},
                "dia": {"type": "string"},
                "hora": {"type": "string", "description": "HH:MM"},
            },
            "required": ["servico", "profissional", "dia", "hora"],
        },
    },
    {
        "name": "listar_meus_agendamentos",
        "description": "Lista os agendamentos futuros deste cliente.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cancelar_agendamento",
        "description": "Cancela um agendamento pelo id.",
        "input_schema": {
            "type": "object",
            "properties": {"agendamento_id": {"type": "integer"}},
            "required": ["agendamento_id"],
        },
    },
    {
        "name": "chamar_humano",
        "description": "Transfere a conversa para a recepção (preço, reclamação, caso fora do escrito).",
        "input_schema": {
            "type": "object",
            "properties": {"motivo": {"type": "string"}},
            "required": ["motivo"],
        },
    },
]


def _executar_tool(nome: str, args: dict, telefone: str) -> dict:
    if nome == "consultar_disponibilidade":
        return tools.consultar_disponibilidade(**args)
    if nome == "criar_agendamento":
        return tools.criar_agendamento(telefone=telefone, **args)
    if nome == "listar_meus_agendamentos":
        return tools.listar_meus_agendamentos(telefone=telefone)
    if nome == "cancelar_agendamento":
        return tools.cancelar_agendamento(telefone=telefone, **args)
    if nome == "chamar_humano":
        # Aqui você dispararia uma notificação real pro time (Slack, WhatsApp da recepção etc.)
        return {"status": "encaminhado", "motivo": args.get("motivo")}
    return {"erro": f"ferramenta desconhecida: {nome}"}


def responder(telefone: str, historico: list[dict], mensagem: str) -> tuple[str, list[dict]]:
    """
    historico: lista de mensagens no formato da API (persistida por telefone, ex. em Redis/DB).
    Retorna (texto_para_o_cliente, historico_atualizado).
    """
    historico = historico + [{"role": "user", "content": mensagem}]

    while True:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFS,
            messages=historico,
        )
        historico.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            texto = "".join(b.text for b in resp.content if b.type == "text")
            return texto, historico

        tool_results = []
        for bloco in resp.content:
            if bloco.type == "tool_use":
                resultado = _executar_tool(bloco.name, bloco.input, telefone)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": bloco.id,
                    "content": json.dumps(resultado, ensure_ascii=False),
                })
        historico.append({"role": "user", "content": tool_results})
        # volta ao topo do loop: o Claude vê o resultado e decide o próximo passo
