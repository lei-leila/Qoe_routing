#-------------------------------------------------------------------------------
# Name:        module1
# Purpose:
#
# Author:      leiw0
#
# Created:     10/01/2022
# Copyright:   (c) leiw0 2022
# Licence:     <your licence>
#-------------------------------------------------------------------------------
from os import link
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER , MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.topology import event
from ryu.topology.api import get_switch, get_link
import networkx as nx
import signal
import network_info, network_metrics
import ml_models_applying
from itertools import islice
import pickle
import pandas
import numpy as np





class QoeForwarding(app_manager.RyuApp):
    """
       QoeForwarding is a Ryu app for forwarding flows in terms of predicted QoE results from ML models.

    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {
        "network_info": network_info.NetworkInfo,
        "network_metrics": network_metrics.NetworkMetrics,
        "ml_model": ml_models_applying.MlModles
      }

    def __init__(self, *args, **kwargs):
        super(QoeForwarding, self).__init__(*args, **kwargs)
        self.name = "qoe_forwarding"
        self.mac_to_port = {}
        self.network = nx.DiGraph()
        self.graph = {}
        self.topology_api_app = self
        self.paths = {}
        self.network_info= kwargs["network_info"]
        self.ml_model = kwargs["ml_model"]
        self.delay_detector = kwargs["network_metrics"]
        self.path_list = []
        self.link_metrics_list = [[8,7,200,100,0.5,0.2],[6, 9, 50, 132, 0.1, 0.1]]


    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self,ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        msg = ev.msg
        self.logger.info("switch %s connected", datapath.id)

         # install table-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]

        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions (ofproto.OFPIT_APPLY_ACTIONS,
                                              actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority= priority, match = match, instructions= inst)
        datapath.send_msg(mod)

    events = [event.EventSwitchEnter]
    # when the switch enters, or other change of the network happens, network topology information get updated
    @set_ev_cls(events)
    def get_topology(self, ev):
        self.network = self.network_info.get_topo(ev)


   # call the ml model here 
    def call_ml(self, metrics, model_name): #input metrics are list form
        X_test=np.array(metrics)     #np.array the list metrics
        self.model = pickle.load(open(model_name, 'rb'))  #load the ml model
        self.qoe = self.model.predict([X_test])
        return self.qoe



    def select_path(self, src, dst, graph):
        
        qoe_list=[]
        link_metrics =[]
        self.graph  =  graph
        self.path_list =  list(islice(nx.shortest_simple_paths(graph, source=src,
                                             target=dst),2))                            # break the path

        self.model = self.ml_model.filename

        print ("++++++++++available paths are +++++++++++++++++++",self.path_list)
        for path in self.path_list:
          
            #link_metrics = self.link_metrics_list[self.path_list.index(path)]
            link_metrics = self.delay_detector.get_path_metrics(path)
            print ("*********link metrics is *********", link_metrics)
            qoe_v = self.call_ml(link_metrics,'finalized_model.sav')
            qoe_list.append(qoe_v)
        

        print ("@@@@@@@@@@@@@@@@@@@@@@@@@ qoe list is: @@@@@@@@@@@@@@@@",qoe_list)
      

        self.selected_path = self.path_list[qoe_list.index(max(qoe_list))]  # the selected path is the path with max qoe predicted

        return self.selected_path


    # get outport by shortest hop
    def get_out_port(self, datapath, src, dst, in_port):
        dpid = datapath.id
        #add link between host and access switch
        if src not in self.network:
            self.network.add_node(src)
            self.network.add_edge(dpid, src, port=in_port)
            self.network.add_edge(src, dpid)
            self.paths.setdefault(src, {})

        if dst in self.network:
            if dst not in self.paths[src]:
                path = self.select_path(src, dst, self.network)

                #path = nx.shortest_path(self.network, src, dst)
       #         self.paths[src][dst] = path

        #    path = self.paths[src][dst]
            next_hop = path[path.index(dpid)+1]
            print ("----------------path-----------------:", path)
            out_port= self.network[dpid][next_hop]['port']
        else:
            out_port = datapath.ofproto.OFPP_FLOOD

        return out_port




    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg= ev.msg
        datapath = msg.datapath
        ofproto= datapath.ofproto
        parser = datapath.ofproto_parser

        in_port = msg.match["in_port"]
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols( ethernet.ethernet)[0]
        src = eth.src
        dst = eth.dst

        dpid = datapath.id
        self.mac_to_port.setdefault( dpid , {})
      #  self.logger.info("packet in %s %s %s %s", dpid, src, dst, in_port)
        self.mac_to_port[dpid][src] = in_port
       

        out_port = self.get_out_port(datapath, src, dst, in_port)
        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
            self.add_flow(datapath, 1, match, actions)
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port = in_port, actions=actions, data=data)
        datapath.send_msg(out)


class GetNetwork():
    pass






