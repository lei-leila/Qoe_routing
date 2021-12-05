# Copyright (C) 2016 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from operator import attrgetter
from ryu.base import app_manager
from ryu.app import my_switch_13
from ryu.controller import ofp_event
from ryu.controller.handler import (MAIN_DISPATCHER, CONFIG_DISPATCHER, 
                                   DEAD_DISPATCHER)
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.lib import hub
from ryu.topology import event
from ryu.topology.api import get_switch, get_link
import networkx as nx
import copy
import csv

class MyMonitor13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    def __init__(self, *args, **kwargs):
        super(MyMonitor13, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.topo_raw_switches = []
        self.topo_raw_links = []
        self.stats = {}
        self.port_stats = {}
        self.flow_stats = {}
        self.queue_stats = {}
        self.datapaths = {}
        self.prev_time = 0
        self.net = nx.DiGraph()
        self.no_of_nodes = 0
        self.no_of_links = 0
        self.topology_api_app = self
        self.monitor_thread = hub.spawn(self._monitor)
        self.duration = 10

    @set_ev_cls(ofp_event.EventOFPStateChange,
                [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        #OVSDB_ADDR = 'tcp:127.0.0.1:6632'
        #ovs_vsctl = vsctl.VSCtl(OVSDB_ADDR)

        
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.logger.debug('register datapath: %016x', datapath.id)
                self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                self.logger.debug('unregister datapath: %016x', datapath.id)
                del self.datapaths[datapath.id]

    def _monitor(self):
        while True:
            self.stats['flow'] = {}
            self.stats['port'] = {}
            self.stats['queue'] = {}
            for dp in self.datapaths.values():
                self._request_stats(dp)
            hub.sleep(self.duration)
            #if self.stats['queue']:
            #    self.show_stat('queue')
            #    hub.sleep(1)
            #if self.stats['flow'] or self.stats['port']:
            #    self.show_stat('flow')
            #    self.show_stat('port')
            #    hub.sleep(1)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        # If you hit this you might want to increase
        # the "miss_send_length" of your switch
        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.debug("packet truncated: only %s of %s bytes",
                              ev.msg.msg_len, ev.msg.total_len)
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            # ignore lldp packet
            return
        dst = eth.dst
        src = eth.src

        dpid = format(datapath.id, "d").zfill(16)
        self.mac_to_port.setdefault(dpid, {})

        self.logger.info("packet in %s %s %s %s", dpid, src, dst, in_port)

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            # verify if we have a valid buffer_id, if yes avoid to send both
            # flow_mod & packet_out
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                return
            else:
                self.add_flow(datapath, 1, match, actions)
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
    
    def _request_stats(self, datapath):
        self.logger.debug('send stats request: %016x', datapath.id)
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)

        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        #self.logger.info("Port stats request")
        #self.logger.info(req)
        datapath.send_msg(req)
        
        #self.logger.info("Sending Queue stats request") 
        req = parser.OFPQueueStatsRequest(datapath, 0, ofproto.OFPP_ANY,
                                          ofproto.OFPQ_ALL)
        #req = parser.OFPQueueGetConfigRequest(datapath, ofproto.OFPP_ANY)
        #self.logger.info(req)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply_handler(self, ev):
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        self.stats['flow'][dpid] = body
        self.flow_stats.setdefault(dpid, {})
        for stat in sorted([flow for flow in body if flow.priority == 1],
                           key=lambda flow: (flow.match.get('in_port'),
                                             flow.match.get('eth_dst'))):
            key = (stat.match['in_port'],  stat.match.get('eth_dst'),
                   stat.instructions[0].actions[0].port)
            value = (stat.packet_count, stat.byte_count,
                     stat.duration_sec, stat.duration_nsec)
            self._save_stats(self.flow_stats[dpid], key, value, 5)
        #self.logger.info(self.flow_stats)
#        body = ev.msg.body
#
#        self.logger.info('datapath         '
#                         'in-port  eth-dst           '
#                         'out-port packets  bytes')
#        self.logger.info('---------------- '
#                         '-------- ----------------- '
#                         '-------- -------- --------')
#        for stat in sorted([flow for flow in body if flow.priority == 1],
#                           key=lambda flow: (flow.match['in_port'],
#                                             flow.match['eth_dst'])):
#            self.logger.info('%016x %8x %17s %8x %8d %8d',
#                             ev.msg.datapath.id,
#                             stat.match['in_port'], stat.match['eth_dst'],
#                             stat.instructions[0].actions[0].port,
#                             stat.packet_count, stat.byte_count)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        self.stats['port'][dpid] = body

        for stat in sorted(body, key=attrgetter('port_no')):
            port_no = stat.port_no
            if port_no != ofproto_v1_3.OFPP_LOCAL:
                key = (dpid, port_no)
                value = (stat.tx_bytes, stat.rx_bytes, stat.rx_errors,
                         stat.duration_sec, stat.duration_nsec)
                #self.logger.info('Computing ' + str(stat.duration_sec) + ' - ' + str(self.prev_time))
        #for stat in sorted(bod):
                #if str(port_no) == '2':
                #    self.logger.info('Switch ' + str(dpid))
                #    #tx_bytes = stat.tx_bytes
                #    bw = 2*(stat.tx_bytes-stat.rx_bytes)/self.duration# - self.prev_bw[str(dpid)]
                #    self.logger.info('Original BW: ' + str(bw/1.25e+8))
                #elif str(port_no) == '1':
                #    rx_bytes = stat.rx_bytes
                self.calculate_bw(dpid, port_no, stat.tx_bytes, stat.rx_bytes)
                self._save_stats(self.port_stats, key, value, 5)
        #self.prev_bw[str(dpid)] = bw
        #self.prev_time = copy.copy(stat.duration_sec)

        #self.logger.info(self.port_stats)

    def calculate_bw(self, dpid, port_no, tx_bytes, rx_bytes):
        if str(port_no) == '2':
                #tx_bytes = port_stats[stat][0][0]
                #rx_bytes = port_stats[stat][0][1]
            self.logger.info('Switch ' + str(dpid))
            self.bw = 10 - ((tx_bytes - rx_bytes)/self.duration)/1.25e+8
            self.logger.info('BW: ' + str(self.bw) + '\n')
            #self.logger.info('Switch: ' + str(stat[0]))
            #self.logger.info('Tx Bytes: ' + str(port_stats[stat][0][0]))
            #self.logger.info('Rx Bytes: ' + str(port_stats[stat][0][1]))
            

#    @set_ev_cls(ofp_event.EventOFPQueueGetConfigReply, MAIN_DISPATCHER)
#    def queue_get_config_reply_handler(self, ev):
#        msg = ev.msg
#        
#        self.logger.debug('OFPQueueGetConfigReply received: '
#                          'port=%s queues=%s',
#                           msg.port, msg.queues)    

    @set_ev_cls(ofp_event.EventOFPQueueStatsReply, MAIN_DISPATCHER)
    def queue_stats_reply_handler(self, ev):
        queues = []
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        self.stats['queue'][dpid] = body
    

        for stat in sorted(body, key=attrgetter('queue_id')):
            queue_id = stat.queue_id
            key = (dpid, queue_id)
            value = (stat.port_no, stat.tx_bytes, stat.tx_packets,
                     stat.tx_errors, stat.duration_sec, stat.duration_nsec)
            self._save_stats(self.queue_stats, key, value, 6)
        
            #queues.append('port_no=%d queue_id=%d '
            #              'tx_bytes=%d tx_packets=%d tx_errors=%d '
            #              'duration_sec=%d duration_nsec=%d' %
            #              (stat.port_no, stat.queue_id,
            #               stat.tx_bytes, stat.tx_packets, stat.tx_errors,
            #               stat.duration_sec, stat.duration_nsec))
        #self.logger.info('QueueStats: %s', queues) 

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        msg = ev.msg
        self.logger.info('OFPSwitchFeatures received: '
                         '\n\tdatapath_id=0x%016x n_buffers=%d '
                         '\n\tn_tables=%d auxiliary_id=%d '
                         '\n\tcapabilities=0x%08x',
                         msg.datapath_id, msg.n_buffers, msg.n_tables,
                         msg.auxiliary_id, msg.capabilities)
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # install table-miss flow entry
        #
        # We specify NO BUFFER to max_len of the output action due to
        # OVS bug. At this moment, if we specify a lesser number, e.g.,
        # 128, OVS will send Packet-In with invalid buffer_id and
        # truncated packet data. In that case, we cannot output packets
        # correctly.  The bug has been fixed in OVS v2.1.0.
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)


    @set_ev_cls(event.EventSwitchEnter)
    def get_topology_data(self, ev):
        self.topo_raw_switches = get_switch(self.topology_api_app, None)   
        switches=[switch.dp.id for switch in self.topo_raw_switches]
        self.net.add_nodes_from(switches)
         
        print ("**********List of switches")
        for switch in self.topo_raw_switches:
            print (switch)
            self.no_of_nodes += 1
	
        self.topo_raw_links = get_link(self.topology_api_app, None)
        links=[(link.src.dpid,link.dst.dpid,{'port':link.src.port_no}) for link in self.topo_raw_links]
        self.net.add_edges_from(links)
        links=[(link.dst.dpid,link.src.dpid,{'port':link.dst.port_no}) for link in self.topo_raw_links]
        self.net.add_edges_from(links)
        print ("**********List of links")
        print (self.net.edges())
        for link in self.topo_raw_links:
            print(link)
            self.no_of_links +=1


    @set_ev_cls(event.EventSwitchLeave, [MAIN_DISPATCHER, CONFIG_DISPATCHER, DEAD_DISPATCHER])
    def handler_switch_leave(self, ev):
        self.logger.info("Not tracking Switches, switch leaved.")
        self.logger.info(self.no_of_nodes)        
        self.logger.info(self.no_of_links)        

    def _save_stats(self, _dict, key, value, length):
        if key not in _dict:
            _dict[key] = []
        _dict[key].append(value)

        if len(_dict[key]) > length:
            _dict[key].pop(0)

    def show_stat(self, type):
        '''
            Show statistics info according to data type.
            type: 'port' 'flow' 'queue'
        '''

        bodys = self.stats[type]
        if(type == 'flow'):
            print('datapath         ''   in-port        eth-dst      '
                  'out-port packets  bytes')
            print('---------------- ''  -------- ----------------- '
                  '-------- -------- --------')
            for dpid in bodys.keys():
                for stat in sorted(
                    [flow for flow in bodys[dpid] if flow.priority == 1],
                    key=lambda flow: (flow.match.get('in_port'),
                                      flow.match.get('eth_dst'))):
                    print('%016x %8x %17s %8x %8d %8d' % (
                        dpid,
                        stat.match['in_port'], stat.match['eth_dst'],
                        stat.instructions[0].actions[0].port,
                        stat.packet_count, stat.byte_count))
            print('\n')

        if(type == 'port'):
            print('datapath             port   ''rx-pkts  rx-bytes rx-error '
                  'tx-pkts  tx-bytes tx-error')
            print('----------------   -------- ''-------- -------- -------- '
                  '-------- -------- -------- ')
            format = '%016x %8x %8d %8d %8d %8d %8d %8d'
            for dpid in bodys.keys():
                for stat in sorted(bodys[dpid], key=attrgetter('port_no')):
                    if stat.port_no != ofproto_v1_3.OFPP_LOCAL:
                        print(format % (
                            dpid, stat.port_no,
                            stat.rx_packets, stat.rx_bytes, stat.rx_errors,
                            stat.tx_packets, stat.tx_bytes, stat.tx_errors,))
            print('\n')
        
        if(type == 'queue'):
            print('datapath           queue-id  port''  tx-bytes  tx-pkts  tx-error  '
                  'duration_sec  duration_nsec')
            print('----------------   --------  ----''  --------  -------  --------  '
                  '------------  -------------')
            format = '%016x %6x %7x %10d %7d %8d %15d %13d'
            for dpid in bodys.keys():
                for stat in sorted(bodys[dpid], key=attrgetter('queue_id')):
                    print(format % (
                        dpid, stat.queue_id, stat.port_no,
                        stat.tx_bytes, stat.tx_packets, stat.tx_errors,
                        stat.duration_sec, stat.duration_nsec,))
            print('\n')

#app_manager.require_app('ryu.app.rest_qos')
#app_manager.require_app('ryu.app.rest_conf_switch')
#app_manager.require_app('ryu.app.ofctl_rest')
    
    #def handler_switch_enter(self, ev):
    #    #cop.copy creates a shallow copy of the lists returned by get_switch and get_link
    #    self.topo_raw_switches = copy.copy(get_switch(self, None))
    #    self.topo_raw_links = copy.copy(get_link(self, None))

    #    print(" \t" + "Current Links:")
    #    for l in self.topo_raw_links:
    #        print (" \t\t" + str(l))

    #    print(" \t" + "Current Switches:")
    #    for s in self.topo_raw_switches:
    #        print (" \t\t" + str(s))

#   def write_stats_to_file(self, ev)
#        body = ev.msg.body
#        path_to_file = 'NetworkStats.csv'
#        
#        self.logger.info('datapath         port     '
#                         'rx-pkts  rx-bytes rx-error '
#                         'tx-pkts  tx-bytes tx-error')
#        self.logger.info('---------------- -------- '
#                         ' -------- -------- -------- '
#                         '-------- -------- --------')
#        data = []
#        
#        for stat in sorted(body, key=attrgetter('port_no')):
#            self.logger.info('%016x %8x %8d %8d %8d %8d %8d %8d',
#                                ev.msg.datapath.id, stat.port_no,
#                                stat.rx_packets, stat.rx_bytes, stat.rx_errors,
#                                stat.tx_packets, stat.tx_bytes, stat.tx_errors)
#           
#            data.append({'datapath': ev.msg.datapath.id, 'port': stat.port_no,
#                    'rx-pkts': stat.rx_packets, 'rx-bytes': stat.rx_bytes,
#                    'rx-error': stat.rx_errors, 'tx-pkts': stat.tx_packets,
#                    'tx-bytes': stat.tx_bytes, 'tx-error': stat.tx_errors
#                  })
#            
#        with open(path_to_file, "a") as file:
#            csv_writer = csv.writer(file)
#            for count,row in enumerate(data):
#                if count == 0:
#                    header=row.keys()
#                    csv_writer.writerow(header)
#                    count +=1
#                
#                csv_writer.writerow(row.values())
#            csv_writer.writerow([])
