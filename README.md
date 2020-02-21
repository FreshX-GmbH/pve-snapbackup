# pveSnapBackup

PveSnapBackup is a wrapper script to make snapshot based backups of your PVE virtual machines. Leveraging the PVE API for snapshotting virtual machines and the awesome [Benji](https://github.com/elemental-lf/benji)
 backup to make fast differential backups.

Basically pveSnapBackup takes snapshots using the [promoxer](https://github.com/swayf/proxmoxer) module. Then Benji will back up the snapshot data to a storage backend of your choice. 

For features like differential backups and data deduplication and/or encryption, please see the [Benji documentation](https://benji-backup.me/quickstart.html)

Contributions are welcome!

### Why should I use pveSnapBackup?

- Your virtualization hosts are running Proxmox VE
- Your storage Backend is Ceph based
- You want to combine the Ceph features like differential snapshots with the convenience of PVEs KVM snapshotting mechanism and the power of benji Backup. 

In general all Storage backends with native support for snapshots should be compatible. For this to work there may be some work to do. 

### Prerequisites

- PVE Cluster with Ceph Storage Backend
- working benji installation
- Your backup server which will also run benji and pveSnapBackup should be a configured client of your Ceph cluster. In most cases it will be enough to copy your /etc/ceph.conf and the needed keys from a PVE Client Node to your backup host. 

### Installation 
First [install benji](https://benji-backup.me/installation.html#common-to-all-distributions). Most likely you will want to do this in a python virtual environment. 

Install dependencies: 

```
. /usr/local/benji/bin/activate
pip install proxmoxer
pip install pyaml
pip install coloredlogs
```

```
git clone https://github.com/networkhell/pve-snapbackup
cd pve-snapbackup
cp settings.yml-template settings.yml
```
Modify settings as needed
```
---
# change defaults to your needs
# Filter String for pve hostnames to search for vms to backup
nodeFilter: 'compute'
# Filter String to search for in PVE VM description to decide if we back up the vm
vmFilter: 'benjiBackup=true'
# Snapshot prefix to use - so we do not interfere with other snapshots
snapRegex: '^b_'
# Maximum age for a snapshot used for a differential backup in seconds - 48h = 172800s
# When a snasphot is older than this, a initial backup is performed
snapMaxAge: 172800
logLevel: 'debug'
pve:
  apiEndpoint: 'pve-compute01'
  apiUser: 'backup@pve'
  apiPwd: ''
  verifySsl: false
```

### Operation

pveSnapbackup will take snapshots prefixed with **b_** for backup and will always keep the latest snapshot. This is necessary for taking differential backups.

#### Set up a PVE user with sufficient rights
In this example the user name is admin. The rest needs to be done in the file **/etc/pve/user.cfg** on a proxmox cluster member.

```
acl:1:/:backup@pve:PVEAuditor:
acl:1:/vms:backup@pve:PVEVMAdmin:
```

#### Set up VMs for backup
Currently the script is looking for a String in the VM description field of Proxmox VE. The default is 'benjiBackup=true'. 
![description](https://github.com/networkhell/pve-snapbackup/raw/master/contrib/screenshots/vmdesc.png "")


#### Exclude single disks from backup
You can use the PVE Web GUI to set **backup=0** on single disks of a VM. These disks will be excluded from backup.

#### Quirks
If you add a new disk to a VM that is backed up by pveSnapBackup, you should remove the last snapshot to enforce a new initial backup of this VM. Otherwise subsequent differential backups will not work!

#### Retention 
Currently I use the run.sh Script to enforce Benji retention rules. 

#### Restore
A simple restore script focused on file based restore and Ceph based restore is currently WIP. Please feel free to contribute to [benjiRestore](https://github.com/networkhell/benjiRestore)


#### Scheduled backups
E.g. via cronjob
```
0 3 * * * root /data/backup/pvesnapbackup/run.sh > /dev/null 2>&1
```
