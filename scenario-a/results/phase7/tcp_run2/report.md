# Experiment tcp_run2

- protocol: **TCP**, offered load: **None Mbit/s**, duration 10 s, observation interval (snapshot midpoints): 10.708 s

## iperf3 receiver-side result

| metric | value |
|---|---|
| receiver_mbps | 94.25 |
| sender_mbps | 102.76 |
| retransmits | 15 |

## OpenFlow flow-counter deltas (reference path, rules matching dl_dst=h4)

| switch | in_port | out_port | Δpackets (path total) | Δbytes (path total) | Δpackets h1 rule only | other-ingress extra pkts | Δbytes/interval (Mbit/s) |
|---|---|---|---|---|---|---|---|
| s1 | 1 | 3 | 27176 | 123429160 | 27176 | 0 | 92.215 |
| s2 | 1 | 2 | 27176 | 123429160 | 27176 | 0 | 92.215 |
| s3 | 3 | 2 | 27176 | 123429160 | 27176 | 0 | 92.215 |

Flow counters identical across s1, s2, s3: **True** (packet spread 0, 0.0 %; snapshot re-reads until stable: {'before': 2, 'after': 3})

## Inter-switch port counters (tx at one end vs rx at the other)

| link | tx pkts | rx pkts | tx bytes | rx bytes | match |
|---|---|---|---|---|---|
| s1:3->s2:1 | 27176 | 27176 | 123429160 | 123429160 | True |
| s2:1->s1:3 | 17730 | 17730 | 1177915 | 1177915 | True |
| s2:2->s3:3 | 27176 | 27176 | 123429160 | 123429160 | True |
| s3:3->s2:2 | 17730 | 17730 | 1177915 | 1177915 | True |

All inter-switch counters match: **True**; port drops/errors per switch: {'s1': 0, 's2': 0, 's3': 0}

