# HTTPS teskari proksi — ko'p replika (docker-compose.ha.yml). `ges` xizmati nomi Docker DNS da barcha
# replikalarga hal bo'ladi (dynamic a); faol sog'liq tekshiruvi /api/ready — 503 bergan replika chetlanadi.
{$GES_DOMAIN} {
    tls internal
    encode gzip zstd
    request_body {
        max_size 2GB
    }
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
        Content-Security-Policy "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' ws: wss: blob: data:; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        -Server
    }
    reverse_proxy {
        dynamic a {
            name ges
            port 8000
            refresh 10s
        }
        lb_policy least_conn
        health_uri /api/ready
        health_interval 10s
        health_timeout 5s
        fail_duration 30s
        flush_interval -1
    }
}
