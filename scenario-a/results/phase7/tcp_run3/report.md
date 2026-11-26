# Experiment tcp_run3

- protocol: **TCP**, offered load: **None Mbit/s**, duration 10 s, observation interval (snapshot midpoints): 11.021 s

## iperf3 receiver-side result

| metric | value |
|---|---|
| receiver_mbps | 94.41 |
| sender_mbps | 102.43 |
| retransmits | 31 |

## OpenFlow flow-counter deltas (reference path, rules matching dl_dst=h4)

| switch | in_port | out_port | Δpackets (path total) | Δbytes (path total) | Δpackets h1 rule only | other-ingress extra pkts | Δbytes/interval (Mbit/s) |
|---|---|---|---|---|---|---|---|
| s1 | 1 | 3 | 28211 | 123858021 | 28211 | 0 | 89.907 |
| s2 | 1 | 2 | 28211 | 123858021 | 28211 | 0 | 89.907 |
| s3 | 3 | 2 | 28211 | 123858021 | 28211 | 0 | 89.907 |

Flow counters identical across s1, s2, s3: **True** (packet spread 0, 0.0 %; snapshot re-reads until stable: {'before': 2, 'after': 4})

## Inter-switch port counters (tx at one end vs rx at the other)

| link | tx pkts | rx pkts | tx bytes | rx bytes | match |
|---|---|---|---|---|---|
| s1:3->s2:1 | 28211 | 28211 | 123858021 | 123858021 | True |
| s2:1->s1:3 | 18131 | 18131 | 1210565 | 1210565 | True |
| s2:2->s3:3 | 28211 | 28211 | 123858021 | 123858021 | True |
| s3:3->s2:2 | 18131 | 18131 | 1210565 | 1210565 | True |

All inter-switch counters match: **True**; port drops/errors per switch: {'s1': 0, 's2': 0, 's3': 0}

