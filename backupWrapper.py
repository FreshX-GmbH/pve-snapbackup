from proxmoxer import ProxmoxAPI
import re
import time
import subprocess
import shlex
import json
from datetime import datetime
import logging, coloredlogs
import yaml
import sys
import os

# Config File definition
configFile = 'settings.yml'
# default log format + level
coloredlogs.install(fmt='%(asctime)s [%(filename)s] %(levelname)s %(message)s', level=logging.DEBUG)
logging.info('Starting script execution')

# read config file or die!
logging.info(f'Reading config file {configFile}')
if not os.path.exists(configFile):
    logging.error(f'Config File {configFile} not found. Exiting!')
    sys.exit(1)
with open(configFile, 'r') as ymlfile:
    try:
        cfg = yaml.load(ymlfile, Loader=yaml.FullLoader)
        logging.debug(f'Contents of config file {configFile}:')
        logging.debug(cfg)

    except:
        logging.warning(f'Failed to load  file {configFile}. Continue with defaults - that will most likely fail!')
        cfg = {}

# global stuff - populate config dict or die!
defaults = {
    'nodeFilter': 'compute', # Filter String for pve hostnames to search for vms to backup
    'vmFilter': 'benjiBackup=true', # Filter String to search for in VM description to decide if we back up the vm
    'snapRegex': '^b_', # Snapshot prefix to use - so we do not interfere with other snapshots
    'snapMaxAge': int(172800), # 48h
    'logFile': '/var/log/pvesnapbackup', # this is not yet implemented
    'pve': {
        'apiEndpoint': 'localhost',
        'apiUser': 'root@pam',
        'apiPwd': 'changeMe',
        'verifySsl': True
    }
}

# build configuration from defaults and config file
def buildConf(cfg):
    __conf = {
        'pveApiEndpoint': str(cfg.get('pve', {}).get('apiEndpoint', defaults['pve']['apiEndpoint'])),
        'pveApiUser': str(cfg.get('pve', {}).get('apiUser', defaults['pve']['apiUser'])),
        'pveApiPwd': str(cfg.get('pve', {}).get('apiPwd', defaults['pve']['apiPwd'])),
        'pveVerifySsl': bool(cfg.get('pve', {}).get('verifySsl', defaults['pve']['verifySsl'])),
        'nodeFilter': str(cfg.get('nodeFilter', defaults['nodeFilter'])),
        'vmFilter': str(cfg.get('vmFilter', defaults['vmFilter'])),
        'snapRegex': str(cfg.get('snapRegex', defaults['snapRegex'])),
        'snapMaxAge': int(cfg.get('snapMaxAge', defaults['snapMaxAge'])),
        'logFile': str(cfg.get('logFile', defaults['logFile'])),
        'logLevel': str(cfg.get('logLevel'))

    }
    return __conf

# build conf dict
logging.debug(f'Generating config object')
conf = buildConf(cfg)
logging.debug(f'Running with the following config: {conf}')
if conf['logLevel'] != 'None':
    __logLevel = getattr(logging, conf['logLevel'].upper())
    logging.debug(f'Setting log level to {conf["logLevel"]}')
    logging.getLogger().setLevel(__logLevel)
logging.debug(conf)
sys.exit()

# Global dict with nodes and vmids
toBackupDict = {}
# Track VM Snapshots to prevent unnecessary snapshots
vmList = []
# Proxmox API Object
proxmox = ProxmoxAPI(conf['pveApiEndpoint'], user=conf['pveApiUser'], password=conf['pveApiPwd'], verify_ssl=conf['pveVerifySsl'])

# returns a list of proxmox nodes matching the filterString  
def getNodeList():
    __nodeList = []
    for node in proxmox.nodes.get():
        if conf['nodeFilter'] in node['node']:
            __nodeList.append(node['node'])
    return __nodeList

# takes a proxmox node as argument, returns a list VMs configured for backup (description contains 'vmFilter' string)
def getVmList(node):
    __vmList = []
    for vm in proxmox.nodes(node).qemu.get():
        __config = proxmox.nodes(node).qemu(vm['vmid']).config.get()
        if 'description' in __config:
            __description = __config['description']
            if conf['vmFilter'] in __description:
                __vmList.append(vm['vmid'])
    return __vmList

# takes a proxmox node and a vmid as argument and creates a list of snapshots
def getSnapList(node, vmid):
    # get a list of all snapshots
    __snapshots = proxmox.nodes(node).qemu(vmid).snapshot.get()
    # filter out all benji snapshots - we do not touch other snapshots
    __benjiSnapshots = []
    for el in __snapshots: 
        if re.search(conf['snapRegex'], el['name']):
            __benjiSnapshots.append(el)
    return __benjiSnapshots

# takes a proxmox node and a vmid as argument and takes a snapshot of the given vm - named with b_datetimestamp
# Example Code for a snapshot!
#proxmox.nodes('pve-compute01').qemu('104').snapshot.create(snapname='test')
def takeSnapshot(node, vmid):
    __now = datetime.now()
    __snapPrefix = 'b_'
    __snapTimestamp = __now.strftime("%Y_%m_%d_T%H_%M_%S")
    __snapName = __snapPrefix + __snapTimestamp
    logging.info(f'Invoking snapshot for VMID: {vmid}')
    proxmox.nodes(node).qemu(vmid).snapshot.create(snapname=__snapName)
    # sleep while waiting for snapshot to complete
    # TODO: error handling when snapshot hangs!!!
    __exists = False
    __loopcount = 0
    while not __exists:
        __loopcount += __loopcount
        if __loopcount > 12:
            logging.info('Snapshot hanging... Aborting backup!')
            break
        logging.info('Waiting for new Snapshot to be completed...')
        time.sleep(5)
        __snapshots = getSnapList(node, vmid)
        if len(__snapshots) > 0:
            for element in __snapshots:
                if element['name'] == __snapName:
                    if not 'snapstate' in __snapshots[0]:
                        __exists = True
                        __snapshots.sort(key = lambda i: i['snaptime'], reverse=True)
                        if __snapshots[0]['name'] == __snapName:
                            __snap = __snapshots[0]
                        else:
                            sys.exit("Something went wrong while creating a new snapshot")
                        logging.info(f'snapshot done: {__snap}')
                        return __snap

# takes node, vmid, snapname as arguments, returns Snapshot info dictionary
def getSnapConfig(node, vmid, snapname):
    __snapConf = proxmox.nodes(node).qemu(vmid).snapshot(snapname).config.get()
    return __snapConf

# takes node, vmid, pve-api snapshot dict as arguments - deletes given snapshot
def deleteSnapshot(node, vmid, snapshot):
     logging.info(f'Deleting Snapshot {snapshot["name"]}')
     proxmox.nodes(node).qemu(vmid).snapshot(snapshot['name']).delete()
     # wait until the snapshot does not longer appear in snapshot list
     # TODO: maybe introduce max waiting time and panic if deletion lasts longer than e.g. 5 Minutes
     __exists = True
     while __exists: 
         logging.info('waiting for snapshot to be deleted')
         time.sleep(10)
         __list = getSnapList(node, vmid)
         if not any(d['name'] == snapshot['name'] for d in __list):
             __exists = False
             logging.info(f'Snapshot {snapshot["name"]} deleted!')

# Benji Backup Logic - takes rbd disk (e.g. HDD/vm-104-disk-0) and vmid and creates benji backup
def benjiBackup(disk, lastSnap, vmid):
    logging.info(f'Invoking Benji Backup for disk {disk} - snapshot {lastSnap}') 
    __volume = re.split('/', disk)[0] + '/' + re.split('/', disk)[1]
    __args = 'rbd:' + disk + '@' + lastSnap['name'] + ' ' + __volume
    __newSnap = {}
    logging.info(__args)
    uid = benjiCheckSnapshot(disk, lastSnap, __volume)
    if uid:
        # when vmid was not seen before take a snap
        if not vmid in vmList:
            logging.info(f'Found valid backup {uid}. Going on with differential backup')
            __newSnap = takeSnapshot(node, vmid)
            vmList.append(vmid)
        else: 
            #get newest Snapshot of vmid because a disk of this VM has already been processed
            __node = getNodeFromVMID(vmid)
            __snapList = getSnapList(__node, vmid)
            __snapList.sort(key = lambda i: i['snaptime'], reverse=True)
            __newSnap = __snapList[0]
        benjiDifferentialBackup(disk, lastSnap, __newSnap, uid)
    else: 
        logging.info('proceed with inital backup')
        benjiInitialBackup(disk, lastSnap)

def getNodeFromVMID(vmid):
    __resources = proxmox.cluster.resources.get()
    for element in __resources: 
        if 'vmid' in element.keys():
            if element['vmid'] == int(vmid):
                return element['node']

# create Benji differential backup
def benjiDifferentialBackup(disk, lastSnap, newSnap, uid):
    __pool = re.split('/',disk)[0]
    __disk = re.split('/',disk)[1]
    __benji = '/data/backup/scripts/benji_differential_backup.sh'
    __args = __pool + " " + __disk + " "  + lastSnap['name'] + " " + newSnap['name'] + " " + uid
    __cmd = __benji + " " + __args
    __pcmd = shlex.split(__cmd)
    logging.info(f'Executing shell command: {__pcmd}')
    __out = subprocess.Popen(__pcmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    __stdout,__stderr = __out.communicate()
    __rc = __out.returncode
    if __rc != 0:
        sys.exit("Differential benji backup failed with Errors", __stderr)
    logging.info(f"Differential Backup of RBD Volume {disk}@{newSnap['name']} was successfull... Proceeding with next Volume")

# create Benji initial backup
def benjiInitialBackup(disk, lastSnap):
    __pool = re.split('/',disk)[0]
    __disk = re.split('/',disk)[1]
    __benji = '/data/backup/scripts/benji_initial_backup.sh'
    __args = __pool + " " + __disk + " "  + lastSnap['name']
    __cmd = __benji + " " + __args
    __pcmd = shlex.split(__cmd)
    logging.info(f'Executing shell command: {__pcmd}')
    __out = subprocess.Popen(__pcmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    __stdout,__stderr = __out.communicate()
    __rc = __out.returncode
    if __rc != 0:
        sys.exit("Initial benji backup failed with Errors", __stderr)
    logging.info(f"Initial Backup of RBD Volume {disk}@{lastSnap['name']} was successfull... Proceeding with next Volume")
    
# checks if a given snapshot is valid for benji differential backup and returns a uid if successful
def benjiCheckSnapshot(disk, lastSnap, volume):
    #benji -m ls 'volume == "HDD_vm-104-disk-0" and snapshot == "b-2020-01-02T16:47:03"' | jq -r '.versions[0] | select(.status == "valid") | .uid // ""'
    __benji = 'benji'
    __args = '--log-level ERROR -m ls \'volume == ' + '"' + volume + '"' + ' and snapshot == "' + lastSnap['name'] + '"\''
    __cmd = __benji + ' ' + __args
    __pcmd = shlex.split(__cmd)
    out = subprocess.Popen(__pcmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    __stdout,__stderr = out.communicate()
    __res = json.loads(__stdout)
#    logging.info(__res)
    if len(__res['versions']) > 0:
        if __res['versions'][0]['status'] == 'valid':
            return __res['versions'][0]['uid']  
# takes vmid as argument, cleans up snapshots and remains last snapshot which is returned as object
def cleanSnapshots(vmid):
     logging.info(f'Starting cleanup routine for snapshots of VMID: {vmid}')
     __node = getNodeFromVMID(vmid)
     # Fetch, Clean and Take Snapshots of VMs - after that one snapshot should exist
     logging.info(f'Fetching Snapshots of: {vmid}')
     __snapshots = getSnapList(__node, vmid)
     # Check if more than one pve snapshots are available, if so delete all but the newest one !!! this is not perfect - in the future we maybe check the list of snapshots against the list of benji snapshot names
     if len(__snapshots) > 1:
         logging.info('More than one snapshot found! - Starting the cleanup')
         # sort list of snashot dicts by timestamp - newest snapshot is index 0
         __snapshots.sort(key = lambda i: i['snaptime'], reverse=True)
         # save newest snapshot in __lastsnap and remove it from __snapshots
         __takeSnapshot = True
         __snapAge = int(time.time()) - int(__snapshots[0]['snaptime']) 
         if not __snapAge > conf['snapMaxAge']:
             __lastSnap = __snapshots.pop(0)
             __takeSnapshot = False
         # delete unnecessary snapshots
         for snap in __snapshots:
             deleteSnapshot(__node, vmid, snap)
         if __takeSnapshot:
             __lastSnap = takeSnapshot(__node, vmid)
     # only one snapshot exists - we can continue with our backup logic
     elif len(__snapshots) == 1:
         __takeSnapshot = True
         __snapAge = int(time.time()) - int(__snapshots[0]['snaptime']) 
         if not __snapAge > conf['snapMaxAge']:
             __lastSnap = __snapshots[0]
             __takeSnapshot = False
         if __takeSnapshot:
             logging.info('Snapshot too old - deleting and taking a new one')
             deleteSnapshot(__node, vmid, __snapshots[0])
             __lastSnap = takeSnapshot(node, vmid)
     # no snapshot existing - take a new one and continue
     elif len(__snapshots) == 0:
         # take snapshot and save name to __lastSnap
         __lastSnap = takeSnapshot(node, vmid)
     else: 
         logging.info('Panic - unforseen condition')

     return __lastSnap

# Work is done here
# generate List of Nodes
nodeList = getNodeList()

#generate dict with proxmox nodes as key and list of vmids to backup as value 
for node in nodeList: 
    toBackupDict[node] = getVmList(node)

# when there are vmids to backup then start the backup Logic
for node in toBackupDict:
    if len(toBackupDict[node]) > 0:
        logging.info(f'Processing VMs of {node}')
        for vmid in toBackupDict[node]:
            __snapDisks = []
            __disksProcessed = int(0)
            # Fetch, Clean and Take Snapshots of VMs - after that one snapshot should exist
            __lastSnap = cleanSnapshots(vmid)
            # Create List of disks for backup --> __snapDisks
            if __lastSnap:
                logging.info(f'Processing backup for {__lastSnap}')
                __snapConf = getSnapConfig(node, vmid, __lastSnap['name'])
                for key,value in __snapConf.items():
                    if re.match(r'scsi\d',key):
                        if not re.search('size=4G',value) and not re.search('size=8G',value):
                            __snapDisks.append(re.sub(':','/',(re.split(',',value)[0])))
                logging.info(f'Running backup for disks: {__snapDisks}')
            # benji backup 
            if len(__snapDisks) > 0:
                for disk in __snapDisks:
                    if re.match('HDD/', disk) or re.match('SSD/',disk):
                        logging.info(f'Starting Benji Backup for VMID {vmid} disk {disk}')
                        benjiBackup(disk, __lastSnap, vmid)
                        __disksProcessed += 1
            # run cleanup a second time after backup so that always just one benji snapshots remains
            if __disksProcessed > 0: 
                logging.info(f'Benji has backed up {__disksProcessed} disks of VM {vmid}. Now we clean up unnecessary snapshots')
                __remainingSnap = cleanSnapshots(vmid)
        logging.info('Backup Completed. See list of backed up VMs below')
        logging.info(toBackupDict)

    else: 
        logging.info (f'No VMs to backup for node: {node}')


