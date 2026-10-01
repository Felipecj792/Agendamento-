# Agente de agenda — Salão Lúmen (versão 100% grátis)

Sistema real, sem custo: motor de regras em Python (sem API paga de IA) +
SQLite + WhatsApp Cloud API, hospedado em camada gratuita.

## O que já funciona
- `app/db.py` — banco de dados (clientes, agendamentos).
- `app/tools.py` — regras reais de disponibilidade, criação e cancelamento (nunca inventa horário).
- `app/rule_engine.py` — entende português por palavras-chave e decide as respostas. **Não chama nenhuma API paga.**
- `app/main.py` — webhook do WhatsApp: recebe mensagem, chama o motor de regras, responde.
- `app/claude_agent.py` — versão com Claude de verdade, para quando quiser trocar (ver "Como evoluir" no final).

## Por que isso é grátis
- **IA:** nenhuma chamada de API paga — a "inteligência" é código Python comum.
- **WhatsApp:** respostas dentro da janela de 24h aberta pelo cliente são gratuitas até 1.000 mensagens de serviço por mês, por número (regra da Meta a partir de 01/10/2026). Para um salão pequeno, dificilmente passa disso.
- **Banco de dados:** SQLite é um arquivo local, sem custo algum.
- **Hospedagem:** camada gratuita do Render (ou similar) não cobra nada, com a ressalva abaixo.

## Limitação importante da camada gratuita de hospedagem
Servidores grátis "dormem" depois de um tempo sem uso e demoram alguns segundos para acordar.
Isso pode fazer o WhatsApp dar timeout esperando resposta na primeira mensagem do dia.
Não trava o sistema, mas a primeira resposta pode demorar. Se isso incomodar, o passo mais barato
é migrar para um plano pago de hospedagem (a partir de uns R$ 20/mês) — nada mais muda no código.

## Rodando localmente

```bash
pip install -r requirements.txt
export WHATSAPP_VERIFY_TOKEN="escolha-uma-senha"
export WHATSAPP_TOKEN="token-da-Meta"
export WHATSAPP_PHONE_NUMBER_ID="id-do-numero"
uvicorn app.main:app --reload
```

Para testar sem WhatsApp ainda, chame `rule_engine.responder(telefone, mensagem)` direto num script Python —
foi assim que testei a conversa completa (agendar, confirmar, cancelar) antes de te entregar.

## Ligando ao WhatsApp de verdade (grátis)
1. Crie um app no [Meta for Developers](https://developers.facebook.com) e ative o **WhatsApp Business Platform**.
2. Pegue `WHATSAPP_TOKEN` e `WHATSAPP_PHONE_NUMBER_ID` no painel do app.
3. Suba o código de graça no [Render](https://render.com) (Web Service, plano Free) ou similar.
4. No painel da Meta, configure o webhook apontando para `https://seu-app.onrender.com/webhook`, com o mesmo `WHATSAPP_VERIFY_TOKEN`.

## Antes de vender como "sem bugs"
- [ ] Trocar o estado da conversa em memória (`ESTADOS` em `rule_engine.py`) por uma tabela no banco — hoje reseta se o servidor reiniciar ou "dormir".
- [ ] Testar concorrência: dois clientes tentando o mesmo horário ao mesmo tempo (o `criar_agendamento` já rechecha antes de gravar, mas teste mesmo assim).
- [ ] Ampliar as palavras-chave do `rule_engine.py` com frases reais de clientes do salão — ele só entende o que você ensinar.
- [ ] Adicionar fila de lembretes (24h/2h antes) — um job agendado (cron, APScheduler) que varre `agendamentos` e dispara mensagens. Atenção: fora da janela de 24h, essas mensagens têm custo (são "template", não "serviço").
- [ ] Log de erros para saber na hora se algo quebrar.
- [ ] Revisar as respostas com casos reais do salão (nomes, políticas, horário de funcionamento).

## Como evoluir para IA de verdade, quando fizer sentido pagar
Troque, em `main.py`:
```python
from app import db, rule_engine          # grátis
# por:
from app import db, claude_agent         # Claude de verdade, pago por uso
```
E ajuste a chamada em `receber_mensagem` para usar `claude_agent.responder(...)`.
O resto do sistema (banco, regras de agenda, webhook) não muda nada.

## Estrutura
```
agente-salao/
├── app/
│   ├── main.py          # webhook WhatsApp
│   ├── rule_engine.py   # motor de conversa grátis (sem IA paga)
│   ├── claude_agent.py  # alternativa paga, com Claude de verdade
│   ├── tools.py         # lógica real de agenda
│   └── db.py            # SQLite
├── requirements.txt
└── README.md
```
