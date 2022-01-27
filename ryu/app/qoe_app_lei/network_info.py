from ryu.base import app_manager
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
import networkx as nx
from ryu.topology.api import get_switch, get_link

class NetworkInfo(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(NetworkInfo, self).__init__(*args, **kwargs)
        self.name = "network_info"
        self.network = nx.DiGraph()
        self.topology_api_app = self
        self.paths = []
        self.switches=[]
        self.links = []

    def get_topo(self, ev):
     #   print ("topology changed!!!!!!!!!!!!!!!!!!11")
        switch_list = get_switch(self.topology_api_app, None)
        self.switches = [switch.dp.id for switch in switch_list]
        self.network.add_nodes_from(self.switches)

        link_list = get_link(self.topology_api_app, None)
     #   print("******************link list are:***********",link_list)
        self.links = [(link.src.dpid, link.dst.dpid, {'port':link.src.port_no}) for link in link_list]
        self.network.add_edges_from(self.links)
        self.links = [(link.dst.dpid, link.src.dpid, {'port':link.dst.port_no}) for link in link_list]
        self.network.add_edges_from(self.links)
        print("******************links are:***********",self.links)

        links = get_link(self.topology_api_app, None)
        self.create_interior_links(links)
        self.create_access_ports()
        self.get_graph(self.link_to_port.keys())
    
        return self.network
    
  