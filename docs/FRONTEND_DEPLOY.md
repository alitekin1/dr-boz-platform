# Deploy Custom Frontend to New Server

The subscription/upgrade/billing UI is in the SvelteKit frontend, which must be **built**
and deployed separately from the backend. The Docker image has the stock Open WebUI
frontend — we need to override it with our custom build.

## Option A: Build on the new server (recommended)

The source code is already in the repo at `src/`. Build it:

```bash
cd /opt/drboz
git clone https://github.com/alitekin1/dr-boz-platform.git /tmp/drboz-src 2>/dev/null || true

# Install deps and build
cd /tmp/drboz-src
npm install

# CRITICAL for 4GB servers: reset swap first
swapoff /swapfile 2>/dev/null || true
sleep 2
mkswap /swapfile 2>/dev/null || true
swapon /swapfile 2>/dev/null || true

# Build with memory limit (skip pyodide, we already have it in the image)
NODE_OPTIONS="--max-old-space-size=3072" npx vite build

# Deploy the build into the container
docker cp build/. open-webui:/app/build/

# Restart
docker restart open-webui
```

If the build OOM-kills, try:
```bash
# Drop caches, wait 30s, retry
sync && echo 3 > /proc/sys/vm/drop_caches
sleep 30
NODE_OPTIONS="--max-old-space-size=3072" npx vite build
docker cp build/. open-webui:/app/build/
docker restart open-webui
```

## Option B: Copy pre-built frontend from old server

If building fails on the new 4GB server, copy the build from the old server:

```bash
# On OLD server — pack the frontend
sudo docker cp open-webui:/app/build/. /tmp/frontend-build/
cd /tmp
tar czf frontend-build.tar.gz frontend-build/

# SCP to new server
scp frontend-build.tar.gz root@NEW_SERVER_IP:/tmp/

# On NEW server — deploy
cd /tmp && tar xzf frontend-build.tar.gz
docker cp frontend-build/. open-webui:/app/build/
docker restart open-webui
```

Option B is ~100MB download but guaranteed to work.

## Verify

After deploying, check that the subscription UI appears:

```bash
# Check the API returns plans
docker exec open-webui curl -s http://localhost:8080/api/v1/billing/public/plans

# Check the frontend has our custom files
docker exec open-webui ls /app/build/upgrade-bg.svg

# Open in browser: https://your-domain:3000
# You should see the subscription badge in the sidebar and upgrade page
```
