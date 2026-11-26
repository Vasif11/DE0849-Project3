#!/usr/bin/env bash
# Phase 1 - start and verify the Project 2 Open5GS 5G SA core (core network functions only).
# The Project 2 gNB/UE containers are NOT started: the OCUDU gNB and srsUE replace them.
# Evidence: results/phase1/core_verification.txt
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
P2="${PROJECT2_DEPLOY:-$ROOT/../../DE0849-Project2/deploy}"
OUT="$ROOT/results/phase1"; mkdir -p "$OUT"
E="$OUT/core_verification.txt"; : > "$E"
say() { echo "$*" | tee -a "$E"; }

say "# Phase 1 - Project 2 5G core ($(date -Is))"
docker compose -f "$P2/docker-compose.5g.yml" up -d mongodb nrf scp ausf udm udr pcf nssf bsf amf smf upf 2>&1 | tail -3
sleep 20

say ""; say "## core network functions"
for c in amf smf upf nrf scp ausf udm udr pcf nssf bsf mongodb; do
  say "scenario-b-$c: $(docker inspect -f '{{.State.Status}}' scenario-b-$c 2>&1)"
done

say ""; say "## networks (expected N2 10.20.2.0/24, N3 10.20.3.0/24, N4 10.20.5.0/24, SBI 10.20.4.0/24, N6 10.20.6.0/24)"
for n in n2 n3 n4 sbi dn; do
  say "scenario-b-$n: $(docker network inspect scenario-b-$n -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>&1)"
done

say ""; say "## interface addresses"
say "AMF N2: $(docker inspect -f '{{(index .NetworkSettings.Networks "scenario-b-n2").IPAddress}}' scenario-b-amf)"
say "UPF N3: $(docker inspect -f '{{(index .NetworkSettings.Networks "scenario-b-n3").IPAddress}}' scenario-b-upf)"
say "SMF N4: $(docker inspect -f '{{(index .NetworkSettings.Networks "scenario-b-n4").IPAddress}}' scenario-b-smf)   UPF N4: $(docker inspect -f '{{(index .NetworkSettings.Networks "scenario-b-n4").IPAddress}}' scenario-b-upf)"
say "UPF N6: $(docker inspect -f '{{(index .NetworkSettings.Networks "scenario-b-dn").IPAddress}}' scenario-b-upf)"

say ""; say "## subscriber database (IMSI used by srsUE: 001010000000001, DNN internet)"
docker exec scenario-b-mongodb mongosh --quiet open5gs --eval \
  'db.subscribers.find({imsi:"001010000000001"},{imsi:1,"slice.session.name":1,_id:0}).forEach(printjson)' 2>&1 | tee -a "$E"
N=$(docker exec scenario-b-mongodb mongosh --quiet open5gs --eval 'db.subscribers.countDocuments({imsi:"001010000000001"})' 2>/dev/null)
if [ "${N:-0}" = "0" ]; then
  say "subscriber missing -> provisioning with add_subscriber.js"
  docker exec scenario-b-mongodb mongosh --quiet open5gs /scripts/add_subscriber.js 2>&1 | tail -2 | tee -a "$E"
fi

say ""; say "## AMF NGAP listener"
docker logs scenario-b-amf 2>&1 | grep -iE 'ngap.*listen|sctp' | tail -2 | tee -a "$E"
