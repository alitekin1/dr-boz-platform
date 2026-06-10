#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# Dr. Boz — one-command deployment for 4GB Iranian servers
# ──────────────────────────────────────────────────────────────
# Usage:
#   1. tar xzf drboz-deploy.tar.gz
#   2. cd drboz-deploy
#   3. bash setup.sh
# ──────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
BOLD='\033[1m'

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/opt/drboz"

banner() {
    echo -e "${CYAN}${BOLD}"
    echo "╔══════════════════════════════════════════════╗"
    echo "║        Dr. Boz — Server Deployment           ║"
    echo "║        Open WebUI + Nginx + Redis + Bot      ║"
    echo "╚══════════════════════════════════════════════╝"
    echo -e "${NC}"
}

info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
err()   { echo -e "${RED}[✗]${NC} $*"; }
step()  { echo -e "\n${CYAN}${BOLD}▶ $*${NC}"; }
cmd()   { echo -e "  ${YELLOW}\$ $*${NC}"; }

# ── Check requirements ────────────────────────────────────────
check_requirements() {
    step "Checking system requirements..."

    if [[ "$(uname -s)" != "Linux" ]]; then
        err "This script only runs on Linux."
        exit 1
    fi

    local mem_kb; mem_kb=$(awk '/MemTotal/{print $2}' /proc/meminfo 2>/dev/null || echo 0)
    local mem_gb=$(( mem_kb / 1024 / 1024 ))
    info "Memory: ${mem_gb}GB detected"
    if [[ $mem_gb -lt 3 ]]; then
        warn "Less than 3GB RAM — services may struggle. Proceed with caution."
    fi

    local disk_free; disk_free=$(df /opt --output=avail 2>/dev/null | tail -1 || df / --output=avail | tail -1)
    local disk_gb=$(( disk_free / 1024 / 1024 ))
    info "Free disk: ~${disk_gb}GB"
    if [[ $disk_gb -lt 10 ]]; then
        warn "Less than 10GB free — Docker images need ~8GB."
    fi
}

# ── Install Docker if needed ──────────────────────────────────
install_docker() {
    step "Setting up Docker..."

    if command -v docker &>/dev/null; then
        info "Docker already installed: $(docker --version)"
    else
        warn "Docker not found. Installing..."
        curl -fsSL https://get.docker.com | bash
        systemctl enable docker --now
        info "Docker installed."
    fi

    if ! docker compose version &>/dev/null && ! docker-compose --version &>/dev/null; then
        warn "Docker Compose plugin not found. Installing..."
        apt-get update -qq && apt-get install -y -qq docker-compose-plugin 2>/dev/null || {
            curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
                -o /usr/local/bin/docker-compose && chmod +x /usr/local/bin/docker-compose
        }
        info "Docker Compose installed."
    fi
}

# ── Gather user input ─────────────────────────────────────────
gather_input() {
    step "Configuration"

    # Domain
    if [[ -f "$DEPLOY_DIR/.env" ]]; then
        source "$DEPLOY_DIR/.env" 2>/dev/null || true
    fi
    local current_domain="${DOMAIN:-}"
    echo ""
    echo -e "  ${BOLD}Enter your server domain name${NC}"
    echo -e "  This is the public domain that will serve the app (e.g. ai.example.com)"
    echo ""
    if [[ -n "$current_domain" ]]; then
        read -rp "  Domain [$current_domain]: " input_domain
        DOMAIN="${input_domain:-$current_domain}"
    else
        while [[ -z "${DOMAIN:-}" ]]; do
            read -rp "  Domain: " DOMAIN
        done
    fi

    # Email for Let's Encrypt
    local current_email="${EMAIL:-}"
    echo ""
    echo -e "  ${BOLD}Email for SSL certificate notifications${NC}"
    echo ""
    if [[ -n "$current_email" ]]; then
        read -rp "  Email [$current_email]: " input_email
        EMAIL="${input_email:-$current_email}"
    else
        read -rp "  Email: " EMAIL
    fi

    echo ""
    echo -e "  ${BOLD}──────────────────────────────────────────${NC}"
    echo -e "  Domain:  ${GREEN}${DOMAIN}${NC}"
    echo -e "  Email:   ${GREEN}${EMAIL:-none}${NC}"
    echo -e "  ${BOLD}──────────────────────────────────────────${NC}"
    echo ""

    # 4GB RAM optimization
    echo -e "  ${YELLOW}4GB RAM optimization:${NC}"
    echo -e "    On 4GB servers, disabling Whisper (speech-to-text) saves ~300MB."
    echo ""
    read -rp "  Disable Whisper? [Y/n]: " disable_whisper
    if [[ ! "$disable_whisper" =~ ^[Nn] ]]; then
        WHISPER_MODEL=""
        info "Whisper disabled — memory saved."
    else
        WHISPER_MODEL="base"
        info "Whisper enabled (base model)."
    fi

    # BOZ GPT bot
    echo ""
    echo -e "  ${YELLOW}BOZ GPT Bot (JGPTi):${NC}"
    echo -e "    Main AI chatbot + admin panel (FastAPI, port 7000)."
    echo -e "    Runs on host for best 4GB RAM efficiency."
    echo ""
    read -rp "  Install BOZ GPT bot? [Y/n]: " install_pbozi
    if [[ ! "$install_pbozi" =~ ^[Nn] ]]; then
        DEPLOY_BOZ=true
        info "BOZ GPT bot will be installed."
    else
        DEPLOY_BOZ=false
        info "Skipping BOZ GPT bot."
    fi
}

# ── Write .env ─────────────────────────────────────────────────
write_env() {
    step "Writing .env file..."
    cat > "$DEPLOY_DIR/.env" <<EOF
# Generated by setup.sh — $(date)
BOT_SHARED_SECRET=797cdeed234b7d14da3a81dd6d3139c433599b7b1ba5db18937a51f147f98526
TELEGRAM_BOT_TOKEN=8837001286:AAEGVQ0B-nDXRA6tNmR4PoSEUmVZdqgenso
TELEGRAM_BOT_USERNAME=drboz_bot
BALE_BOT_TOKEN=1346701489:DemWJ_ArouL5Sqdg7f-NEJTi4j8Nf9MSAvc
BALE_BOT_USERNAME=drboz_bale
BOT_ADMIN_IDS=48859866
CARD_HOLDER_NAME=بزرگ‌نیا
CARD_NUMBER=6037-9975-9123-4567
BALE_SAFIR_CLIENT_ID=
BALE_SAFIR_CLIENT_SECRET=
WHISPER_MODEL=${WHISPER_MODEL:-}
WEBUI_SECRET_KEY=
ENABLE_LOGIN_FORM=true
ENABLE_OAUTH_SIGNUP=true
DOMAIN=${DOMAIN}
EMAIL=${EMAIL:-}
EOF
    chmod 600 "$DEPLOY_DIR/.env"
    info ".env written."
}

# ── Generate self-signed SSL ──────────────────────────────────
generate_ssl() {
    step "Generating SSL certificates..."

    local ssl_dir="$DEPLOY_DIR/ssl/live"
    mkdir -p "$ssl_dir"

    if [[ -f "$ssl_dir/fullchain.pem" ]] && [[ -f "$ssl_dir/privkey.pem" ]]; then
        info "SSL certificates already exist. Skipping."
        return
    fi

    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$ssl_dir/privkey.pem" \
        -out "$ssl_dir/fullchain.pem" \
        -subj "/C=IR/ST=Tehran/L=Tehran/O=DrBoz/CN=${DOMAIN}" 2>/dev/null

    chmod 600 "$ssl_dir/privkey.pem"
    info "Self-signed SSL certificate generated (365 days)."
    warn "This is a SELF-SIGNED cert — browsers will show a warning."
    echo -e "  ${CYAN}→ After DNS is pointing here, run: bash get-letsencrypt.sh${NC}"
}

# ── Create letsencrypt helper script ──────────────────────────
create_le_script() {
    cat > "$DEPLOY_DIR/get-letsencrypt.sh" <<'LESCRIPT'
#!/usr/bin/env bash
# Get real Let's Encrypt SSL certificates for production use.
# Run this AFTER your domain DNS points to this server's IP.
set -euo pipefail
DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DEPLOY_DIR/.env" 2>/dev/null || true
DOMAIN="${DOMAIN:?Set DOMAIN in .env first}"
EMAIL="${EMAIL:-admin@${DOMAIN}}"

echo "▶ Getting Let's Encrypt certificate for $DOMAIN..."

# Stop nginx temporarily to free port 80 for certbot
docker compose -f "$DEPLOY_DIR/docker-compose.yml" stop nginx 2>/dev/null || true

# Install certbot if needed
if ! command -v certbot &>/dev/null; then
    apt-get update -qq && apt-get install -y -qq certbot
fi

certbot certonly --standalone \
    --agree-tos --non-interactive \
    -d "$DOMAIN" \
    --email "$EMAIL"

# Copy certs
SSL_DIR="$DEPLOY_DIR/ssl/live"
mkdir -p "$SSL_DIR"
cp /etc/letsencrypt/live/"$DOMAIN"/fullchain.pem "$SSL_DIR/fullchain.pem"
cp /etc/letsencrypt/live/"$DOMAIN"/privkey.pem   "$SSL_DIR/privkey.pem"
chmod 600 "$SSL_DIR/privkey.pem"

# Restart nginx
docker compose -f "$DEPLOY_DIR/docker-compose.yml" start nginx

# Add renewal cron job
CRON_JOB="30 2 * * 1 certbot renew --quiet && cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem $SSL_DIR/fullchain.pem && cp /etc/letsencrypt/live/$DOMAIN/privkey.pem $SSL_DIR/privkey.pem && docker compose -f $DEPLOY_DIR/docker-compose.yml restart nginx"
(crontab -l 2>/dev/null | grep -v "certbot renew.*$DOMAIN"; echo "$CRON_JOB") | crontab -

echo "✓ Real SSL certificates installed. Auto-renewal cron job added."
LESCRIPT
    chmod +x "$DEPLOY_DIR/get-letsencrypt.sh"
    info "Created get-letsencrypt.sh (run after DNS is pointed here)."
}

# ── Install to /opt/drboz ─────────────────────────────────────
install_files() {
    step "Installing to ${INSTALL_DIR}..."

    if [[ "$DEPLOY_DIR" != "$INSTALL_DIR" ]]; then
        info "Copying files to $INSTALL_DIR..."
        mkdir -p "$INSTALL_DIR"
        rsync -a --delete "$DEPLOY_DIR"/ "$INSTALL_DIR"/ 2>/dev/null || cp -a "$DEPLOY_DIR"/* "$INSTALL_DIR"/
    fi
    info "Files installed at $INSTALL_DIR"
}

# ── Build & start ─────────────────────────────────────────────
build_and_start() {
    step "Building Docker images..."

    cd "$INSTALL_DIR"
    docker compose build nginx bale-bot 2>&1 | sed 's/^/  /'

    step "Pulling pre-built images..."
    docker pull ghcr.io/open-webui/open-webui:main 2>&1 | sed 's/^/  /' || warn "Could not pull open-webui image (will try on start)"
    docker pull redis:7-alpine 2>&1 | sed 's/^/  /' || true

    step "Starting all services..."
    docker compose up -d 2>&1 | sed 's/^/  /'

    echo ""
    sleep 5
}

# ── Show status ───────────────────────────────────────────────
show_status() {
    step "Deployment status"

    echo ""
    docker compose -f "$INSTALL_DIR/docker-compose.yml" ps 2>/dev/null || true

    if [[ "${DEPLOY_BOZ:-false}" == "true" ]]; then
        echo ""
        echo -e "  ${CYAN}BOZ GPT:${NC}"
        echo -e "  API:   $(systemctl is-active pbozi-api 2>/dev/null || echo 'inactive')    (port 7000)"
        echo -e "  Bot:   $(systemctl is-active pbozi-bot 2>/dev/null || echo 'inactive')"

        echo ""
        echo -e "${GREEN}${BOLD}║${NC}  ${CYAN}BOZ GPT Bot:${NC}                                     ${GREEN}${BOLD}║${NC}"
        echo -e "${GREEN}${BOLD}║${NC}  API:     ${CYAN}http://localhost:7000${NC}                       ${GREEN}${BOLD}║${NC}"
        echo -e "${GREEN}${BOLD}║${NC}  Logs:    journalctl -u pbozi-bot -f                ${GREEN}${BOLD}║${NC}"
        echo -e "${GREEN}${BOLD}║${NC}           journalctl -u pbozi-api -f                ${GREEN}${BOLD}║${NC}"
        echo -e "${GREEN}${BOLD}║${NC}                                                     ${GREEN}${BOLD}║${NC}"
    fi

    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║  Deployment Complete!                               ║${NC}"
    echo -e "${GREEN}${BOLD}╠══════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}${BOLD}║${NC}                                                     ${GREEN}${BOLD}║${NC}"
    echo -e "${GREEN}${BOLD}║${NC}  URL:     ${CYAN}https://${DOMAIN}:3000${NC}                       ${GREEN}${BOLD}║${NC}"
    echo -e "${GREEN}${BOLD}║${NC}  Auth:    ${CYAN}https://${DOMAIN}:3000/auth${NC}                   ${GREEN}${BOLD}║${NC}"
    echo -e "${GREEN}${BOLD}║${NC}                                                     ${GREEN}${BOLD}║${NC}"
    echo -e "${GREEN}${BOLD}║${NC}  ${YELLOW}▶ Next steps:${NC}                                      ${GREEN}${BOLD}║${NC}"
    echo -e "${GREEN}${BOLD}║${NC}  1. Point DNS (${DOMAIN} → this server IP)          ${GREEN}${BOLD}║${NC}"
    echo -e "${GREEN}${BOLD}║${NC}  2. Run: ${CYAN}bash ${INSTALL_DIR}/get-letsencrypt.sh${NC}       ${GREEN}${BOLD}║${NC}"
    echo -e "${GREEN}${BOLD}║${NC}  3. Open: ${CYAN}https://${DOMAIN}:3000${NC}                     ${GREEN}${BOLD}║${NC}"
    echo -e "${GREEN}${BOLD}║${NC}                                                     ${GREEN}${BOLD}║${NC}"
    echo -e "${GREEN}${BOLD}║${NC}  ${YELLOW}Management:${NC}                                        ${GREEN}${BOLD}║${NC}"
    echo -e "${GREEN}${BOLD}║${NC}  Logs:    docker compose -f ${INSTALL_DIR}/docker-compose.yml logs -f ${GREEN}${BOLD}║${NC}"
    echo -e "${GREEN}${BOLD}║${NC}  Restart: docker compose -f ${INSTALL_DIR}/docker-compose.yml restart ${GREEN}${BOLD}║${NC}"
    echo -e "${GREEN}${BOLD}║${NC}  Stop:    docker compose -f ${INSTALL_DIR}/docker-compose.yml down   ${GREEN}${BOLD}║${NC}"
    echo -e "${GREEN}${BOLD}║${NC}                                                     ${GREEN}${BOLD}║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# ── Main ──────────────────────────────────────────────────────
main() {
    banner

    # Check if running as root
    if [[ $EUID -ne 0 ]]; then
        err "Please run as root: sudo bash setup.sh"
        exit 1
    fi

    check_requirements
    install_docker
    gather_input
    write_env
    install_files
    generate_ssl
    create_le_script
    build_and_start

    # ── BOZ GPT (pbozi) ──────────────────────────────────────
    if [[ "${DEPLOY_BOZ:-false}" == "true" ]]; then
        step "Setting up BOZ GPT bot..."
        bash "$INSTALL_DIR/pbozi/setup-pbozi.sh"
    fi

    show_status
}

main "$@"
