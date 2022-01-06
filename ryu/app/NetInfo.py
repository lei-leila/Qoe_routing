from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
import networkx as nx
from ryu.topology import event, switches
from ryu.topology.api import get_all_switch, get_all_link, get_all_host

class NetInfo(app_manager.RyuApp):
    def __init__(self, *args, **kwargs):
        super(NetInfo, self).__init__(*args, **kwargs)
        self.topo_raw_switches = {}
        self.topo_raw_links = {}
        self.no_of_nodes = 0
        self.no_of_links = 0
        self.topology_api_app = self
        self.graph = nx.DiGraph()
        self. path_metrics = {}

    def get_topology(self):
        self.get_topology_data()
        self.get_paths(self.graph)

    def get_host_info(self):
        hosts = get_all_host(self.topology_api_app)
        print("Hosts are : " + str(hosts))

    #@set_ev_cls(event.EventSwitchEnter)
    def get_topology_data(self):
        self.topo_raw_switches = get_all_switch(self.topology_api_app)
        switches = [switch.dp.id for switch in self.topo_raw_switches]
        self.graph.add_nodes_from(switches)
        print("The nodes are: " + str(switches))

        print("**********List of switches")
        for switch in self.topo_raw_switches:
            print(switch)
            self.no_of_nodes += 1

        self.topo_raw_links = get_all_link(self.topology_api_app)
        links = [(link.src.dpid, link.dst.dpid, {'port': link.src.port_no})
                 for link in self.topo_raw_links]
        self.graph.add_edges_from(links)
        #links = [(link.dst.dpid, link.src.dpid, {'port': link.dst.port_no})
        #         for link in self.topo_raw_links]
        #self.graph.add_edges_from(links)
        print("**********List of links")
#        print(self.graph.edges())
        for link in self.topo_raw_links:
            print(link)
            self.no_of_links += 1
        return self.graph

    def get_paths(self, G):
        paths = list(nx.all_simple_paths(G, source=1, target=3))
        for path in paths:
            print(path)
