---
name: peca-da-loja
description: Escolher, procurar e conferir peças de verdade pro Sianvolt - primeiro no catálogo (ferramenta/catalogo/, um arquivo por categoria, a lista de compras de sempre), com a loja JLCPCB/LCSC como double check; importar a peça escolhida e conferir no datasheet o que a loja não diz. Use quando precisar de uma peça, trocar uma peça, ou quando o app avisar "falta o Claude conferir no datasheet".
---

# Peça da loja

## O catálogo primeiro

`ferramenta/catalogo/` é a lista de compras de sempre (vai pro repositório): ~4.500 peças em ~90 categorias (passivos, semicondutores, energia, cérebros como ESP32, comunicação, sensores, telas, conectores, movimento, módulos prontos), da LCSC e de lojas brasileiras (Eletrogate, Baú, Usinainfo, RoboCore). Cada arquivo diz como buscar, filtrar e dar nome às peças daquela categoria (formato no docstring de `catalogo.py`). Cada peça tem tudo que a loja diz, a montagem (furo, superfície, módulo, fio), `visto` (o dia em que viu), `situacao` (`ok`, `sem estoque`, `sumiu`) e, quando já foi lida, `conferido` (o que veio do datasheet). O app mostra o mundo de opções (tela Catálogo e o Trocar do carrinho) a partir dela.

```
python3 ferramenta/catalogo.py ver led              # o que tem na lista
python3 ferramenta/catalogo.py checar C779439       # preço e estoque agora, na loja (sem código: a lista toda)
python3 ferramenta/catalogo.py encher botao         # busca de novo as sementes da categoria e põe o que faltar
python3 ferramenta/catalogo.py categorias           # as categorias, por grupo
python3 ferramenta/catalogo.py recalcular botao     # refaz nome, montagem e tamanho com as regras de agora
```

Ao escolher uma peça, você é livre pra pensar: usar uma da lista, procurar uma melhor ou testar outra. Só siga estas regras:

1. **Olhe a lista antes da loja.** Prefira peça já `conferido` (está pronta pra placa).
2. **Antes de pôr no carrinho, confira na loja** (`checar`): preço e estoque mudam todo dia. Se ela estiver `sem estoque` ou tiver `sumiu`, ela fica na lista marcada (não apague) e você escolhe outra.
3. **Achou coisa melhor na loja?** Ela entra na lista: `python3 ferramenta/loja.py buscar "..."` e depois `importar`, ou o "Procurar mais na loja" do app.
4. **Viu que algo na lista está errado** (a loja mudou o atributo, o datasheet diz outra coisa)? Corrija na lista e diga ao Luiz o que mudou.
5. Depois de mexer no catálogo, faça commit dele ("Catálogo: ..."). Peça errada que o encher traz de volta: ponha o código em `filtro.fora` da categoria.
6. Loja brasileira (`ferramenta/lojas.py`): só página de produto, com a pausa que o robots.txt pede (10 s na Eletrogate e na Baú); Mercado Livre, AliExpress, Mouser e MakerHero não deixam ler.

A busca da loja é por palavra exata: `CR2032 Plugin` acha, `CR2032 battery holder through hole` não. LED de qualquer cor: `LED 5mm` (as cores vêm nos atributos). As buscas que enchem cada bloco ficam em `SEMENTES` (`catalogo.py`).

## Importar a escolhida

```
python3 ferramenta/loja.py importar C779439 led placas/lanterna
```

ou `blocos.escolher(pasta, ref, codigo, quem)`, que também grava o `projeto.json` e troca o tipo no `placa.txt`. O import pega o desenho oficial (pads, furos, serigrafia) do EasyEDA e a foto e o pdf da LCSC. Essas coisas ficam só na máquina (`placas/<nome>/pecas/` e `~/.cache/sianvolt/`), e a peça entra (ou se atualiza) na lista.

## O que a loja não diz: conferir no datasheet

Sem `conferido`, a peça fica `pendente`: não liga no papel nem vai pra fábrica. Baixe o PDF pelo `pdfUrl` da página da LCSC e leia as figuras (`pdftoppm`, depois Read na imagem). Escreva em `conferido`, dentro da peça, no arquivo da categoria em `ferramenta/catalogo/`, com a origem em `fonte`/`_eletrica`:

| bloco | conferir |
|---|---|
| pilha (suporte) | qual furo é o + (desenho "PCB layout"); a pilha que vai nele e o datasheet dela: `v`, `v_min`, `mah`, `r_interna` (gráfico IR), `i_testada` (o maior consumo que o fabricante testou) |
| botão | quais pinos são ligados por dentro (SCHEMATIC do datasheet), `i_max` |
| LED | o + e o − (símbolo do EasyEDA: A = +, K = −), `i_max` (IF contínua), `vf` típica e `r_s` (curva IF × VF entre 10 e 30 mA), `brilho` (curva de intensidade relativa × corrente, pares `[corrente A, fração]` com 1,0 na corrente de teste) |
| resistor | nada: valor e potência vêm dos atributos da loja |

O `C779439` (LED) e o `C393938` (botão) já estão lá de exemplo. Depois, importe de novo e rode o `testar.py`.

**Nunca chute** o + de uma peça ou os pinos de um botão. Se o datasheet não deixar claro, deixe pendente e diga ao Luiz qual figura faltou.
