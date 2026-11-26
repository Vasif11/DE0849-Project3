#!/usr/bin/env bash
# Phases 2-5 bring-up with evidence: RIC -> gNB (E2/N2/F1) -> srsUE (ZeroMQ), verbose logs to stdout.
# Needs a persistent WSL session (see README, "Environment pitfalls"). Evidence: results/phase2..5.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
mkdir -p results/phase2 results/phase3 results/phase4 results/phase5 /tmp/vb
docker rm -f project3-ue project3-gnb project3-flexric project3-dn-iperf3 >/dev/null 2>&1
docker compose down >/dev/null 2>&1

echo "# Phase 2/3 - RAN network, FlexRIC ($(date -Is))" | tee results/phase2/ran_network.txt >/dev/null
docker compose up -d flexric dn-iperf3 >/dev/null 2>&1; sleep 6
{
  docker network inspect project3-ric-lab_ran-net -f 'network {{.Name}} subnet {{range .IPAM.Config}}{{.Subnet}}{{end}}'
  for c in project3-flexric project3-dn-iperf3; do
    echo "$c: $(docker inspect -f '{{.State.Status}} {{range $k,$v := .NetworkSettings.Networks}}{{$k}}={{$v.IPAddress}} {{end}}' $c)"
  done
  echo "images: $(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E 'flexric|ocudu|srsran-ue' | tr '\n' ' ')"
} >> results/phase2/ran_network.txt

{
  echo "# Phase 3 - FlexRIC Near-RT RIC ($(date -Is))"
  echo "FlexRIC commit: $(docker run --rm --entrypoint sh telecom-lab-flexric:1.0 -c 'cd /opt/flexric && git rev-parse HEAD')"
  echo "config:"; grep -v '^#' configs/flexric.conf | grep -v '^$'
  echo "--- RIC log"; docker logs project3-flexric 2>&1
  echo "--- listening sockets"; docker exec project3-flexric sh -c 'ss -anp 2>/dev/null | grep -E "36421|36422"'
} > results/phase3/flexric.txt

# verbose copies of the gNB/UE configs that log to stdout (so docker logs shows live events)
sed -e 's/all_level: warning/all_level: info/' -e 's#filename: /tmp/gnb.log#filename: stdout#' configs/gnb_zmq.yaml > /tmp/vb/gnb.yaml
sed -e 's/all_level = warning/all_level = info/' -e 's#filename = /tmp/ue.log#filename = stdout#' configs/ue_zmq.conf > /tmp/vb/ue.conf
docker run -d --name project3-gnb -t --cap-add SYS_NICE --network project3-ric-lab_ran-net --ip 10.20.11.10 \
  -v /tmp/vb/gnb.yaml:/config/gnb_zmq.yaml:ro --entrypoint gnb aetherproject/ocudu:rel-0.7.0 -c /config/gnb_zmq.yaml >/dev/null
docker network connect --ip 10.20.2.11 scenario-b-n2 project3-gnb
docker network connect --ip 10.20.3.11 scenario-b-n3 project3-gnb
sleep 20
docker run -d --name project3-ue -t --privileged --network project3-ric-lab_ran-net --ip 10.20.11.20 \
  -v /tmp/vb/ue.conf:/config/ue_zmq.conf:ro --entrypoint /bin/bash aetherproject/srsran-ue:rel-0.7.0 \
  -c 'ip netns add ue1 2>/dev/null; exec srsue /config/ue_zmq.conf' >/dev/null
sleep 80

BR="br-$(docker network inspect project3-ric-lab_ran-net -f '{{.Id}}' | cut -c1-12)"
timeout 5 tcpdump -i "$BR" -nn -q 'tcp port 2000 or tcp port 2001' -w /tmp/zmq_probe.pcap >/dev/null 2>&1
ZMQ_PKTS=$(tcpdump -nn -r /tmp/zmq_probe.pcap 2>/dev/null | wc -l)

{
  echo "# Phase 4 - OCUDU gNB ($(date -Is))"
  echo "gNB version: $(docker run --rm --entrypoint gnb aetherproject/ocudu:rel-0.7.0 --version 2>&1 | grep -E 'version')"
  echo "gnb command (image provides the binary 'gnb'; the guidebook calls it ocudu-gnb): gnb -c /config/gnb_zmq.yaml"
  echo "interfaces: $(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}={{$v.IPAddress}} {{end}}' project3-gnb)"
  echo "--- gNB log (non-JSON lines)"; docker logs project3-gnb 2>&1 | grep -aE '^20[0-9]{2}-|^N2|^Cell|^Lower|^Available' | cut -c1-210 | grep -avE 'Logical|CONFIG'
  echo "--- AMF view of the gNB"; docker logs scenario-b-amf 2>&1 | grep -aE 'gNB-N2 accepted|Number of gNBs' | tail -2 | sed 's/\x1b\[[0-9;]*m//g' | cut -c1-200
  echo "--- SCTP associations seen by gNB (N2) / FlexRIC (E2)"
  docker exec project3-gnb sh -c 'cat /proc/net/sctp/assocs | cut -c1-130'
  echo "RIC:"; docker exec project3-flexric sh -c 'cat /proc/net/sctp/assocs | cut -c1-130'
} > results/phase4/gnb_bringup.txt

{
  echo "# Phase 5 - srsUE over ZeroMQ ($(date -Is))"
  echo "--- UE log"; docker logs project3-ue 2>&1 | grep -avE 'Skipping|plugins' | cut -c1-200
  echo "--- ZeroMQ TCP links (gNB tx 2000 <- UE rx, UE tx 2001 <- gNB rx)"
  /opt/p1venv/bin/python - <<'PY'
import subprocess
ST={"01":"ESTABLISHED","0A":"LISTEN","02":"SYN_SENT"}
def a(h):
    ip,p=h.split(":"); return ".".join(str(x) for x in bytes.fromhex(ip)[::-1])+":"+str(int(p,16))
for c in ("project3-gnb","project3-ue"):
    out=subprocess.run(["docker","exec",c,"cat","/proc/net/tcp"],capture_output=True,text=True).stdout
    for l in out.splitlines()[1:]:
        p=l.split(); la,ra=a(p[1]),a(p[2])
        if any(x in la+ra for x in (":2000",":2001")): print(f"  {c}: {la} -> {ra} {ST.get(p[3],p[3])}")
PY
  echo "ZeroMQ packets observed on the RAN bridge in 5 s: $ZMQ_PKTS"
  echo "UE IP address in netns ue1: $(docker exec project3-ue ip netns exec ue1 ip -4 -br addr 2>/dev/null | grep tun_srsue || echo 'none (UE not attached)')"
} > results/phase5/ue_attach.txt

echo "ZMQ packets: $ZMQ_PKTS"; cat results/phase5/ue_attach.txt | tail -12
docker rm -f project3-ue project3-gnb project3-flexric project3-dn-iperf3 >/dev/null 2>&1
