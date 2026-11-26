"""Scenario A learning-switch application for OS-Ken (OpenFlow 1.3).

Behaviour (guidebook Phase 6):
  1. install a table-miss rule (priority 0 -> controller) when a switch connects
  2. receive packet-in events for unknown traffic
  3. learn  source MAC -> ingress port  per datapath
  4. destination unknown  -> flood
  5. destination known    -> install a forwarding rule (priority 10, match in_port + eth_dst)
     so later packets are forwarded by the switch itself, without the controller.

Every event is logged with a stable prefix so the evidence can be grepped:
  SWITCH_CONNECT / TABLE_MISS / PACKET_IN / LEARN / FLOOD / FLOW_MOD
"""
from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from os_ken.lib.packet import ethernet, packet
from os_ken.ofproto import ofproto_v1_3

FORWARD_PRIORITY = 10
IDLE_TIMEOUT = 0      # 0 = permanent: keeps flow counters stable across the measurement runs
HARD_TIMEOUT = 0


class LearningSwitch(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mac_to_port = {}   # {dpid: {mac: port}}

    # ---- switch handshake ------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        self.logger.info("SWITCH_CONNECT dpid=%016x ofp_version=%s n_tables=%s",
                         dp.id, hex(dp.ofproto.OFP_VERSION), ev.msg.n_tables)
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self._add_flow(dp, 0, match, actions)
        self.logger.info("TABLE_MISS dpid=%016x installed priority=0 -> controller", dp.id)

    def _add_flow(self, dp, priority, match, actions, buffer_id=None):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        kw = dict(datapath=dp, priority=priority, match=match, instructions=inst,
                  idle_timeout=IDLE_TIMEOUT if priority else 0,
                  hard_timeout=HARD_TIMEOUT if priority else 0)
        if buffer_id is not None and buffer_id != ofp.OFP_NO_BUFFER:
            kw["buffer_id"] = buffer_id
        dp.send_msg(parser.OFPFlowMod(**kw))

    def learn(self, dp, in_port, src):
        """Remember src MAC -> ingress port for this datapath (logs LEARN on change)."""
        table = self.mac_to_port.setdefault(dp.id, {})
        if table.get(src) != in_port:
            table[src] = in_port
            self.logger.info("LEARN dpid=%016x mac=%s port=%s", dp.id, src, in_port)

    # ---- packet-in -> learn / flood / install ----------------------------
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        in_port = msg.match["in_port"]
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]
        if eth.ethertype == 0x88CC:          # ignore LLDP
            return
        dst, src, dpid = eth.dst, eth.src, dp.id
        table = self.mac_to_port.setdefault(dpid, {})
        self.logger.info("PACKET_IN dpid=%016x in_port=%s src=%s dst=%s", dpid, in_port, src, dst)
        self.learn(dp, in_port, src)

        if dst in table:
            out_port = table[dst]
            actions = [parser.OFPActionOutput(out_port)]
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
            self._add_flow(dp, FORWARD_PRIORITY, match, actions, msg.buffer_id)
            self.logger.info("FLOW_MOD dpid=%016x match(in_port=%s,eth_dst=%s) -> output:%s priority=%d",
                             dpid, in_port, dst, out_port, FORWARD_PRIORITY)
            if msg.buffer_id != ofp.OFP_NO_BUFFER:
                return                       # buffered packet is released by the flow-mod
        else:
            actions = [parser.OFPActionOutput(ofp.OFPP_FLOOD)]
            self.logger.info("FLOOD dpid=%016x dst=%s unknown", dpid, dst)

        data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None
        dp.send_msg(parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id, in_port=in_port,
                                        actions=actions, data=data))
