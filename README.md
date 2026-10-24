# Sianvolt

Ferramenta pessoal que transforma a descrição de uma placa em texto nos arquivos que a fábrica aceita (Gerber + Excellon), sem KiCad. Vem com um app local para investigar a placa, ligar o circuito no papel e acompanhar o caminho até a fábrica.

A ordem é a de quem projeta de verdade: primeiro o que a placa tem que fazer ("quanta luz você quer?"), depois o tipo de cada peça (pilha → botão → resistor → LED), depois as peças de verdade, escolhidas no estoque da JLCPCB/LCSC com o desenho oficial delas, e só então a placa:

```
placa 52 34
furos cantos 3.2
peca BT1 C5365915 20 17     # suporte de CR2032 (código da LCSC)
peca SW1 C393938 43 25      # botão 6×6
peca R1 C119310 43 15       # 240 Ω: sai da conta do brilho fraco
peca D1 C779439 43 7        # LED vermelho 5 mm
liga BT1.1 SW1.1
liga SW1.3 R1.1
liga R1.2 D1.2
liga D1.1 GND
```

## Usar

```bash
uv venv .venv && uv pip install -r requirements.txt
.venv/bin/python ferramenta/testar.py placas/estudo
python3 ferramenta/instalar.py   # põe o "Sianvolt" no menu de aplicativos
```

O app (`ferramenta/app.py`) abre numa janela própria, sem abas, com a lista de projetos. Cada projeto conta a história em 7 passos (objetivo, blocos, carrinho, placa, testes, fábrica, montar); dá pra responder as perguntas, trocar uma peça pelas opções da loja e rodar os testes de lá. Sem instalar: `python3 ferramenta/app.py`.

Peças: a lista de compras de sempre é o `ferramenta/catalogo.json` (~300 peças de furo, com preço, estoque, o dia em que viu e o que já foi conferido no datasheet), visível na tela **Catálogo de peças** do app. A loja online é o double check: `python3 ferramenta/catalogo.py checar` (preço e estoque agora), `python3 ferramenta/loja.py buscar "LED 5mm"` e `python3 ferramenta/loja.py importar C779439 led placas/lanterna`.

O `testar.py` gera `modelo.json`, os Gerbers, o Excellon e a versão, e depois roda 7 etapas: lê o txt, confere peças, confere ligações, liga o circuito no papel (pilha fraca, nominal e nova), regras da fábrica (JLCPCB), relê o Gerber com o `gerbonara` e tira uma foto da placa. O `fabrica.zip` só sai quando tudo passa.

O app tem quatro abas: **Processo** (a história do projeto: objetivo, blocos, carrinho, placa, testes, fábrica, montar), **Thinking** (objetivo e requisitos), **Projeto** (a placa, com inspetor e o ▶ que liga o circuito, com painel pra mexer na pilha e no resistor) e **Testes** (as etapas ao vivo).

A especificação inteira está em [PROJETO.md](PROJETO.md). As peças da loja trazem o desenho do EasyEDA; o que a loja não diz (o + do LED, os pinos do botão, as curvas) o Claude lê no datasheet e guarda na própria peça, no catálogo. As peças do ESP32 da placa de estudo ainda são de exemplo.
