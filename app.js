/* eslint-disable node/no-unsupported-features */
'use strict';

// initialize logging
const winston = require('winston');

const logger = winston.createLogger({
    format: winston.format.combine(
        winston.format.timestamp(),
        winston.format.json()
    ),
    transports: [
        new winston.transports.Console(),
        new winston.transports.File({ filename: './log/app.log' }),
    ],
});
// initialize settings File
const settings = require('./settings.json');
// initialize PVE Api client
const endpoint = settings.pve.apiNodes[Math.floor(Math.random() * settings.pve.apiNodes.length)];
const proxmox = require('./lib/proxmox.js')(settings.pve.user, settings.pve.password, endpoint, settings.pve.authRealm);

// utility function 1 
function filteredKeys(obj, filter) {
    let key = [];
    const keys = [];
    for (key in obj) {
        if (obj.hasOwnProperty(key) && filter.test(key)) {
            keys.push(key);
        }
    };

    return keys;
}

logger.info(`API Endpoint selected: ${endpoint}`);

// get all pve nodes
function getNodesPromise() {
    return new Promise(resolve => proxmox.getNodes((err, response) => {
        if (err) {
            throw err;
        } else {
            const data = JSON.parse(response);
            const nodes = data.data.map(node => (node.node));

            resolve(nodes);
        }
    }));
}

function getQemusPromise(node) {
    return new Promise(resolve => proxmox.getQemu(node, (err, response) => {
        if (err) {
            logger.error(err);
            throw err;
        } else {
            const data = JSON.parse(response);
            const qemus = data.data.map(qemu => ({ vmid: qemu.vmid, name: qemu.name, node }));

            return resolve(qemus);
        }
    }));
}

// more data for list of vms (qemus)
function getVmConfigPromise(vm) {
    return new Promise(resolve => proxmox.qemu.getConfig(vm.node, vm.vmid, (err, response) => {
        if (err) {
            logger.error(err);
            throw err;
        } else {
            const res = JSON.parse(response);
            const { data } = res;
            // new Object containing all desired Infos 
            const newObject = {};
            const regex = new RegExp('scsi[0-9]');
            // find all properties containing scsi to get disks
            const scsiDisks = filteredKeys(data, regex);
            Object.assign(newObject, vm);
            newObject.description = data.description || '';
            newObject.digest = data.digest;
            scsiDisks.forEach((disk) => {
                newObject[disk] = data[disk];
            });

            return resolve(newObject);
        }
    }));
}

function getSnapshotsPromise(vm) {
    return new Promise(resolve => proxmox.qemu.snapshot.list(vm.node, vm.vmid, (err, response) => {
        if (err) {
            logger.error(err);
            throw err;
        } else {
            const res = JSON.parse(response);
            let { data } = res;
            // strip out current snapshot
            data = data.filter(snap => snap.name !== 'current');
            // we return the original vm object enriched with snapshot information
            const newObject = Object.assign({}, vm);
            newObject.snapshots = data;

            return resolve(newObject);
        }
    }));
}

async function getNodes() {
    const promises = getNodesPromise;
    let nodes = [];
    await promises().then((data) => {
        nodes = data;
    });

    return nodes;
}

// loop over all pve nodes to create an array of objects. One object for each VM with properties - vmid, name, node
async function getQemus(nodes) {
    const promises = nodes.map(getQemusPromise);
    const res = await Promise.all(promises);
    const qemus = [].concat.apply([], res);

    return qemus;
}

async function getVmConfig(qemus) {
    const promises = qemus.map(getVmConfigPromise);
    const res = await Promise.all(promises);

    return res;
}

async function getSnapshots(qemus) {
    const promises = qemus.map(getSnapshotsPromise);
    const res = await Promise.all(promises);

    return res;
}

async function makeSnapshot(vm) {
    const promise = new Promise((resolve) => {
        proxmox.qemu.snapshot.make(vm.node, vm.vmid, { snapname: 'backy2' }, (err, response) => {
            if (err) {
                logger.error(err);
                throw err;
            } else {
                const res = JSON.parse(response);
                const { data } = res;

                resolve(data);
            }
        });
    });
    let res = '';
    await promise.then((data) => {
        res = data;
    });

    return res;
}

function createBackupList(callback) {
    logger.info('Invoking getNodes()');
    getNodes().then((nodes) => {
        logger.info(`Nodelist: ${nodes}`);
        logger.debug('Invoking getQemus()');
        getQemus(nodes).then((qemus) => {
            logger.debug(`VMs: ${JSON.stringify(qemus)}`);
            logger.debug('Invoking getVmConfig');
            logger.info(`VM Count: ${qemus.length}`);
            getVmConfig(qemus).then((list) => {
                // filter out machines to backup.
                const backupList = list.filter((item) => {
                    const regex = new RegExp('backy2: true');
                    if (item.description !== '') {
                        if (regex.test(item.description)) {
                            return item;
                        }
                    }
                });
                logger.debug('Invoking getSnapshots');
                getSnapshots(backupList).then((snapBackupList) => {
                    logger.info(`Backup List: ${JSON.stringify(snapBackupList)}`);

                    return callback(snapBackupList);
                });
            });
        });
    });
}

createBackupList((snapBackupList) => {
    snapBackupList.forEach((element) => {
        console.log(element);
        if (element.snapshots.length === 0) {
            console.log('we can start taking a snapshot if not already done');
            //wahrscheinlich muss man hier checken, ob genügend Platz auf den storages verfügbar ist.
            // try to take a snapshot and see what will happen
            makeSnapshot(element).then((result) => {
                console.log(result);
            });
         
            return;
        }
        if (element.snapshots.length <= 2) {
            console.log('maybe we expire snapshots here');

            return;
        }
        logger.error(`${element.name}: no backy2 snapshot available`);
    });
});

