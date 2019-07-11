
'use strict';

const proxmox = require('./lib/proxmox.js')('root', '', 'sec.freshx.de', 'pam');

proxmox.qemu.snapshot.make('sec', 101, { snapname: 'backy2' }, (err, response) => {
    if (err) {throw err;} {
        const data = JSON.parse(response);
        console.log(data);
    }
});
