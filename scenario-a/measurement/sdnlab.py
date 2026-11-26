"""Scenario A measurement framework (Phases 7-9).

run_experiment()  - one controlled experiment: before/after OpenFlow snapshots (tightly
                    timestamped), iperf3 TCP/UDP h1->h4, optional bounded PCAP on h1.
analyze()         - Phase 9: parse an experiment directory, compute packet/byte deltas,
                    verify inter-switch counter consistency, parse iperf3 + PCAP, write
                    analysis.json / analysis.csv / report.md.
"""
import csv
import json
import os
import re
import shutil
import subprocess
import time

H4_MAC = "00:00:00:00:00:04"
SRC, DST = "h1", "h4"
DST_IP = "10.0.0.4"
IPERF_PORT = 5201
# reference path h1-s1-s2-s3-h4 : (switch, in_port, out_port)
PATH = [("s1", 1, 3), ("s2", 1, 2), ("s3", 3, 2)]
# inter-switch links as (switch_a, port_a, switch_b, port_b)
ISL = [("s1", 3, "s2", 1), ("s2", 2, "s3", 3)]
# ingress ports whose dl_dst=h4 rules feed the path (h1 and h2 both enter s2 through s1)
PATH_INGRESS = {"s1": [1, 2], "s2": [1], "s3": [3]}


def sh(cmd, timeout=120):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout).stdout


# ----------------------------------------------------------------------------- snapshots
def snapshot(outdir, tag):
    """Record flow tables and port counters of s1..s3 with a tight epoch window."""
    t0 = time.time()
    flows = {s: sh(f"ovs-ofctl -O OpenFlow13 dump-flows {s}") for s in ("s1", "s2", "s3")}
    ports = {s: sh(f"ovs-ofctl -O OpenFlow13 dump-ports {s}") for s in ("s1", "s2", "s3")}
    t1 = time.time()
    for s in flows:
        with open(os.path.join(outdir, f"flows_{tag}_{s}.txt"), "w") as f:
            f.write(flows[s])
        with open(os.path.join(outdir, f"ports_{tag}_{s}.txt"), "w") as f:
            f.write(ports[s])
    return {"start": t0, "end": t1, "mid": (t0 + t1) / 2}


def _signature(outdir, tag):
    """All dl_dst=h4 flow counters + all port counters of s1..s3 from one snapshot."""
    sig = []
    for s in ("s1", "s2", "s3"):
        fl = parse_flows(open(os.path.join(outdir, f"flows_{tag}_{s}.txt")).read())
        sig.append(tuple(sorted((f["in_port"], f["packets"], f["bytes"]) for f in fl if f["dl_dst"] == H4_MAC)))
        pr = parse_ports(open(os.path.join(outdir, f"ports_{tag}_{s}.txt")).read())
        sig.append(tuple(sorted((p, v.get("rx_pkts"), v.get("tx_pkts")) for p, v in pr.items())))
    return tuple(sig)


def stable_snapshot(outdir, tag, poll_s=0.25, max_reads=16):
    """OVS refreshes OpenFlow flow counters from the datapath with a delay (revalidator), so a single
    read can lag by a few packets and the lag differs between switches. Re-read until two consecutive
    snapshots are identical.  Returns the timestamps of the FIRST snapshot that showed the final
    values (t_final) and of the last one (t_last): 'after' uses t_final (end of activity), 'before'
    uses t_last (just before traffic starts)."""
    prev, t_final, snap = None, None, None
    for _ in range(max_reads):
        snap = snapshot(outdir, tag)
        sig = _signature(outdir, tag)
        if sig == prev:
            break
        prev, t_final = sig, snap
        time.sleep(poll_s)
    return dict(start=t_final["start"], end=t_final["end"], mid=t_final["mid"], last_mid=snap["mid"],
                reads_to_stabilise=_ + 1)


# ----------------------------------------------------------------------------- experiment
def run_experiment(net, outroot, name, proto, rate_mbps=None, duration=10, capture=False,
                   cap_packets=25000, parallel=1, repeat=1):
    outdir = os.path.join(outroot, name)
    os.makedirs(outdir, exist_ok=True)
    h1, h4 = net.get(SRC), net.get(DST)
    params = dict(name=name, proto=proto, offered_mbps=rate_mbps, duration_s=duration,
                  src=SRC, dst=DST, dst_ip=DST_IP, dst_mac=H4_MAC, port=IPERF_PORT,
                  capture=capture, capture_packet_limit=cap_packets if capture else None,
                  parallel=parallel, repeat=repeat, started=time.strftime("%Y-%m-%dT%H:%M:%S"))

    # make sure MAC-learning state exists for h1<->h4 before the measured window
    rtt = h1.cmd(f"ping -c 5 -i 0.2 {DST_IP}")
    params["pre_ping_rtt"] = (re.search(r"rtt .* = ([\d./]+) ms", rtt) or [None, None])[1]

    h4.cmd("pkill -f 'iperf3 -s' ; true")
    srv_json = os.path.join(outdir, "iperf3_server.json")
    h4.cmd(f"iperf3 -s -1 -J --logfile {srv_json} &")
    time.sleep(1.0)

    cap_tmp = f"/tmp/p3cap_{name}.pcap"
    cap_proc = None
    if capture:
        # bounded capture on h1: UDP flow filter + finite packet count + short snaplen
        flt = f"udp and dst host {DST_IP} and dst port {IPERF_PORT}"
        cap_proc = h1.popen(f"tcpdump -i {SRC}-eth0 -n -s 96 -c {cap_packets} -w {cap_tmp} '{flt}'",
                            shell=True)
        time.sleep(1.0)

    before = stable_snapshot(outdir, "before")
    before["mid"] = before["last_mid"]          # counters are valid until traffic starts
    t_start = time.time()
    if proto == "udp":
        cmd = f"iperf3 -c {DST_IP} -u -b {rate_mbps}M -t {duration} -J"
    else:
        cmd = f"iperf3 -c {DST_IP} -t {duration} -P {parallel} -J"
        if rate_mbps:
            cmd += f" -b {rate_mbps}M"
    out = h1.cmd(cmd)
    t_end = time.time()
    after = stable_snapshot(outdir, "after")    # mid = first snapshot that showed the final counters

    with open(os.path.join(outdir, "iperf3_client.json"), "w") as f:
        f.write(out)
    if cap_proc is not None:
        try:
            cap_proc.wait(timeout=15)
        except Exception:
            cap_proc.terminate()
        if os.path.exists(cap_tmp):
            shutil.copy(cap_tmp, os.path.join(outdir, "capture_h1.pcap"))
            os.remove(cap_tmp)
    h4.cmd("pkill -f 'iperf3 -s' ; true")

    params.update(snapshot_before=before, snapshot_after=after,
                  iperf_window={"start": t_start, "end": t_end, "wall_s": round(t_end - t_start, 3)},
                  observation_interval_s=round(after["mid"] - before["mid"], 3))
    with open(os.path.join(outdir, "params.json"), "w") as f:
        json.dump(params, f, indent=2)
    return outdir


# ----------------------------------------------------------------------------- parsing
FLOW_RE = re.compile(r"n_packets=(\d+), n_bytes=(\d+), priority=(\d+)(?:,([^ ]*))? actions=(.*)")


def parse_flows(text):
    flows = []
    for line in text.splitlines():
        m = FLOW_RE.search(line)
        if not m:
            continue
        pkts, byts, prio, match, actions = m.groups()
        kv = dict(p.split("=", 1) for p in (match or "").split(",") if "=" in p)
        flows.append(dict(packets=int(pkts), bytes=int(byts), priority=int(prio),
                          in_port=int(kv["in_port"]) if "in_port" in kv else None,
                          dl_dst=kv.get("dl_dst"), actions=actions.strip()))
    return flows


PORT_RX = re.compile(r"port\s+(\S+): rx pkts=(\d+), bytes=(\d+), drop=(\d+), errs=(\d+)")
PORT_TX = re.compile(r"tx pkts=(\d+), bytes=(\d+), drop=(\d+), errs=(\d+)")


def parse_ports(text):
    ports, cur = {}, None
    for line in text.splitlines():
        m = PORT_RX.search(line)
        if m:
            name = m.group(1)
            if not name.isdigit():
                cur = None
                continue
            cur = int(name)
            ports[cur] = dict(rx_pkts=int(m.group(2)), rx_bytes=int(m.group(3)),
                              rx_drop=int(m.group(4)), rx_errs=int(m.group(5)))
            continue
        m = PORT_TX.search(line)
        if m and cur is not None:
            ports[cur].update(tx_pkts=int(m.group(1)), tx_bytes=int(m.group(2)),
                              tx_drop=int(m.group(3)), tx_errs=int(m.group(4)))
    return ports


def find_flow(flows, in_port, dl_dst):
    for f in flows:
        if f["priority"] > 0 and f["in_port"] == in_port and f["dl_dst"] == dl_dst:
            return f
    return None


def parse_iperf(outdir):
    res = {}
    for role in ("client", "server"):
        p = os.path.join(outdir, f"iperf3_{role}.json")
        try:
            txt = open(p).read()
            res[role] = json.loads(txt[txt.index("{"):])
        except Exception:
            res[role] = None
    return res


def pcap_summary(pcap, params):
    if not os.path.exists(pcap):
        return None
    flt = f"udp && ip.dst=={params['dst_ip']} && udp.dstport=={params['port']}"
    rows = sh(f"tshark -r {pcap} -Y '{flt}' -T fields -e frame.time_epoch -e ip.src -e ip.dst "
              f"-e udp.dstport -e frame.len 2>/dev/null").splitlines()
    total = int(sh(f"tshark -r {pcap} 2>/dev/null | wc -l").strip() or 0)
    times, lens, srcs, dsts, dports = [], [], set(), set(), set()
    for r in rows:
        p = r.split("\t")
        if len(p) < 5:
            continue
        times.append(float(p[0])); srcs.add(p[1]); dsts.add(p[2]); dports.add(p[3]); lens.append(int(p[4]))
    gaps = [b - a for a, b in zip(times, times[1:])]
    return dict(file=os.path.basename(pcap), size_bytes=os.path.getsize(pcap),
                packets_in_file=total, packets_matching_udp_flow=len(times),
                src=sorted(srcs), dst=sorted(dsts), protocol="UDP", dst_ports=sorted(dports),
                frame_len_min=min(lens) if lens else None, frame_len_max=max(lens) if lens else None,
                frame_len_mean=round(sum(lens) / len(lens), 1) if lens else None,
                duration_s=round(times[-1] - times[0], 4) if len(times) > 1 else None,
                mean_interarrival_us=round(1e6 * sum(gaps) / len(gaps), 1) if gaps else None)


# ----------------------------------------------------------------------------- Phase 9 analysis
def analyze(outdir):
    params = json.load(open(os.path.join(outdir, "params.json")))
    interval = params["observation_interval_s"]
    a = {"name": params["name"], "proto": params["proto"], "offered_mbps": params["offered_mbps"],
         "duration_s": params["duration_s"], "observation_interval_s": interval}

    # --- flow counters on the reference path (aggregate destination-MAC rules)
    # Traffic to h4 enters s2 from s1 whichever host (h1 or h2) sent it, so the s1 figure compared
    # with s2/s3 is the sum over BOTH ingress rules; the h1-only rule is reported separately.
    flow_rows, consistent_pkts, consistent_bytes = [], set(), set()
    for sw, inp, outp in PATH:
        fb = parse_flows(open(os.path.join(outdir, f"flows_before_{sw}.txt")).read())
        fa = parse_flows(open(os.path.join(outdir, f"flows_after_{sw}.txt")).read())
        f_main = find_flow(fa, inp, H4_MAC)
        if f_main is None:
            flow_rows.append(dict(switch=sw, in_port=inp, out_port=outp, found=False))
            continue
        b_main = find_flow(fb, inp, H4_MAC)
        d_main_p = f_main["packets"] - (b_main["packets"] if b_main else 0)
        d_main_b = f_main["bytes"] - (b_main["bytes"] if b_main else 0)
        dp_tot, db_tot = 0, 0
        for ing in PATH_INGRESS[sw]:
            fx, bx = find_flow(fa, ing, H4_MAC), find_flow(fb, ing, H4_MAC)
            if fx:
                dp_tot += fx["packets"] - (bx["packets"] if bx else 0)
                db_tot += fx["bytes"] - (bx["bytes"] if bx else 0)
        consistent_pkts.add(dp_tot); consistent_bytes.add(db_tot)
        flow_rows.append(dict(switch=sw, in_port=inp, out_port=outp, found=True,
                              d_packets_rule=d_main_p, d_bytes_rule=d_main_b,
                              d_packets=dp_tot, d_bytes=db_tot,
                              extra_other_ingress_packets=dp_tot - d_main_p,
                              extra_other_ingress_bytes=db_tot - d_main_b,
                              rate_mbps=round(db_tot * 8 / interval / 1e6, 3),
                              action=f_main["actions"]))
    a["flow_deltas"] = flow_rows
    a["flow_counters_identical_across_switches"] = (len(consistent_pkts) == 1 and len(consistent_bytes) == 1
                                                    and all(r.get("found") for r in flow_rows))
    tot = [r["d_packets"] for r in flow_rows if r.get("found")]
    a["flow_packet_spread"] = (max(tot) - min(tot)) if tot else None
    a["flow_max_relative_spread_percent"] = round(100 * (max(tot) - min(tot)) / max(tot), 4) if tot and max(tot) else None
    a["snapshot_reads_to_stabilise"] = dict(before=params["snapshot_before"].get("reads_to_stabilise"),
                                            after=params["snapshot_after"].get("reads_to_stabilise"))

    # --- port counters + inter-switch consistency
    pb = {s: parse_ports(open(os.path.join(outdir, f"ports_before_{s}.txt")).read()) for s in ("s1", "s2", "s3")}
    pa = {s: parse_ports(open(os.path.join(outdir, f"ports_after_{s}.txt")).read()) for s in ("s1", "s2", "s3")}

    def d(sw, port, key):
        return pa[sw][port][key] - pb[sw][port][key]

    isl_rows = []
    for s1, p1, s2, p2 in ISL:
        for (tx_sw, tx_p, rx_sw, rx_p) in ((s1, p1, s2, p2), (s2, p2, s1, p1)):
            tp, tb = d(tx_sw, tx_p, "tx_pkts"), d(tx_sw, tx_p, "tx_bytes")
            rp, rb = d(rx_sw, rx_p, "rx_pkts"), d(rx_sw, rx_p, "rx_bytes")
            isl_rows.append(dict(link=f"{tx_sw}:{tx_p}->{rx_sw}:{rx_p}", tx_pkts=tp, rx_pkts=rp,
                                 tx_bytes=tb, rx_bytes=rb, match=(tp == rp and tb == rb)))
    a["inter_switch_ports"] = isl_rows
    a["inter_switch_counters_match"] = all(r["match"] for r in isl_rows)
    a["port_drops_errors"] = {s: sum(pa[s][p].get(k, 0) - pb[s][p].get(k, 0) for p in pa[s]
                                     for k in ("rx_drop", "tx_drop", "rx_errs", "tx_errs")) for s in pa}

    # --- iperf3 receiver-side
    ip = parse_iperf(outdir)
    if params["proto"] == "udp" and ip["server"]:
        # iperf3 3.20 reports bits_per_second=0 in the server's end.sum for UDP; the receiver rate
        # is in end.sum_received (loss/jitter/packets are identical in both blocks).
        s = ip["server"]["end"]["sum_received"]
        a["iperf"] = dict(receiver_mbps=round(s["bits_per_second"] / 1e6, 2), jitter_ms=round(s["jitter_ms"], 4),
                          lost_packets=s["lost_packets"], packets=s["packets"],
                          lost_percent=round(s["lost_percent"], 4))
    elif params["proto"] == "tcp" and ip["client"]:
        e = ip["client"]["end"]
        a["iperf"] = dict(receiver_mbps=round(e["sum_received"]["bits_per_second"] / 1e6, 2),
                          sender_mbps=round(e["sum_sent"]["bits_per_second"] / 1e6, 2),
                          retransmits=e["sum_sent"].get("retransmits"))
    else:
        a["iperf"] = None

    # --- PCAP
    pc = os.path.join(outdir, "capture_h1.pcap")
    a["pcap"] = pcap_summary(pc, params)

    # --- derived: flow-vs-UDP packet comparison (aggregate rule may count more than the UDP stream)
    if a["pcap"] and a["flow_deltas"] and a["flow_deltas"][0].get("found"):
        a["note_flow_vs_pcap"] = (
            f"flow rule (dl_dst={H4_MAC}) counted {a['flow_deltas'][0]['d_packets']} packets; the bounded capture "
            f"holds {a['pcap']['packets_matching_udp_flow']} UDP-flow packets (capture limit "
            f"{params['capture_packet_limit']}); the aggregate rule also counts the iperf3 TCP control "
            f"connection and any other frame to {H4_MAC}.")

    with open(os.path.join(outdir, "analysis.json"), "w") as f:
        json.dump(a, f, indent=2)
    _write_report(outdir, a)
    return a


def _write_report(outdir, a):
    L = [f"# Experiment {a['name']}", "",
         f"- protocol: **{a['proto'].upper()}**, offered load: **{a['offered_mbps']} Mbit/s**, "
         f"duration {a['duration_s']} s, observation interval (snapshot midpoints): {a['observation_interval_s']} s", ""]
    if a.get("iperf"):
        L += ["## iperf3 receiver-side result", "", "| metric | value |", "|---|---|"]
        L += [f"| {k} | {v} |" for k, v in a["iperf"].items()]
        L.append("")
    L += ["## OpenFlow flow-counter deltas (reference path, rules matching dl_dst=h4)", "",
          "| switch | in_port | out_port | Δpackets (path total) | Δbytes (path total) | Δpackets h1 rule only | other-ingress extra pkts | Δbytes/interval (Mbit/s) |",
          "|---|---|---|---|---|---|---|---|"]
    for r in a["flow_deltas"]:
        if r.get("found"):
            L.append(f"| {r['switch']} | {r['in_port']} | {r['out_port']} | {r['d_packets']} | {r['d_bytes']} | "
                     f"{r['d_packets_rule']} | {r['extra_other_ingress_packets']} | {r['rate_mbps']} |")
        else:
            L.append(f"| {r['switch']} | {r['in_port']} | {r['out_port']} | rule not found | | | | |")
    L += ["", f"Flow counters identical across s1, s2, s3: **{a['flow_counters_identical_across_switches']}** "
              f"(packet spread {a['flow_packet_spread']}, {a['flow_max_relative_spread_percent']} %; "
              f"snapshot re-reads until stable: {a['snapshot_reads_to_stabilise']})", "",
          "## Inter-switch port counters (tx at one end vs rx at the other)", "",
          "| link | tx pkts | rx pkts | tx bytes | rx bytes | match |", "|---|---|---|---|---|---|"]
    for r in a["inter_switch_ports"]:
        L.append(f"| {r['link']} | {r['tx_pkts']} | {r['rx_pkts']} | {r['tx_bytes']} | {r['rx_bytes']} | {r['match']} |")
    L += ["", f"All inter-switch counters match: **{a['inter_switch_counters_match']}**; "
              f"port drops/errors per switch: {a['port_drops_errors']}", ""]
    if a.get("pcap"):
        L += ["## PCAP summary (h1, bounded capture)", ""] + [f"- {k}: {v}" for k, v in a["pcap"].items()]
        L.append("")
    if a.get("note_flow_vs_pcap"):
        L += [f"> {a['note_flow_vs_pcap']}", ""]
    with open(os.path.join(outdir, "report.md"), "w") as f:
        f.write("\n".join(L) + "\n")


def append_summary_csv(csv_path, a):
    """One row per experiment in a shared CSV (the standard evidence format)."""
    new = not os.path.exists(csv_path)
    ip = a.get("iperf") or {}
    fd = (a["flow_deltas"] or [{}])[0]
    row = dict(experiment=a["name"], proto=a["proto"], offered_mbps=a["offered_mbps"],
               duration_s=a["duration_s"], observation_interval_s=a["observation_interval_s"],
               receiver_mbps=ip.get("receiver_mbps"), jitter_ms=ip.get("jitter_ms"),
               lost_packets=ip.get("lost_packets"), lost_percent=ip.get("lost_percent"),
               retransmits=ip.get("retransmits"),
               flow_d_packets=fd.get("d_packets"), flow_d_bytes=fd.get("d_bytes"),
               flow_rate_mbps=fd.get("rate_mbps"),
               flow_identical=a["flow_counters_identical_across_switches"],
               flow_spread_pkts=a["flow_packet_spread"],
               isl_match=a["inter_switch_counters_match"],
               pcap_udp_packets=(a.get("pcap") or {}).get("packets_matching_udp_flow"))
    with open(csv_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)
