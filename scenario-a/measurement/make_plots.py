#!/usr/bin/env python3
"""Figures for Scenario A: Phase 7 load/throughput/loss and Phase 10 policy comparison."""
import csv
import glob
import os
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIG = os.path.join(ROOT, "figures")
os.makedirs(FIG, exist_ok=True)
BLUE, ORANGE, GREY = "#2a78d6", "#e8743b", "#7f8793"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25})


def rows(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def phase7():
    r = [x for x in rows(os.path.join(ROOT, "results", "summary.csv")) if x["experiment"].startswith("udp") and "run" in x["experiment"]]
    rates = sorted({int(x["offered_mbps"]) for x in r})
    mean = lambda k, rt: [float(x[k]) for x in r if int(x["offered_mbps"]) == rt]
    rx = [st.mean(mean("receiver_mbps", rt)) for rt in rates]
    rx_sd = [st.pstdev(mean("receiver_mbps", rt)) for rt in rates]
    loss = [st.mean(mean("lost_percent", rt)) for rt in rates]
    fig, ax = plt.subplots(1, 2, figsize=(9.5, 3.8))
    ax[0].plot([0, 105], [0, 105], "--", color=GREY, label="ideal (received = offered)")
    ax[0].errorbar(rates, rx, yerr=rx_sd, fmt="o-", color=BLUE, capsize=3, label="received (mean of 3 runs)")
    ax[0].axhline(100, color=ORANGE, lw=1, ls=":"); ax[0].text(52, 101.5, "100 Mbit/s TBF limit", color=ORANGE, fontsize=8)
    ax[0].set_xlabel("UDP offered load (Mbit/s)"); ax[0].set_ylabel("receiver throughput (Mbit/s)")
    ax[0].set_title("Offered load vs delivered"); ax[0].legend(fontsize=8, loc="upper left")
    ax[1].bar([str(x) for x in rates], loss, color=[BLUE, BLUE, ORANGE])
    for i, v in enumerate(loss):
        ax[1].text(i, v + 0.03, f"{v:.2f} %", ha="center", fontsize=9)
    ax[1].set_xlabel("UDP offered load (Mbit/s)"); ax[1].set_ylabel("packet loss (%)")
    ax[1].set_title("Loss: 100 Mbit/s is a saturation test")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "phase7_udp_load_vs_throughput.png"), dpi=140); plt.close(fig)


def phase10():
    base = os.path.join(ROOT, "results", "phase10")
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.9), sharey=True)
    for a, mode, title in ((ax[0], "off", "POLICY OFF (control)"), (ax[1], "on", "POLICY ON (UDP capped by meter)")):
        p = os.path.join(base, f"policy_{mode}", "run1", "timeseries.csv")
        if not os.path.exists(p):
            continue
        t = rows(p)
        s = [int(x["second"]) for x in t]
        a.plot(s, [float(x["tcp_mbps"]) for x in t], color=BLUE, lw=2, label="TCP h1->h4 (iperf3)")
        a.plot(s, [float(x["udp_delivered_mbps"]) for x in t], color=ORANGE, lw=2, label="UDP h2->h3 delivered (PCAP)")
        a.axvspan(4, 18, color=GREY, alpha=0.08)
        a.set_title(title); a.set_xlabel("time (s)  [UDP active 4-18 s]")
    ax[0].set_ylabel("throughput (Mbit/s)"); ax[0].legend(fontsize=8, loc="center left")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "phase10_policy_timeseries.png"), dpi=140); plt.close(fig)

    p = os.path.join(base, "policy_comparison.csv")
    if os.path.exists(p):
        r = rows(p)
        fig, ax = plt.subplots(1, 2, figsize=(9.5, 3.6))
        for i, (k, lab) in enumerate((("tcp_overlap_steady_mbps", "TCP throughput during contention (Mbit/s)"),
                                      ("ping_avg_ms", "ICMP RTT under load, mean (ms)"))):
            vals = {m: [float(x[k]) for x in r if x["policy"] == m and x[k] not in ("", "None")] for m in ("OFF", "ON")}
            ax[i].bar(["policy OFF", "policy ON"], [st.mean(vals["OFF"]), st.mean(vals["ON"])],
                      yerr=[st.pstdev(vals["OFF"]), st.pstdev(vals["ON"])], color=[GREY, BLUE], capsize=4)
            ax[i].set_title(lab, fontsize=9)
        fig.tight_layout(); fig.savefig(os.path.join(FIG, "phase10_policy_summary.png"), dpi=140); plt.close(fig)


if __name__ == "__main__":
    phase7()
    phase10()
    print("figures written to", FIG)
