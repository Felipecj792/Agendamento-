"""
Motor de conversa SEM IA paga. Entende palavras-chave em português e
usa as mesmas funções reais de agenda de tools.py — a agenda nunca é
inventada, só a "inteligência" da conversa é mais simples que o Claude.

Troque isto por app/claude_agent.py quando quiser IA de verdade;
o resto do sistema (db.py, tools.py, main.py) não muda.
"""
import re
from app import db, tools

# Estado da conversa por telefone. Em produção, troque por uma tabela
# no banco — hoje reseta se o servidor reiniciar (ver README).
ESTADOS: dict[str, dict] = {}

SERVICO_PALAVRAS = {
    "corte": ["corte feminino", "corte", "cortar"],
    "escova": ["escova"],
    "coloracao": ["coloração", "coloracao", "tintura", "mecha", "mechas"],
    "masculino": ["masculino", "barba"],
}
DIA_PALAVRAS = {"hoje": "hoje", "amanha": "amanha", "amanhã": "amanha"}


def _novo_estado():
    return {"passo": "inicio", "servico": None, "profissional": None, "dia": None, "candidatos": []}


def _achar_servico(texto: str):
    for chave, palavras in SERVICO_PALAVRAS.items():
        if any(p in texto for p in palavras):
            return chave
    return None


def _achar_profissional(texto: str):
    for p in db.PROFISSIONAIS:
        if p.lower() in texto:
            return p
    if "tanto faz" in texto or "qualquer" in texto:
        return "qualquer"
    return None


def _achar_dia(texto: str):
    for chave, valor in DIA_PALAVRAS.items():
        if chave in texto:
            return valor
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", texto)
    return m.group(1) if m else None


def _achar_hora(texto: str):
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", texto)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def _formatar_opcoes(candidatos):
    return ", ".join(f"{c['inicio']} ({c['profissional']})" for c in candidatos[:3])


def _dia_legivel(dia: str) -> str:
    return {"hoje": "hoje", "amanha": "amanhã"}.get(dia, dia)


def responder(telefone: str, texto: str) -> str:
    texto = texto.strip().lower()
    estado = ESTADOS.setdefault(telefone, _novo_estado())
    cliente = db.buscar_cliente(telefone)

    # Palavras que valem em qualquer ponto da conversa
    if re.search(r"pre[cç]o|quanto custa|promo|desconto|reclama|gerente|humano|pessoa", texto):
        return "Vou chamar alguém da recepção para te ajudar. Só um instante 😊"
    if "reiniciar" in texto or "recomeçar" in texto:
        ESTADOS[telefone] = _novo_estado()
        return "Conversa reiniciada. Como posso ajudar?"

    passo = estado["passo"]

    if passo == "inicio":
        if "cancel" in texto:
            return _iniciar_cancelamento(telefone, estado)
        if "remarc" in texto:
            return _iniciar_remarcacao(telefone, estado)
        servico = _achar_servico(texto)
        if servico or "agend" in texto or "marc" in texto or "hor" in texto:
            if servico:
                estado["servico"] = servico
                estado["passo"] = "profissional"
                return _perguntar_profissional(servico)
            estado["passo"] = "servico"
            return "Claro! Qual serviço: corte feminino, escova, coloração ou corte masculino?"
        return "Posso agendar, remarcar ou cancelar um horário. O que você precisa?"

    if passo == "servico":
        servico = _achar_servico(texto)
        if not servico:
            return "Não entendi. Diga: corte feminino, escova, coloração ou corte masculino."
        estado["servico"] = servico
        estado["passo"] = "profissional"
        return _perguntar_profissional(servico)

    if passo == "profissional":
        prof = _achar_profissional(texto)
        if not prof:
            return f"Profissionais disponíveis: {', '.join(db.PROFISSIONAIS)}, ou diga 'tanto faz'."
        estado["profissional"] = prof
        estado["passo"] = "dia"
        return "Para quando você quer? (hoje, amanhã ou uma data)"

    if passo == "dia":
        dia = _achar_dia(texto)
        if not dia:
            return "Não entendi o dia. Diga 'hoje', 'amanhã' ou uma data (AAAA-MM-DD)."
        estado["dia"] = dia
        return _mostrar_horarios(estado)

    if passo == "horario":
        hora = _achar_hora(texto)
        candidato = next((c for c in estado["candidatos"] if c["inicio"] == hora), None)
        if not candidato:
            return f"Escolha um destes horários: {_formatar_opcoes(estado['candidatos'])}"
        estado["hora"] = hora
        estado["profissional_escolhido"] = candidato["profissional"]
        estado["passo"] = "confirmar"
        info = db.SERVICOS[estado["servico"]]
        return (
            f"Confira: {info['nome']} com {candidato['profissional']}, "
            f"{_dia_legivel(estado['dia'])} às {hora} (R$ {info['preco']:.2f}). Confirma? (sim/não)"
        )

    if passo == "confirmar":
        if "sim" in texto or "confirma" in texto:
            r = tools.criar_agendamento(
                telefone, estado["servico"], estado["profissional_escolhido"], estado["dia"], estado["hora"]
            )
            ESTADOS[telefone] = _novo_estado()
            if "erro" in r:
                return f"Esse horário acabou de ser ocupado. Vamos ver outro? Diga o dia de novo."
            return f"Agendado! ✅ {r['servico']} dia {_dia_legivel(estado.get('dia'))} às {r['inicio'][-5:]}."
        estado["passo"] = "dia"
        return "Sem problema. Para quando você quer tentar?"

    if passo == "cancelar_confirmar":
        return _confirmar_cancelamento(telefone, estado, texto)

    ESTADOS[telefone] = _novo_estado()
    return "Vamos recomeçar: você quer agendar, remarcar ou cancelar?"


def _perguntar_profissional(servico):
    info = db.SERVICOS[servico]
    return f"{info['nome']} ({info['minutos']} min, R$ {info['preco']:.2f}). Tem preferência de profissional?"


def _mostrar_horarios(estado):
    prof = estado["profissional"] or "qualquer"
    r = tools.consultar_disponibilidade(estado["servico"], prof, estado["dia"])
    if "erro" in r or not r["horarios_disponiveis"]:
        estado["passo"] = "dia"
        return "Não tenho horários nesse dia. Quer tentar outro?"
    estado["candidatos"] = r["horarios_disponiveis"]
    estado["passo"] = "horario"
    return f"Tenho estes horários: {_formatar_opcoes(r['horarios_disponiveis'])}. Qual prefere?"


def _iniciar_cancelamento(telefone, estado):
    ags = tools.listar_meus_agendamentos(telefone)["agendamentos"]
    if not ags:
        return "Não encontrei agendamentos futuros no seu nome."
    alvo = ags[0]
    estado["cancelar_id"] = alvo["id"]
    estado["passo"] = "cancelar_confirmar"
    return f"Vou cancelar {alvo['servico_nome']} em {alvo['inicio'][:16].replace('T',' ')}. Confirma? (sim/não)"


def _confirmar_cancelamento(telefone, estado, texto):
    ESTADOS[telefone] = _novo_estado()
    if "sim" in texto:
        r = tools.cancelar_agendamento(telefone, estado["cancelar_id"])
        if r.get("erro") == "cancelamento_tardio":
            return "Esse horário é em menos de 3h. Vou chamar a recepção para resolver com você."
        return "Cancelado. Quando quiser, é só marcar outro horário 💜"
    return "Tudo bem, mantive seu horário."


def _iniciar_remarcacao(telefone, estado):
    ags = tools.listar_meus_agendamentos(telefone)["agendamentos"]
    if not ags:
        return "Não encontrei agendamentos para remarcar. Quer marcar um novo?"
    alvo = ags[0]
    tools.cancelar_agendamento(telefone, alvo["id"])
    estado["servico"] = alvo["servico"]
    estado["profissional"] = alvo["profissional"]
    estado["passo"] = "dia"
    return f"Certo, vamos remarcar {alvo['servico_nome']}. Para quando você quer?"
