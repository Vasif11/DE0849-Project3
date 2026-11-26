"""Phase 10 - traffic classification and SDN policy control (OS-Ken, OpenFlow 1.3).

Builds on the validated learning switch (learning_switch.LearningSwitch).

Pipeline
  1. First packet of an IPv4 TCP/UDP flow arrives as packet-in.
     -> install a per-flow monitor rule (priority 20, 5-tuple match) that forwards like the
        learning switch and counts packets/bytes.  Provisional class = transport protocol.
  2. A monitor thread polls OpenFlow flow statistics every second and derives, per flow,
     the rate (Mbit/s) and the mean packet size from counter deltas.
  3. Transparent rule-based classifier (thresholds are environment variables):
        UDP & rate >= UDP_HIGH_MBPS  -> udp_high_rate
        UDP & rate <  UDP_HIGH_MBPS  -> udp_low_rate
        TCP & rate >= TCP_BULK_MBPS  -> tcp_bulk
        TCP & rate <  TCP_BULK_MBPS  -> tcp_light
     A class is committed only after CONFIRM consecutive samples agree (decision stability).
     Port numbers are NOT used as features; only protocol, rate, packet size and counters.
  4. Policy (POLICY=on): the udp_high_rate class is rate-limited with an OpenFlow meter
     (DROP band, UDP_CAP_KBPS) attached to the flow's rule on every switch.  POLICY=off keeps
     classification and logging but changes no forwarding (the control experiment).

All decisions are logged as one-line JSON with the prefix  CLASSIFY / POLICY  for later analysis.
"""
import json
import os
import time

from os_ken.controller import ofp_event
from os_ken.controller.handler import DEAD_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from os_ken.lib import hub
from os_ken.lib.packet import ethernet, ipv4, packet, tcp, udp
from os_ken.ofproto import ofproto_v1_3

from learning_switch import LearningSwitch

FLOW_PRIORITY = 20
METER_ID = 1


def _env(name, default):
    return type(default)(os.environ.get(name, default))


class ClassifierPolicy(LearningSwitch):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_on = os.environ.get("POLICY", "off").lower() == "on"
        self.udp_high = _env("UDP_HIGH_MBPS", 20.0)
        self.tcp_bulk = _env("TCP_BULK_MBPS", 10.0)
        self.cap_kbps = _env("UDP_CAP_KBPS", 30000)
        self.confirm = _env("CONFIRM", 2)
        self.poll_s = _env("POLL_S", 1.0)
        self.model = "rule-based-v1"
        self.datapaths = {}
        self.flows = {}       # {(dpid, key): state}
        self.logger.info("CONFIG policy=%s udp_high=%s tcp_bulk=%s cap_kbps=%s confirm=%s",
                         "ON" if self.policy_on else "OFF", self.udp_high, self.tcp_bulk,
                         self.cap_kbps, self.confirm)
        hub.spawn(self._monitor)

    # ---- datapath registry + meter -------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change(self, ev):
        dp = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[dp.id] = dp
            if self.policy_on:
                self._install_meter(dp)
        elif dp.id in self.datapaths:
            del self.datapaths[dp.id]

    def _install_meter(self, dp):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        band = parser.OFPMeterBandDrop(rate=self.cap_kbps, burst_size=max(1000, self.cap_kbps // 20))
        dp.send_msg(parser.OFPMeterMod(datapath=dp, command=ofp.OFPMC_ADD, flags=ofp.OFPMF_KBPS | ofp.OFPMF_BURST,
                                       meter_id=METER_ID, bands=[band]))
        self.logger.info("POLICY_METER dpid=%016x meter_id=%d rate_kbps=%d", dp.id, METER_ID, self.cap_kbps)

    # ---- packet-in: per-flow monitor rule -----------------------------------------------
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        in_port = msg.match["in_port"]
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]
        if eth.ethertype == 0x88CC:
            return
        dst, src, dpid = eth.dst, eth.src, dp.id
        table = self.mac_to_port.setdefault(dpid, {})
        self.learn(dp, in_port, src)
        out_port = table.get(dst)

        ip4 = pkt.get_protocol(ipv4.ipv4)
        l4 = pkt.get_protocol(tcp.tcp)
        if l4 is None:
            l4 = pkt.get_protocol(udp.udp)
        if ip4 is not None:
            self.logger.debug("PKT dpid=%016x in_port=%s %s->%s proto=%s l4=%s out_port=%s",
                              dpid, in_port, ip4.src, ip4.dst, ip4.proto, type(l4).__name__, out_port)
        if out_port is not None and ip4 is not None and l4 is not None and ip4.proto in (6, 17):
            key = (ip4.proto, ip4.src, ip4.dst, l4.src_port, l4.dst_port)
            if (dpid, key) not in self.flows:
                self.flows[(dpid, key)] = dict(first_seen=time.time(), out_port=out_port, in_port=in_port,
                                               last_bytes=0, last_pkts=0, last_t=None, streak=0,
                                               pending_cls=None, cls=None, policed=False)
                self._install_flow(dp, key, out_port, meter=False)
                self.logger.info("FLOW_NEW dpid=%016x %s provisional=%s", dpid, self._fmt(key),
                                 "udp" if ip4.proto == 17 else "tcp")
            actions = [parser.OFPActionOutput(out_port)]
        elif out_port is not None:
            actions = [parser.OFPActionOutput(out_port)]
            # Non-TCP/UDP traffic (ARP, ICMP, ...) gets L2 rules that are NARROWED by eth_type (and
            # ip_proto), so they cannot swallow TCP/UDP flows: those must reach the controller once
            # to be classified and receive their own priority-20 5-tuple rule.
            kw = dict(in_port=in_port, eth_dst=dst, eth_type=eth.ethertype)
            if ip4 is not None:
                kw["ip_proto"] = ip4.proto
            self._add_flow(dp, 10, parser.OFPMatch(**kw), actions)
            self.logger.info("FLOW_MOD dpid=%016x match(in_port=%s,eth_dst=%s,eth_type=%#06x%s) -> output:%s priority=10",
                             dpid, in_port, dst, eth.ethertype,
                             f",ip_proto={ip4.proto}" if ip4 is not None else "", out_port)
        else:
            actions = [parser.OFPActionOutput(ofp.OFPP_FLOOD)]
        data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None
        dp.send_msg(parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id, in_port=in_port,
                                        actions=actions, data=data))

    @staticmethod
    def _fmt(key):
        proto, s, d, sp, dp_ = key
        return f"{'udp' if proto == 17 else 'tcp'} {s}:{sp}->{d}:{dp_}"

    def _match(self, parser, key):
        proto, s, d, sp, dp_ = key
        kw = dict(eth_type=0x0800, ip_proto=proto, ipv4_src=s, ipv4_dst=d)
        if proto == 6:
            kw.update(tcp_src=sp, tcp_dst=dp_)
        else:
            kw.update(udp_src=sp, udp_dst=dp_)
        return parser.OFPMatch(**kw)

    def _install_flow(self, dp, key, out_port, meter):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        inst = []
        if meter:
            inst.append(parser.OFPInstructionMeter(METER_ID))
        inst.append(parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, [parser.OFPActionOutput(out_port)]))
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=FLOW_PRIORITY, match=self._match(parser, key),
                                      instructions=inst, command=ofp.OFPFC_ADD))

    # ---- flow-stats monitor -> classification -> policy -----------------------------------
    def _monitor(self):
        while True:
            hub.sleep(self.poll_s)
            for dp in list(self.datapaths.values()):
                ofp, parser = dp.ofproto, dp.ofproto_parser
                dp.send_msg(parser.OFPFlowStatsRequest(dp, 0, ofp.OFPTT_ALL, ofp.OFPP_ANY, ofp.OFPG_ANY,
                                                       0, 0, parser.OFPMatch()))

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats(self, ev):
        dp = ev.msg.datapath
        now = time.time()
        for st in ev.msg.body:
            if st.priority != FLOW_PRIORITY:
                continue
            m = st.match
            proto = m.get("ip_proto")
            if proto == 6:
                sp, dpt = m.get("tcp_src"), m.get("tcp_dst")
            else:
                sp, dpt = m.get("udp_src"), m.get("udp_dst")
            key = (proto, m.get("ipv4_src"), m.get("ipv4_dst"), sp, dpt)
            fl = self.flows.get((dp.id, key))
            if fl is None:
                continue
            if fl["last_t"] is not None and now > fl["last_t"]:
                dt = now - fl["last_t"]
                d_bytes = st.byte_count - fl["last_bytes"]
                d_pkts = st.packet_count - fl["last_pkts"]
                rate = d_bytes * 8 / dt / 1e6
                avg = (d_bytes / d_pkts) if d_pkts > 0 else 0.0
                if d_pkts > 0:
                    self._classify(dp, key, fl, rate, avg, d_pkts, d_bytes, dt, st)
            fl["last_bytes"], fl["last_pkts"], fl["last_t"] = st.byte_count, st.packet_count, now

    def _label(self, proto, rate):
        if proto == 17:
            return "udp_high_rate" if rate >= self.udp_high else "udp_low_rate"
        return "tcp_bulk" if rate >= self.tcp_bulk else "tcp_light"

    def _classify(self, dp, key, fl, rate, avg, d_pkts, d_bytes, dt, st):
        label = self._label(key[0], rate)
        fl["streak"] = fl["streak"] + 1 if label == fl["pending_cls"] else 1
        fl["pending_cls"] = label
        if fl["cls"] == label or fl["streak"] < self.confirm:
            return
        fl["cls"] = label
        rec = dict(ts=round(time.time(), 3), dpid=f"{dp.id:016x}", flow=self._fmt(key), proto="udp" if key[0] == 17 else "tcp",
                   rate_mbps=round(rate, 3), avg_pkt_bytes=round(avg, 1), d_packets=d_pkts, d_bytes=d_bytes,
                   interval_s=round(dt, 3), flow_age_s=st.duration_sec, cls=label,
                   features="proto,rate,avg_pkt_size,counters", model=self.model)
        self.logger.info("CLASSIFY %s", json.dumps(rec))
        if label == "udp_high_rate" and self.policy_on and not fl["policed"]:
            self._install_flow(dp, key, fl["out_port"], meter=True)
            fl["policed"] = True
            self.logger.info("POLICY %s", json.dumps(dict(ts=round(time.time(), 3), dpid=f"{dp.id:016x}",
                             flow=self._fmt(key), action=f"meter {METER_ID} drop>{self.cap_kbps}kbps",
                             policy="cap udp_high_rate", mode="ENFORCED")))
        elif label == "udp_high_rate":
            self.logger.info("POLICY %s", json.dumps(dict(ts=round(time.time(), 3), dpid=f"{dp.id:016x}",
                             flow=self._fmt(key), action="none", policy="cap udp_high_rate",
                             mode="OBSERVE_ONLY")))
