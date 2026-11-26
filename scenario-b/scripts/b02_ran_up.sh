#!/usr/bin/env bash
# Phases 2-5 - deploy RAN network + FlexRIC, OCUDU gNB (E2 setup), srsUE (attach, PDU session).
# Evidence: results/phase2..phase5/*.txt
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p results/phase2 results/phase3 results/phase4 results/phase5 results/logs
say() { echo "$*"; }

say "### Phase 2/3: RAN network, FlexRIC Near-RT RIC"
docker compose up -d --build flexric dn-iperf3 2>&1 | tail -3
sleep 6
{
  echo "# Phase 2 - Project 3 RAN network and containers ($(date -Is))"
  docker network inspect project3-ric-lab_ran-net -f 'network {{.Name}} subnet {{range .IPAM.Config}}{{.Subnet}}{{end}}'
  for c in project3-flexric project3-dn-iperf3; do
    echo "$c: $(docker inspect -f '{{.State.Status}} {{range $k,$v := .NetworkSettings.Networks}}{{$k}}={{$v.IPAddress}} {{end}}' $c)"
  done
} | tee results/phase2/ran_network.txt

{
  echo "# Phase 3 - FlexRIC ($(date -Is))"
  echo "config:"; cat configs/flexric.conf | grep -v '^#' | grep -v '^$'
  echo "--- RIC log"; docker logs project3-flexric 2>&1 | head -30
  echo "--- sockets (SCTP E2 36421 / E42 36422)"
  docker exec project3-flexric sh -c 'ss -anp 2>/dev/null | grep -E "36421|36422"; cat /proc/net/sctp/eps 2>/dev/null | head -5'
} | tee results/phase3/flexric.txt

say "### Phase 4: OCUDU gNB"
docker compose up -d gnb 2>&1 | tail -2
sleep 25
{
  echo "# Phase 4 - OCUDU gNB ($(date -Is))"
  docker inspect -f '{{.State.Status}} {{range $k,$v := .NetworkSettings.Networks}}{{$k}}={{$v.IPAddress}} {{end}}' project3-gnb
  echo "--- gNB log"; docker logs project3-gnb 2>&1 | tail -40
  echo "--- RIC log (E2 setup)"; docker logs project3-flexric 2>&1 | tail -25
} | tee results/phase4/gnb_e2_setup.txt
