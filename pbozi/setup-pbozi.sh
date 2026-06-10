#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# BOZ GPT (JGPTi) — host-level setup
# Called by main setup.sh or run standalone:
#   sudo bash pbozi/setup-pbozi.sh
# ──────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
DEPLOY_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PBOZI_DIR="$DEPLOY_DIR/pbozi"
VENV_DIR="$PBOZI_DIR/backend/venv"

step() { echo -e "${CYAN}▶ $*${NC}"; }
info() { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }

# ── Write .env ────────────────────────────────────────────────
write_pbozi_env() {
    step "Writing pbozi .env..."

    cat > "$PBOZI_DIR/backend/.env" <<'EOF'
BOT_TOKEN=1346701489:DemWJ_ArouL5Sqdg7f-NEJTi4j8Nf9MSAvc
BOT_PLATFORM=bale
BALE_API_BASE_URL=https://tapi.bale.ai/
BALE_FILE_BASE_URL=https://tapi.bale.ai/file/
BALE_WALLET_PROVIDER_TOKEN=
TRANSACTIONS_BOT_TOKEN=
TRANSACTIONS_BOT_ADMIN_CHAT_ID=0
TRANSACTIONS_BOT_PLATFORM=bale
DATABASE_URL=sqlite+aiosqlite:///./jgpti.db
CHROMA_PERSIST_DIR=./chroma_data
REDIS_URL=redis://127.0.0.1:6379/0
ADMIN_PASSWORD=admin123
WEB_SEARCH_PROVIDER=exa
WEB_SEARCH_API_URL=https://api.exa.ai/search
WEB_SEARCH_API_KEY=
WEB_SEARCH_MODEL=
OPENROUTER_API_KEY=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
BACKUP_ENABLED=false
BACKUP_INTERVAL_MINUTES=5
BACKUP_MAX_COUNT=6
BACKUP_GOOGLE_DRIVE_FOLDER_ID=
BACKUP_GOOGLE_SERVICE_ACCOUNT_JSON=
OPENWEBUI_URL=http://localhost:3000
OPENWEBUI_SYNC_SECRET=
EOF
    chmod 600 "$PBOZI_DIR/backend/.env"
    info "pbozi .env written."
}

# ── Create Python venv ────────────────────────────────────────
setup_venv() {
    step "Setting up Python virtual environment..."

    if ! command -v python3 &>/dev/null; then
        apt-get update -qq && apt-get install -y -qq python3 python3-venv python3-pip
    fi

    if [[ ! -d "$VENV_DIR" ]]; then
        python3 -m venv "$VENV_DIR"
        info "venv created at $VENV_DIR"
    else
        info "venv already exists."
    fi

    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip -q
    pip install -r "$PBOZI_DIR/backend/requirements.txt" 2>&1 | tail -3
    info "Python dependencies installed."
}

# ── Install systemd services ──────────────────────────────────
install_services() {
    step "Installing systemd services..."

    # --- pbozi-api (uvicorn on port 7000) ---
    cat > /etc/systemd/system/pbozi-api.service << UNIT
[Unit]
Description=BOZ GPT API (FastAPI)
After=network-online.target drboz-redis.service
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$PBOZI_DIR/backend
ExecStart=$VENV_DIR/bin/uvicorn app.main:app --host 0.0.0.0 --port 7000
Restart=always
RestartSec=5
StandardOutput=append:$PBOZI_DIR/backend/api.log
StandardError=append:$PBOZI_DIR/backend/api_error.log

[Install]
WantedBy=multi-user.target
UNIT

    # --- pbozi-bot (main chat bot) ---
    cat > /etc/systemd/system/pbozi-bot.service << UNIT
[Unit]
Description=BOZ GPT Bot (Bale/Telegram)
After=pbozi-api.service
Wants=pbozi-api.service

[Service]
Type=simple
User=root
WorkingDirectory=$PBOZI_DIR/backend
Environment=PYTHONPATH=$PBOZI_DIR/backend
ExecStart=$VENV_DIR/bin/python3 -u -m app.bot
Restart=always
RestartSec=10
StandardOutput=append:$PBOZI_DIR/backend/bot.log
StandardError=append:$PBOZI_DIR/backend/bot_error.log

[Install]
WantedBy=multi-user.target
UNIT

    systemctl daemon-reload
    info "systemd units installed."
}

# ── Start services ────────────────────────────────────────────
start_pbozi() {
    step "Starting BOZ GPT services..."

    systemctl enable pbozi-api.service --now
    systemctl enable pbozi-bot.service --now

    sleep 3

    echo ""
    echo -e "  API:   $(systemctl is-active pbozi-api)    (port 7000)"
    echo -e "  Bot:   $(systemctl is-active pbozi-bot)"
    echo ""
}

# ── Main ──────────────────────────────────────────────────────
main() {
    write_pbozi_env
    setup_venv
    install_services
    start_pbozi

    echo -e "${GREEN}BOZ GPT setup complete.${NC}"
    echo ""
    echo "  Logs:  journalctl -u pbozi-api -f"
    echo "         journalctl -u pbozi-bot -f"
    echo "  API:   http://localhost:7000"
}

main "$@"
