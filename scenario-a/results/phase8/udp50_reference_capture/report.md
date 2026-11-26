# Experiment udp50_reference_capture

- protocol: **UDP**, offered load: **50 Mbit/s**, duration 10 s, observation interval (snapshot midpoints): 10.4 s

## iperf3 receiver-side result

| metric | value |
|---|---|
| receiver_mbps | 49.95 |
| jitter_ms | 0.0275 |
| lost_packets | 0 |
| packets | 43168 |
| lost_percent | 0 |

## OpenFlow flow-counter deltas (reference path, rules matching dl_dst=h4)

| switch | in_port | out_port | Δpackets (path total) | Δbytes (path total) | Δpackets h1 rule only | other-ingress extra pkts | Δbytes/interval (Mbit/s) |
|---|---|---|---|---|---|---|---|
| s1 | 1 | 3 | 43183 | 64321790 | 43183 | 0 | 49.478 |
| s2 | 1 | 2 | 43183 | 64321790 | 43183 | 0 | 49.478 |
| s3 | 3 | 2 | 43183 | 64321790 | 43183 | 0 | 49.478 |

Flow counters identical across s1, s2, s3: **True** (packet spread 0, 0.0 %; snapshot re-reads until stable: {'before': 2, 'after': 3})

## Inter-switch port counters (tx at one end vs rx at the other)

| link | tx pkts | rx pkts | tx bytes | rx bytes | match |
|---|---|---|---|---|---|
| s1:3->s2:1 | 43183 | 43183 | 64321790 | 64321790 | True |
| s2:1->s1:3 | 14 | 14 | 1249 | 1249 | True |
| s2:2->s3:3 | 43183 | 43183 | 64321790 | 64321790 | True |
| s3:3->s2:2 | 14 | 14 | 1249 | 1249 | True |

All inter-switch counters match: **True**; port drops/errors per switch: {'s1': 0, 's2': 0, 's3': 0}

## PCAP summary (h1, bounded capture)

- file: capture_h1.pcap
- size_bytes: 2799974
- packets_in_file: 25000
- packets_matching_udp_flow: 25000
- src: ['10.0.0.1']
- dst: ['10.0.0.4']
- protocol: UDP
- dst_ports: ['5201']
- frame_len_min: 46
- frame_len_max: 1490
- frame_len_mean: 1489.9
- duration_s: 5.8026
- mean_interarrival_us: 232.1

> flow rule (dl_dst=00:00:00:00:00:04) counted 43183 packets; the bounded capture holds 25000 UDP-flow packets (capture limit 25000); the aggregate rule also counts the iperf3 TCP control connection and any other frame to 00:00:00:00:00:04.

