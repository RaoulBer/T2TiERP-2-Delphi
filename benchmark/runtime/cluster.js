var config = JSON.parse(os.loadTextFile('C:/benchmark/db/cluster-control.json'));
var credentials = JSON.parse(os.loadTextFile('C:/benchmark/db/credentials.json'));

function connection(ip) {
    return {
        scheme: 'mysql',
        user: 'clusteradmin',
        password: credentials.root_password,
        host: ip,
        port: 3306,
        'ssl-mode': 'REQUIRED'
    };
}

var cluster;
if (config.action === 'create') {
    for (var i = 0; i < config.ips.length; i++) {
        dba.checkInstanceConfiguration(connection(config.ips[i]));
    }
    shell.connect(connection(config.ips[0]));
    cluster = dba.createCluster('T2TiSalesScaling', {
        communicationStack: 'MYSQL',
        gtidSetIsComplete: true,
        memberSslMode: 'REQUIRED',
        consistency: 'BEFORE_ON_PRIMARY_FAILOVER',
        autoRejoinTries: 3
    });
    for (var j = 1; j < config.ips.length; j++) {
        cluster.addInstance(connection(config.ips[j]), { recoveryMethod: 'clone' });
    }
} else {
    shell.connect(connection(config.ips[0]));
    cluster = dba.getCluster('T2TiSalesScaling');
    if (config.action === 'multi') {
        cluster.switchToMultiPrimaryMode();
    } else if (config.action === 'single') {
        cluster.switchToSinglePrimaryMode(config.ips[0] + ':3306');
    } else {
        throw Error('UNKNOWN_ACTION');
    }
}

var status = cluster.status({ extended: 2 });
var topology = status.defaultReplicaSet.topology;
if (Object.keys(topology).length !== 3) {
    throw Error('THREE_MEMBERS_REQUIRED');
}
for (var member in topology) {
    if (topology[member].status !== 'ONLINE') {
        throw Error('MEMBER_NOT_ONLINE');
    }
}
print(JSON.stringify(status));
