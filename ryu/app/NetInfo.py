from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
import networkx as nx


class NetInfo():
    def __init__(self, *args, **kwargs):
        super(NetInfo, self).__init__(*args, **kwargs)
        self.topo_raw_switches = {}
        self.topo_raw_links = {}
        self.no_of_nodes = 0
        self.no_of_links = 0
        self.topology_api_app = self
        self.graph = nx.DiGraph()
        self. path_metrics = {}

    def get_topology(self, ev):
        self.get_topology_data(ev)
        self.get_paths()

    #@set_ev_cls(event.EventSwitchEnter)
    def get_topology_data(self, ev):
        self.topo_raw_switches = get_switch(self.topology_api_app, None)
        switches = [switch.dp.id for switch in self.topo_raw_switches]
        self.graph.add_nodes_from(switches)

        print("**********List of switches")
        for switch in self.topo_raw_switches:
            print(switch)
            self.no_of_nodes += 1

        self.topo_raw_links = get_link(self.topology_api_app, None)
        links = [(link.src.dpid, link.dst.dpid, {'port': link.src.port_no})
                 for link in self.topo_raw_links]
        self.graph.add_edges_from(links)
        links = [(link.dst.dpid, link.src.dpid, {'port': link.dst.port_no})
                 for link in self.topo_raw_links]
        self.graph.add_edges_from(links)
        print("**********List of links")
        print(self.net.edges())
        for link in self.topo_raw_links:
            print(link)
            self.no_of_links += 1

    def get_paths(self):
        self.graph['paths'] = list(nx.all_simple_paths(G, source=0, target=3))
        for path in graph['paths']:
            print(path)