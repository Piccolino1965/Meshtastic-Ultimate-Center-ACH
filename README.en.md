# Meshtastic Ultimate Center

IPython desktop interface built with Tkinter to read, configure, and manage a Meshtastic node from a single window.

The project was designed with a practical approach: connect the device via serial or TCP, read the node's actual configuration, adjust the most useful parameters, and also have an operational area dedicated to nodes, chat, direct messages, history, and delivery confirmations.

## What it does

Meshtastic Ultimate Center provides a GUI organized into multiple sections. From the toolbar, you can connect via serial or TCP/IP, read the current configuration, apply changes, create JSON backups, restore a snapshot, and manage several operational utilities. At the core of the application is the MeshtasticDevice class, which handles connection, node reading, message sending, ACKs, backup, and configuration restore.

The available tabs cover node identity, position parameters and range test, MQTT, display, radio, WiFi, primary channel, other channels, mesh view, node list, channel messages, direct messages, message status, statistics, and general settings. The GUI is built around the MeshtasticUltimateCenter notebook and initialized by main.py.

Among the most useful features are primary channel management, selective writing of configuration sections, full JSON backup, configuration restore, reading the node list, favorites, quick filtering, sending direct messages with delivery confirmation, ACK timeout control, and message history with success statistics.

## Main features
### Node connection

The project supports both serial and TCP/IP connections. After connecting, the local node is retrieved and Meshtastic packet reception is subscribed.

### Reading and writing configuration

The application reads localConfig, moduleConfig, and channels, then allows modification of several parameter groups such as position, range test, MQTT, display, node role, LoRa settings, WiFi, and primary channel. The modified sections are then written selectively, with transaction support when needed.

### Backup and restore

A full JSON backup of the configuration is available, along with later restoration of the snapshot, including owner, localConfig, moduleConfig, and channels.

### Node management

The GUI displays the node list and supports text filtering, favorites, contextual menu actions, and cleanup operations. In the latest fixes, node removal on the core side through remove_node() has also been restored, consistently with the GUI commands. The view also uses the lastHeard field to show the most recent contact time.

### Messages and ACKs

The core handles both plain text sending and sending with delivery confirmation. Pending messages are tracked with timeouts, history, and callbacks, while received packets are classified as either text or ACK. The GUI includes a dedicated section for direct messages, a history view, and a tab for delivery statistics.

### Desktop interface

The interface uses Tkinter and the clam theme when available. The visual style is defined in constants.py, with a dark palette and dedicated colors for logs, MQTT, WiFi, channels, and ACK status.

## Hardware compatibility

The application is not limited to Heltec V3. The software uses the Meshtastic Python library and connects to the device through a serial or TCP/IP interface, so in general it can work with Meshtastic-compatible nodes from other manufacturers as well.

Actual compatibility for some sections, however, depends on hardware and firmware. Features such as WiFi, GPS, display, or some configuration options may only be available on certain devices or may be exposed differently depending on the firmware version.

## Project structure

```text
.
├── main.py        # entry point
├── gui.py         # interfaccia principale Tkinter
├── core.py        # logica di connessione e gestione Meshtastic
├── utils.py       # funzioni helper
├── constants.py   # costanti UI e stati
└── tabs.py        #  
```



## Requirements

The project uses Python and several external dependencies. Based on the current imports, at least the following are required:

meshtastic
pypubsub
protobuf
tkinter, already included in many desktop Python installations
plyer, optional, used for desktop notifications if available

The required libraries can be identified directly from the imports in core.py and gui.py.

## Installation
pip install meshtastic pypubsub protobuf plyer

On Linux, you may also need to install system Tk support, since the interface is based on Tkinter.

## Launch
python main.py

main.py creates the main Tkinter window and initializes the MeshtasticUltimateCenter class.

## Typical workflow

The node is connected via serial or TCP, configuration and channels are read, identity and role are checked, the required parameters are adjusted, and then a JSON backup is saved before applying more invasive changes. On the operational side, you can inspect the nodes seen by the device, use channel chat, send direct messages with ACK, and review delivery history.

## Project status

The project is fully geared toward practical use and combines both configuration features and mesh observation tools. The foundation is already broad, but some aspects can still be refined further, such as packaging, dependencies declared in requirements.txt, cleanup of the tabs.py file, and the addition of screenshots or demo GIFs.


## Screenshot

### Panoramica

[![Interface overview](screenshot/home.png)](screenshot/home.png)

### Node management

[![None Management](screenshot/nodi.png)](screenshot/nodi.png)

### Channel chat

[![Panoramica interfaccia](screenshot/messages0.png)](screenshot/messages0.png)

### Direct messages and confirmations

[![ ](screenshot/messages.png)](screenshot/messages.png)

[![ ](screenshot/messages2.png)](screenshot/messages2.png)

[![](screenshot/messages3.png)](screenshot/messages3.png)

### Node configuration

[![ ](screenshot/config1.png)](screenshot/config1.png)

[![ ](screenshot/config2.png)](screenshot/config2.png)

[![ ](screenshot/config3.png)](screenshot/config3.png)

[![ ](screenshot/config4.png)](screenshot/config4.png)

## Notes

This repository is intended for anyone who wants a single desktop console to work with Meshtastic devices in a more readable way than the CLI alone, while still keeping visibility into configuration, nodes, messages, and the device's operational status.

### Hardware compatibility

The application is not limited to Heltec V3.

It generally works with Meshtastic-compatible devices that can be reached through:

USB serial connection
TCP/IP connection

The actual compatibility of some features, however, depends on the hardware and installed firmware. For example, options such as WiFi, GPS, display, or some configuration sections may only be available on certain devices or on specific firmware versions.

# Custom Software License

Copyright (c) 2026 Giovanni Popolizio. All rights reserved.

## 1. Grant of Use

Permission is granted to use this software solely in accordance with the terms of this license.

## 2. Restrictions

Redistribution, republication, sublicensing, resale, leasing, lending, sharing, or otherwise making the software available to any third party, in whole or in part, in original or modified form, is strictly prohibited.

## 3. Attribution

The author's name, copyright notice, and all attribution references must remain present, intact, and clearly visible in the software, documentation, and any authorized copy or use of the software.

## 4. Modifications

Modification of the software is permitted only for personal or internal use. Any modified version may not be redistributed, published, shared, sold, sublicensed, or transferred to third parties.

## 5. No Warranty

This software is provided "as is", without warranty of any kind, express or implied, including but not limited to warranties of merchantability, fitness for a particular purpose, non-infringement, reliability, availability, or security.

## 6. Limitation of Liability

Under no circumstances shall the author be liable for any direct, indirect, incidental, special, consequential, or exemplary damages, including but not limited to damages for loss of data, loss of profits, business interruption, service disruption, or any other commercial or personal damages arising out of or related to the use, misuse, or inability to use the software.

## 7. User Responsibility

The user assumes full responsibility for any improper, unlawful, unsafe, unauthorized, or technically incorrect use of the software.

## 8. Reservation of Rights

All rights not expressly granted under this license are reserved.
