# Experiment udp50_run2

- protocol: **UDP**, offered load: **50 Mbit/s**, duration 10 s, observation interval (snapshot midpoints): 10.407 s

## iperf3 receiver-side result

| metric | value |
|---|---|
| receiver_mbps | 49.95 |
| jitter_ms | 0.0307 |
| lost_packets | 0 |
| packets | 43168 |
| lost_percent | 0 |

## OpenFlow flow-counter deltas (reference path, rules matching dl_dst=h4)

| switch | in_port | out_port | Δpackets (path total) | Δbytes (path total) | Δpackets h1 rule only | other-ingress extra pkts | Δbytes/interval (Mbit/s) |
|---|---|---|---|---|---|---|---|
| s1 | 1 | 3 | 43183 | 64321793 | 43183 | 0 | 49.445 |
| s2 | 1 | 2 | 43183 | 64321793 | 43183 | 0 | 49.445 |
| s3 | 3 | 2 | 43183 | 64321793 | 43183 | 0 | 49.445 |

Flow counters identical across s1, s2, s3: **True** (packet spread 0, 0.0 %; snapshot re-reads until stable: {'before': 2, 'after': 3})

## Inter-switch port counters (tx at one end vs rx at the other)

| link | tx pkts | rx pkts | tx bytes | rx bytes | match |
|---|---|---|---|---|---|
| s1:3->s2:1 | 43183 | 43183 | 64321793 | 64321793 | True |
| s2:1->s1:3 | 14 | 14 | 1245 | 1245 | True |
| s2:2->s3:3 | 43183 | 43183 | 64321793 | 64321793 | True |
| s3:3->s2:2 | 14 | 14 | 1245 | 1245 | True |

All inter-switch counters match: **True**; port drops/errors per switch: {'s1': 0, 's2': 0, 's3': 0}

