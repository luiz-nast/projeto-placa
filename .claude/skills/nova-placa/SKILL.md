---
name: nova-placa
description: Começar uma placa nova (ou refazer uma) na ordem certa com o Luiz - objetivo e perguntas de gente, blocos (tipo de peça sem número), carrinho com peças de verdade da loja, e só então o desenho. Use quando o Luiz pedir uma placa nova, uma ideia de circuito, ou quiser mudar o que a placa faz.
---

# Placa nova, na ordem

O Luiz não sabe eletrônica. Ele precisa ver **de onde vem cada decisão**. Nada de peça posicionada "de cabeça": primeiro o que ele quer, depois o tipo de cada peça, depois a peça de verdade da loja, por último o desenho.

## 1. Objetivo (com ele, em linguagem de gente)

- Uma frase do que a placa faz ("aperta o botão e o LED acende").
- As perguntas que decidem o projeto. Hoje o Sianvolt conhece `brilho` (fraca, média, forte = ¼, metade e o brilho que o fabricante anuncia). Pergunte; se ele não quiser escolher, sugira e marque `"quem": "sugestão do Claude"`. Ele troca no app (Processo, passo 1).
- Pergunta nova (duração, volume, ...) vira código: `PERGUNTAS` em `ferramenta/blocos.py`, com a conta que ela muda.

## 2. Blocos (tipo de peça, sem número)

A cadeia de funções: Energia (pilha) → Liga e desliga (botão) → Freio (resistor) → Luz (LED). Cada bloco tem uma frase de "por que ele está aí" em `BLOCOS` (`blocos.py`). Bloco novo (buzzer, sensor) entra lá, com a busca da loja e as peças que ele precisa conferir.

## 3. Carrinho (peças de verdade)

Pra cada bloco, uma peça que a loja tem em estoque e que a gente solda na mão (de furo): **primeiro do catálogo** (`ferramenta/catalogo/`, a lista de compras de sempre), conferida na loja antes de entrar no carrinho. Siga a skill `peca-da-loja`. O resistor **sai da conta** (`blocos.conta_do_freio`: brilho pedido → corrente pela curva do LED → resistor → valor E24 mais perto) e só é procurado com esse valor.

Tudo fica em `placas/<nome>/projeto.json`:

```json
{"objetivo": "Lanterninha de chaveiro", "frase": "Aperta o botão e o LED acende.",
 "perguntas": {"brilho": {"resposta": "fraca", "quem": "sugestão do Claude"}},
 "blocos": [{"ref": "BT1", "bloco": "pilha", "peca": "C5365915", "quem": "sugestão do Claude"}, ...]}
```

`blocos.escolher(pasta, ref, codigo, quem)` importa a peça, grava o projeto e troca o tipo no `placa.txt`. O app faz o mesmo quando o Luiz clica em Escolher.

## 4. Só então a placa

`placa.txt` com o código da LCSC como tipo (`peca R1 C119310 43 15`, sem valor: o valor é o da peça). Os números dos pinos são os do desenho oficial: confira os `nomes` em `placas/<nome>/pecas/<codigo>.json` antes de ligar (no LED da loja o pino 2 é o +). Depois siga a skill `placa` (testar, foto, resumo).

`requisitos.md` ganha `verifica: brilho D1` quando tem pergunta de brilho: o LED tem que dar o nível que o Luiz pediu.
