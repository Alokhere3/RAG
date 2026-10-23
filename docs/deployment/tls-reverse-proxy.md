# Production TLS Edge Termination & Port Isolation Runbook (F-06)

## Overview

The RAG platform runs in a single-tenant self-hosted model. To guarantee confidentiality and integrity of user credentials, authentication cookies, and query payloads:

1. **Loopback Port Isolation**: All Docker containers bind strictly to host loopback (`127.0.0.1`). No container exposes ports to public interfaces (`0.0.0.0`).
2. **Mandatory TLS Edge Termination**: An edge reverse proxy (such as Nginx, Caddy, Cloudflare Tunnel, or AWS Application Load Balancer) must terminate TLS using valid X.509 certificates and forward requests to `http://127.0.0.1:3001`.
3. **Secure Cookie Enforcement**: In production (`APP_ENV=production`), `AUTH_COOKIE_SECURE=true` is enforced at application startup, requiring HTTPS for browsers to transmit session cookies.

---

## 1. Port Exposure Verification

Inspect `docker-compose.yml` to confirm that all host bindings use `127.0.0.1`:

| Service | Port Mapping in Compose | Bound Interface | Purpose |
| :--- | :--- | :--- | :--- |
| `postgres` | `127.0.0.1:${POSTGRES_PORT:-5432}:5432` | Loopback only | Direct database management (if needed) |
| `redis` | `127.0.0.1:${REDIS_PORT:-6379}:6379` | Loopback only | Cache inspection (if needed) |
| `backend` | `127.0.0.1:${BACKEND_PORT:-8001}:8000` | Loopback only | Direct API debugging |
| `frontend` | `127.0.0.1:${FRONTEND_PORT:-3001}:80` | Loopback only | Web UI and unified API gateway |

External clients cannot connect directly to ports 3001, 8001, 5432, or 6379 over the public internet or local area network.

---

## 2. Setting Up Nginx Edge Reverse Proxy

A production template is provided at [`deployment/nginx/tls-proxy.conf.template`](../../deployment/nginx/tls-proxy.conf.template).

### Step 1: Install Nginx and Certbot

On Ubuntu / Debian hosts:
```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

### Step 2: Obtain TLS Certificate

```bash
sudo certbot certonly --nginx -d rag.example.com
```

### Step 3: Install Configuration

Copy the template to `/etc/nginx/sites-available/rag.example.com`:
```bash
sudo cp deployment/nginx/tls-proxy.conf.template /etc/nginx/sites-available/rag.example.com
# Edit domain name and certificate paths
sudo sed -i 's/rag.example.com/your-actual-domain.com/g' /etc/nginx/sites-available/rag.example.com
sudo ln -s /etc/nginx/sites-available/rag.example.com /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 3. Alternative: Caddy (Automatic HTTPS)

If deploying with Caddy, add the following to `/etc/caddy/Caddyfile`:

```caddy
rag.example.com {
    reverse_proxy 127.0.0.1:3001 {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-Proto https
    }
}
```

Caddy automatically provisions and renews Let's Encrypt certificates.

---

## 4. Verification Checklist

Run these commands from a remote machine:

1. **Test Port 3001 directly from remote machine**:
   ```bash
   curl -I http://<HOST_PUBLIC_IP>:3001/
   ```
   *Expected*: Connection refused or timeout (traffic blocked by loopback binding).

2. **Test HTTPS through edge reverse proxy**:
   ```bash
   curl -I https://rag.example.com/
   ```
   *Expected*: `HTTP/2 200` with `Strict-Transport-Security` header.

3. **Verify Cookie Security Flags**:
   Log in to the application and inspect the `Set-Cookie` response header:
   ```text
   Set-Cookie: rag_refresh_token=...; Path=/api/v1/auth; Secure; HttpOnly; SameSite=Lax
   ```
