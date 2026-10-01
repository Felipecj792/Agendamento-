"""
Implementação real de cada ferramenta que o Claude pode chamar.
Cada função aqui SUBSTITUI uma resposta "inventada" pela IA por um fato do banco.
"""
from datetime import datetime, timedelta
from app import db

SLOT_MINUTOS = 15  # granularidade dos horários candidatos


def _parse_dia(dia_str: str) -> str:
    """Aceita 'hoje', 'amanha', ou 'YYYY-MM-DD'. Retorna sempre 'YYYY-MM-DD'."""
    hoje = datetime.now().date()
    s = dia_str.strip().lower()
    if s in ("hoje",):
        d = hoje
    elif s in ("amanha", "amanhã"):
        d = hoje + timedelta(days=1)
    else:
        d = datetime.fromisoformat(dia_str).date()
    return d.isoformat()


def consultar_disponibilidade(servico: str, profissional: str, dia: str) -> dict:
    if servico not in db.SERVICOS:
        return {"erro": f"Serviço '{servico}' não existe. Opções: {list(db.SERVICOS)}"}
    duracao = db.SERVICOS[servico]["minutos"]
    dia_iso = _parse_dia(dia)

    profissionais = db.PROFISSIONAIS if profissional.lower() in ("qualquer", "tanto faz") else [profissional]
    if not all(p in db.PROFISSIONAIS for p in profissionais):
        return {"erro": f"Profissional inválido. Opções: {db.PROFISSIONAIS}"}

    abertura = datetime.fromisoformat(f"{dia_iso}T{db.ABERTURA}")
    fechamento = datetime.fromisoformat(f"{dia_iso}T{db.FECHAMENTO}")

    candidatos = []
    for prof in profissionais:
        ocupados = db.horarios_ocupados(prof, dia_iso)
        ocupados = [(datetime.fromisoformat(a), datetime.fromisoformat(b)) for a, b in ocupados]

        cursor = abertura
        while cursor + timedelta(minutes=duracao) <= fechamento:
            fim = cursor + timedelta(minutes=duracao)
            conflita = any(cursor < oc_fim and fim > oc_ini for oc_ini, oc_fim in ocupados)
            if not conflita and cursor > datetime.now():
                candidatos.append({"profissional": prof, "inicio": cursor.strftime("%H:%M")})
            cursor += timedelta(minutes=SLOT_MINUTOS)

    return {
        "dia": dia_iso,
        "servico": db.SERVICOS[servico]["nome"],
        "duracao_minutos": duracao,
        "preco": db.SERVICOS[servico]["preco"],
        "horarios_disponiveis": candidatos[:6],  # não sobrecarregar o cliente de opções
    }


def criar_agendamento(telefone: str, servico: str, profissional: str, dia: str, hora: str) -> dict:
    if servico not in db.SERVICOS:
        return {"erro": f"Serviço inválido: {servico}"}
    if profissional not in db.PROFISSIONAIS:
        return {"erro": f"Profissional inválido: {profissional}"}

    dia_iso = _parse_dia(dia)
    inicio = datetime.fromisoformat(f"{dia_iso}T{hora}")
    fim = inicio + timedelta(minutes=db.SERVICOS[servico]["minutos"])

    # trava real contra conflito, checada de novo no momento de gravar
    ocupados = db.horarios_ocupados(profissional, dia_iso)
    for oc_ini, oc_fim in ocupados:
        oc_ini, oc_fim = datetime.fromisoformat(oc_ini), datetime.fromisoformat(oc_fim)
        if inicio < oc_fim and fim > oc_ini:
            return {"erro": "Esse horário acabou de ser ocupado. Peça outra opção ao cliente."}

    agendamento_id = db.criar_agendamento(
        telefone, servico, profissional, inicio.isoformat(), fim.isoformat()
    )
    return {
        "id": agendamento_id,
        "servico": db.SERVICOS[servico]["nome"],
        "profissional": profissional,
        "inicio": inicio.strftime("%d/%m %H:%M"),
        "preco": db.SERVICOS[servico]["preco"],
        "status": "confirmado",
    }


def listar_meus_agendamentos(telefone: str) -> dict:
    ags = db.listar_agendamentos_futuros(telefone)
    for a in ags:
        a["servico_nome"] = db.SERVICOS.get(a["servico"], {}).get("nome", a["servico"])
    return {"agendamentos": ags}


def cancelar_agendamento(telefone: str, agendamento_id: int) -> dict:
    ags = db.listar_agendamentos_futuros(telefone)
    alvo = next((a for a in ags if a["id"] == agendamento_id), None)
    if not alvo:
        return {"erro": "Agendamento não encontrado para esse cliente."}

    inicio = datetime.fromisoformat(alvo["inicio"])
    horas_restantes = (inicio - datetime.now()).total_seconds() / 3600
    if horas_restantes < 3:
        return {
            "erro": "cancelamento_tardio",
            "mensagem": "Menos de 3h de antecedência. Chame um humano (chamar_humano).",
        }

    db.cancelar_agendamento(agendamento_id)
    return {"status": "cancelado", "id": agendamento_id}
