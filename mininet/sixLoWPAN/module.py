"""
author: Ramon Fontes (ramonrf@dca.fee.unicamp.br)
"""

import glob
import os
import re
import subprocess
import logging
from mininet.log import debug, info, error


class module(object):
    "wireless module"

    wlan_list = []
    hwsim_ids = []
    prefix = ""
    externally_managed = False
    devices_created_dynamically = False
    phyID = 0

    @classmethod
    def load_module(cls, n_radios, alternativeModule=''):
        """ Load WiFi Module 
        
        :param n_radios: number of radios
        :param alternativeModule: dir of a fakelb alternative module"""
        debug('Loading %s virtual interfaces\n' % n_radios)
        if not cls.externally_managed:
            if alternativeModule == '':
                output_ = os.system('modprobe fakelb numlbs=%s' % n_radios)
            else:
                output_ = os.system('insmod %s numlbs=0' % alternativeModule)

            if output_ == 0:
                cls.__create_hwsim_mgmt_devices(n_radios)
            else:
                # Useful for tests in Kernels like Kernel 3.13.x
                if n_radios == 0:
                    n_radios = 1
                if alternativeModule == '':
                    os.system('modprobe fakelb numlbs=%s' % n_radios)
                else:
                    os.system('insmod %s numlbs=%s' % (alternativeModule,
                                                       n_radios))
        else:
            cls.devices_created_dynamically = True
            cls.__create_hwsim_mgmt_devices(n_radios)

    @classmethod
    def __create_hwsim_mgmt_devices(cls, n_radios):
        # generate prefix
        phys = subprocess.check_output("find /sys/kernel/debug/ieee80211 -name "
                                       "hwsim | cut -d/ -f 6 | sort",
                                       shell=True).decode('utf-8').split("\n")
        num = 0
        numokay = False
        cls.prefix = ""
        while not numokay:
            cls.prefix = "mn%02ds" % num
            numokay = True
            for phy in phys:
                if phy.startswith(cls.prefix):
                    num += 1
                    numokay = False
                    break
        """try:
            for i in range(0, n_radios):
                p = subprocess.Popen(["hwsim_mgmt", "-c", "-n", cls.prefix +
                                      ("%02d" % i)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, bufsize=-1)
                output, err_out = p.communicate()
                if p.returncode == 0:
                    m = re.search("ID (\d+)", output.decode())
                    debug("Created mac80211_hwsim device with ID %s\n" % m.group(1))
                    cls.hwsim_ids.append(m.group(1))
                else:
                    error("\nError on creating mac80211_hwsim device with name %s"
                          % (cls.prefix + ("%02d" % i)))
                    error("\nOutput: %s" % output)
                    error("\nError: %s" % err_out)
        except:
            info("Warning! If you already had Mininet-WiFi installed "
                 "please run util/install.sh -W and then sudo make install.\n")"""

    @classmethod
    def kill_fakelb(cls):
        'Kill fakelb'
        info("*** Killing fakelb")
        os.system('rmmod fakelb')

    @classmethod
    def stop(cls):
        'Stop wireless Module'
        if glob.glob("*.apconf"):
            os.system('rm *.apconf')
        if glob.glob("*.staconf"):
            os.system('rm *.staconf')
        if glob.glob("*wifiDirect.conf"):
            os.system('rm *wifiDirect.conf')
        if glob.glob("*.nodeParams"):
            os.system('rm *.nodeParams')

        try:
            (subprocess.check_output("lsmod | grep ifb", shell=True))
            os.system('rmmod ifb')
        except:
            pass

        try:
            confnames = "mn%d_" % os.getpid()
            os.system('pkill -f \'wpa_supplicant -B -Dnl80211 -c%s\''
                      % confnames)
        except:
            pass

        try:
            pidfiles = "mn%d_" % os.getpid()
            os.system('pkill -f \'wpa_supplicant -B -Dnl80211 -P %s\''
                      % pidfiles)
        except:
            pass

        cls.kill_fakelb()

    @classmethod
    def start(cls, nodes, n_radios, alternativeModule='', **params):
        """Starts environment
        
        :param nodes: list of wireless nodes
        :param n_radios: number of wifi radios
        :param alternativeModule: dir of a fakelb alternative module
        :param **params: ifb -  Intermediate Functional Block device
        """
        """kill hostapd if it is already running"""
        try:
            h = subprocess.check_output("ps -aux | grep -ic \'hostapd\'",
                                        shell=True)
            if h >= 2:
                os.system('pkill -f \'hostapd\'')
        except:
            pass

        cls.load_module(n_radios, alternativeModule)  # Initatilize WiFi Module
        phys = cls.get_virtual_wlan()  # Get Phy Interfaces
        cls.assign_iface(nodes, phys, **params)  # iface assign

    @classmethod
    def get_virtual_wlan(cls):
        'Gets the list of virtual wlans that already exist'
        cls.wlans = []
        cls.wlans = (subprocess.check_output("iwpan dev 2>&1 | grep Interface "
                                             "| awk '{print $2}'",
                                             shell=True)).split("\n")
        cls.wlans.pop()
        cls.wlan_list = sorted(cls.wlans)
        cls.wlan_list.sort(key=len, reverse=False)
        return cls.wlan_list

    @classmethod
    def getPhy(cls, wlan):
        'Gets the list of virtual wlans that already exist'
        phy = (subprocess.check_output("iwpan dev | grep -B 1 %s"
                                       " | sed -ne '1 s/phy#\([0-9]\)/\\1/p'" % wlan,
                                       shell=True)).split("\n")
        phy.pop()
        return phy[0]

    @classmethod
    def load_ifb(cls, wlans):
        """ Loads IFB
        
        :param wlans: Number of wireless interfaces
        """
        debug('\nLoading IFB: modprobe ifb numifbs=%s' % wlans)
        os.system('modprobe ifb numifbs=%s' % wlans)

    @classmethod
    def assign_iface(cls, nodes, phys, **params):
        """Assign virtual interfaces for all nodes
        
        :param nodes: list of wireless nodes
        :param phys: list of phys
        :param **params: ifb -  Intermediate Functional Block device"""
        from mininet.wifi.node import Station, Car

        log_filename = '/tmp/mininetwifi-mac80211_hwsim.log'
        cls.logging_to_file("%s" % log_filename)

        try:
            debug("\n*** Configuring interfaces with appropriated network"
                  "-namespaces...\n")
            for node in nodes:
                if (isinstance(node, Station) or isinstance(node, Car)) \
                        or 'inNamespace' in node.params:
                    node.ifb = []
                    for wlan in range(0, len(node.params['wlan'])):
                        node.phyID[wlan] = cls.phyID
                        cls.phyID += 1
                        #rfkill = os.system(
                        #    'rfkill list | grep %s | awk \'{print $1}\' '
                        #    '| tr -d \":\" >/dev/null 2>&1' % phys[0])
                        #debug('rfkill unblock %s\n' % rfkill)
                        #os.system('rfkill unblock %s' % rfkill)
                        phy = cls.getPhy(phys[0])
                        os.system('iwpan phy phy%s set netns %s' % (phy, node.pid))
                        node.cmd('ip link set %s down' % cls.wlan_list[0])
                        node.cmd('ip link set %s name %s'
                                 % (cls.wlan_list[0], node.params['wlan'][wlan]))
                        cls.wlan_list.pop(0)
        except:
            logging.exception("Warning:")
            info("Warning! Error when loading mac80211_hwsim. "
                 "Please run sudo 'mn -c' before running your code.\n")
            info("Further information available at %s.\n" % log_filename)
            exit(1)

    @classmethod
    def logging_to_file(cls, filename):
        logging.basicConfig(filename=filename,
                            filemode='a',
                            level=logging.DEBUG,
                            format='%(asctime)s - %(levelname)s - %(message)s',
                           )
