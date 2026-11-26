#!/usr/bin/env python3
"""Phases 3, 5 and 6: topology deployment, OpenFlow 1.3 connectivity, learning-switch behaviour.

Run as root with the OS-Ken container already running (Phase 4).
Evidence is written to results/phase3, results/phase5 and results/phase6.
"""
import os
import re
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "topology"))
from scenario_a_topo import build_net, port_map, start_net  # noqa: E402
from mininet.log import setLogLevel  # noqa: E402

CTRL = "scenario-a-osken"


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


def write(phase, name, text):
    d = os.path.join(ROOT, "results", phase)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "w") as f:
        f.write(text)
    print(f"--- {phase}/{name}\n{text.rstrip()}\n")


SINCE = [0]   # unix epoch of this run; `docker logs --since` needs an epoch, not a duration


def ctrl_log():
    return subprocess.run(f"docker logs --since {SINCE[0]} {CTRL} 2>&1", shell=True,
                          capture_output=True, text=True).stdout


def flows(sw):
    return sh(f"ovs-ofctl -O OpenFlow13 dump-flows {sw}")


def main():
    setLogLevel("warning")
    sh("mn -c >/dev/null 2>&1")
    # fresh controller log window: restart the container so MAC tables start empty
    sh(f"docker restart {CTRL} >/dev/null"); time.sleep(5)
    SINCE[0] = int(time.time())

    net = build_net()
    connected = start_net(net)
    try:
        # ---------------- Phase 3: topology -------------------------------------------------
        t = ["# Phase 3 - Scenario A topology deployment", ""]
        t.append(f"switches: {[s.name for s in net.switches]}")
        t.append(f"hosts:    {[(h.name, h.IP()) for h in net.hosts]}")
        t.append(f"links created: {len(net.links)} (expected 6)")
        t.append("DPIDs: " + ", ".join(f"{s.name}={s.dpid}" for s in net.switches))
        t.append("port map (switch -> {port: neighbour}):")
        pm = port_map(net)
        for s, m in pm.items():
            t.append(f"  {s}: {dict(sorted(m.items()))}")
        t.append("")
        t.append("## TBF + netem queue structure on every switch-side interface")
        for sw in net.switches:
            for intf in sw.intfList():
                if intf.name == "lo":
                    continue
                q = sh(f"tc qdisc show dev {intf.name}")
                t.append(f"[{intf.name}]\n{q.strip()}")
        write("phase3", "topology.txt", "\n".join(t))

        # ---------------- Phase 5: OpenFlow 1.3 connectivity --------------------------------
        f = ["# Phase 5 - OpenFlow 1.3 integration", ""]
        f.append(f"all three switches report an active controller session: {connected}")
        f.append("## ovs-vsctl show")
        f.append(sh("ovs-vsctl show"))
        f.append("## controller records (target / is_connected / role / status)")
        f.append(sh("ovs-vsctl --columns=target,is_connected,role,status list controller"))
        for sw in net.switches:
            f.append(f"## {sw.name}: protocols={sh(f'ovs-vsctl get bridge {sw.name} protocols').strip()} "
                     f"fail_mode={sh(f'ovs-vsctl get bridge {sw.name} fail_mode').strip()}")
            f.append(sh(f"ovs-ofctl -O OpenFlow13 show {sw.name} | head -3"))
        f.append("## controller log: switch connections")
        f.append("\n".join(l for l in ctrl_log().splitlines() if "SWITCH_CONNECT" in l or "TABLE_MISS" in l))
        write("phase5", "openflow_connectivity.txt", "\n".join(f))

        # ---------------- Phase 6: learning switch -----------------------------------------
        l = ["# Phase 6 - learning-switch application", ""]
        l.append("## table-miss rule before any traffic (s1)")
        l.append(flows("s1"))

        before = len([x for x in ctrl_log().splitlines() if "PACKET_IN" in x])
        l.append("## h1 -> h4 first ping (controller-assisted discovery)")
        l.append(net.get("h1").cmd("ping -c 3 10.0.0.4"))
        mid = len([x for x in ctrl_log().splitlines() if "PACKET_IN" in x])
        l.append("## h1 -> h4 second ping (switch-local forwarding expected)")
        l.append(net.get("h1").cmd("ping -c 3 10.0.0.4"))
        after = len([x for x in ctrl_log().splitlines() if "PACKET_IN" in x])
        l.append(f"PACKET_IN count: before={before}  after-first-ping={mid}  after-second-ping={after}")
        l.append(f"new packet-ins caused by the second ping: {after - mid} "
                 f"(0 means forwarding became switch-local)")
        l.append("")
        l.append("## pingall (all four hosts)")
        loss = net.pingAll()
        l.append(f"pingall packet loss: {loss}%")
        l.append("")
        for sw in net.switches:
            l.append(f"## flow table {sw.name}")
            l.append(flows(sw.name))
        l.append("## controller log (SWITCH/LEARN/FLOOD/FLOW_MOD excerpt)")
        keep = [x for x in ctrl_log().splitlines() if re.search(r"LEARN|FLOOD|FLOW_MOD|TABLE_MISS|SWITCH_CONNECT", x)]
        l.extend(keep[:60])
        l.append(f"... ({len(keep)} such events in total)")
        write("phase6", "learning_switch.txt", "\n".join(l))
        verdict = "PASS" if loss == 0 and after == mid else "FAIL"
        print(f"PHASE 3-6 VERDICT: {verdict} (pingall loss={loss}%, second-ping packet-ins={after - mid})")
    finally:
        net.stop()
        sh("mn -c >/dev/null 2>&1")


if __name__ == "__main__":
    main()
