# Deploying Cimphawng on Hetzner

This puts the whole site on one Hetzner server at **cimphawng.com**:

- **Caddy** serves the web app (`index.html`) over HTTPS, with certificates obtained and renewed automatically.
- **Caddy** forwards `/api/*` to the **Python API**, which handles wallet sign-in and paper trading.
- The API stores data in **PostgreSQL**.

The database and API are not reachable from the internet. Only Caddy's ports 80 and 443 are open.

You need: a Hetzner Cloud account, the domain `cimphawng.com`, and about 30 minutes.

---

## 1. Create the server

1. In the Hetzner Cloud console, choose **Add Server**:
   - **Location:** the one closest to most of your users.
   - **Image:** Ubuntu 24.04.
   - **Type:** a small shared-vCPU plan (2 vCPU / 4 GB RAM is plenty to start).
   - **SSH key:** add your public key. Don't use a password.
   - **Firewall:** create one allowing inbound **TCP 22, 80, 443** and **UDP 443** only.
2. Note the server's **IPv4** (and IPv6) address.

## 2. Point the domain at it

At your domain registrar (or Cloudflare), add DNS records:

| Type | Name | Value |
|---|---|---|
| A | `@` | server IPv4 |
| A | `www` | server IPv4 |
| AAAA | `@` | server IPv6 (optional) |
| AAAA | `www` | server IPv6 (optional) |

If you use Cloudflare, set these records to **DNS only** (grey cloud) at first, so Caddy can get its certificate.

## 3. Prepare the server

SSH in as root once, then create a deploy user and lock things down:

```bash
ssh root@SERVER_IP

adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh && cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
echo "deploy ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/deploy

# SSH keys only, no root login
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/; s/^#\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart ssh

# Automatic security updates and brute-force protection
apt update && apt -y upgrade
apt -y install unattended-upgrades fail2ban git
dpkg-reconfigure -f noninteractive unattended-upgrades
```

Install Docker (official repository):

```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy
```

Log out, then log back in as `deploy`: `ssh deploy@SERVER_IP`.

## 4. Get the code and configure it

```bash
git clone https://github.com/mangpijasuan/cimphawng.git
cd cimphawng/infra
cp .env.example .env
nano .env
```

Fill in `.env`:

- `SITE_DOMAIN=cimphawng.com`
- `POSTGRES_PASSWORD=`: generate one with `openssl rand -base64 32`
- `OWNER_ADDRESSES=`: your wallet address, which gives you the owner role

`.env` holds secrets. It stays on the server and is ignored by git.

## 5. Start it

```bash
docker compose up -d --build
docker compose ps           # all three should be "running" / "healthy"
docker compose logs -f api  # Ctrl+C to stop watching
```

Then open **https://cimphawng.com**. The first visit can take a few seconds while Caddy gets the certificate.

Check the API: **https://cimphawng.com/api/health** should show `"ok": true`, and `"prices_fresh": true` within about a minute.
API docs are at **https://cimphawng.com/api/docs**.

## 6. Updating

```bash
cd ~/cimphawng && git pull && cd infra && docker compose up -d --build
```

(Automatic deploys on every merge to `main` come later with GitHub Actions.)

## 7. Backups

Nightly database dump, keeping 14 days:

```bash
mkdir -p ~/backups
crontab -e
# add this line:
15 3 * * * cd ~/cimphawng/infra && docker compose exec -T db pg_dump -U cimp cimphawng | gzip > ~/backups/cimphawng-$(date +\%F).sql.gz && find ~/backups -name '*.sql.gz' -mtime +14 -delete
```

Also:

- **Copy backups off the server.** A Hetzner Storage Box with `rsync` works well.
- **Turn on Hetzner's server backups or snapshots** in the console.

To test a restore:

```bash
gunzip -c ~/backups/cimphawng-YYYY-MM-DD.sql.gz | docker compose exec -T db psql -U cimp cimphawng
```

## Troubleshooting

| Problem | Check |
|---|---|
| Site doesn't load / certificate error | DNS points at the server (`dig cimphawng.com`), ports 80/443 open in the Hetzner firewall, `docker compose logs caddy` |
| `/api/health` shows `prices_fresh: false` | `docker compose logs api` for price feed warnings. GeckoTerminal may be rate-limiting; it retries automatically |
| Sign-in fails | The domain in `.env` must match the address in the browser exactly (`cimphawng.com`, not `www.`) |
