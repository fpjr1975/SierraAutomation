#!/bin/bash
# =============================================================================
# Sierra SaaS — Backup PostgreSQL com Rotação
# Mantém: últimos 7 backups diários + últimos 4 semanais (domingo)
# Executar: todo dia às 6h UTC (3h BRT)
# =============================================================================

BACKUP_DIR="/root/sierra/backups"
DB_NAME="sierra_db"
LOG_FILE="$BACKUP_DIR/backup.log"

# Cria diretório se não existir
mkdir -p "$BACKUP_DIR"

# Data e timestamp
DATETIME=$(date +%Y%m%d_%H%M%S)
DOW=$(date +%u)  # 1=Segunda ... 7=Domingo

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== Iniciando backup Sierra DB ==="

# ── 1. Backup diário ──────────────────────────────────────────────────────────
DAILY_FILE="$BACKUP_DIR/daily_${DATETIME}.sql.gz"

log "Gerando backup diário: $DAILY_FILE"

# Usa postgres (superuser) para dump completo mesmo com RLS ativo
if sudo -u postgres pg_dump "$DB_NAME" | gzip -9 > "$DAILY_FILE"; then
    FILESIZE=$(du -sh "$DAILY_FILE" | cut -f1)
    log "Backup gerado com sucesso: $FILESIZE"
else
    log "ERRO: Falha ao gerar backup!"
    exit 1
fi

# ── 2. Backup semanal (se for domingo) ───────────────────────────────────────
if [ "$DOW" = "7" ]; then
    WEEK=$(date +%Y_W%V)
    WEEKLY_FILE="$BACKUP_DIR/weekly_${WEEK}.sql.gz"
    log "Domingo detectado — copiando como backup semanal: $WEEKLY_FILE"
    cp "$DAILY_FILE" "$WEEKLY_FILE"
fi

# ── 3. Rotação de backups diários (manter últimos 7) ─────────────────────────
log "Verificando rotação de backups diários (manter últimos 7)..."
DAILY_COUNT=$(find "$BACKUP_DIR" -name "daily_*.sql.gz" | wc -l)
if [ "$DAILY_COUNT" -gt 7 ]; then
    ls -1t "$BACKUP_DIR"/daily_*.sql.gz | tail -n +8 | xargs rm -f
    log "Removidos backup(s) diário(s) antigos. Total atual: 7"
else
    log "Total diários: $DAILY_COUNT (sem remoção necessária)"
fi

# ── 4. Rotação de backups semanais (manter últimos 4) ────────────────────────
log "Verificando rotação de backups semanais (manter últimos 4)..."
WEEKLY_COUNT=$(find "$BACKUP_DIR" -name "weekly_*.sql.gz" | wc -l)
if [ "$WEEKLY_COUNT" -gt 4 ]; then
    ls -1t "$BACKUP_DIR"/weekly_*.sql.gz | tail -n +5 | xargs rm -f
    log "Removidos backup(s) semanal(is) antigos. Total atual: 4"
else
    log "Total semanais: $WEEKLY_COUNT (sem remoção necessária)"
fi

# ── 5. Resumo ─────────────────────────────────────────────────────────────────
TOTAL_DAILY=$(find "$BACKUP_DIR" -name "daily_*.sql.gz" | wc -l)
TOTAL_WEEKLY=$(find "$BACKUP_DIR" -name "weekly_*.sql.gz" | wc -l)
log "Resumo: $TOTAL_DAILY backup(s) diário(s), $TOTAL_WEEKLY semanal(is)"
log "=== Backup concluído com sucesso ==="
