---
name: placa
description: Editar uma placa deste repositório (placa.txt, requisitos.md, biblioteca) e gerar os arquivos de fábrica (Gerber + Excellon). Use sempre que o Luiz pedir mudança numa placa, peça nova, ligação, ou pra mandar pra fábrica.
---

# Placa

O Claude decide só a **intenção** (quais peças, onde, o que liga em quê). Contas, pinos, checagens e Gerber são código em `ferramenta/`. Especificação inteira: `PROJETO.md`.

**Antes de desenhar vem o projeto**: objetivo, blocos e carrinho (`projeto.json`, skill `nova-placa`). Peça que não está no carrinho não entra na placa; peça nova vem da loja (skill `peca-da-loja`).

## Fluxo

1. Edite `placas/<nome>/placa.txt` (e `requisitos.md` se o objetivo mudou). Nada mais à mão.
2. Rode a bateria (ela também gera tudo e salva a versão):
   ```
   .venv/bin/python ferramenta/testar.py placas/<nome> -m "o que mudou, numa frase"
   ```
   Sem `-m`, a frase sai do diff do txt.
3. Falhou? Leia `testes.json` (ou a saída do comando), corrija o txt e rode de novo, **sozinho**, até passar ou até precisar de uma decisão do Luiz.
4. Passou da etapa 6? Olhe `saida/foto.png` antes de dizer que está bom.
5. No fim da rodada, e só no fim, escreva o resumo (2 ou 3 frases, termine com a pergunta do próximo passo):
   ```
   .venv/bin/python ferramenta/testar.py placas/<nome> --resumo "..."
   ```
6. Atualize o `AGORA.md` no fim da sessão.

**Nunca diga que terminou sem ter rodado o `testar.py`.** Mexeu no código da ferramenta (`ferramenta/`, `bancada/`)? Rode também `.venv/bin/python testes/rodar.py`: simulador (com circuitos sorteados e a mesma conta no JS do app), gerador, as 7 etapas com cada defeito, catálogo inteiro, segurança do app e fuzz. O Sianvolt (`python3 ferramenta/app.py`, ou o atalho "Sianvolt" no menu) se atualiza sozinho; não descreva o progresso no chat, o resumo final basta.

## Simulador

`ferramenta/circuito.py` (etapa 4 e as checagens `acende`/`nao_queima`/`brilho`) e a função `simular` em `bancada/index.html` (o ▶ e o painel) são **a mesma conta em duas línguas**: análise nodal; LED aceso = joelho (`vf − r_s·i_teste`) mais `r_s` em série, os três do datasheet, entre os pinos `mais` e `menos` da peça; pilha com a `r_interna` do datasheet em série (sem ela, uma resistência mínima só pra conta); chave apertada vira fio; pino sem net é aberto. A curva de brilho (`blocos.brilho_da_corrente` e `brilhoDaCorrente`) também existe nas duas. Mudou um, muda o outro, e confira que os dois dão o mesmo número pra lanterninha (4,3 mA com 3,0 V e 240 Ω).

## Falar com o Luiz sobre eletrônica

Ele não sabe eletrônica e quer aprender pelo app, não por despejo de números. No app e nas respostas: nome de gente (`D1 +`, `o lado A do botão`), uma frase por ideia, e a conta só quando ela explica alguma coisa (`(pilha − LED) ÷ resistor`). A faixa importa mais que o valor exato: diga o que acontece com a pilha fraca e com a nova.

## Fábrica

Só quando o Luiz pedir: suba o `saida/fabrica.zip` (ele só existe se a última rodada passou inteira) na página de cotação da JLCPCB (`https://cart.jlcpcb.com/quote`, "Add gerber file") e pare na cotação. **Nunca** salve no carrinho, faça pedido ou pague sem ele confirmar o item e o total. Depois, registre o que aconteceu em `placas/<nome>/fabrica.json` (a aba Processo mostra):

```json
{"site": "JLCPCB", "url": "https://cart.jlcpcb.com/quote", "quando": "AAAA-MM-DD HH:MM", "versao": 1,
 "situacao": "cotação, sem pedido", "detectou": "placa de 2 camadas, 34 × 52 mm",
 "preco": "US$ 4,00 por 5 placas, fabricação em 2 dias (sem o frete)", "imagem": "fabrica-jlcpcb.jpg"}
```

## placa.txt

Uma instrução por linha, mm, origem no canto inferior esquerdo. `#` começa comentário.

```
placa 70 45                 # contorno L x A
furos cantos 3.2            # 4 furos de fixação a 3,5 mm das bordas (3,2 = M3)
peca R1 C119310 43 15       # REF TIPO X Y; TIPO = código da LCSC (peça do carrinho) ou um tipo de biblioteca.py
peca R2 resistor_axial 38.62 5 100   # tipo da biblioteca: VALOR em ohms (100, 4.7k); peça da loja já traz o valor
liga DevKit.11 R1.1         # REF.PINO ou nome de net (GND)
liga D1.1 GND               # vai até o pino de GND mais perto
```

- Os pinos de uma peça da loja são os do desenho oficial: veja os `nomes` em `placas/<nome>/pecas/<codigo>.json` antes de ligar (no LED `C779439` o + é o pino **2**).

- Trilha de 0,3 mm. O roteador (`gerar.rotear`) tenta a reta; se algo de outra net está no caminho, desvia em L ou Z e, se precisar, passa pro outro lado da placa por uma via (furo 0,4, anel 0,8, coberta pela máscara), sempre a 0,25 mm do cobre das outras nets e a 0,5 mm da borda e dos furos de fixação. Pad de superfície só tem cobre em cima. Nada coube: fica a reta e a etapa 3 acusa o curto; aí mude as peças de lugar.
- A etapa 3 também para quando uma peça sai da placa, um pino encosta no furo de fixação ou os corpos de duas peças se sobrepõem.
- Uma ligação entre nets com nome diferente (GND com 3V3) é erro.

## requisitos.md

```
# Objetivo: título
Uma frase.

## R1 Título do requisito
pecas: D1 R1
verifica: ligado R1.2 D1.2      # existe | ligado A B | separado A B | sem_pino_solto | acende REF | nao_queima REF | brilho REF
- sub-requisito em texto
```

`brilho D1`: o LED, na pilha nominal, dá o nível que o Luiz pediu em `projeto.json` (fraca, média ou forte, o mais perto pela curva do datasheet). O status é calculado pelo `testar.py`. Nunca escreva status à mão. Checagem nova vira código em `testar.py` (`CHECAGENS`, `checar`).

## Biblioteca

Peça nova sai do catálogo (`ferramenta/catalogo/`) ou da loja (skill `peca-da-loja`): o desenho é o oficial do EasyEDA e o que a loja não diz entra no `conferido` da peça, no catálogo. A `ferramenta/biblioteca.py` fica pras peças de antes (e de exemplo): `tipo -> pinos (dx, dy, pad[, net]), furo, corpo, juntos, nomes, eletrica, compra, fonte`. **Toda peça leva `nomes`** de gente pros pinos (`+`, `−`, `A`/`B`, `lado 1`): o Luiz não sabe o que é "pino 1", e o app mostra o nome. `eletrica` é o modelo do simulador; sem ele a etapa 4 pula. `juntos` = pinos ligados por dentro da peça (botão 1-2 e 3-4): ligar os dois lados do botão no mesmo pino deixa ele em curto. **Nenhum número inventado**: medidas vêm do datasheet da peça escolhida, com o link em `fonte`. `fonte: None` = exemplo: a bancada avisa e o `fabrica.zip` não é gerado. Não sabe a medida? Pergunte ou deixe pendente. Peça nova: tire pinos, pads e furo do footprint oficial do KiCad (`.kicad_mod` bruto do GitLab, y invertido, origem no centro do corpo) e confira com o datasheet.

## Regras de formato (já aprendidas)

- Gerber: `%FSLAX46Y46*%` e `%MOMM*%`, coordenadas em milionésimos de mm (arredondar, não truncar), `G01*` antes de desenhar, `D02` move, `D01` desenha, `D03` carimba pad, `M02*` no fim. Aberturas a partir de `D10`.
- Excellon: `M48`, `METRIC,TZ`, ferramentas `T1C3.200`, **`G90` antes do `%`** (fora do cabeçalho o leitor reclama), `M30` no fim. Furo com cobre (PTH) e sem cobre (NPTH) em arquivos separados.
- Máscara: arquivo com `%TF.FilePolarity,Negative*%` (desenhar = abrir); abertura 1:1 com o pad.
- Serigrafia: texto com a fonte de traços de `letras.py`, recortado pra ficar a 0,15 mm dos pads.
- Nomes no padrão do KiCad (`placa-F_Cu.gbr`, `placa-Edge_Cuts.gbr`, `placa-PTH.drl`, `placa-NPTH.drl`): o gerbonara e a fábrica reconhecem sozinhos.
- Regras da fábrica ficam em `testar.py`, com o link da página da JLCPCB. Mudou a página? Atualize o número e a data.

## Eletrônica (regras simples, pra explicar pro Luiz)

- LED sempre com resistor em série; sem ele, o LED queima. O `+` (ânodo, perna comprida) muda de número conforme a peça: olhe os `nomes`.
- Quem manda no brilho é a **corrente**, não a voltagem: a pilha empurra, o LED pede uns 1,9 V, o resistor freia o resto. Resistor menor, mais luz e pilha dura menos.
- Corrente do LED = (pilha − LED) ÷ (resistor + o que a pilha e o LED freiam sozinhos). Lanterninha com brilho fraco: (3,0 − 1,9) ÷ (240 + 13,5) ≈ 4,3 mA, ≈ 27% do brilho do anúncio.
- Pilha CR2032: 3,0 V nominal, fraca em 2,0 V; o fabricante só testou até ~6,8 mA (pulsos de 2 s). Acima disso funciona, mas rende menos. Teste sempre a faixa toda, não só o valor nominal.
- Botão de 4 pinos: 1-2 são o mesmo lado, 3-4 o outro. Ligar a pilha e o resistor no mesmo lado deixa o LED sempre aceso (a checagem `separado` pega).
- GND é o terra, o 0 V de referência. Todo GND da placa é a mesma net.
- Furo de fixação não tem cobre; cobre perto dele conta como borda (0,2 mm).
