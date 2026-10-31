#!/bin/sh
set -e

DYNAMIC_DIR="/etc/traefik/dynamic"
mkdir -p "$DYNAMIC_DIR"

generate_route() {
    name=$1
    domain=$2
    upstream=$3

    if [ -z "$domain" ]; then
        echo "Skipping $name: no domain set"
        return
    fi

    echo "Generating route: $name -> $domain -> $upstream"

    cat > "${DYNAMIC_DIR}/${name}.yml" <<EOF
http:
  routers:
    ${name}-http:
      rule: "Host(\`${domain}\`)"
      entryPoints:
        - http
      middlewares:
        - ${name}-https-redirect
      service: ${name}-svc
    ${name}-https:
      rule: "Host(\`${domain}\`)"
      entryPoints:
        - https
      tls:
        certResolver: letsencrypt
      service: ${name}-svc
  middlewares:
    ${name}-https-redirect:
      redirectScheme:
        scheme: https
  services:
    ${name}-svc:
      loadBalancer:
        servers:
          - url: "http://${upstream}"
EOF
}

generate_route "backend"   "$DOMAIN_BACKEND"       "backend:8000"
generate_route "sales"     "$DOMAIN_SALES"          "sales-agent:8000"
generate_route "connector" "$DOMAIN_CONNECTOR_HUB"  "wappi-module:8000"

exec "$@"
