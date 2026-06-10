#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# Migrate data from old Dr. Boz server to new server
# ──────────────────────────────────────────────────────────────
# On the OLD server, create backups:
#
#   # Open WebUI data
#   cd /root/bozi/open-webui/backend
#   tar czf /tmp/drboz-data.tar.gz data
#
#   # BOZ GPT bot data
#   cd /bozi/pbozi/backend
#   tar czf /tmp/pbozi-data.tar.gz jgpti.db* chroma_data/ uploads/
#
# Then scp both to the new server.
# ──────────────────────────────────────────────────────────────
set -euo pipefail

DEPLOY_DIR="/opt/drboz"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "${CYAN}▶ Dr. Boz — Data Migration${NC}"
echo ""

restore_webui() {
    local BACKUP_FILE="$DEPLOY_DIR/drboz-data-backup.tar.gz"
    if [[ ! -f "$BACKUP_FILE" ]]; then
        echo -e "  ${YELLOW}No Open WebUI backup at $BACKUP_FILE — skipping${NC}"
        return
    fi
    echo -e "${GREEN}Restoring Open WebUI data...${NC}"
    cd "$DEPLOY_DIR"
    docker compose stop webui 2>/dev/null || true
    local DATA_DIR="$DEPLOY_DIR/backend/data"
    [[ -d "$DATA_DIR" ]] && mv "$DATA_DIR" "${DATA_DIR}.bak.$(date +%s)" 2>/dev/null || true
    tar xzf "$BACKUP_FILE" -C "$DEPLOY_DIR/backend/"
    chmod -R 755 "$DATA_DIR"
    docker compose start webui 2>/dev/null || docker compose up -d webui
    echo -e "  ${GREEN}✓ WebUI data restored${NC}"
}

restore_pbozi() {
    local BACKUP_FILE="$DEPLOY_DIR/pbozi-data-backup.tar.gz"
    if [[ ! -f "$BACKUP_FILE" ]]; then
        echo -e "  ${YELLOW}No BOZ GPT backup at $BACKUP_FILE — skipping${NC}"
        return
    fi
    echo -e "${GREEN}Restoring BOZ GPT data...${NC}"
    systemctl stop pbozi-api pbozi-bot 2>/dev/null || true
    local PBOZI_DIR="$DEPLOY_DIR/pbozi/backend"
    cd "$PBOZI_DIR"
    tar xzf "$BACKUP_FILE"
    systemctl start pbozi-api pbozi-bot 2>/dev/null || true
    echo -e "  ${GREEN}✓ BOZ GPT data restored (jgpti.db, chroma_data, uploads)${NC}"
}

# Check for backups
FOUND=false
for f in drboz-data-backup.tar.gz pbozi-data-backup.tar.gz; do
    [[ -f "$DEPLOY_DIR/$f" ]] && FOUND=true
done

if [[ "$FOUND" != "true" ]]; then
    echo -e "${YELLOW}No backup files found.${NC}"
    echo ""
    echo "  On OLD server, run:"
    echo ""
    echo "  # Open WebUI"
    echo "  ${CYAN}cd /root/bozi/open-webui/backend${NC}"
    echo "  ${CYAN}tar czf /tmp/drboz-data.tar.gz data${NC}"
    echo "  ${CYAN}scp /tmp/drboz-data.tar.gz root@NEW_IP:/opt/drboz/drboz-data-backup.tar.gz${NC}"
    echo ""
    echo "  # BOZ GPT bot"
    echo "  ${CYAN}cd /bozi/pbozi/backend${NC}"
    echo "  ${CYAN}tar czf /tmp/pbozi-data.tar.gz jgpti.db* chroma_data/ uploads/${NC}"
    echo "  ${CYAN}scp /tmp/pbozi-data.tar.gz root@NEW_IP:/opt/drboz/pbozi-data-backup.tar.gz${NC}"
    echo ""
    echo "  Then run this script again."
    exit 0
fi

echo -e "${YELLOW}This will OVERWRITE data on this server.${NC}"
read -rp "  Continue? [y/N]: " confirm
if [[ ! "$confirm" =~ ^[Yy] ]]; then
    echo "Aborted."
    exit 0
fi

restore_webui
restore_pbozi

echo ""
echo -e "${GREEN}✓ All data restored.${NC}"
