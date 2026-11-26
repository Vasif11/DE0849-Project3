# DE0849 Telecommunications Software - Project 3
## Software-Defined Telecommunication Networks

**Author:** Vasif Yusifli, 261AEM001
**Course:** DE0849 Telecommunications Software - Riga Technical University (2026/27)
**Builds on:** [Project 1](https://github.com/Vasif11/DE0849-Project1) (5G SA deployment/measurement) and [Project 2](https://github.com/Vasif11/DE0849-Project2) (5G security).
**Workflow:** Deploy → Control → Measure → Observe → Analyze → Infer → Manage.

| Scenario | Topic | Status |
|---|---|---|
| **A** | SDN deployment, measurement and observability: Mininet + Open vSwitch + Dockerized OS-Ken controller | **complete - Phases 1-10 executed with evidence** |
| **B** | O-RAN intelligent RAN monitoring (OCUDU gNB, srsUE, Open5GS, FlexRIC, KPM / Edge-AI / RM xApps) | **incomplete** - core, FlexRIC, gNB N2/F1 verified; UE radio link and all xApp phases not achieved on the 4 GB host, see [Scenario B status](#scenario-b-status) |

Repository layout: `scenario-a/{topology,controller,measurement,scripts,results,figures}`. Every number below
comes from a file under `scenario-a/results/` produced by the scripts in this repository.

---

# Scenario A - SDN deployment, measurement and observability

## 1. Architecture

```
 h1 10.0.0.1 --\                                         /-- h3 10.0.0.3
                s1 (dpid ..01) ---- s2 (dpid ..02) ---- s3 (dpid ..03)
 h2 10.0.0.2 --/       \                |                /       \-- h4 10.0.0.4
                        \_______ OpenFlow 1.3 / TCP 6633 _______/
                                  OS-Ken 3.1.1 (Docker, host network)
```

* **Data plane:** Mininet 2.3.0, three Open vSwitch 3.7.1 switches (kernel datapath, OpenFlow 1.3, `fail-mode secure`), four hosts in `10.0.0.0/24`, fixed DPIDs `…01/02/03`.
* **Links (all six):** Mininet `TCLink`, **TBF** 100 Mbit/s + `netem` child: 1 ms delay, 0 % loss, 1000-packet queue (`use_tbf`, not the default HTB).
* **Control plane:** controller `scenario-a-osken` (image `telecom-lab-osken:1.0`, OS-Ken 3.1.1, `python:3.11-slim`), started **before** the switches, host networking, TCP 6633.
* **Ports** are created in a fixed order so the reference path `h1-s1-s2-s3-h4` is `s1:1→3`, `s2:1→2`, `s3:3→2` (verified from the flow tables, [results/phase3](scenario-a/results/phase3/topology.txt)).

Host used here: Windows 11 + WSL2 (Ubuntu 26.04, kernel 6.18, 4 vCPU, 4 GB RAM), Docker 29.1.3, Python 3.14.4 (host) / 3.11 (controller image), iperf3 3.20, tcpdump 4.99.6, tshark. The guidebook's reference host is Ubuntu 22.04.5 / Docker 27.3.1 / Python 3.11.5; the tool versions that matter for results (Mininet 2.3.0, OS-Ken 3.1.1, OpenFlow 1.3) are the same.

## 2. Reproduction

```bash
sudo apt install mininet openvswitch-switch iperf3 tcpdump tshark
cd scenario-a && sudo docker compose up -d --build           # Phase 4: OS-Ken controller
sudo scripts/01_prepare_verify.sh && sudo scripts/02_baseline.sh   # Phases 1-2
sudo python3 scripts/verify_phase3_6.py                       # Phases 3, 5, 6
sudo P3_DURATION=10 P3_REPS=3 python3 scripts/run_phase7_9.py # Phases 7, 8, 9
sudo python3 scripts/run_phase10.py                           # Phase 10
python3 measurement/make_plots.py                             # figures
```

## 3. Results by phase

### Phase 1 - host preparation ([evidence](scenario-a/results/phase1/host_environment.txt))
Mininet 2.3.0, OVS 3.7.1 (`openvswitch-switch` active, `openvswitch` kernel module loaded), Docker operational, `iperf3`/`tcpdump`/`tshark` present; an OVS bridge can be created and removed; `mn --test pingall` works. Host declared **READY**.

### Phase 2 - baseline without controller ([evidence](scenario-a/results/phase2/baseline.txt))
Two hosts, one OVS switch in standalone mode, no external controller: **0 % packet loss**; after `mn -c` no OVS bridge, Mininet process or veth link remains (`BASELINE: PASS`).

### Phase 3 - topology ([evidence](scenario-a/results/phase3/topology.txt))
Six links created; DPIDs `0000000000000001/2/3`; port map `s1{1:h1,2:h2,3:s2} s2{1:s1,2:s3} s3{1:h3,2:h4,3:s2}`; every switch-side interface carries `tbf rate 100Mbit burst 15000b lat 1.2ms` with a `netem limit 1000 delay 1ms` child.

### Phase 4 - controller
Container `scenario-a-osken` / `telecom-lab-osken:1.0` running, `os-ken 3.1.1`, `LISTEN 0.0.0.0:6633`, application loaded without errors.

### Phase 5 - OpenFlow 1.3 ([evidence](scenario-a/results/phase5/openflow_connectivity.txt))
All three switches report `is_connected: true`, `protocols=[OpenFlow13]`, `fail_mode=secure`; the controller logged `SWITCH_CONNECT` for dpid 1, 2, 3 with `ofp_version=0x4` (OpenFlow 1.3) and installed the table-miss rule on each.

### Phase 6 - learning switch ([evidence](scenario-a/results/phase6/learning_switch.txt))
The application ([`controller/learning_switch.py`](scenario-a/controller/learning_switch.py)) installs the table-miss rule, learns `MAC → port` from packet-ins, floods unknown destinations and installs priority-10 `in_port + eth_dst` rules for known ones.
* `pingall`: **0 % loss**.
* Flow tables show the `priority=0 → CONTROLLER` miss rule plus learned priority-10 rules; the reference path is `s1: in_port=1,dl_dst=h4 → 3`, `s2: 1 → 2`, `s3: 3 → 2`.
* Controller-assisted → switch-local: PACKET_IN count 11 after the first `h1→h4` ping and **still 11 after the second** (0 new packet-ins).

### Phase 7 - controlled traffic and link characterisation (`h1 → h4`, 10 s, 3 repetitions; [summary.csv](scenario-a/results/summary.csv), [figure](scenario-a/figures/phase7_udp_load_vs_throughput.png))

| Workload | Receiver throughput (Mbit/s) | Loss | Jitter (ms) |
|---|---|---|---|
| UDP 50 Mbit/s | 49.95 / 49.95 / 49.95 | **0 / 0 / 0 %** | 0.012-0.041 |
| UDP 80 Mbit/s | 79.93 / 79.92 / 79.93 | **0 / 0 / 0 %** | 0.019-0.028 |
| UDP 100 Mbit/s (saturation) | 97.10 / 97.10 / 97.11 | 1.66 / 1.66 / 1.66 % | 0.020-0.033 |
| TCP | 94.62 / 94.25 / 94.41 (receiver) | - (11 / 15 / 31 retransmissions) | - |

This agrees with the reference behaviour in the guidebook: loss-free at 50 and 80 Mbit/s, non-zero loss only in the 100 Mbit/s saturation test (treated as a stress condition; the TBF configuration was **not** altered to hide it). The `TBF` shaper delivered 80 Mbit/s without loss in all three runs (an earlier, less careful warm-up produced one run with 62 lost packets; see *Reproducibility notes*).

### Phase 8 - packet capture, OpenFlow measurement, cross-layer observability ([report](scenario-a/results/phase8/udp50_reference_capture/report.md))
Reference run: UDP 50 Mbit/s, bounded PCAP on h1 (`udp and dst host 10.0.0.4 and dst port 5201`, 25,000-packet limit, 96-byte snaplen), before/after flow and port snapshots.

| Evidence | Result |
|---|---|
| iperf3 receiver | **49.95 Mbit/s, 0 lost of 43,168** datagrams |
| Flow-counter Δ on `s1`, `s2`, `s3` | **identical: 43,183 packets, 64,321,790 bytes** on all three switches |
| Inter-switch ports | `s1:3→s2:1` and `s2:2→s3:3`: tx = rx = 43,183 packets / 64,321,790 bytes; reverse direction 14 / 1,249 B on both |
| Port drops / errors | 0 on all switches |
| PCAP (25,000 packets) | all match the UDP flow `10.0.0.1 → 10.0.0.4`, UDP dst port 5201, frame length 1,490 B (mean 1,489.9), mean inter-arrival 232.1 µs |

The flow counter (43,183) is larger than iperf3's 43,168 datagrams because the aggregate `dl_dst=h4` rule also counts the iperf3 TCP control connection and other frames to h4 - the framework reports this explicitly rather than equating the two. The guidebook's reference run reports the same 43,183-packet increment.

### Phase 9 - automated, repeatable analysis ([`measurement/sdnlab.py`](scenario-a/measurement/sdnlab.py))
`run_experiment()` + `analyze()` accept an experiment directory and produce `analysis.json`, `report.md` and one row in `results/summary.csv`: flow packet/byte deltas, inter-switch counter consistency, iperf3 receiver parsing, PCAP summary (via `tshark`), snapshot timestamps.
* **Observation interval:** deltas are divided by the interval between snapshot mid-points, not by the iperf3 duration.
* **Stable snapshots:** OVS refreshes OpenFlow counters from the datapath with a delay, so a single `dump-flows` can lag by a few packets and the lag differs per switch. Each snapshot is therefore re-read until two consecutive reads agree. Without this, flow counters on the three switches differed by up to 9 packets (0.02 %); with it they are identical in 12 of 13 experiments (the exception, `tcp_run1`, has a 3-packet spread).
* Aggregate counters: for `s1` the framework sums both ingress rules (h1 and h2 both reach `s2` through `s1`) and reports the h1-only rule separately.

### Phase 10 - traffic classification and SDN policy ([`controller/classifier_policy.py`](scenario-a/controller/classifier_policy.py))

**Method.** The first packet of each IPv4 TCP/UDP flow reaches the controller, which installs a per-flow monitor rule (priority 20, 5-tuple match). A monitor thread reads OpenFlow flow statistics every second and derives rate and mean packet size from counter deltas. A transparent rule-based classifier (thresholds as environment variables) assigns one of four classes, committed only after two consecutive agreeing samples:

| Class | Rule |
|---|---|
| `udp_high_rate` | UDP and rate ≥ 20 Mbit/s |
| `udp_low_rate` | UDP and rate < 20 Mbit/s |
| `tcp_bulk` | TCP and rate ≥ 10 Mbit/s |
| `tcp_light` | TCP and rate < 10 Mbit/s |

Features used: protocol, rate, mean packet size, counters. **Port numbers are not features.** Decisions are logged as JSON (`CLASSIFY …`).

**Validation against ground truth** ([results](scenario-a/results/phase10/classification/classification_results.csv)): four controlled traffic types, each run twice alone, ground truth taken from the traffic-generation configuration:

| True class \ predicted | tcp_bulk | tcp_light | udp_high_rate | udp_low_rate |
|---|---|---|---|---|
| tcp_bulk (iperf3 TCP) | 2 | 0 | 0 | 0 |
| tcp_light (TCP `-b 2M`) | 0 | 2 | 0 | 0 |
| udp_high_rate (UDP 40 M) | 0 | 0 | 2 | 0 |
| udp_low_rate (UDP 3 M) | 0 | 0 | 0 | 2 |

Accuracy 8/8, every decision made after a flow age of 2 s (two polling samples); measured rates at decision: 98-99, 2.1, 41.2 and 3.1 Mbit/s. **n = 8 on well-separated controlled classes - this validates the mechanism, not a general classifier.**

**Policy.** For `udp_high_rate` the controller attaches an OpenFlow **meter** (drop band, 30 Mbit/s) to the flow's rule on every switch. `POLICY=off` classifies and logs but changes no forwarding (control experiment).

**Policy experiment** ([data](scenario-a/results/phase10/policy_comparison.csv), [figure](scenario-a/figures/phase10_policy_timeseries.png)): TCP `h1→h4` (20 s) competes with an 80 Mbit/s UDP flow `h2→h3` that starts at t = 4 s, sharing the 100 Mbit/s path; three repetitions each.

| Metric (mean of 3 runs) | Policy OFF | Policy ON |
|---|---|---|
| TCP receiver average over the 20 s run | 41.0 Mbit/s | **70.1 Mbit/s** |
| TCP steady state during contention (sender intervals) | 17.4 Mbit/s | **66.8 Mbit/s** |
| UDP delivered, steady state (PCAP, includes headers) | 82.4 Mbit/s | **29.9 Mbit/s** |
| ICMP RTT during contention (mean) | 122 ms | **54 ms** |
| Flow-table change | priority-20 UDP rule: `output:3` | `meter:1,output:3` (meter band counter 50,189 packets dropped) |

The controller log shows `CLASSIFY … udp_high_rate` followed by `POLICY … ENFORCED` on dpids 1, 2, 3 ([log](scenario-a/results/phase10/policy_on/run1/controller_policy.json)); PCAP samples at h3 are kept per run. The UDP sender's apparent "loss" (54 %) under policy ON is the intended meter drop.

## 4. Limitations and honest notes
* **Single bottleneck, synthetic traffic.** Classification and policy were validated on iperf3 traffic with known ground truth; thresholds (20 / 10 Mbit/s) were chosen from these workloads and are not universal.
* **Reactive design costs.** The first packets of every flow pass through the controller; narrowing the L2 rules by `eth_type` was required so TCP/UDP flows are not swallowed by earlier ARP/ICMP rules (found and fixed during Phase 10).
* **Learning needs broadcasts.** A reactive learning switch only learns from packet-ins; a host whose frames match existing rules can stay unknown on a switch and every packet to it is then flooded via the controller (observed: h4 unknown at s1/s2, throughput fell to ~25 Mbit/s). The experiments therefore start with an explicit warm-up (`warm_up()` in the topology module: ARP flush, broadcast announce, assertion that all switches hold the reference-path rules).
* **Throughput definitions.** TCP "alone" figures above 100 Mbit/s are sender-side iperf3 intervals (socket buffering); receiver averages are the reliable figure. PCAP rates include Ethernet/IP/UDP headers, hence 82 Mbit/s for an 80 Mbit/s payload.
* **Flow counters vs UDP stream.** The aggregate `dl_dst` counter also counts TCP control and other frames (see Phase 8).
* **Optional multi-path traffic-engineering extension: not implemented.**
* **Host differences** from the reference environment are listed in §1.

### Reproducibility notes (what changed during development)
Early runs without the warm-up and without stable snapshots produced misleading numbers (e.g. 25 Mbit/s instead of 50, counter spreads of a few packets, one 80 Mbit/s run with 62 lost packets). They were diagnosed (unknown host at `s1`, delayed OVS counter refresh) and fixed in the code; all results in this repository come from the final scripts in a single end-to-end run.

---

# Scenario B status

**Scenario B is NOT complete.** The O-RAN infrastructure was built and brought up as far as the lab host
allowed; the srsUE ↔ OCUDU radio link over ZeroMQ never started, so there is no UE attach, no E2 setup, and
therefore **no KPM, Edge-AI or Resource-Management results**. Nothing below Phase 5 was executed, and no
measurement from Scenario B is reported anywhere in this repository.

| Phase | Result | Evidence |
|---|---|---|
| 1 Project 2 5G core | **done** - AMF/SMF/UPF and all NFs running; N2 `10.20.2.12`, N3 `10.20.3.14`, N4 `10.20.5.13/.14`, N6 `10.20.6.14` as in the guidebook; IMSI `001010000000001` / DNN `internet` provisioned; AMF listening on NGAP 38412 | [core_verification.txt](scenario-b/results/phase1/core_verification.txt) |
| 2 RAN network + containers | **done** - `project3-ric-lab_ran-net` `10.20.11.0/24`; gNB `10.20.11.10` (+ `10.20.2.11` N2, `10.20.3.11` N3), srsUE `10.20.11.20`, FlexRIC `10.20.11.30`, iperf3 endpoint `10.20.6.21` | [ran_network.txt](scenario-b/results/phase2/ran_network.txt) |
| 3 FlexRIC | **done** - built from source (`telecom-lab-flexric:1.0`, FlexRIC `br-flexric` commit `73650812`, E2AP v2, KPM v3.00); starts on `10.20.11.30`, SCTP **36421 (E2)** and **36422 (E42)** listening; service models loaded: **KPM = RAN function 2, RC = RAN function 3** (as in the guidebook) | [flexric.txt](scenario-b/results/phase3/flexric.txt) |
| 4 OCUDU gNB | **partly** - OCUDU gNB 26.04.0 (`050a2bb`, image `aetherproject/ocudu:rel-0.7.0`): cell configured (n3, ARFCN 368500, 10 MHz, 15 kHz, PCI 1, 1T1R), **N2 up** (`NGSetupRequest/Response`, AMF "gNB-N2 accepted [10.20.2.11]"), **E1 and F1 setup complete**, `Cell scheduling was activated`. **E2 association to FlexRIC: not established** | [gnb_bringup.txt](scenario-b/results/phase4/gnb_bringup.txt) |
| 5 srsUE | **failed** - srsUE (`eea87b1`) starts, the two ZeroMQ TCP links (gNB `tx` 2000 ← UE, UE `tx` 2001 ← gNB) are `ESTABLISHED`, `NAS5G Switching on`, but the UE stays at `Attaching UE...`; no sample traffic is exchanged | [ue_attach.txt](scenario-b/results/phase5/ue_attach.txt) |
| 6-10 xApps | **not executed** | - |

### Why it stopped (diagnosed, not guessed)
1. **Radio link deadlock.** With both sides up and the ZeroMQ sockets connected, a 5 s capture on the RAN bridge shows **0 ZeroMQ packets**, and the gNB `radio` and UE `SYNC` threads sit idle (CPU ≈ 7 %): the lock-step sample exchange never starts. Changing the start order (UE first or gNB first) did not help. The gNB log also reports `Worker pool "main_pool" instantiated with #workers=1` on this 4-vCPU WSL VM. I did not find the root cause; the most likely factors are the single-worker real-time pipeline and CPU/memory starvation, but that is **a hypothesis, not a result**.
2. **Memory.** The OCUDU gNB alone uses ≈ 2.1-2.5 GiB RSS; with the core (~1 GB) and srsUE (~0.7 GB) the 4 GB WSL VM swaps (≈ 400 MB swap in use). The guidebook's Scenario B assumes a larger host.
3. **E2.** No E2 association ever appeared at the RIC and the gNB log (info level) contains no E2 message, so I cannot say whether the E2 agent tried to connect. The FlexRIC/OCUDU E2AP/KPM compatibility - a real risk with this FlexRIC version - therefore remains **untested**.

### Environment pitfalls found (useful for anyone repeating this on WSL2)
* **The WSL distro shuts down shortly after the last `wsl.exe` session ends**; `systemd` then stops `docker.service` and every container without a restart policy exits with code 255 ("Could not stop application after 5 seconds"). Early gNB/RIC "crashes" were this artefact. Keep one session open (e.g. `wsl -d Ubuntu -- sleep infinity`) while the RAN stack runs.
* FlexRIC does not build with the default `gcc-11` of Ubuntu 22.04 (internal compiler error on the `_Generic` decoder macros); the image therefore uses `gcc-12`, `pkg-config`, `libconfig-dev`, and builds only the KPM and RC service models.
* The srsUE version in the image rejects `pcap.mac_enable` (use `[pcap] enable = none`); the gNB binary is called `gnb`, not `ocudu-gnb`; gNB/UE file logs are buffered, so use `filename: stdout`.

### What is ready for a host with more resources
`scenario-b/docker-compose.yml`, `configs/gnb_zmq.yaml`, `configs/ue_zmq.conf`, `configs/flexric.conf`, the FlexRIC `Dockerfile`, the N6 iperf3 endpoint image and `scripts/b01_core_up.sh` / `b03_bringup_evidence.sh`. The KPM xApp configurations for Phase 6 (`xapp_kpm_phase6.conf`: format 1, `ngran_gNB_DU`, `DRB.UEThpDl`, `DRB.UEThpUl`, 1000 ms) and Phase 7 (`xapp_kpm_phase7.conf`: adds `RRU.PrbTotDl`, `RRU.PrbTotUl`, `DRB.RlcSduDelayDl`) are written for FlexRIC's `xapp_oran_moni` **but have never been run**. The Edge-AI and Resource-Management xApps (Phases 8-9) were not started.
