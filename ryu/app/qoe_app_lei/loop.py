#-------------------------------------------------------------------------------
# Name:        module1
# Purpose:
#
# Author:      leiw0
#
# Created:     29/12/2021
# Copyright:   (c) leiw0 2021
# Licence:     <your licence>
#-------------------------------------------------------------------------------

#!/usr/bin/python

from mininet.topo import Topo

from mininet.cli import CLI
from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel

from mininet.node import RemoteController

REMOTE_CONTROLLER_IP = "127.0.0.1"


def simpleTest():
    # Create and test a simple network
    topo = SingleLoopTopo()

    net = Mininet(topo=topo,
                  controller=None,
                  autoStaticArp=True)
    net.addController("c0",
                      controller=RemoteController,
                      ip=REMOTE_CONTROLLER_IP,
                      port=6633)
    net.start()
    print ("Dumping host connections")
    dumpNodeConnections(net.hosts)
    print ("Testing network connectivity")
   # net.pingAll()
    net.stop()


class SingleLoopTopo(Topo):
    # Single switch connected to n hosts
    def __init__(self, **opts):
        # Initialize topology and default optioe
        Topo.__init__(self, **opts)
        switches = []
        hosts = []

        # create switches
        for s in range(4):
            switches.append(self.addSwitch('s%s' % (s + 1), protocols='OpenFlow13'))

        # create hosts
        for h in range(3):
            hosts.append(self.addHost('h%s' % (h + 1)))

        self.addLink(hosts[0], switches[0])
        self.addLink(hosts[1], switches[2])
        self.addLink(hosts[2], switches[3])


        self.addLink(switches[0], switches[1], bw=4, delay='100ms', loss=1)
     #   self.addLink(switches[0], switches[3])
        self.addLink(switches[1], switches[2],bw=10, delay='100ms', loss=1)
        self.addLink(switches[2], switches[3],bw=8, delay='100ms', loss=0.5)
        self.addLink(switches[3], switches[1],bw=8, delay='100ms', loss=0.8) #bw = 10Mps, delay = 100ms, packetloss= 0.8%



if __name__ == '__main__':
    # Tell mininet to print useful information
    setLogLevel('info')
    simpleTest()
    topo = SingleLoopTopo()
    net = Mininet(topo=topo,
                  controller=None,
                  autoStaticArp=True)
    net.addController("c0",
                      controller=RemoteController,
                      ip=REMOTE_CONTROLLER_IP,
                      port=6633)
    net.start()
    CLI(net)
    net.stop()