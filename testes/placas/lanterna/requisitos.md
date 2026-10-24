# Objetivo: Lanterninha de teste
Aperta o botão e o LED acende.

## R1 Pilha no lugar
pecas: BT1
verifica: existe BT1

## R2 Botão liga e desliga
pecas: SW1
verifica: ligado BT1.1 SW1.1
verifica: ligado SW1.3 R1.1
verifica: separado BT1.1 R1.1

## R3 LED acende sem queimar
pecas: R1 D1
verifica: ligado R1.2 D1.1
verifica: sem_pino_solto D1
verifica: acende D1
verifica: nao_queima D1
