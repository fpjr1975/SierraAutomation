#!/bin/bash
# Importa todos os meses do OneDrive — sequencial
# Jan e Março já feitos, Fevereiro rodando separado

cd /root/sierra

MESES=(
    "4 ABRIL|F8DA20F2479D8100!170701"
    "5 MAIO|F8DA20F2479D8100!170702"
    "6 JUNHO|F8DA20F2479D8100!170703"
    "7 JULHO|F8DA20F2479D8100!170704"
    "8 AGOSTO|F8DA20F2479D8100!170705"
    "9 SETEMBRO|F8DA20F2479D8100!170706"
    "10 OUTUBRO|F8DA20F2479D8100!170697"
    "11 NOVEMBRO|F8DA20F2479D8100!170698"
    "12 DEZEMBRO|F8DA20F2479D8100!170699"
)

echo "$(date) — Iniciando importação de todos os meses" >> /root/sierra/import_all.log

for entry in "${MESES[@]}"; do
    MES_NOME="${entry%%|*}"
    MES_ID="${entry##*|}"
    
    SAFE=$(echo "$MES_NOME" | tr ' ' '_')
    PROGRESS="/root/sierra/import_${SAFE}_progress.json"
    
    # Checa se já foi feito
    if [ -f "$PROGRESS" ]; then
        FINISHED=$(python3 -c "import json; d=json.load(open('$PROGRESS')); print('yes' if d.get('finished') else 'no')" 2>/dev/null)
        if [ "$FINISHED" = "yes" ]; then
            echo "$(date) — $MES_NOME: já concluído, pulando" >> /root/sierra/import_all.log
            continue
        fi
    fi
    
    echo "$(date) — Iniciando $MES_NOME..." >> /root/sierra/import_all.log
    python3 import_mes.py "$MES_NOME" "$MES_ID"
    echo "$(date) — $MES_NOME concluído" >> /root/sierra/import_all.log
    
    # Pausa 10s entre meses pra não estressar o OneDrive
    sleep 10
done

echo "$(date) — TODOS OS MESES CONCLUÍDOS" >> /root/sierra/import_all.log

# Resumo final
python3 -c "
import asyncio, asyncpg
async def q():
    c = await asyncpg.connect('postgresql://sierra:SierraDB2026!!@localhost/sierra_db')
    total = await c.fetchval(\"SELECT count(*) FROM apolices WHERE status='importada'\")
    clientes = await c.fetchval(\"SELECT count(DISTINCT cliente_id) FROM apolices WHERE status='importada'\")
    print(f'TOTAL FINAL: {total} apólices | {clientes} clientes')
    await c.close()
asyncio.run(q())
" >> /root/sierra/import_all.log
