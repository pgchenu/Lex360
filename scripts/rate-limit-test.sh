#!/bin/bash
# =============================================================================
# Test de Rate Limiting — Lexis 360 Intelligence
# =============================================================================
#
# Usage:
#   1. Copier le access_token depuis le localStorage du navigateur
#   2. Exporter: export LEX_TOKEN="votre_token_ici"
#   3. Lancer: bash rate-limit-test.sh
#
# Ce script teste plusieurs endpoints avec des rafales de requêtes
# et détecte les réponses 429, les headers de rate-limit, et les ralentissements.
# =============================================================================

set -euo pipefail

BASE_URL="https://www.lexis360intelligence.fr"
TOKEN="${LEX_TOKEN:?Erreur: définir LEX_TOKEN avec le access_token JWT}"
RESULTS_DIR="./results-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RESULTS_DIR"

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC} $1"; }
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }

# =============================================================================
# Fonction: envoyer une requête et capturer les détails
# =============================================================================
send_request() {
    local method="$1"
    local endpoint="$2"
    local body="${3:-}"
    local label="$4"
    local output_file="$5"

    local url="${BASE_URL}${endpoint}"
    local start_time
    start_time=$(python3 -c 'import time; print(int(time.time()*1000))')

    local curl_args=(
        -s -o /dev/null
        -w '%{http_code}|%{time_total}|%{size_download}'
        -H "Authorization: Bearer ${TOKEN}"
        -H "Content-Type: application/json"
        -H "Accept: application/json"
        -D "${output_file}.headers"
    )

    if [ "$method" = "POST" ] && [ -n "$body" ]; then
        curl_args+=(-X POST -d "$body")
    fi

    local response
    response=$(curl "${curl_args[@]}" "$url" 2>/dev/null || echo "000|0|0")

    local http_code time_total size
    IFS='|' read -r http_code time_total size <<< "$response"

    local end_time
    end_time=$(python3 -c 'import time; print(int(time.time()*1000))')
    local elapsed=$(( end_time - start_time ))

    # Chercher des headers de rate-limit
    local rate_headers=""
    if [ -f "${output_file}.headers" ]; then
        rate_headers=$(grep -iE '(rate-limit|retry-after|x-ratelimit|x-rate-limit|ratelimit)' "${output_file}.headers" 2>/dev/null || true)
    fi

    echo "${http_code}|${time_total}|${size}|${elapsed}|${rate_headers}" >> "$output_file"
    echo "$http_code"
}

# =============================================================================
# Fonction: test en rafale séquentielle
# =============================================================================
burst_test_sequential() {
    local label="$1"
    local method="$2"
    local endpoint="$3"
    local body="${4:-}"
    local count="${5:-20}"
    local delay="${6:-0}"  # délai entre requêtes en secondes

    local output_file="${RESULTS_DIR}/${label}.csv"
    echo "http_code|time_total|size|elapsed_ms|rate_headers" > "$output_file"

    log "━━━ Test: ${label} ━━━"
    log "  Endpoint: ${method} ${endpoint}"
    log "  Requêtes: ${count}, délai: ${delay}s"

    local count_429=0
    local count_ok=0
    local count_err=0
    local total_time=0

    for i in $(seq 1 "$count"); do
        local code
        code=$(send_request "$method" "$endpoint" "$body" "$label" "$output_file")

        if [ "$code" = "429" ]; then
            err "  #${i} → 429 RATE LIMITED"
            count_429=$((count_429 + 1))
        elif [ "$code" = "200" ] || [ "$code" = "201" ]; then
            printf "  #%-3d → %s (ok)\n" "$i" "$code"
            count_ok=$((count_ok + 1))
        elif [ "$code" = "401" ]; then
            err "  #${i} → 401 UNAUTHORIZED — token expiré?"
            count_err=$((count_err + 1))
            if [ "$i" -ge 3 ]; then
                err "  Abandon: token invalide"
                break
            fi
        else
            warn "  #${i} → ${code}"
            count_err=$((count_err + 1))
        fi

        [ "$delay" != "0" ] && sleep "$delay"
    done

    # Analyse des headers de rate-limit
    local found_headers
    found_headers=$(grep -v "^http_code" "$output_file" | cut -d'|' -f5 | grep -v "^$" | head -5 || true)

    echo ""
    log "  Résultats: ${count_ok} OK, ${count_429} rate-limited, ${count_err} erreurs"

    if [ -n "$found_headers" ]; then
        warn "  Headers de rate-limit détectés:"
        echo "$found_headers" | while read -r h; do
            warn "    → $h"
        done
    else
        log "  Aucun header de rate-limit détecté"
    fi

    # Vérifier la dégradation de performance (latence croissante)
    local latencies
    latencies=$(grep -v "^http_code" "$output_file" | cut -d'|' -f4 | head -"$count")
    local first_5_avg last_5_avg
    first_5_avg=$(echo "$latencies" | head -5 | awk '{s+=$1} END {printf "%.0f", s/NR}')
    last_5_avg=$(echo "$latencies" | tail -5 | awk '{s+=$1} END {printf "%.0f", s/NR}')

    if [ "$last_5_avg" -gt $(( first_5_avg * 3 )) ] 2>/dev/null; then
        warn "  Latence dégradée: ${first_5_avg}ms (début) → ${last_5_avg}ms (fin) — possible throttling"
    else
        log "  Latence stable: ~${first_5_avg}ms (début), ~${last_5_avg}ms (fin)"
    fi

    echo ""
}

# =============================================================================
# Fonction: test en rafale parallèle (concurrentes)
# =============================================================================
burst_test_parallel() {
    local label="$1"
    local method="$2"
    local endpoint="$3"
    local body="${4:-}"
    local count="${5:-10}"

    local output_file="${RESULTS_DIR}/${label}.csv"
    echo "http_code|time_total|size|elapsed_ms|rate_headers" > "$output_file"

    log "━━━ Test parallèle: ${label} ━━━"
    log "  Endpoint: ${method} ${endpoint}"
    log "  Requêtes concurrentes: ${count}"

    local pids=()
    local tmp_dir="${RESULTS_DIR}/${label}_tmp"
    mkdir -p "$tmp_dir"

    for i in $(seq 1 "$count"); do
        (
            local url="${BASE_URL}${endpoint}"
            local curl_args=(
                -s -o /dev/null
                -w '%{http_code}|%{time_total}|%{size_download}'
                -H "Authorization: Bearer ${TOKEN}"
                -H "Content-Type: application/json"
                -D "${tmp_dir}/headers_${i}"
            )
            if [ "$method" = "POST" ] && [ -n "$body" ]; then
                curl_args+=(-X POST -d "$body")
            fi
            local resp
            resp=$(curl "${curl_args[@]}" "$url" 2>/dev/null || echo "000|0|0")
            echo "$resp" > "${tmp_dir}/result_${i}"
        ) &
        pids+=($!)
    done

    # Attendre toutes les requêtes
    for pid in "${pids[@]}"; do
        wait "$pid" 2>/dev/null || true
    done

    # Collecter les résultats
    local count_429=0 count_ok=0 count_err=0
    for i in $(seq 1 "$count"); do
        local result
        result=$(cat "${tmp_dir}/result_${i}" 2>/dev/null || echo "000|0|0")
        local code
        code=$(echo "$result" | cut -d'|' -f1)

        local rate_h=""
        if [ -f "${tmp_dir}/headers_${i}" ]; then
            rate_h=$(grep -iE '(rate-limit|retry-after|x-ratelimit)' "${tmp_dir}/headers_${i}" 2>/dev/null || true)
        fi
        echo "${result}|0|${rate_h}" >> "$output_file"

        if [ "$code" = "429" ]; then
            err "  #${i} → 429 RATE LIMITED"
            count_429=$((count_429 + 1))
        elif [ "$code" = "200" ] || [ "$code" = "201" ]; then
            count_ok=$((count_ok + 1))
        else
            warn "  #${i} → ${code}"
            count_err=$((count_err + 1))
        fi
    done

    rm -rf "$tmp_dir"
    log "  Résultats: ${count_ok} OK, ${count_429} rate-limited, ${count_err} erreurs"
    echo ""
}

# =============================================================================
# TESTS
# =============================================================================

echo ""
echo "============================================="
echo "  Rate Limiting Test — Lexis 360 Intelligence"
echo "============================================="
echo "  Date: $(date)"
echo "  Résultats: ${RESULTS_DIR}/"
echo ""

# --- Test 0: Vérification du token ---
log "Vérification du token..."
check_code=$(send_request "GET" "/api/user/whoami" "" "auth_check" "${RESULTS_DIR}/auth_check.csv")
if [ "$check_code" != "200" ]; then
    err "Token invalide (HTTP ${check_code}). Exporter LEX_TOKEN avec un token valide."
    exit 1
fi
ok "Token valide"
echo ""

# --- Test 1: Rafale sur /whoami (GET léger) ---
burst_test_sequential "whoami_burst" "GET" "/api/user/whoami" "" 30 0

# --- Test 2: Rafale sur /suggest (GET avec paramètre) ---
burst_test_sequential "suggest_burst" "GET" "/api/recherche/suggest?t=licenciement" "" 30 0

# --- Test 3: Rafale sur /search (POST lourd) ---
SEARCH_BODY='{"q":"licenciement abusif","project":"all","highlight":true,"offset":0,"size":10,"from":"0","to":"1776592724072","filters":[],"sorts":[{"field":"SCORE","order":"DESC"}],"aggregations":["TYPEDOC"],"relevanceProfile":null,"combining":null,"fields":null}'
burst_test_sequential "search_burst" "POST" "/api/recherche//search" "$SEARCH_BODY" 20 0

# --- Test 4: Rafale sur /aggregate (POST moyen) ---
AGG_BODY='{"q":"contrat de travail","project":"all","highlight":false,"offset":0,"size":0,"from":"0","to":"1776592724072","filters":[],"sorts":[],"aggregations":["TYPEDOC","ANNEE"],"relevanceProfile":null,"combining":null,"fields":null}'
burst_test_sequential "aggregate_burst" "POST" "/api/recherche//aggregate" "$AGG_BODY" 20 0

# --- Test 5: Rafale sur /metadata (GET document) ---
burst_test_sequential "metadata_burst" "GET" "/api/document/metadata/JP_KODCASS-0519779_0KRH" "" 20 0

# --- Test 6: Requêtes parallèles sur /search ---
burst_test_parallel "search_parallel_10" "POST" "/api/recherche//search" "$SEARCH_BODY" 10

# --- Test 7: Requêtes parallèles sur /search (plus agressif) ---
burst_test_parallel "search_parallel_30" "POST" "/api/recherche//search" "$SEARCH_BODY" 30

# --- Test 8: Rafale rapide puis attente, puis reprise ---
log "━━━ Test: récupération après rafale ━━━"
burst_test_sequential "recovery_phase1" "POST" "/api/recherche//search" "$SEARCH_BODY" 15 0
log "  Pause de 10 secondes..."
sleep 10
burst_test_sequential "recovery_phase2" "POST" "/api/recherche//search" "$SEARCH_BODY" 15 0

# --- Test 9: Montée en charge progressive ---
log "━━━ Test: montée en charge progressive ━━━"
for rate in 1 0.5 0.2 0.1 0; do
    burst_test_sequential "progressive_${rate}s" "POST" "/api/recherche//search" "$SEARCH_BODY" 10 "$rate"
done

# =============================================================================
# Rapport final
# =============================================================================
echo ""
echo "============================================="
echo "  RAPPORT FINAL"
echo "============================================="
echo ""

total_429=$(cat "${RESULTS_DIR}"/*.csv | grep -c "^429" || true)
total_requests=$(cat "${RESULTS_DIR}"/*.csv | grep -v "^http_code" | wc -l | tr -d ' ')

if [ "$total_429" -gt 0 ]; then
    err "Rate limiting DÉTECTÉ: ${total_429}/${total_requests} requêtes ont reçu un 429"
else
    ok "Aucun rate limiting détecté sur ${total_requests} requêtes"
fi

# Vérifier si des headers de rate-limit existent
all_headers=$(cat "${RESULTS_DIR}"/*.csv | cut -d'|' -f5 | grep -v "^$" | grep -v "rate_headers" | sort -u || true)
if [ -n "$all_headers" ]; then
    warn "Headers de rate-limit trouvés:"
    echo "$all_headers" | while read -r h; do
        warn "  → $h"
    done
else
    log "Aucun header de rate-limit dans les réponses"
fi

echo ""
log "Résultats détaillés dans: ${RESULTS_DIR}/"
log "Pour analyser: cat ${RESULTS_DIR}/*.csv"
echo ""
