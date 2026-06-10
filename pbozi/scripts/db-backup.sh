#!/usr/bin/env bash
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────
DB_PATH="/root/bozgpt/backend/jgpti.db"
BACKUP_DIR="/root/bozgpt/backups/.git-backup"
REPO_NAME="bozgpt-db-backups"
INTERVAL_SECONDS=300  # 5 minutes
MAX_BACKUPS=100       # keep last N backups locally before pushing
# ───────────────────────────────────────────────────────────────

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Ensure backup repo exists
init_backup_repo() {
    mkdir -p "$BACKUP_DIR"
    cd "$BACKUP_DIR"

    if [ ! -d ".git" ]; then
        log "Creating local git repo..."
        git init -q
        git config user.email "backup@bozgpt"
        git config user.name "BOZ Backup"

        # Create or reuse remote
        if ! gh repo view "$REPO_NAME" &>/dev/null; then
            log "Creating private GitHub repo: $REPO_NAME"
            gh repo create "$REPO_NAME" --private --description "Automated BOZ GPT database backups"
        fi

        git remote add origin "https://github.com/$(gh api user --jq '.login')/$REPO_NAME" || true
        log "Backup repo ready."
    else
        cd "$BACKUP_DIR"
        git remote set-url origin "https://github.com/$(gh api user --jq '.login')/$REPO_NAME" 2>/dev/null || true
    fi
}

# Take backup and push
take_backup() {
    cd "$BACKUP_DIR"

    if [ ! -f "$DB_PATH" ]; then
        log "ERROR: Database not found at $DB_PATH"
        return 1
    fi

    local timestamp
    timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_file="jgpti_${timestamp}.db"

    # Copy database (use sqlite3 backup if available, else cp)
    if command -v sqlite3 &>/dev/null; then
        sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/$backup_file'" 2>/dev/null || cp "$DB_PATH" "$backup_file"
    else
        cp "$DB_PATH" "$backup_file"
    fi

    # Compress
    gzip -f "$backup_file"

    log "Backup created: ${backup_file}.gz ($(du -h "${backup_file}.gz" | cut -f1))"

    # Git add and commit
    git add "${backup_file}.gz"
    git commit -q -m "backup: $timestamp"

    # Cleanup old local backups (keep last MAX_BACKUPS)
    local count
    count=$(git rev-list --count HEAD)
    if [ "$count" -gt "$MAX_BACKUPS" ]; then
        local to_delete=$((count - MAX_BACKUPS))
        log "Cleaning up $to_delete old commit(s)..."
        git rev-list --skip="$MAX_BACKUPS" HEAD | tail -n "$to_delete" | while read -r old_commit; do
            git rm -q --cached -- "$(git diff-tree --no-commit-id --name-only -r "$old_commit")" 2>/dev/null || true
        done
        git commit -q -m "cleanup: removed old backups" || true
    fi

    # Push to GitHub
    log "Pushing to GitHub..."
    if git push origin main --quiet 2>/dev/null || git push origin master --quiet 2>/dev/null; then
        log "Push successful."
    else
        log "WARNING: Push failed. Will retry next cycle."
    fi
}

# ── Main ───────────────────────────────────────────────────────
log "BOZ GPT Database Backup Script started."
log "Database: $DB_PATH"
log "Interval: ${INTERVAL_SECONDS}s"

# Check gh auth
if ! gh auth status &>/dev/null; then
    log "ERROR: Not authenticated with GitHub. Run: gh auth login"
    exit 1
fi

init_backup_repo

# First backup immediately
take_backup

# Then loop
while true; do
    sleep "$INTERVAL_SECONDS"
    take_backup
done
