# snmp2mqtt - An SNMP to MQTT Bridge for polling and publishing metrics

It is quite simple and does what its name says: It works as a bridge between SNMP-enabled devices and MQTT, translating SNMP data into MQTT messages for easy integration with various systems.

## Installation

### Native installation with Python venv

The installation requires at least Python 3.9.
On some systems, additional packages may be required for SNMP library compilation.

Philosophy is to install it under /usr/local/lib/snmp2mqtt and control it via systemd.

```bash
cd /usr/local/lib
git clone https://github.com/yourusername/snmp2mqtt.git
cd snmp2mqtt
./install
```

The `install` script creates a virtual python environment using the `venv` module.
All required libraries are installed automatically.
Depending on your system this may take some time.

## Configuration

The configuration is located in `/etc/snmp2mqtt.conf`.

Each configuration option is also available as command line argument.

- copy `snmp2mqtt.conf.example`
- configure as you like

| option                   | default              | arguments                  | comment                                                                                |
|--------------------------|----------------------|----------------------------|----------------------------------------------------------------------------------------|
| `mqtt_host`              | 'localhost'          | `-m`, `--mqtt_host`        | The hostname of the MQTT server.                                                       |
| `mqtt_port`              | 1883                 | `--mqtt_port`              | The port of the MQTT server.                                                           |
| `mqtt_keepalive`         | 30                   | `--mqtt_keepalive`         | The keep alive interval for the MQTT server connection in seconds.                     |
| `mqtt_clientid`          | 'snmp2mqtt'          | `--mqtt_clientid`          | The clientid to send to the MQTT server.                                               |
| `mqtt_user`              | -                    | `-u`, `--mqtt_user`        | The username for the MQTT server connection.                                           |
| `mqtt_password`          | -                    | `-p`, `--mqtt_password`    | The password for the MQTT server connection.                                           |
| `mqtt_topic`             | 'bus/snmp'           | `-t`, `--mqtt_topic`       | The topic to publish MQTT messages.                                                    |
| `mqtt_tls`               | -                    | `--mqtt_tls`               | Use SSL/TLS encryption for MQTT connection.                                            |
| `mqtt_tls_version`       | 'TLSv1.2'            | `--mqtt_tls_version`       | The TLS version to use for MQTT. One of TLSv1, TLSv1.1, TLSv1.2.                      |
| `mqtt_verify_mode`       | 'CERT_REQUIRED'      | `--mqtt_verify_mode`       | The SSL certificate verification mode. One of CERT_NONE, CERT_OPTIONAL, CERT_REQUIRED. |
| `mqtt_ssl_ca_path`       | -                    | `--mqtt_ssl_ca_path`       | The SSL certificate authority file to verify the MQTT server.                          |
| `mqtt_tls_no_verify`     | -                    | `--mqtt_tls_no_verify`     | Do not verify SSL/TLS constraints like hostname.                                       |
| `timestamp`              | -                    | `-z`, `--timestamp`        | Publish timestamps for all topics, e.g. for monitoring purposes.                       |
| `verbose`                | -                    | `-v`, `--verbose`          | Be verbose while running.                                                              |
| -                        | '/etc/snmp2mqtt.conf'| `-c`, `--config`           | The path to the config file.                                                           |
| `targets`                | see below            | -                          | The configuration for the SNMP targets to poll.                                        |

### SNMP

Currently, both SNMP v2c and v3 are supported for polling remote agents.
The service supports both scalar OID retrieval (GET operations) and table walking (WALK operations).

### Targets & OIDs

Then you can configure your SNMP targets and OIDs to monitor.

```bash
    ...
    "targets": [
        {
            "name": "router1",
            "host": "192.168.1.1",
            "port": 161,
            "version": "v2c",
            "community": "public",
            "interval": 30,
            "oids": [
                { "oid": "1.3.6.1.2.1.1.3.0", "name": "uptime" },
                { "oid": "1.3.6.1.2.1.2.2", "name": "ifTable", "walk": true }
            ]
        },
        ...
    ]
    ...
```

Each target needs a `name`, `host`, and SNMP credentials. The `interval` defines polling frequency in seconds.
Each target contains `oids` entries defining what data to retrieve.

For SNMP v3, additional authentication and privacy settings are available.

The default operating mode for an OID is to perform a scalar GET operation and publish the value to MQTT.

That may be changed using the following settings:

* `walk` (default: false): if set to `true`, performs SNMP WALK operation for table data

### Publishing

All values are published using the target name, OID name, and the MQTT topic.

Topics follow the pattern: `<mqtt_topic>/<target>/<name-or-oid>[/<index>]`.

So, an uptime sensor in the example publishes to `bus/snmp/router1/uptime` and table entries publish to `bus/snmp/router1/ifTable/<index>`.

## Running snmp2mqtt

I use [systemd](https://systemd.io/) to manage my local services.

## Support

I have not the time (yet) to provide professional support for this project.
But feel free to submit issues and PRs, I'll check for it and honor your contributions.

## License

The whole project is licensed under BSD-3-Clause license. Stay fair.
