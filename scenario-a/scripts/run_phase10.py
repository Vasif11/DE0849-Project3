#!/usr/bin/env python3
"""Phase 10 - traffic classification and SDN policy control, evaluated experimentally.

Part A  classification accuracy: four controlled traffic classes with known ground truth
        (tcp_bulk, tcp_light, udp_high_rate, udp_low_rate), each run alone, POLICY=off.
Part B  policy evaluation: TCP h1->h4 competes with an 80 Mbit/s UDP flow h2->h3 on the shared
        100 Mbit/s path, once with POLICY=off (control) and once with POLICY=on (UDP capped by an
        OpenFlow meter once the controller has classified it as udp_high_rate).

Evidence (results/phase10): controller CLASSIFY/POLICY logs, flow tables, meter statistics,
per-second throughput time series, iperf3 JSON, ping RTT under load, bounded PCAP samples.
"""
import csv
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "topology"))
from scenario_a_topo import build_net, start_net, warm_up  # noqa: E402
from mininet.log import setLogLevel  # noqa: E402

OUT = os.path.join(ROOT, "results", "phase10")
CTRL = "scenario-a-osken-p10"
REPS_B = int(os.environ.get("P10_REPS", "3"))
UDP_RATE = int(os.environ.get("P10_UDP_MBPS", "80"))


def sh(cmd, timeout=120):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout).stdout


def start_controller(policy_on, extra_env=""):
    sh("docker rm -f scenario-a-osken scenario-a-osken-p10 >/dev/null 2>&1")
    sh(f"docker run -d --name {CTRL} --network host -e POLICY={'on' if policy_on else 'off'} "
       f"-e PYTHONPATH=/app {extra_env} -v {ROOT}/controller:/app:ro telecom-lab-osken:1.0 "
       f"osken-manager --ofp-tcp-listen-port 6633 --verbose /app/classifier_policy.py")
    for _ in range(30):
        if ":6633" in sh("ss -ltn"):
            break
        time.sleep(1)
    time.sleep(2)


def ctrl_lines(since, tag):
    log = sh(f"docker logs --since {int(since)} {CTRL} 2>&1")
    out = []
    for line in log.splitlines():
        m = re.search(tag + r" (\{.*\})", line)
        if m:
            out.append(json.loads(m.group(1)))
    return out


def jload(path):
    t = open(path).read()
    return json.loads(t[t.index("{"):])


def ping_rtt(text):
    m = re.search(r"rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)", text)
    return dict(zip(("min", "avg", "max", "mdev"), map(float, m.groups()))) if m else None


# ------------------------------------------------------------------------------ Part A
CLASS_PLAN = [  # name, src, dst, dst_ip, port, proto, args, true_class
    ("tcp_bulk", "h1", "h4", "10.0.0.4", 5201, "tcp", "", "tcp_bulk"),
    ("tcp_light", "h2", "h3", "10.0.0.3", 5202, "tcp", "-b 2M", "tcp_light"),
    ("udp_high", "h1", "h4", "10.0.0.4", 5203, "udp", "-b 40M", "udp_high_rate"),
    ("udp_low", "h2", "h3", "10.0.0.3", 5204, "udp", "-b 3M", "udp_low_rate"),
]


def part_a(net):
    d = os.path.join(OUT, "classification")
    os.makedirs(d, exist_ok=True)
    rows = []
    for rep in (1, 2):
        for name, src, dst, dip, port, proto, args, truth in CLASS_PLAN:
            t0 = time.time()
            hs, hd = net.get(src), net.get(dst)
            hd.cmd(f"iperf3 -s -1 -p {port} >/dev/null 2>&1 &")
            time.sleep(0.8)
            u = "-u" if proto == "udp" else ""
            out = hs.cmd(f"iperf3 -c {dip} -p {port} {u} {args} -t 10 -J")
            time.sleep(2.5)           # let the last stats poll and class commit happen
            cj = out[out.index("{"):]
            cl = json.loads(cj)
            lport = cl["start"]["connected"][0]["local_port"]
            flow = f"{proto} {hs.IP()}:{lport}->{dip}:{port}"
            recs = [r for r in ctrl_lines(t0 - 1, "CLASSIFY") if r["flow"] == flow and r["dpid"].endswith("2")]
            pred = recs[-1]["cls"] if recs else "UNCLASSIFIED"
            first_cls = recs[0] if recs else None
            rows.append(dict(run=f"{name}_rep{rep}", flow=flow, true_class=truth, predicted=pred,
                             correct=pred == truth, rate_mbps_at_decision=first_cls["rate_mbps"] if first_cls else "",
                             avg_pkt_bytes=first_cls["avg_pkt_bytes"] if first_cls else "",
                             decision_flow_age_s=first_cls["flow_age_s"] if first_cls else "",
                             n_decisions=len(recs)))
            with open(os.path.join(d, f"{name}_rep{rep}.json"), "w") as f:
                json.dump(dict(plan=dict(name=name, src=src, dst=dst, port=port, proto=proto, args=args,
                                         true_class=truth), flow=flow, decisions=recs), f, indent=1)
    with open(os.path.join(d, "classification_results.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    classes = ["tcp_bulk", "tcp_light", "udp_high_rate", "udp_low_rate", "UNCLASSIFIED"]
    cm = {t: {p: 0 for p in classes} for t in classes[:4]}
    for r in rows:
        cm[r["true_class"]][r["predicted"]] += 1
    acc = sum(r["correct"] for r in rows) / len(rows)
    with open(os.path.join(d, "confusion_matrix.json"), "w") as f:
        json.dump(dict(confusion=cm, accuracy=acc, n=len(rows)), f, indent=1)
    print("classification accuracy:", acc, cm)
    return acc


# ------------------------------------------------------------------------------ Part B
def pcap_bins(pcap, port, t0=None):
    rows = sh(f"tshark -r {pcap} -Y 'udp.dstport=={port}' -T fields -e frame.time_epoch -e frame.len 2>/dev/null",
              timeout=300).splitlines()
    ts = [(float(a), int(b)) for a, b in (r.split("\t") for r in rows if "\t" in r)]
    if not ts:
        return []
    base = ts[0][0] if t0 is None else t0
    bins = {}
    for t, ln in ts:
        bins[int(t - base)] = bins.get(int(t - base), 0) + ln * 8
    return [(s, bins.get(s, 0) / 1e6) for s in range(0, max(bins) + 1)]


def contention_run(net, label, policy_on, rep):
    d = os.path.join(OUT, "policy_" + ("on" if policy_on else "off"), f"run{rep}")
    os.makedirs(d, exist_ok=True)
    h1, h2, h3, h4 = (net.get(x) for x in ("h1", "h2", "h3", "h4"))
    TCP_T, UDP_T, UDP_START = 20, 14, 4
    t_ref = time.time()
    h4.cmd(f"iperf3 -s -1 -p 5201 >/dev/null 2>&1 &")
    h3.cmd(f"iperf3 -s -1 -p 5202 >/dev/null 2>&1 &")
    time.sleep(1)
    cap = f"/tmp/p10_{label}_{rep}.pcap"
    capp = h3.popen(f"tcpdump -i h3-eth0 -n -s 96 -w {cap} 'udp and dst port 5202'", shell=True)
    time.sleep(1)
    start = time.time()
    h1.cmd(f"iperf3 -c 10.0.0.4 -p 5201 -t {TCP_T} -i 1 -J > {d}/tcp_client.json 2>&1 &")
    h2.cmd(f"(sleep {UDP_START}; iperf3 -c 10.0.0.3 -p 5202 -u -b {UDP_RATE}M -t {UDP_T} -i 1 -J > {d}/udp_client.json 2>&1) &")
    h1.cmd(f"(sleep {UDP_START + 1}; ping -c {UDP_T - 2} -i 1 10.0.0.4 > {d}/ping_under_load.txt 2>&1) &")
    time.sleep(UDP_START + UDP_T + 1)
    mid_flows = {s: sh(f"ovs-ofctl -O OpenFlow13 dump-flows {s}") for s in ("s1", "s2", "s3")}
    mid_meters = {s: sh(f"ovs-ofctl -O OpenFlow13 meter-stats {s}") for s in ("s1", "s2", "s3")}
    time.sleep(max(0, TCP_T - (UDP_START + UDP_T + 1)) + 3)
    h1.cmd("wait"); h2.cmd("wait")
    capp.terminate(); time.sleep(1)
    for s in mid_flows:
        open(f"{d}/flows_{s}.txt", "w").write(mid_flows[s])
        open(f"{d}/meter_stats_{s}.txt", "w").write(mid_meters[s])
    tcp = jload(f"{d}/tcp_client.json")
    udp = jload(f"{d}/udp_client.json")
    tcp_series = [(int(i["sum"]["start"]), i["sum"]["bits_per_second"] / 1e6) for i in tcp["intervals"]]
    udp_series = pcap_bins(cap, 5202, t0=start + UDP_START)
    # align: UDP bins are relative to UDP start; shift by UDP_START to the TCP clock
    rows = []
    for s in range(0, TCP_T):
        u = next((v for k, v in udp_series if k + UDP_START == s), 0.0)
        t_ = next((v for k, v in tcp_series if k == s), 0.0)
        rows.append(dict(second=s, tcp_mbps=round(t_, 2), udp_delivered_mbps=round(u, 2)))
    with open(f"{d}/timeseries.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["second", "tcp_mbps", "udp_delivered_mbps"])
        w.writeheader(); w.writerows(rows)
    sh(f"tshark -r {cap} -c 20000 -w {d}/udp_sample_h3.pcap 2>/dev/null")
    os.remove(cap)

    ping = ping_rtt(open(f"{d}/ping_under_load.txt").read())
    pre = [r["tcp_mbps"] for r in rows if r["second"] < UDP_START and r["second"] >= 1]
    ov_early = [r for r in rows if UDP_START <= r["second"] < UDP_START + 4]
    ov_late = [r for r in rows if UDP_START + 5 <= r["second"] < UDP_START + UDP_T]
    mean = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
    e = udp["end"]["sum"]
    summary = dict(label=label, rep=rep, policy="ON" if policy_on else "OFF",
                   tcp_alone_mbps=mean(pre),
                   tcp_overlap_first4s_mbps=mean([r["tcp_mbps"] for r in ov_early]),
                   tcp_overlap_steady_mbps=mean([r["tcp_mbps"] for r in ov_late]),
                   udp_delivered_first4s_mbps=mean([r["udp_delivered_mbps"] for r in ov_early]),
                   udp_delivered_steady_mbps=mean([r["udp_delivered_mbps"] for r in ov_late]),
                   udp_offered_mbps=UDP_RATE, udp_sender_lost_percent=round(e.get("lost_percent", 0), 2),
                   tcp_retransmits=tcp["end"]["sum_sent"].get("retransmits"),
                   tcp_avg_receiver_mbps=round(tcp["end"]["sum_received"]["bits_per_second"] / 1e6, 2),
                   ping_avg_ms=ping["avg"] if ping else None, ping_max_ms=ping["max"] if ping else None,
                   ping_mdev_ms=ping["mdev"] if ping else None)
    json.dump(summary, open(f"{d}/summary.json", "w"), indent=1)
    print(label, rep, summary)
    return summary, d


def main():
    setLogLevel("warning")
    sh("mn -c >/dev/null 2>&1")
    os.makedirs(OUT, exist_ok=True)
    summaries = []

    # ---- Part A: classification (POLICY=off)
    start_controller(False)
    net = build_net()
    assert start_net(net)
    try:
        assert warm_up(net), "MAC-learning warm-up incomplete"
        part_a(net)
    finally:
        net.stop(); sh("mn -c >/dev/null 2>&1")

    # ---- Part B: control (off) then policy (on)
    for policy_on in (False, True):
        t_start = time.time()
        start_controller(policy_on)
        net = build_net()
        assert start_net(net)
        try:
            assert warm_up(net), "MAC-learning warm-up incomplete"
            for rep in range(1, REPS_B + 1):
                # restart the controller state per repetition so classification starts fresh
                s, d = contention_run(net, "policy_on" if policy_on else "policy_off", policy_on, rep)
                summaries.append(s)
                if rep == 1:
                    for kind in ("CLASSIFY", "POLICY"):
                        recs = ctrl_lines(t_start, kind)
                        json.dump(recs, open(os.path.join(d, f"controller_{kind.lower()}.json"), "w"), indent=1)
                time.sleep(3)
        finally:
            net.stop(); sh("mn -c >/dev/null 2>&1")
    keys = list(summaries[0])
    with open(os.path.join(OUT, "policy_comparison.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader(); w.writerows(summaries)
    sh("docker rm -f scenario-a-osken-p10 >/dev/null 2>&1")
    sh(f"cd {ROOT} && docker compose up -d >/dev/null 2>&1")   # restore the reference controller
    print("PHASE 10 DONE")


if __name__ == "__main__":
    main()
