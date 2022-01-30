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
        self.link_to_port = {} 

    def _discover(self):
        while True:
            self.show_topo()
            hub.sleep(5)

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

        #links = get_link(self.topology_api_app, None)
        #self.create_interior_links(links)
        #self.create_access_ports()
        #self.get_graph(self.link_to_port.keys())
    
        return self.network

    def create_interior_links(self, link_list):
        """
            Create a list of the links and the ports connecting the links
        """
        for link in link_list:
            src = link.src
            dst = link.dst
            self.link_to_port[
                (src.dpid, dst.dpid)] = (src.port_no, dst.port_no)
