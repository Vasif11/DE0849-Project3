#!/usr/bin/env python3
"""Phases 7-9: controlled traffic, link characterisation, PCAP + OpenFlow observability, analysis.

  Phase 7: UDP 50 / 80 / 100 Mbit/s and TCP, h1 -> h4, three repetitions each
  Phase 8: reference run (UDP 50 Mbit/s) with bounded PCAP + before/after snapshots
  Phase 9: every experiment directory is analysed by sdnlab.analyze(); results/summary.csv
"""
import os
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "topology"))
sys.path.insert(0, os.path.join(ROOT, "measurement"))
from scenario_a_topo import build_net, start_net, warm_up  # noqa: E402
from sdnlab import analyze, append_summary_csv, run_experiment  # noqa: E402
from mininet.log import setLogLevel  # noqa: E402

DURATION = int(os.environ.get("P3_DURATION", "10"))
REPS = int(os.environ.get("P3_REPS", "3"))
OUT7 = os.path.join(ROOT, "results", "phase7")
OUT8 = os.path.join(ROOT, "results", "phase8")
SUMMARY = os.path.join(ROOT, "results", "summary.csv")


def main():
    setLogLevel("warning")
    subprocess.run("mn -c >/dev/null 2>&1", shell=True)
    subprocess.run("docker restart scenario-a-osken >/dev/null", shell=True)
    time.sleep(5)
    if os.path.exists(SUMMARY):
        os.remove(SUMMARY)
    net = build_net()
    assert start_net(net), "switches did not connect to the controller"
    try:
        assert warm_up(net), "MAC-learning warm-up incomplete: some switch does not know all hosts"
        print("warm-up OK: all switches hold the learned reference-path rules")
        # ---- Phase 8 reference experiment first (clean counters, bounded PCAP)
        d = run_experiment(net, OUT8, "udp50_reference_capture", "udp", 50, DURATION, capture=True)
        a = analyze(d); append_summary_csv(SUMMARY, a)
        print("phase8:", a["iperf"], "flows identical:", a["flow_counters_identical_across_switches"],
              "ISL match:", a["inter_switch_counters_match"], "pcap udp pkts:", (a.get("pcap") or {}).get("packets_matching_udp_flow"))
        # ---- Phase 7 characterisation
        for rate in (50, 80, 100):
            for rep in range(1, REPS + 1):
                d = run_experiment(net, OUT7, f"udp{rate}_run{rep}", "udp", rate, DURATION, repeat=rep)
                a = analyze(d); append_summary_csv(SUMMARY, a)
                print(f"udp{rate} run{rep}:", a["iperf"])
        for rep in range(1, REPS + 1):
            d = run_experiment(net, OUT7, f"tcp_run{rep}", "tcp", None, DURATION, repeat=rep)
            a = analyze(d); append_summary_csv(SUMMARY, a)
            print(f"tcp run{rep}:", a["iperf"])
    finally:
        net.stop()
        subprocess.run("mn -c >/dev/null 2>&1", shell=True)


if __name__ == "__main__":
    main()
