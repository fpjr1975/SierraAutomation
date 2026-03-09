#!/bin/bash
BACKUP_DIR="/root/sierra/backups"
DATE=$(date +%Y%m%d_%H%M)
PGPASSWORD="SierraDB2026!!" pg_dump -U sierra -h localhost sierra_db > "$BACKUP_DIR/sierra_db_$DATE.sql"
# Mantém só os últimos 7 dias
find "$BACKUP_DIR" -name "*.sql" -mtime +7 -delete
echo "Backup feito: sierra_db_$DATE.sql"
