# pveSnapBackup

PveSnapBackup is a wrapper script to make snapshot based backups of your PVE virtual machines. Leveraging the PVE API for snapshotting virtual machines and the awesome [Benji](https://github.com/elemental-lf/benji)
 backup to make fast differential backups.

Basically pveSnapBackup takes snapshots using the [promoxer](https://github.com/swayf/proxmoxer) module. Then Benji will back up the snapshot data to a storage backend of your choice. 

For features like differential backups and data deduplication and/or encryption, please see the [Benji documentation](https://benji-backup.me/quickstart.html)

### Is pveSnapBackup the tool of choice for me?

- Your virtualization hosts are running Proxmox VE? 
- Your storage Backend is Ceph based
- You want to combine the Ceph features like differential snapshots with the convenience of PVEs KVM snapshotting mechanism and the power of benji Backup. 

In general all Storage backends with native support for snapshots should be compatible. For this to work there may be some work to do. 

### Prerequisites

- PVE Cluster with Ceph Storage Backend
- working benji installation
- Your backup server which will also run benji and pveSnapBackup should be a configured client of your Ceph cluster

### Installation 
```
git clone https://github.com/networkhell/pve-snapbackup
cd pve-snapbackup
cp settings.yml-template settings.yml
```
Edit settings to your needs
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
