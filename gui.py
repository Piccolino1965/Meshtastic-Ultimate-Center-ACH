# gui.py - Interfaccia principale - 
###################################
# aiutocomputerhelp.it
# Giovanni Popolizio - anon@m00n
###################################


import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import queue
import sys
import traceback
import json
import time
from datetime import datetime

from constants import UI, ConnectionState, MessageState
import utils
from core import MeshtasticDevice

class MeshtasticUltimateCenter:
    def __init__(self, root):
        self.root = root
        self.root.title("Meshtastic Ultimate Center v4.2 - aiutocomputerhelp.it")
        self.root.geometry("1500x950")
        self.root.configure(bg=UI.BG)
        
        # Core
        self.device = MeshtasticDevice(logger=self.log)
        self.device.add_message_callback(self.on_new_message)
        self.ui_queue = queue.Queue()
        
        # Variabili di stato
        self.favorite_nodes = set()
        self.message_history = []
        self.mesh_diag_rows = []
        self.parse_errors = 0
        self.current_primary_channel_index = None
        self.original_snapshot = {}
        
        # Variabili per ACK
        self.pending_messages = {}  # {msg_id: {'item_id': tree_item_id, 'timestamp': time, 'dest': dest, 'text': text}}
        self.message_callbacks = {}
        
        # Variabili Tkinter
        self.vars = self._create_variables()
        
        # Costruzione UI
        self._build_ui()
        
        # Avvio
        self.root.after(100, self.process_queue)
        self.root.after(1000, self._update_clock)
        self.root.after(5000, self._check_ack_timeouts)  # Controllo ACK ogni 5 secondi
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Controlla import error
        try:
            import meshtastic
        except Exception as e:
            self.log(f"ERRORE: Libreria meshtastic non installata: {e}", "error")
            messagebox.showerror("Errore", "Installa meshtastic: pip install meshtastic")
    
    def on_new_message(self):
        
        try:
            # Aggiorna la UI in modo thread-safe
            self.root.after(0, self.refresh_message_stats)
            self.root.after(0, self._update_pending_count)
        except Exception as e:
            print(f"Errore in on_new_message: {e}")


    # delineo tutte le variabili Tkinter
    def _create_variables(self):
        
        return {
            # Connessione
            'conn_type': tk.StringVar(value="serial"),
            'port': tk.StringVar(value="COM3"),
            'host': tk.StringVar(value="192.168.1.1"),
            'status': tk.StringVar(value="Disconnesso"),
            
            # Identita
            'long_name': tk.StringVar(),
            'short_name': tk.StringVar(),
            
            # Green - Posizione
            'gps_mode': tk.StringVar(),
            'gps_update': tk.StringVar(),
            'pos_broadcast': tk.StringVar(),
            'smart_broadcast': tk.BooleanVar(value=False),
            'fixed_position': tk.BooleanVar(value=False),
            
            # Range Test
            'range_enabled': tk.BooleanVar(value=False),
            'range_sender': tk.BooleanVar(value=False),
            'range_interval': tk.StringVar(),
            
            # MQTT
            'mqtt_enabled': tk.BooleanVar(value=False),
            'mqtt_proxy': tk.BooleanVar(value=False),
            'mqtt_address': tk.StringVar(),
            'mqtt_username': tk.StringVar(),
            'mqtt_password': tk.StringVar(),
            'mqtt_tls': tk.BooleanVar(value=False),
            'mqtt_root': tk.StringVar(),
            'mqtt_encryption': tk.BooleanVar(value=False),
            'mqtt_json': tk.BooleanVar(value=False),
            
            # Display
            'display_screen': tk.StringVar(),
            'display_gps': tk.StringVar(),
            'display_compass': tk.BooleanVar(value=False),
            'display_24h': tk.BooleanVar(value=True),
            
            # Radio
            'role': tk.StringVar(),
            'region': tk.StringVar(),
            'modem': tk.StringVar(),
            'hop_limit': tk.StringVar(),
            'tx_enabled': tk.BooleanVar(value=True),
            
            # WiFi
            'wifi_enabled': tk.BooleanVar(value=False),
            'wifi_ssid': tk.StringVar(),
            'wifi_psk': tk.StringVar(),
            
            # Channel
            'channel_index': tk.StringVar(),
            'channel_name': tk.StringVar(),
            'channel_role': tk.StringVar(),
            'channel_uplink': tk.BooleanVar(),
            'channel_downlink': tk.BooleanVar(),
            'channel_psk': tk.StringVar(value="Non gestita"),
            'channel_write_name': tk.BooleanVar(value=True),
            'channel_write_flags': tk.BooleanVar(value=True),
            
            # Mesh
            'mesh_include_self': tk.BooleanVar(value=False),
            'mesh_only_recent': tk.BooleanVar(value=False),
            'mesh_recent_secs': tk.StringVar(value="86400"),
            'mesh_selected': tk.StringVar(value="Nessun nodo"),
            
            # UI Options
            'auto_scroll': tk.BooleanVar(value=True),
            'filter_text': tk.StringVar(),
            'only_my_msgs': tk.BooleanVar(value=True),
            'preserve_mqtt': tk.BooleanVar(value=False),
            'show_channel_debug': tk.BooleanVar(value=True),
            'rssi_threshold': tk.IntVar(value=-80),
            'auto_refresh': tk.BooleanVar(value=False),
            'refresh_interval': tk.IntVar(value=30),
            
            # Variabili per ACK
            'use_ack': tk.BooleanVar(value=True),
            'ack_timeout': tk.IntVar(value=30),
            'show_ack_notifications': tk.BooleanVar(value=True),
            'auto_retry_on_timeout': tk.BooleanVar(value=False),
            'max_retries': tk.IntVar(value=3),
            
            # Destinatario messaggi
            'dest': tk.StringVar(),
        }
    
    # costruisco interfaccia
    def _build_ui(self):
        
        # Toolbar
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=10, pady=10)
        self._build_toolbar(toolbar)
        
        # Panello principale
        main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))
        
        # Log a sinistra
        left = ttk.Frame(main)
        self._build_log_panel(left)
        main.add(left, weight=1)
        
        # Notebook a destra
        right = ttk.Frame(main)
        self._build_notebook(right)
        main.add(right, weight=3)
        
        # Statusbar
        self._build_statusbar()
    
    #Toolbar comendio principali
    def _build_toolbar(self, parent):
        
        # Connessione
        ttk.Label(parent, text="Connessione:").pack(side=tk.LEFT)
        ttk.Radiobutton(parent, text="Seriale", variable=self.vars['conn_type'], 
                       value="serial").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(parent, text="TCP/IP", variable=self.vars['conn_type'],
                       value="tcp").pack(side=tk.LEFT)
        
        self.port_combo = ttk.Combobox(parent, textvariable=self.vars['port'],
                                      values=UI.PORTS, width=12)
        self.port_combo.pack(side=tk.LEFT, padx=5)
        
        self.host_entry = ttk.Entry(parent, textvariable=self.vars['host'], width=15)
        self._update_conn_fields()
        self.vars['conn_type'].trace('w', lambda *a: self._update_conn_fields())
        
        self.connect_btn = ttk.Button(parent, text="Connetti", command=self.connect)
        self.connect_btn.pack(side=tk.LEFT, padx=2)
        
        self.disconnect_btn = ttk.Button(parent, text="Disconnetti", command=self.disconnect)
        self.disconnect_btn.pack(side=tk.LEFT, padx=2)
        
        # Separatore
        ttk.Separator(parent, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Comandi configurazione
        ttk.Button(parent, text="Leggi config", command=self.read_config).pack(side=tk.LEFT, padx=2)
        ttk.Button(parent, text="Update", command=self.apply_config).pack(side=tk.LEFT, padx=2)
        
        # Separatore
        ttk.Separator(parent, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Backup/Restore
        ttk.Button(parent, text="Backup", command=self.export_snapshot).pack(side=tk.LEFT, padx=2)
        ttk.Button(parent, text="Restore", command=self.import_snapshot).pack(side=tk.LEFT, padx=2)
        
        # Separatore
        ttk.Separator(parent, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Utilità
        ttk.Button(parent, text="Pulisci Log", command=self.clear_log).pack(side=tk.LEFT, padx=2)
        ttk.Button(parent, text="Statistiche", command=self.show_stats).pack(side=tk.LEFT, padx=2)
        ttk.Button(parent, text="Reboot", command=self.confirm_reboot,
                  style='Danger.TButton').pack(side=tk.LEFT, padx=2)
        
        # Checkbox
        ttk.Checkbutton(parent, text="Solo messaggi per me", 
                    variable=self.vars['only_my_msgs']).pack(side=tk.LEFT, padx=5)
    
    # pannello log
    def _build_log_panel(self, parent):
        
        header = ttk.Frame(parent)
        header.pack(fill=tk.X)
        ttk.Label(header, text="Log", font=('',10,'bold')).pack(side=tk.LEFT)
        
        self.parse_error_label = ttk.Label(header, text="", foreground='orange')
        self.parse_error_label.pack(side=tk.RIGHT, padx=10)
        
        ttk.Checkbutton(header, text="Auto-scroll", 
                       variable=self.vars['auto_scroll']).pack(side=tk.RIGHT)
        
        self.log_text = scrolledtext.ScrolledText(parent, wrap=tk.WORD,
            bg=UI.PANEL, fg=UI.FG, font=('Consolas',10))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Tags colori
        self.log_text.tag_config('error', foreground=UI.ERR)
        self.log_text.tag_config('success', foreground=UI.OK)
        self.log_text.tag_config('info', foreground=UI.INFO)
        self.log_text.tag_config('warn', foreground=UI.WARN)
        self.log_text.tag_config('mqtt', foreground=UI.MQTT)
        self.log_text.tag_config('channel', foreground=UI.CHANNEL)
        self.log_text.tag_config('wifi', foreground=UI.WIFI)
        self.log_text.tag_config('ack_pending', foreground=UI.ACK_PENDING)
        self.log_text.tag_config('ack_delivered', foreground=UI.ACK_DELIVERED)
        self.log_text.tag_config('ack_timeout', foreground=UI.ACK_TIMEOUT)
        self.log_text.tag_config('debug', foreground=UI.DEBUG)
        self.log_text.tag_config('muted', foreground='gray')
    
    
    
    
    # Notebook
    def _build_notebook(self, parent):
        
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Identity tab
        self.tab_identity = ttk.Frame(self.notebook)
        self._build_identity_tab()
        self.notebook.add(self.tab_identity, text="Identita")
        
        # Green tab
        self.tab_green = ttk.Frame(self.notebook)
        self._build_green_tab()
        self.notebook.add(self.tab_green, text="Green")
        
        # Radio tab - MODIFICATO (rimosso colore)
        self.tab_radio = ttk.Frame(self.notebook)
        self._build_radio_tab()
        self.notebook.add(self.tab_radio, text="Radio")
        
        # WiFi tab - MODIFICATO (rimossi colori)
        self.tab_wifi = ttk.Frame(self.notebook)
        self._build_wifi_tab()
        self.notebook.add(self.tab_wifi, text="WiFi")
        
        # Primary Channel tab
        self.tab_primary = ttk.Frame(self.notebook)
        self._build_primary_tab()
        self.notebook.add(self.tab_primary, text="Canale Primario")
        
        # Channels tab
        self.tab_channels = ttk.Frame(self.notebook)
        self._build_channels_tab()
        self.notebook.add(self.tab_channels, text="Canali")
        
        # Mesh tab
        self.tab_mesh = ttk.Frame(self.notebook)
        self._build_mesh_tab()
        self.notebook.add(self.tab_mesh, text="Mesh")
        
        # Nodes tab
        self.tab_nodes = ttk.Frame(self.notebook)
        self._build_nodes_tab()
        self.notebook.add(self.tab_nodes, text="Nodi")
        
        # Chat tab
        self.tab_chat = ttk.Frame(self.notebook)
        self._build_chat_tab()
        self.notebook.add(self.tab_chat, text="Chat")
        
        # Direct tab con ACK
        self.tab_direct = ttk.Frame(self.notebook)
        self._build_direct_tab()
        self.notebook.add(self.tab_direct, text="Messaggi diretti")
        
        # Tab Stato Messaggi
        self.tab_messages = ttk.Frame(self.notebook)
        self._build_messages_tab()
        self.notebook.add(self.tab_messages, text="Stato Messaggi")
        
        # Stats tab
        self.tab_stats = ttk.Frame(self.notebook)
        self._build_stats_tab()
        self.notebook.add(self.tab_stats, text="Statistiche")
        
        # Settings tab con impostazioni ACK
        self.tab_settings = ttk.Frame(self.notebook)
        self._build_settings_tab()
        self.notebook.add(self.tab_settings, text="Impostazioni")
    
    def _build_identity_tab(self):
        frame = self.tab_identity
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        ttk.Label(frame, text="Long Name").grid(row=0, column=0, sticky="w", pady=8)
        ttk.Entry(frame, textvariable=self.vars['long_name'], width=40).grid(row=0, column=1, padx=5)
        
        ttk.Label(frame, text="Short Name").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(frame, textvariable=self.vars['short_name'], width=20).grid(row=1, column=1, padx=5)
    
    def _build_green_tab(self):
        outer = self.tab_green
        outer.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Posizione
        pos = ttk.LabelFrame(outer, text="Posizione")
        pos.pack(fill=tk.X, pady=5)
        
        ttk.Label(pos, text="GPS Mode").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(pos, textvariable=self.vars['gps_mode'], width=20).grid(row=0, column=1, padx=5)
        
        ttk.Label(pos, text="GPS Update").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(pos, textvariable=self.vars['gps_update'], width=15).grid(row=1, column=1, padx=5)
        
        ttk.Label(pos, text="Broadcast secs").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(pos, textvariable=self.vars['pos_broadcast'], width=15).grid(row=2, column=1, padx=5)
        
        ttk.Checkbutton(pos, text="Smart Broadcast", variable=self.vars['smart_broadcast']).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(pos, text="Fixed Position", variable=self.vars['fixed_position']).grid(row=4, column=0, columnspan=2, sticky="w")
        
        # Range Test
        range_f = ttk.LabelFrame(outer, text="Range Test")
        range_f.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(range_f, text="Enabled", variable=self.vars['range_enabled']).pack(anchor="w")
        ttk.Checkbutton(range_f, text="Sender", variable=self.vars['range_sender']).pack(anchor="w")
        ttk.Label(range_f, text="Interval:").pack(anchor="w")
        ttk.Entry(range_f, textvariable=self.vars['range_interval'], width=15).pack(anchor="w", padx=10)
        
        # MQTT
        mqtt = ttk.LabelFrame(outer, text="MQTT")
        mqtt.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(mqtt, text="Enabled", variable=self.vars['mqtt_enabled']).pack(anchor="w")
        ttk.Checkbutton(mqtt, text="Proxy to Client", variable=self.vars['mqtt_proxy']).pack(anchor="w")
        ttk.Checkbutton(mqtt, text="TLS", variable=self.vars['mqtt_tls']).pack(anchor="w")
        ttk.Checkbutton(mqtt, text="Encryption", variable=self.vars['mqtt_encryption']).pack(anchor="w")
        ttk.Checkbutton(mqtt, text="JSON", variable=self.vars['mqtt_json']).pack(anchor="w")
        
        ttk.Label(mqtt, text="Broker:").pack(anchor="w")
        ttk.Entry(mqtt, textvariable=self.vars['mqtt_address'], width=40).pack(fill=tk.X, padx=5)
        
        ttk.Label(mqtt, text="Username:").pack(anchor="w")
        ttk.Entry(mqtt, textvariable=self.vars['mqtt_username'], width=30).pack(fill=tk.X, padx=5)
        
        ttk.Label(mqtt, text="Password:").pack(anchor="w")
        ttk.Entry(mqtt, textvariable=self.vars['mqtt_password'], width=30, show="*").pack(fill=tk.X, padx=5)
        
        ttk.Label(mqtt, text="Root Topic:").pack(anchor="w")
        ttk.Entry(mqtt, textvariable=self.vars['mqtt_root'], width=40).pack(fill=tk.X, padx=5)
        
        # Display
        disp = ttk.LabelFrame(outer, text="Display")
        disp.pack(fill=tk.X, pady=5)
        
        ttk.Label(disp, text="Screen On (secs):").pack(anchor="w")
        ttk.Entry(disp, textvariable=self.vars['display_screen'], width=15).pack(anchor="w", padx=10)
        
        ttk.Label(disp, text="GPS Format:").pack(anchor="w")
        ttk.Combobox(disp, textvariable=self.vars['display_gps'], 
                    values=UI.GPS_FORMATS, width=20).pack(anchor="w", padx=10)
        
        ttk.Checkbutton(disp, text="Compass North Top", variable=self.vars['display_compass']).pack(anchor="w")
        ttk.Checkbutton(disp, text="24 Hour Format", variable=self.vars['display_24h']).pack(anchor="w")
    
    
    def _build_radio_tab(self):
        # Tab Radio 
        frame = self.tab_radio
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # RIMOSSO foreground=UI.WARN - ora solo grassetto per leggibilità
        ttk.Label(frame, text="Attenzione !! Parametri delicati", 
                  font=('', 10, 'bold')).grid(row=0, column=0, columnspan=2, 
                                              sticky="w", pady=(5,15))

        ttk.Label(frame, text="Node Role").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Combobox(frame, textvariable=self.vars['role'], 
                     values=UI.ROLES, width=25).grid(row=1, column=1, padx=5)
        
        ttk.Label(frame, text="Region").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Combobox(frame, textvariable=self.vars['region'], 
                     values=UI.REGIONS, width=25).grid(row=2, column=1, padx=5)
        
        ttk.Label(frame, text="Modem Preset").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Combobox(frame, textvariable=self.vars['modem'], 
                     values=UI.MODEM_PRESETS, width=25).grid(row=3, column=1, padx=5)
        
        ttk.Label(frame, text="Hop Limit").grid(row=4, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.vars['hop_limit'], width=10).grid(row=4, column=1, sticky="w", padx=5)
        
        ttk.Checkbutton(frame, text="TX Enabled", 
                        variable=self.vars['tx_enabled']).grid(row=5, column=0, columnspan=2, 
                                                               sticky="w", pady=5)
    
    def _build_wifi_tab(self):
        #Tab WiFi 
        frame = self.tab_wifi
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Abilitazione WiFi
        enabled_frame = ttk.LabelFrame(frame, text="Abilitazione WiFi")
        enabled_frame.pack(fill=tk.X, pady=10)
        
        ttk.Checkbutton(enabled_frame, text="Abilita WiFi sul dispositivo", 
                       variable=self.vars['wifi_enabled']).pack(anchor="w", padx=10, pady=5)
        ttk.Label(enabled_frame, 
                 text="(Il dispositivo deve supportare WiFi e avere l'antenna connessa)").pack(anchor="w", padx=10, pady=(0,5))

        # Configurazione rete
        network_frame = ttk.LabelFrame(frame, text="Configurazione Rete WiFi")
        network_frame.pack(fill=tk.X, pady=10)

        # SSID
        ssid_frame = ttk.Frame(network_frame)
        ssid_frame.pack(fill=tk.X, pady=5, padx=10)
        ttk.Label(ssid_frame, text="SSID (Nome rete):", width=15).pack(side=tk.LEFT)
        ttk.Entry(ssid_frame, textvariable=self.vars['wifi_ssid'], 
                  width=40).pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        # Password
        psk_frame = ttk.Frame(network_frame)
        psk_frame.pack(fill=tk.X, pady=5, padx=10)
        ttk.Label(psk_frame, text="Password:", width=15).pack(side=tk.LEFT)
        psk_entry = ttk.Entry(psk_frame, textvariable=self.vars['wifi_psk'], 
                              width=40, show="*")
        psk_entry.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        def toggle_password():
            if psk_entry.cget('show') == '*':
                psk_entry.config(show='')
                show_btn.config(text='Nascondi')
            else:
                psk_entry.config(show='*')
                show_btn.config(text='Mostra')
        
        show_btn = ttk.Button(psk_frame, text="Mostra", command=toggle_password, width=8)
        show_btn.pack(side=tk.LEFT)

        # Nota sulla sicurezza -
        note = ttk.LabelFrame(frame, text="Nota sulla sicurezza")
        note.pack(fill=tk.X, pady=20)
        ttk.Label(note, 
                 text="La password WiFi viene inviata al dispositivo in chiaro.\n"
                      "Assicurati che la connessione al dispositivo sia sicura (es. via cavo USB).\n\n"
                      "Dopo aver applicato la configurazione, il dispositivo si connetterà alla rete WiFi\n"
                      "specificata se nelle vicinanze e se le credenziali sono corrette.",
                 justify=tk.LEFT).pack(anchor="w", padx=10, pady=10)
        
        # Informazioni 
        info_frame = ttk.LabelFrame(frame, text="Informazioni")
        info_frame.pack(fill=tk.X, pady=10)
        ttk.Label(info_frame, 
                 text="Una volta connesso al WiFi, puoi connetterti al dispositivo via TCP usando il suo IP\n"
                      "Alcuni dispositivi (es. T-Beam, T-Echo) hanno il WiFi integrato\n"
                      "Verifica che il tuo firmware supporti la configurazione WiFi",
                 justify=tk.LEFT).pack(anchor="w", padx=10, pady=10)
    
    def _build_primary_tab(self):
        outer = self.tab_primary
        outer.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        head = ttk.LabelFrame(outer, text="Canale Primario")
        head.pack(fill=tk.X, pady=5)
        
        ttk.Label(head, text="Indice").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(head, textvariable=self.vars['channel_index'], width=10, state="readonly").grid(row=0, column=1, padx=5)
        
        ttk.Label(head, text="Ruolo").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(head, textvariable=self.vars['channel_role'], width=20, state="readonly").grid(row=1, column=1, padx=5)
        
        ttk.Label(head, text="Nome").grid(row=2, column=0, sticky="w", pady=5)
        name_entry = ttk.Entry(head, textvariable=self.vars['channel_name'], width=30)
        name_entry.grid(row=2, column=1, padx=5)
        name_entry.bind("<FocusOut>", lambda e: self._validate_channel_name())
        
        ttk.Checkbutton(head, text="Uplink", variable=self.vars['channel_uplink']).grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(head, text="Downlink", variable=self.vars['channel_downlink']).grid(row=3, column=1, sticky="w")
        
        ttk.Label(head, text="PSK").grid(row=4, column=0, sticky="w", pady=5)
        ttk.Entry(head, textvariable=self.vars['channel_psk'], width=40, state="readonly").grid(row=4, column=1, padx=5)
        
        write_frame = ttk.LabelFrame(outer, text="Opzioni scrittura")
        write_frame.pack(fill=tk.X, pady=10)
        
        ttk.Checkbutton(write_frame, text="Consenti scrittura nome", 
                       variable=self.vars['channel_write_name']).pack(anchor="w")
        ttk.Checkbutton(write_frame, text="Consenti scrittura uplink/downlink", 
                       variable=self.vars['channel_write_flags']).pack(anchor="w")
        
        ttk.Button(outer, text="Rileggi", command=self.read_primary_channel).pack(pady=10)
    
    def _build_channels_tab(self):
        frame = self.tab_channels
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        ttk.Button(frame, text="Aggiorna canali", command=self.read_channels).pack(anchor="w", pady=5)
        
        self.channels_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD,
            bg=UI.PANEL, fg=UI.FG, font=('Consolas',10))
        self.channels_text.pack(fill=tk.BOTH, expand=True)
    
    def _build_mesh_tab(self):
        outer = self.tab_mesh
        outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=5)
        
        ttk.Button(controls, text="Aggiorna", command=self.refresh_mesh).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(controls, text="Includi self", variable=self.vars['mesh_include_self']).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(controls, text="Solo recenti", variable=self.vars['mesh_only_recent']).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(controls, text="Secondi:").pack(side=tk.LEFT, padx=(10,2))
        ttk.Entry(controls, textvariable=self.vars['mesh_recent_secs'], width=8).pack(side=tk.LEFT)
        
        ttk.Label(controls, textvariable=self.vars['mesh_selected']).pack(side=tk.RIGHT, padx=5)
        
        columns = ("id", "short", "long", "hw", "role", "hops", "snr", "distance", "lastheard")
        self.mesh_tree = ttk.Treeview(outer, columns=columns, show="headings", height=15)
        
        col_widths = {"id":120, "short":80, "long":150, "hw":100, "role":80, 
                     "hops":50, "snr":60, "distance":90, "lastheard":120}
        for col in columns:
            self.mesh_tree.heading(col, text=col.upper())
            self.mesh_tree.column(col, width=col_widths.get(col, 80))
        
        scroll = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=self.mesh_tree.yview)
        self.mesh_tree.configure(yscrollcommand=scroll.set)
        
        self.mesh_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.mesh_tree.bind("<<TreeviewSelect>>", self.on_mesh_select)
        
        self.mesh_detail = scrolledtext.ScrolledText(outer, height=8,
            bg=UI.PANEL, fg=UI.FG, font=('Consolas',9))
        self.mesh_detail.pack(fill=tk.BOTH, expand=True, pady=5)
    
    def _build_nodes_tab(self):
        frame = self.tab_nodes
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, pady=5)
        
        ttk.Label(toolbar, text="Filtro:").pack(side=tk.LEFT)
        ttk.Entry(toolbar, textvariable=self.vars['filter_text'], width=20).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(toolbar, text="Aggiorna Nodi", command=self.refresh_nodes).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(toolbar, text="Preferiti", command=self.manage_favorites).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Pulisci", command=self.confirm_clean_nodes,
                  style='Danger.TButton').pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(toolbar, text="Preserva MQTT", variable=self.vars['preserve_mqtt']).pack(side=tk.LEFT, padx=5)
        
        columns = ("id", "nome", "tipo", "fav", "hops", "snr", "rssi", "qual", "last")
        self.nodes_tree = ttk.Treeview(frame, columns=columns, show="headings", height=20)
        
        col_widths = {"id":120, "nome":150, "tipo":60, "fav":40, "hops":50, "snr":60, "rssi":60, "qual":70, "last":120}
        for col in columns:
            self.nodes_tree.heading(col, text=col.upper())
            self.nodes_tree.column(col, width=col_widths.get(col, 80), anchor="center")
        
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.nodes_tree.yview)
        self.nodes_tree.configure(yscrollcommand=scroll.set)
        
        self.nodes_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.nodes_tree.bind("<<TreeviewSelect>>", self.on_node_select)
        self.nodes_tree.bind("<Double-Button-1>", self.on_node_double)
        self.nodes_tree.bind("<Button-3>", self.show_node_menu)
        
        self.vars['filter_text'].trace('w', lambda *a: self.filter_nodes())
    
    def _build_chat_tab(self):
        frame = self.tab_chat
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        ttk.Label(frame, text="Messaggio sul canale:").pack(anchor="w")
        
        self.chat_text = tk.Text(frame, height=6, wrap=tk.WORD,
            bg=UI.PANEL, fg=UI.FG, font=('',11))
        self.chat_text.pack(fill=tk.X, pady=10)
        
        ttk.Button(frame, text="Invia", command=self.send_chat).pack()
    
    def _build_direct_tab(self):
        frame = self.tab_direct
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Destinatario
        ttk.Label(frame, text="Destinatario:").pack(anchor="w")
        dest_frame = ttk.Frame(frame)
        dest_frame.pack(fill=tk.X, pady=5)
        ttk.Entry(dest_frame, textvariable=self.vars['dest'], width=30).pack(side=tk.LEFT)
        ttk.Button(dest_frame, text="Lista nodi", command=self.show_node_list).pack(side=tk.LEFT, padx=5)
        
        # Opzioni ACK
        ack_frame = ttk.LabelFrame(frame, text="Opzioni di consegna")
        ack_frame.pack(fill=tk.X, pady=10)
        
        ack_check_frame = ttk.Frame(ack_frame)
        ack_check_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Checkbutton(ack_check_frame, text="Richiedi conferma di consegna (ACK)", 
                       variable=self.vars['use_ack']).pack(side=tk.LEFT)
        
        timeout_frame = ttk.Frame(ack_frame)
        timeout_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(timeout_frame, text="Timeout (secondi):").pack(side=tk.LEFT)
        ttk.Spinbox(timeout_frame, from_=5, to=120, textvariable=self.vars['ack_timeout'],
                   width=5).pack(side=tk.LEFT, padx=10)
        
        notif_frame = ttk.Frame(ack_frame)
        notif_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Checkbutton(notif_frame, text="Mostra notifiche consegna", 
                       variable=self.vars['show_ack_notifications']).pack(side=tk.LEFT)
        
        retry_frame = ttk.Frame(ack_frame)
        retry_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Checkbutton(retry_frame, text="Riprova automaticamente in caso di timeout", 
                       variable=self.vars['auto_retry_on_timeout']).pack(side=tk.LEFT)
        ttk.Label(retry_frame, text="Max tentativi:").pack(side=tk.LEFT, padx=(20,5))
        ttk.Spinbox(retry_frame, from_=1, to=10, textvariable=self.vars['max_retries'],
                   width=3).pack(side=tk.LEFT)
        
        # Messaggio
        ttk.Label(frame, text="Messaggio:").pack(anchor="w", pady=(10,0))
        self.direct_text = tk.Text(frame, height=5, wrap=tk.WORD,
            bg=UI.PANEL, fg=UI.FG, font=('',11))
        self.direct_text.pack(fill=tk.X, pady=5)
        
        # Pulsanti invio
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Invia", command=self.send_direct).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Invia con conferma", 
                  command=self.send_direct_with_ack).pack(side=tk.LEFT, padx=2)
        
        # Cronologia
        ttk.Label(frame, text="Cronologia messaggi:").pack(anchor="w", pady=(15,5))
        
        columns = ("ora", "dest", "msg", "stato", "tempo", "id")
        self.history_tree = ttk.Treeview(frame, columns=columns, show="headings", height=8)
        
        self.history_tree.heading("ora", text="Ora")
        self.history_tree.heading("dest", text="Destinatario")
        self.history_tree.heading("msg", text="Messaggio")
        self.history_tree.heading("stato", text="Stato")
        self.history_tree.heading("tempo", text="Tempo")
        self.history_tree.heading("id", text="ID")
        
        self.history_tree.column("ora", width=80)
        self.history_tree.column("dest", width=120)
        self.history_tree.column("msg", width=200)
        self.history_tree.column("stato", width=100)
        self.history_tree.column("tempo", width=80)
        self.history_tree.column("id", width=80)
        
        scroll_hist = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scroll_hist.set)
        
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_hist.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Tag colori
        self.history_tree.tag_configure('delivered', foreground=UI.ACK_DELIVERED)
        self.history_tree.tag_configure('pending', foreground=UI.ACK_PENDING)
        self.history_tree.tag_configure('timeout', foreground=UI.ACK_TIMEOUT)
        self.history_tree.tag_configure('sent', foreground=UI.INFO)
        
        self.history_tree.bind("<Button-3>", self.show_history_menu)
    
    # Tab per visualizzare tutti i messaggi con statistiche
    def _build_messages_tab(self):
         
        frame = self.tab_messages
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, pady=5)
        
        ttk.Button(toolbar, text="Aggiorna", command=self.refresh_message_stats).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Pulisci storico", command=self.clear_message_history).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Esporta CSV", command=self.export_message_history).pack(side=tk.LEFT, padx=2)
        
        stats_frame = ttk.LabelFrame(frame, text="Statistiche Consegne")
        stats_frame.pack(fill=tk.X, pady=10, padx=5)
        
        self.stats_text = tk.Text(stats_frame, height=5, bg=UI.PANEL, fg=UI.FG, wrap=tk.WORD)
        self.stats_text.pack(fill=tk.X, padx=5, pady=5)
        
        filter_frame = ttk.Frame(frame)
        filter_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(filter_frame, text="Filtra per stato:").pack(side=tk.LEFT)
        self.filter_state = tk.StringVar(value="Tutti")
        state_combo = ttk.Combobox(filter_frame, textvariable=self.filter_state,
                                   values=["Tutti", "Consegnato", "In attesa", "Timeout", "Inviato"],
                                   width=15, state="readonly")
        state_combo.pack(side=tk.LEFT, padx=5)
        state_combo.bind('<<ComboboxSelected>>', lambda e: self.filter_messages())
        
        ttk.Label(filter_frame, text="Cerca:").pack(side=tk.LEFT, padx=(20,5))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(filter_frame, textvariable=self.search_var, width=20)
        search_entry.pack(side=tk.LEFT)
        self.search_var.trace('w', lambda *a: self.filter_messages())
        
        columns = ("ora", "dest", "msg", "stato", "tempo", "tentativi", "id")
        self.messages_tree = ttk.Treeview(frame, columns=columns, show="headings", height=15)
        
        self.messages_tree.heading("ora", text="Ora Invio")
        self.messages_tree.heading("dest", text="Destinatario")
        self.messages_tree.heading("msg", text="Messaggio")
        self.messages_tree.heading("stato", text="Stato")
        self.messages_tree.heading("tempo", text="Tempo (s)")
        self.messages_tree.heading("tentativi", text="Tentativi")
        self.messages_tree.heading("id", text="ID")
        
        self.messages_tree.column("ora", width=120)
        self.messages_tree.column("dest", width=120)
        self.messages_tree.column("msg", width=250)
        self.messages_tree.column("stato", width=100)
        self.messages_tree.column("tempo", width=80)
        self.messages_tree.column("tentativi", width=70)
        self.messages_tree.column("id", width=80)
        
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.messages_tree.yview)
        self.messages_tree.configure(yscrollcommand=scroll.set)
        
        self.messages_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.messages_tree.tag_configure('delivered', foreground=UI.ACK_DELIVERED)
        self.messages_tree.tag_configure('pending', foreground=UI.ACK_PENDING)
        self.messages_tree.tag_configure('timeout', foreground=UI.ACK_TIMEOUT)
        self.messages_tree.tag_configure('sent', foreground=UI.INFO)
    
    def _build_stats_tab(self):
        frame = self.tab_stats
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.stats_display = scrolledtext.ScrolledText(frame, wrap=tk.WORD,
            bg=UI.PANEL, fg=UI.FG, font=('Consolas',10))
        self.stats_display.pack(fill=tk.BOTH, expand=True)
        
        ttk.Button(frame, text="Aggiorna", command=self.update_stats).pack(pady=5)
    
    def _build_settings_tab(self):
        frame = self.tab_settings
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Impostazioni ACK
        ack_settings = ttk.LabelFrame(frame, text="Impostazioni Conferme (ACK)")
        ack_settings.pack(fill=tk.X, pady=10)
        
        ttk.Checkbutton(ack_settings, text="Abilita notifiche desktop per consegna",
                       variable=self.vars['show_ack_notifications']).pack(anchor="w", padx=10, pady=2)
        
        ttk.Checkbutton(ack_settings, text="Ritenta automaticamente in caso di timeout",
                       variable=self.vars['auto_retry_on_timeout']).pack(anchor="w", padx=10, pady=2)
        
        timeout_frame = ttk.Frame(ack_settings)
        timeout_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(timeout_frame, text="Timeout predefinito (secondi):").pack(side=tk.LEFT)
        ttk.Spinbox(timeout_frame, from_=5, to=120, textvariable=self.vars['ack_timeout'],
                   width=5).pack(side=tk.LEFT, padx=10)
        
        retry_frame = ttk.Frame(ack_settings)
        retry_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(retry_frame, text="Numero massimo tentativi:").pack(side=tk.LEFT)
        ttk.Spinbox(retry_frame, from_=1, to=10, textvariable=self.vars['max_retries'],
                   width=5).pack(side=tk.LEFT, padx=10)
        
        # RSSI
        rssi_f = ttk.Frame(frame)
        rssi_f.pack(fill=tk.X, pady=5)
        ttk.Label(rssi_f, text="Soglia RSSI:").pack(side=tk.LEFT)
        ttk.Scale(rssi_f, from_=-100, to=-50, variable=self.vars['rssi_threshold'],
                 orient=tk.HORIZONTAL, length=200).pack(side=tk.LEFT, padx=10)
        ttk.Label(rssi_f, textvariable=self.vars['rssi_threshold']).pack(side=tk.LEFT)
        
        ref_f = ttk.Frame(frame)
        ref_f.pack(fill=tk.X, pady=5)
        ttk.Checkbutton(ref_f, text="Auto-refresh ogni", variable=self.vars['auto_refresh']).pack(side=tk.LEFT)
        ttk.Spinbox(ref_f, from_=10, to=300, textvariable=self.vars['refresh_interval'],
                   width=5).pack(side=tk.LEFT, padx=5)
        ttk.Label(ref_f, text="secondi").pack(side=tk.LEFT)
        
        debug_f = ttk.LabelFrame(frame, text="Debug")
        debug_f.pack(fill=tk.X, pady=10)
        ttk.Checkbutton(debug_f, text="Mostra debug canali", 
                       variable=self.vars['show_channel_debug']).pack(anchor="w", padx=5)
        
        info_f = ttk.LabelFrame(frame, text="Info")
        info_f.pack(fill=tk.X, pady=10)
        ttk.Label(info_f, 
                 text="Persistenza: 1. Cancella nodi 2. Premi Reboot",
                 foreground='orange').pack(padx=5, pady=5)
        
        ttk.Button(frame, text="Salva impostazioni", command=self.save_settings).pack(pady=20)
    
    def _build_statusbar(self):
        status = ttk.Frame(self.root)
        status.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.status_label = ttk.Label(status, textvariable=self.vars['status'],
                                      relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.pending_label = ttk.Label(status, text="", relief=tk.SUNKEN, width=15)
        self.pending_label.pack(side=tk.RIGHT, padx=5)
        
        self.clock_label = ttk.Label(status, relief=tk.SUNKEN, width=20)
        self.clock_label.pack(side=tk.RIGHT)
    
    def _update_conn_fields(self):
        if self.vars['conn_type'].get() == "serial":
            self.host_entry.pack_forget()
            self.port_combo.pack(side=tk.LEFT, padx=5)
        else:
            self.port_combo.pack_forget()
            self.host_entry.pack(side=tk.LEFT, padx=5)
    
    def _update_clock(self):
        self.clock_label.config(text=datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        self.root.after(1000, self._update_clock)
    
    def _validate_channel_name(self, event=None):
        name = self.vars['channel_name'].get().strip()
        if name and len(name.encode('utf-8')) > 11:
            self.log("Nome canale troppo lungo (max 11 byte)", "warn")
            return False
        return True
    
    # ==================== METODI PRINCIPALI ====================
    #------------------------------------------------------------

    def log(self, msg, tag=None):
        self.ui_queue.put(('log', (f"[{utils.timestamp()}] {msg}\n", tag)))
    
    def connect(self):
        try:
            if self.vars['conn_type'].get() == "serial":
                port = self.vars['port'].get().strip()
                if not port:
                    messagebox.showwarning("Attenzione", "Inserisci una porta")
                    return
                ok = self.device.connect_serial(port)
                conn_str = port
            else:
                host = self.vars['host'].get().strip()
                if not host:
                    messagebox.showwarning("Attenzione", "Inserisci un host")
                    return
                ok = self.device.connect_tcp(host)
                conn_str = host
            
            if ok:
                self.vars['status'].set(f"Connesso a {conn_str}")
                self.log(f"Connesso a {conn_str}", "success")
                self.refresh_nodes()
                self.root.after(2000, self.read_config)
            else:
                self.log("Connessione fallita", "error")
        except Exception as e:
            self.log(f"Errore connessione: {e}", "error")
            messagebox.showerror("Errore", str(e))
    
    def disconnect(self):
        self.device.disconnect()
        self.vars['status'].set("Disconnesso")
        self.log("Disconnesso", "success")
        self.nodes_tree.delete(*self.nodes_tree.get_children())
        self.pending_messages.clear()
        self._update_pending_count()
    
    def clear_log(self):
        self.log_text.delete(1.0, tk.END)
    
    def refresh_nodes(self):
        if not self.device.connected:
            self.log("Non connesso", "warn")
            return
        nodes = self.device.get_nodes()
        self.ui_queue.put(('update_nodes', nodes))
    
    def read_config(self):
        if not self.device.connected:
            messagebox.showwarning("Attenzione", "Non connesso")
            return
        
        self.log("Lettura configurazione...", "info")
        
        try:
            self.device.wait_for_config(timeout=3.0)
            
            local_cfg, module_cfg = self.device.read_config()
            
            if not local_cfg:
                self.log("localConfig non disponibile", "warn")
                return
            
            long_name, short_name = self.device.read_local_identity()
            self.vars['long_name'].set(long_name)
            self.vars['short_name'].set(short_name)
            self.log(f"Identita: {long_name} / {short_name}", "info")
            
            if hasattr(local_cfg, 'position'):
                pos = local_cfg.position
                self.vars['gps_mode'].set(self._enum_name(pos, 'gps_mode'))
                self.vars['gps_update'].set(str(utils.safe_attr(pos, 'gps_update_interval', '')))
                self.vars['pos_broadcast'].set(str(utils.safe_attr(pos, 'position_broadcast_secs', '')))
                self.vars['smart_broadcast'].set(bool(utils.safe_attr(pos, 'smart_position_enabled', False)))
                self.vars['fixed_position'].set(bool(utils.safe_attr(pos, 'fixed_position', False)))
            
            if module_cfg and hasattr(module_cfg, 'range_test'):
                rt = module_cfg.range_test
                self.vars['range_enabled'].set(bool(utils.safe_attr(rt, 'enabled', False)))
                self.vars['range_sender'].set(bool(utils.safe_attr(rt, 'sender', False)))
                self.vars['range_interval'].set(str(utils.safe_attr(rt, 'sender_interval', '') or ''))
            
            if module_cfg and hasattr(module_cfg, 'mqtt'):
                mqtt = module_cfg.mqtt
                self.vars['mqtt_enabled'].set(bool(utils.safe_attr(mqtt, 'enabled', False)))
                self.vars['mqtt_proxy'].set(bool(utils.safe_attr(mqtt, 'proxy_to_client_enabled', False)))
                self.vars['mqtt_address'].set(str(utils.safe_attr(mqtt, 'address', '') or ''))
                self.vars['mqtt_username'].set(str(utils.safe_attr(mqtt, 'username', '') or ''))
                self.vars['mqtt_password'].set(str(utils.safe_attr(mqtt, 'password', '') or ''))
                self.vars['mqtt_tls'].set(bool(utils.safe_attr(mqtt, 'tls_enabled', False)))
                self.vars['mqtt_root'].set(str(utils.safe_attr(mqtt, 'root', '') or ''))
                self.vars['mqtt_encryption'].set(bool(utils.safe_attr(mqtt, 'encryption_enabled', False)))
                self.vars['mqtt_json'].set(bool(utils.safe_attr(mqtt, 'json_enabled', False)))
            
            if hasattr(local_cfg, 'display'):
                disp = local_cfg.display
                self.vars['display_screen'].set(str(utils.safe_attr(disp, 'screen_on_secs', '') or ''))
                self.vars['display_gps'].set(self._enum_name(disp, 'gps_format'))
                self.vars['display_compass'].set(bool(utils.safe_attr(disp, 'compass_north_top', False)))
                
                val_24 = utils.safe_attr(disp, 'twentyfourhour', None)
                if val_24 is None:
                    val_24 = utils.safe_attr(disp, 'twenty_four_hour', True)
                self.vars['display_24h'].set(bool(val_24))
            
            if hasattr(local_cfg, 'device'):
                self.vars['role'].set(self._enum_name(local_cfg.device, 'role'))
            if hasattr(local_cfg, 'lora'):
                lora = local_cfg.lora
                self.vars['region'].set(self._enum_name(lora, 'region'))
                self.vars['modem'].set(self._enum_name(lora, 'modem_preset'))
                hop = utils.safe_attr(lora, 'hop_limit', None)
                if hop is None:
                    hop = utils.safe_attr(lora, 'max_hops', '')
                self.vars['hop_limit'].set(str(hop or ''))
                self.vars['tx_enabled'].set(bool(utils.safe_attr(lora, 'tx_enabled', True)))
            
            if hasattr(local_cfg, 'network'):
                net = local_cfg.network
                self.vars['wifi_enabled'].set(bool(utils.safe_attr(net, 'wifi_enabled', False)))
                self.vars['wifi_ssid'].set(str(utils.safe_attr(net, 'wifi_ssid', '') or ''))
                self.vars['wifi_psk'].set(str(utils.safe_attr(net, 'wifi_psk', '') or ''))
                self.log("Configurazione WiFi letta", "wifi")
            
            self.read_primary_channel()
            self.read_channels()
            
            self.log("Configurazione letta con successo", "success")
            
        except Exception as e:
            self.log(f"Errore lettura config: {e}", "error")
            import traceback
            self.log(traceback.format_exc(), "muted")
    
    def _enum_name(self, obj, attr):
        try:
            if obj and hasattr(obj, attr):
                val = getattr(obj, attr)
                desc = getattr(obj, 'DESCRIPTOR', None)
                if desc:
                    field = desc.fields_by_name.get(attr)
                    if field and field.enum_type:
                        return field.enum_type.values_by_number.get(val, str(val)).name
                return str(val)
        except: pass
        return ""
    
    def read_primary_channel(self):
        try:
            idx, ch = self.device.find_primary_channel()
            if not ch:
                self.log("Canale primario non trovato", "warn")
                return
            
            self.current_primary_channel_index = idx
            self.vars['channel_index'].set(str(idx) if idx is not None else "")
            self.vars['channel_role'].set(self.device._get_channel_role_name(ch))
            
            settings = self.device.get_channel_settings(ch)
            if settings:
                self.vars['channel_name'].set(str(utils.safe_attr(settings, 'name', '') or ''))
                self.vars['channel_uplink'].set(bool(utils.safe_attr(settings, 'uplink_enabled', False)))
                self.vars['channel_downlink'].set(bool(utils.safe_attr(settings, 'downlink_enabled', False)))
                
                psk = utils.safe_attr(settings, 'psk', None)
                self.vars['channel_psk'].set("Presente" if psk else "Vuota")
            
            self.log(f"Canale primario: index={idx}", "info")
        except Exception as e:
            self.log(f"Errore lettura canale: {e}", "error")
    
    def read_channels(self):
        try:
            channels = self.device.read_channels()
            primary_idx, _ = self.device.find_primary_channel()
            
            lines = ["CANALI DEL NODO", "="*60, ""]
            
            for ch in channels:
                idx = getattr(ch, 'index', 0)
                role = self.device._get_channel_role_name(ch)
                marker = " <== PRIMARY" if primary_idx == idx else ""
                lines.append(f"[{idx}] role={role}{marker}")
                
                settings = self.device.get_channel_settings(ch)
                if settings:
                    name = utils.safe_attr(settings, 'name', '')
                    uplink = utils.safe_attr(settings, 'uplink_enabled', False)
                    downlink = utils.safe_attr(settings, 'downlink_enabled', False)
                    lines.append(f"  name: {name}")
                    lines.append(f"  uplink: {uplink}, downlink: {downlink}")
                lines.append("")
            
            self.channels_text.delete(1.0, tk.END)
            self.channels_text.insert(tk.END, "\n".join(lines))
            
        except Exception as e:
            self.log(f"Errore lettura canali: {e}", "error")
    
    def refresh_mesh(self):
        if not self.device.connected: return
        
        try:
            nodes = self.device.get_nodes()
            local_lat, local_lon, _ = self._find_local_pos()
            
            include_self = self.vars['mesh_include_self'].get()
            only_recent = self.vars['mesh_only_recent'].get()
            try:
                recent_limit = int(self.vars['mesh_recent_secs'].get())
            except:
                recent_limit = 86400
            
            now_ts = time.time()
            rows = []
            
            for node_id, data in nodes.items():
                if not include_self and node_id == self.device.local_node_id:
                    continue
                
                if only_recent and data.get('lastHeard'):
                    try:
                        if now_ts - float(data['lastHeard']) > recent_limit:
                            continue
                    except: pass
                
                user = data.get('user', {})
                lat, lon, _ = utils.extract_position(data)
                dist = utils.haversine_meters(local_lat, local_lon, lat, lon)
                
                last_str = self._format_last_contact(data.get('lastHeard'))
                
                rows.append({
                    'id': node_id,
                    'short': user.get('shortName', ''),
                    'long': user.get('longName', ''),
                    'hw': user.get('hwModel', ''),
                    'role': user.get('role', ''),
                    'hops': data.get('hopsAway', ''),
                    'snr': data.get('snr', ''),
                    'dist': utils.format_distance(dist),
                    'last': last_str,
                })
            
            self.mesh_tree.delete(*self.mesh_tree.get_children())
            for r in rows:
                self.mesh_tree.insert('', tk.END, values=(
                    r['id'], r['short'], r['long'], r['hw'], r['role'],
                    r['hops'], r['snr'], r['dist'], r['last']
                ))
            
            self.vars['mesh_selected'].set(f"Nodi: {len(rows)}")
            
        except Exception as e:
            self.log(f"Errore mesh: {e}", "error")
    
    def _find_local_pos(self):
        nodes = self.device.get_nodes()
        if self.device.local_node_id and self.device.local_node_id in nodes:
            return utils.extract_position(nodes[self.device.local_node_id])
        return None, None, None
    
    def on_mesh_select(self, event=None):
        sel = self.mesh_tree.selection()
        if not sel: return
        
        item = self.mesh_tree.item(sel[0])
        vals = item['values']
        if vals:
            self.mesh_detail.delete(1.0, tk.END)
            self.mesh_detail.insert(tk.END, f"Dettaglio nodo {vals[0]}\n")
            self.mesh_detail.insert(tk.END, f"Short: {vals[1]}\nLong: {vals[2]}\nHW: {vals[3]}\nRole: {vals[4]}")
    
    def send_chat(self):
        msg = self.chat_text.get(1.0, tk.END).strip()
        if not msg:
            messagebox.showwarning("Attenzione", "Scrivi un messaggio")
            return
        
        if self.device.send_text(msg):
            self.log(f"Canale: {msg}", "channel")
            self.chat_text.delete(1.0, tk.END)
    
    # Invia messaggio diretto senza ACK
    def send_direct(self):
        self._send_direct_impl(use_ack=False)
    
    # Invia messaggio diretto con ACK
    def send_direct_with_ack(self):
        self._send_direct_impl(use_ack=True)
    
    # Implementazione comune per invio messaggi diretti
    def _send_direct_impl(self, use_ack=False):
        msg = self.direct_text.get(1.0, tk.END).strip()
        dest = self.vars['dest'].get().strip()
        
        if not msg or not dest:
            messagebox.showwarning("Attenzione", "Inserisci destinatario e messaggio")
            return
        
        if use_ack is None:
            use_ack = self.vars['use_ack'].get()
        
        timeout = self.vars['ack_timeout'].get()
        
        def on_ack_callback(success, delivery_time, data):
            self.ui_queue.put(('ack_update', {
                'success': success,
                'time': delivery_time,
                'dest': dest,
                'text': msg[:30] + '...',
                'msg_id': data.get('local_id') if data else None,
                'data': data
            }))
        
        self.device._ack_timeout = timeout
        
        try:
            if use_ack:
                msg_id = self.device.send_text_with_ack(msg, dest, callback=on_ack_callback)
                status_text = "In attesa"
                status_tag = 'pending'
            else:
                msg_id = self.device.send_text(msg, dest)
                status_text = "Inviato"
                status_tag = 'sent'
            
            if msg_id:
                log_msg = f"Inviato a {dest} (ID: {msg_id})" + (" con ACK" if use_ack else "")
                self.log(log_msg, "info" if not use_ack else "ack_pending")
                self.direct_text.delete(1.0, tk.END)
                
                item_id = self.history_tree.insert('', 0, values=(
                    datetime.now().strftime("%H:%M:%S"),
                    dest,
                    msg[:30] + ('...' if len(msg) > 30 else ''),
                    status_text,
                    "-",
                    str(msg_id) if msg_id else "-"
                ), tags=(status_tag,))
                
                if use_ack and status_tag == 'pending' and msg_id:
                    self.pending_messages[msg_id] = {
                        'item_id': item_id,
                        'timestamp': time.time(),
                        'dest': dest,
                        'text': msg,
                        'timeout': timeout,
                        'retries': 0
                    }
                
                self._update_pending_count()
            else:
                self.log(f"Invio fallito - nessun ID restituito", "error")
                messagebox.showerror("Errore", "Invio messaggio fallito")
                
        except Exception as e:
            self.log(f"Errore invio: {e}", "error")
            messagebox.showerror("Errore", f"Invio fallito: {e}")

    #######################################################################################################################################

    def _handle_ack_update(self, data):
        try:
            msg_id = data.get('msg_id')
            success = data.get('success', False)
            delivery_time = data.get('time')
            dest = data.get('dest')
            
            if msg_id and msg_id in self.pending_messages:
                pending = self.pending_messages[msg_id]
                item_id = pending['item_id']
                
                if self.history_tree.exists(item_id):
                    values = list(self.history_tree.item(item_id, 'values'))
                    if success:
                        values[3] = f"Consegnato ({delivery_time:.1f}s)"
                        values[4] = f"{delivery_time:.1f}"
                        self.history_tree.item(item_id, values=values, tags=('delivered',))
                        self.log(f"Messaggio {msg_id} consegnato in {delivery_time:.1f}s", "ack_delivered")
                        if self.vars['show_ack_notifications'].get():
                            self._show_notification("Messaggio consegnato", f"A {dest} in {delivery_time:.1f}s")
                    else:
                        values[3] = "Timeout"
                        values[4] = "-"
                        self.history_tree.item(item_id, values=values, tags=('timeout',))
                        self.log(f"Timeout messaggio {msg_id}", "ack_timeout")
                        if self.vars['auto_retry_on_timeout'].get() and pending['retries'] < self.vars['max_retries'].get():
                            pending['retries'] += 1
                            self.root.after(2000, lambda: self._retry_message(pending))
                    
                    del self.pending_messages[msg_id]
            
            self._update_pending_count()
            self.refresh_message_stats()
        except Exception as e:
            self.log(f"Errore aggiornamento ACK: {e}", "error")    
        
    ####################################################################################
    # Ritenta per un messaggio scaduto
    #-----------------------------------------------------------------------------------

    def _retry_message(self, pending):
        
        self.log(f"Ritento invio a {pending['dest']} (tentativo {pending['retries']})", "info")
        
        def retry_callback(success, delivery_time, data):
            self.ui_queue.put(('ack_update', {
                'success': success,
                'time': delivery_time,
                'dest': pending['dest'],
                'text': pending['text'][:30],
                'msg_id': data.get('local_id') if data else None,
                'data': data
            }))
        
        new_id = self.device.send_text_with_ack(
            pending['text'], 
            pending['dest'], 
            callback=retry_callback,
            timeout=pending['timeout']
        )
        
        if new_id and pending.get('item_id') and self.history_tree.exists(pending['item_id']):
            values = list(self.history_tree.item(pending['item_id'], 'values'))
            values[5] = str(new_id)
            self.history_tree.item(pending['item_id'], values=values)
    
    # Controlla periodicamente timeout ACK
    def _check_ack_timeouts(self):
        
        if hasattr(self.device, 'check_ack_timeouts'):
            timed_out = self.device.check_ack_timeouts()
            if timed_out > 0:
                self.refresh_message_stats()
            self._update_pending_count()
        self.root.after(5000, self._check_ack_timeouts)
    
    # Aggiorno messaggi in attesa
    def _update_pending_count(self):
        
        count = len(self.pending_messages)
        if count > 0:
            self.pending_label.config(text=f"{count} in attesa", foreground=UI.ACK_PENDING)
        else:
            self.pending_label.config(text="")
    
    # Mostra notifica desktop
    def _show_notification(self, title, message):
        
        try:
            from plyer import notification
            notification.notify(
                title=title,
                message=message,
                timeout=3
            )
        except:
            self.root.title(f"Notifica: {title} - {message}")
            self.root.after(3000, lambda: self.root.title("Meshtastic Ultimate Center v4.2 - aiutocomputerhelp.it"))
    
    # Menu contestuale per la cronologia
    def show_history_menu(self, event):
        
        sel = self.history_tree.selection()
        if not sel: return
        
        item = self.history_tree.item(sel[0])
        values = item['values']
        
        menu = tk.Menu(self.root, tearoff=0, bg=UI.PANEL, fg=UI.FG)
        menu.add_command(label="Ritenta", command=lambda: self._retry_selected(values))
        menu.add_command(label="Copia ID", command=lambda: self.root.clipboard_append(str(values[5])))
        menu.add_command(label="Copia messaggio", command=lambda: self.root.clipboard_append(str(values[2])))
        menu.add_separator()
        menu.add_command(label="Elimina", command=lambda: self.history_tree.delete(sel[0]))
        
        menu.post(event.x_root, event.y_root)
    
    # Ritenta di inviare il messaggio
    def _retry_selected(self, values):
         
        if len(values) >= 5:
            dest = values[1]
            msg = values[2].replace('...', '')
            
            dialog = tk.Toplevel(self.root)
            dialog.title("Ritenta messaggio")
            dialog.geometry("400x200")
            dialog.configure(bg=UI.BG)
            
            ttk.Label(dialog, text="Destinatario:").pack(anchor="w", padx=10, pady=5)
            dest_var = tk.StringVar(value=dest)
            ttk.Entry(dialog, textvariable=dest_var, width=40).pack(fill=tk.X, padx=10)
            
            ttk.Label(dialog, text="Messaggio:").pack(anchor="w", padx=10, pady=5)
            msg_text = tk.Text(dialog, height=4, bg=UI.PANEL, fg=UI.FG)
            msg_text.insert(1.0, msg)
            msg_text.pack(fill=tk.X, padx=10)
            
            def do_retry():
                new_msg = msg_text.get(1.0, tk.END).strip()
                if new_msg:
                    self.vars['dest'].set(dest_var.get())
                    self.direct_text.delete(1.0, tk.END)
                    self.direct_text.insert(1.0, new_msg)
                    self.send_direct_with_ack()
                    dialog.destroy()
            
            ttk.Button(dialog, text="Invia con ACK", command=do_retry).pack(pady=10)
    

    def refresh_message_stats(self):
    
        if not hasattr(self.device, 'get_message_stats'):
            return
        
        try:
            stats = self.device.get_message_stats()
            history = self.device.get_message_history(limit=200)
            
            stats_text = f"""STATISTICHE MESSAGGI
{'='*50}

Totale messaggi: {stats['total']}
Consegnati: {stats['delivered']} ({stats['success_rate']:.1f}%)
In attesa: {stats['pending']}
Timeout: {stats['timeout']}
Ricevuti: {stats.get('received', 0)}
Tempo medio consegna: {stats['avg_delivery_time']:.2f}s
    """
            self.stats_text.delete(1.0, tk.END)
            self.stats_text.insert(1.0, stats_text)
            
            # Ottieni gli ID correnti per evitare duplicati
            current_ids = set()
            for item in self.messages_tree.get_children():
                values = self.messages_tree.item(item, 'values')
                if len(values) >= 7:
                    current_ids.add(str(values[6]))  # ID è la settima colonna
            
            # Aggiungi solo i messaggi nuovi
            for msg in history:
                msg_id = str(msg['id'])
                if msg_id in current_ids:
                    continue  # Già presente
                
                # Determina il timestamp in base al tipo di messaggio
                if 'sent' in msg:
                    timestamp = msg['sent']
                elif 'received' in msg:
                    timestamp = msg['received']
                else:
                    self.log(f"Messaggio senza timestamp: {msg}", "debug")
                    continue
                
                sent_time = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S %d/%m")
                
                if msg.get('direction') == 'received':
                    destinatario = f"Da: {msg['from']}"
                    stato = "Ricevuto"
                    tempo = "-"
                    tag = 'received'
                    tentativi = 0
                else:
                    destinatario = msg.get('dest', 'Broadcast')
                    if msg['status'] == MessageState.DELIVERED:
                        stato = "Consegnato"
                        tempo = f"{msg.get('delivery_time', 0):.1f}"
                        tag = 'delivered'
                    elif msg['status'] == MessageState.PENDING:
                        stato = "In attesa"
                        tempo = "-"
                        tag = 'pending'
                    elif msg['status'] == MessageState.TIMEOUT:
                        stato = "Timeout"
                        tempo = "-"
                        tag = 'timeout'
                    else:
                        stato = "Inviato"
                        tempo = "-"
                        tag = 'sent'
                    tentativi = msg.get('retries', 0)
                
                # Inserisci in testa (più recente)
                self.messages_tree.insert('', 0, values=(
                    sent_time,
                    destinatario,
                    msg['text'][:50] + ('...' if len(msg['text']) > 50 else ''),
                    stato,
                    tempo,
                    tentativi,
                    msg_id
                ), tags=(tag,))
            
    
            # Limita il numero di elementi mostrati (opzionale)
            children = self.messages_tree.get_children()
            if len(children) > 200:
                for item in children[200:]:
                    self.messages_tree.delete(item)
                
        except Exception as e:
            self.log(f"Errore in refresh_message_stats: {e}", "error")
            import traceback
            self.log(traceback.format_exc(), "debug")

    # Pulisce storico messaggi
    def clear_message_history(self):
        
        if messagebox.askyesno("Conferma", "Cancellare tutto lo storico messaggi?"):
            self.device._message_history = []
            self.pending_messages.clear()
            self.refresh_message_stats()
            self.history_tree.delete(*self.history_tree.get_children())
            self.log("Storico messaggi cancellato", "info")
    
 
    def export_message_history(self):
        
        if not hasattr(self.device, '_message_history') or not self.device._message_history:
            messagebox.showinfo("Info", "Nessun messaggio da esportare")
            return
        
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("Tutti i file", "*.*")],
            title="Esporta storico messaggi"
        )
        if not path:
            return
        
        try:
            with open(path, 'w', encoding='utf-8') as f:
                # Intestazione CSV
                f.write("Data/Ora,Tipo,Destinazione/Mittente,Messaggio,Stato,Tempo (s),Tentativi,ID\n")
                
                for msg in self.device._message_history:
                    # Determina il timestamp
                    if 'sent' in msg:
                        timestamp = msg['sent']
                        data_ora = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                    elif 'received' in msg:
                        timestamp = msg['received']
                        data_ora = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        data_ora = "N/A"
                    
                    # Determina il tipo e destinazione/mittente
                    if msg.get('direction') == 'received':
                        tipo = "Ricevuto"
                        destinazione = msg.get('from', 'Sconosciuto')
                        stato = "Ricevuto"
                        tempo = ""
                        tentativi = ""
                    else:
                        tipo = "Inviato"
                        destinazione = msg.get('dest', 'Broadcast')
                        
                        # Stato del messaggio
                        if msg['status'] == MessageState.DELIVERED:
                            stato = "Consegnato"
                            tempo = f"{msg.get('delivery_time', 0):.1f}"
                        elif msg['status'] == MessageState.PENDING:
                            stato = "In attesa"
                            tempo = ""
                        elif msg['status'] == MessageState.TIMEOUT:
                            stato = "Timeout"
                            tempo = ""
                        else:
                            stato = "Inviato"
                            tempo = ""
                        
                        tentativi = msg.get('retries', 0)
                    
                    # Prepara i campi CSV
                    campi = [
                        data_ora,
                        tipo,
                        destinazione,
                        msg['text'].replace('"', '""'),  # Escape delle virgolette
                        stato,
                        str(tempo),
                        str(tentativi),
                        str(msg['id'])
                    ]
                    
                    # Scrivi la riga CSV
                    f.write(','.join(f'"{c}"' for c in campi) + '\n')
                
            self.log(f"Storico esportato in {path}", "success")
            messagebox.showinfo("Esportazione completata", f"Storico esportato in:\n{path}")
            
        except Exception as e:
            self.log(f"Errore esportazione: {e}", "error")
            import traceback
            self.log(traceback.format_exc(), "debug")
            messagebox.showerror("Errore", f"Esportazione fallita:\n{str(e)}")
    
    def filter_messages(self):
        """Filtra messaggi per stato e testo"""
        filter_state = self.filter_state.get()
        search_text = self.search_var.get().lower()
        
        for item in self.messages_tree.get_children():
            values = self.messages_tree.item(item, 'values')
            stato = values[3]
            msg_text = values[2].lower()
            
            state_match = True
            if filter_state != "Tutti":
                if filter_state == "Consegnato":
                    if not stato.startswith("Consegnato"):
                        state_match = False
                elif filter_state == "In attesa":
                    if stato != "In attesa":
                        state_match = False
                elif filter_state == "Timeout":
                    if stato != "Timeout":
                        state_match = False
                elif filter_state == "Inviato":
                    if stato != "Inviato":
                        state_match = False
            
            text_match = search_text in msg_text if search_text else True
            
            if state_match and text_match:
                self.messages_tree.reattach(item, "", "end")
            else:
                self.messages_tree.detach(item)
    
    def on_node_select(self, event=None):
        sel = self.nodes_tree.selection()
        if sel:
            vals = self.nodes_tree.item(sel[0])['values']
            if vals:
                self.vars['dest'].set(vals[0])
    
    def on_node_double(self, event):
        sel = self.nodes_tree.selection()
        if sel:
            vals = self.nodes_tree.item(sel[0])['values']
            if vals:
                self.show_node_info(vals[0])
    
    def show_node_info(self, node_id):
        nodes = self.device.get_nodes()
        if node_id not in nodes: return
        
        data = nodes[node_id]
        user = data.get('user', {})
        msg = f"ID: {node_id}\n"
        msg += f"Name: {user.get('longName', 'N/A')}\n"
        msg += f"Short: {user.get('shortName', 'N/A')}\n"
        msg += f"HW: {user.get('hwModel', 'N/A')}\n"
        msg += f"SNR: {data.get('snr', 'N/A')}\n"
        msg += f"RSSI: {data.get('rssi', 'N/A')}\n"
        msg += f"Battery: {data.get('deviceMetrics', {}).get('batteryLevel', 'N/A')}%\n"
        msg += f"MQTT: {'Si' if data.get('viaMqtt') else 'No'}\n"
        msg += f"Preferito: {'Si' if node_id in self.favorite_nodes else 'No'}"
        
        messagebox.showinfo(f"Nodo {node_id}", msg)
    
    def show_node_menu(self, event):
        sel = self.nodes_tree.selection()
        if not sel: return
        
        vals = self.nodes_tree.item(sel[0])['values']
        node_id = vals[0]
        is_mqtt = "MQTT" in vals[2] if len(vals) > 2 else False
        
        menu = tk.Menu(self.root, tearoff=0, bg=UI.PANEL, fg=UI.FG)
        
        if node_id in self.favorite_nodes:
            menu.add_command(label="Rimuovi preferito", command=lambda: self.toggle_fav(node_id))
        else:
            menu.add_command(label="Aggiungi preferito", command=lambda: self.toggle_fav(node_id))
        
        menu.add_separator()
        menu.add_command(label="Info", command=lambda: self.show_node_info(node_id))
        menu.add_command(label="Messaggio", command=lambda: self.set_dest(node_id))
        
        if is_mqtt:
            menu.add_separator()
            menu.add_command(label="Elimina MQTT", command=lambda: self.delete_node(node_id),
                           foreground=UI.ERR)
        else:
            menu.add_command(label="Elimina", command=lambda: self.delete_node(node_id))
        
        menu.post(event.x_root, event.y_root)
    
    def toggle_fav(self, node_id):
        if node_id in self.favorite_nodes:
            self.favorite_nodes.remove(node_id)
            self.log(f"Rimosso preferito: {node_id}", "info")
        else:
            self.favorite_nodes.add(node_id)
            self.log(f"Aggiunto preferito: {node_id}", "info")
        self.refresh_nodes()
    
    def set_dest(self, node_id):
        self.vars['dest'].set(node_id)
        self.notebook.select(self.tab_direct)
    
    def delete_node(self, node_id):
        if node_id == self.device.local_node_id:
            messagebox.showwarning("Attenzione", "Non puoi eliminare il nodo locale")
            return
        
        if messagebox.askyesno("Conferma", f"Eliminare nodo {node_id}?"):
            if self.device.remove_node(node_id):
                self.log(f"Nodo {node_id} eliminato", "success")
                self.refresh_nodes()
            else:
                self.log(f"Errore eliminazione {node_id}", "error")
    
    def filter_nodes(self):
        filt = self.vars['filter_text'].get().lower()
        for item in self.nodes_tree.get_children():
            vals = self.nodes_tree.item(item, "values")
            if not filt or any(filt in str(v).lower() for v in vals):
                self.nodes_tree.reattach(item, "", "end")
            else:
                self.nodes_tree.detach(item)
    
    def show_node_list(self):
        nodes = self.device.get_nodes()
        if not nodes:
            messagebox.showinfo("Info", "Nessun nodo disponibile")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Seleziona nodo")
        dialog.geometry("400x300")
        dialog.configure(bg=UI.BG)
        
        listbox = tk.Listbox(dialog, bg=UI.PANEL, fg=UI.FG)
        listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        node_map = {}
        for nid, data in nodes.items():
            name = data.get('user', {}).get('longName', 'N/A')
            tipo = "MQTT" if data.get('viaMqtt') else "Radio"
            display = f"{nid} - {name} [{tipo}]"
            listbox.insert(tk.END, display)
            node_map[display] = nid
        
        def select():
            sel = listbox.curselection()
            if sel:
                display = listbox.get(sel[0])
                self.vars['dest'].set(node_map[display])
                dialog.destroy()
        
        ttk.Button(dialog, text="Seleziona", command=select).pack(pady=5)
    
    def manage_favorites(self):
        messagebox.showinfo("Info", "Usa il menu contestuale per gestire i preferiti (Clic sul nodo e tasto destro)")
    
    def confirm_clean_nodes(self):
        if not self.device.connected:
            messagebox.showwarning("Attenzione", "Non connesso")
            return
        
        mqtt_count = sum(1 for d in self.device.get_nodes().values() if d.get('viaMqtt'))
        msg = f"Eliminare tutti i nodi non preferiti?\n\n"
        msg += f"MQTT: {mqtt_count} nodi\n"
        msg += f"Radio: {len(self.device.get_nodes()) - mqtt_count - 1} nodi\n\n"
        msg += f"Dopo la cancellazione, premi Reboot per rendere permanente."
        
        if messagebox.askyesno("Conferma", msg, icon='warning'):
            self._clean_nodes()
    
    def _clean_nodes(self):
        if not self.device.connected:
            self.log("Non connesso, impossibile pulire i nodi", "warn")
            return

        nodes = self.device.get_nodes()
        local_id = self.device.local_node_id
        preserve_mqtt = self.vars['preserve_mqtt'].get()

        removed = 0
        skipped = 0

        self.root.config(cursor="watch")
        self.root.update()

        for node_id in list(nodes.keys()):
            data = nodes[node_id]

            if node_id == local_id:
                continue

            if node_id in self.favorite_nodes:
                skipped += 1
                continue

            if preserve_mqtt and data.get('viaMqtt', False):
                skipped += 1
                continue

            try:
                if self.device.remove_node(node_id):
                    removed += 1
                    self.log(f"Nodo {node_id} eliminato", "info")
                else:
                    self.log(f"Errore nell'eliminazione di {node_id}", "error")
            except Exception as e:
                self.log(f"Eccezione durante eliminazione {node_id}: {e}", "error")

            self.root.update()

        self.root.config(cursor="")
        self.log(f"Pulizia completata: {removed} nodi rimossi, {skipped} saltati", "success")
        self.refresh_nodes()
    
    def update_stats(self):
        if not self.device.connected:
            self.stats_display.delete(1.0, tk.END)
            self.stats_display.insert(tk.END, "Non connesso")
            return
        
        nodes = self.device.get_nodes()
        mqtt = sum(1 for d in nodes.values() if d.get('viaMqtt'))
        
        msg_stats = self.device.get_message_stats() if hasattr(self.device, 'get_message_stats') else {}
        
        stats = f"""STATISTICHE MESH
{'='*40}

NODI:
Totale nodi: {len(nodes)}
Radio: {len(nodes)-mqtt}
MQTT: {mqtt}
Preferiti: {len(self.favorite_nodes)}

MESSAGGI:
Totale: {msg_stats.get('total', 0)}
Consegnati: {msg_stats.get('delivered', 0)}
In attesa: {msg_stats.get('pending', 0)}
Timeout: {msg_stats.get('timeout', 0)}
Tasso successo: {msg_stats.get('success_rate', 0):.1f}%

ERRORI:
Errori parsing: {self.parse_errors}

Nodo locale: {self.device.local_node_id}
"""
        self.stats_display.delete(1.0, tk.END)
        self.stats_display.insert(tk.END, stats)
    
    def show_stats(self):
        self.update_stats()
        self.notebook.select(self.tab_stats)
    
    def apply_config(self):
        """Applica la configurazione al dispositivo (Update)"""
        if not self.device.connected:
            messagebox.showwarning("Attenzione", "Non connesso a nessun dispositivo")
            return
        
        advanced_changes = any([
            self.vars['role'].get().strip(),
            self.vars['region'].get().strip(),
            self.vars['modem'].get().strip(),
            self.vars['hop_limit'].get().strip()
        ])
        
        if advanced_changes:
            proceed = messagebox.askyesno(
                "Attenzione ! Conferma le modifiche radio",
                "Stai per modificare parametri radio che potrebbero rendere\n"
                "il dispositivo incompatibile con la rete attuale.\n\n"
                "Vuoi continuare?",
                icon='warning'
            )
            if not proceed:
                self.log("Modifiche annullate", "info")
                return
        
        try:
            self.root.config(cursor="watch")
            self.root.update()
            
            self.log("Applicazione configurazione in corso...", "info")
            
            if self.vars['channel_write_name'].get():
                name = self.vars['channel_name'].get().strip()
                if name and len(name.encode('utf-8')) > 11:
                    messagebox.showerror("Errore", 
                        "Il nome del canale è troppo lungo (max 11 byte)")
                    self.root.config(cursor="")
                    return
            
            changes = self.device.apply_all_config(self.vars, self._validate_channel_name)
            
            if changes:
                self.log(f"Modifiche applicate: {len(changes)} parametri", "success")
                for change in changes[:10]:
                    self.log(f"  - {change}", "info")
                
                messagebox.showinfo("Successo", 
                    f"Configurazione applicata!\n\n"
                    f"{len(changes)} parametri modificati.\n\n"
                    f"Rileggi la configurazione per verificare.")
                
                self.root.after(2000, self.read_config)
            else:
                self.log("Nessuna modifica rilevata", "info")
                messagebox.showinfo("Info", "Nessuna modifica da applicare")
        
        except Exception as e:
            self.log(f"Errore applicazione: {e}", "error")
            import traceback
            self.log(traceback.format_exc(), "muted")
            messagebox.showerror("Errore", str(e))
        
        finally:
            self.root.config(cursor="")
    
    def confirm_reboot(self):
        if not self.device.connected:
            messagebox.showwarning("Attenzione", "Non connesso")
            return
        
        if messagebox.askyesno("Conferma", "Riavviare il dispositivo?\n\nLa connessione verrà persa per circa 10 secondi"):
            self.device.reboot()
            self.disconnect()
            self._show_reboot_countdown()
    
    def _show_reboot_countdown(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Reboot")
        dialog.geometry("300x150")
        dialog.configure(bg=UI.BG)
        
        ttk.Label(dialog, text="Reboot in corso...", font=('',12,'bold')).pack(pady=20)
        
        count = tk.StringVar(value="30")
        ttk.Label(dialog, textvariable=count, font=('',24,'bold'), foreground=UI.WARN).pack()
        
        def update(sec):
            if sec > 0:
                count.set(str(sec))
                dialog.after(1000, update, sec-1)
            else:
                dialog.destroy()
        
        update(30)
    
    def export_snapshot(self):
        if not self.device.connected:
            messagebox.showwarning("Attenzione", "Non connesso a nessun dispositivo")
            return

        try:
            self.root.config(cursor="watch")
            self.root.update()

            self.log("Lettura configurazione completa per backup...", "info")
            config = self.device.get_full_config()

            path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("Tutti i file", "*.*")],
                title="Salva backup configurazione"
            )
            if not path:
                return

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            self.log(f"Backup salvato in {path}", "success")
            messagebox.showinfo("Backup completato", f"Configurazione salvata in:\n{path}")

        except Exception as e:
            self.log(f"Errore durante il backup: {e}", "error")
            import traceback
            self.log(traceback.format_exc(), "muted")
            messagebox.showerror("Errore backup", str(e))
        finally:
            self.root.config(cursor="")

    def import_snapshot(self):
        if not self.device.connected:
            messagebox.showwarning("Attenzione", "Non connesso a nessun dispositivo")
            return

        path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("Tutti i file", "*.*")],
            title="Seleziona file di backup"
        )
        if not path:
            return

        if not messagebox.askyesno(
            "Conferma restore",
            "Stai per sovrascrivere TUTTE le impostazioni del dispositivo con quelle del backup.\n\n"
            "Il dispositivo potrebbe diventare incompatibile con la rete attuale.\n"
            "Assicurati che il backup sia compatibile con il firmware corrente.\n\n"
            "Continuare?",
            icon='warning'
        ):
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            self.root.config(cursor="watch")
            self.root.update()

            self.log("Ripristino configurazione in corso...", "info")
            self.device.set_full_config(config)

            self.log("Configurazione ripristinata. Rilettura in corso...", "info")
            self.root.after(2000, self.read_config)
            messagebox.showinfo("Restore completato", "Configurazione ripristinata con successo.")

        except Exception as e:
            self.log(f"Errore durante il restore: {e}", "error")
            import traceback
            self.log(traceback.format_exc(), "muted")
            messagebox.showerror("Errore restore", str(e))
        finally:
            self.root.config(cursor="")
    
    def save_settings(self):
        self.log("Impostazioni salvate", "info")
        messagebox.showinfo("Info", "Impostazioni salvate (in memoria)")
    
    def process_queue(self):
        try:
            while True:
                kind, data = self.ui_queue.get_nowait()
                
                if kind == 'log':
                    msg, tag = data
                    self.log_text.insert(tk.END, msg, tag)
                    if self.vars['auto_scroll'].get():
                        self.log_text.see(tk.END)
                
                elif kind == 'update_nodes':
                    self._populate_nodes(data)
                
                elif kind == 'text_packet':
                    self._handle_message(data)
                
                elif kind == 'ack_update':
                    self._handle_ack_update(data)
                    
        except queue.Empty:
            pass
        
        if (self.vars['auto_refresh'].get() and self.device.connected):
            now = time.time()
            if not hasattr(self, '_last_refresh'):
                self._last_refresh = now
            elif now - self._last_refresh > self.vars['refresh_interval'].get():
                self.refresh_nodes()
                self._last_refresh = now
        
        self.root.after(100, self.process_queue)
    
    def _format_last_contact(self, value):
        if not value:
            return ""
        try:
            ts = float(value)
            abs_time = datetime.fromtimestamp(ts).strftime("%H:%M %d/%m")
            rel_time = utils.time_ago(ts)
            return f"{abs_time} | {rel_time} fa" if rel_time else abs_time
        except:
            return ""

    def _populate_nodes(self, nodes):
        self.nodes_tree.delete(*self.nodes_tree.get_children())
        
        for node_id, data in nodes.items():
            if not isinstance(data, dict): continue
            
            user = data.get('user', {})
            name = user.get('longName', '') or user.get('shortName', '') or '-'
            is_mqtt = data.get('viaMqtt', False)
            tipo = "MQTT" if is_mqtt else "Radio"
            fav = "*" if node_id in self.favorite_nodes else ""
            hops = data.get('hopsAway', '-')
            snr = data.get('snr', '-')
            rssi = data.get('rssi', '-')
            
            qual = "Buono"
            try:
                rssi_val = float(rssi) if rssi != '-' else -100
                if rssi_val > self.vars['rssi_threshold'].get():
                    qual = "Ottimo"
                elif rssi_val > self.vars['rssi_threshold'].get() - 20:
                    qual = "Buono"
                else:
                    qual = "Debole"
            except: pass
            
            last = self._format_last_contact(data.get('lastHeard'))
            
            self.nodes_tree.insert('', tk.END, values=(
                node_id, name, tipo, fav, hops, snr, rssi, qual, last
            ))
    
    def _handle_message(self, packet):
        try:
            from_id = utils.normalize_id(packet.get('fromId', packet.get('from')))
            to_id = utils.normalize_id(packet.get('toId', packet.get('to')))
            text = packet.get('decoded', {}).get('text', '')
            
            if not text: return
            
            if self.vars['only_my_msgs'].get() and to_id != self.device.local_node_id:
                return
            
            msg_type = "Diretto" if to_id == self.device.local_node_id else "Canale"
            self.log(f"{msg_type} da {from_id}: {text}\n", "info" if to_id == self.device.local_node_id else None)
            
        except Exception as e:
            self.parse_errors += 1
    
    def on_close(self):
        self.disconnect()
        self.root.destroy()