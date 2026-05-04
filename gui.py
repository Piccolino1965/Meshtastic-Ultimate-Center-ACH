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
from i18n import tr, load_language, save_language, current_language
from core import MeshtasticDevice

class MeshtasticUltimateCenter:
    def __init__(self, root):
        load_language()
        self.root = root
        self.root.title(tr("app.title"))
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
            self.log(tr("logs.meshtastic_missing", error=e), "error")
            messagebox.showerror(tr("dialogs.meshtastic_missing_title"), tr("dialogs.meshtastic_missing_body"))
    
    def on_new_message(self):
        
        try:
            # Aggiorna la UI in modo thread-safe
            self.root.after(0, self.refresh_message_stats)
            self.root.after(0, self._update_pending_count)
        except Exception as e:
            print(tr("logs.on_new_message_error", error=e))


    # ==================== LINGUA INTERFACCIA ====================

    def _language_label(self, language_code):
        """Restituisce l'etichetta visibile per il codice lingua."""
        code = str(language_code or "").strip().lower()
        if code == "en":
            return tr("settings.english")
        return tr("settings.italian")

    def _language_code(self, language_label):
        """
        Converte l'etichetta scelta nella GUI nel codice lingua interno.
        I codici interni restano sempre it/en e non dipendono dal testo mostrato.
        """
        value = str(language_label or "").strip().lower()
        if value in ("en", "english", tr("settings.english").strip().lower()):
            return "en"
        return "it"

    def _language_labels(self):
        """Etichette mostrate nelle ComboBox lingua."""
        return [tr("settings.italian"), tr("settings.english")]

    def on_language_change(self, event=None):
        """
        Salva la lingua scelta dalla GUI.
        La UI viene aggiornata al prossimo avvio per evitare effetti collaterali sui widget Tkinter.
        """
        lang_code = self._language_code(self.vars["language"].get())

        if save_language(lang_code):
            self.vars["language"].set(self._language_label(lang_code))
            self.log(tr("logs.settings_saved"), "info")
            messagebox.showinfo(
                tr("dialogs.settings_saved_title"),
                tr("settings.language_restart_note")
            )
        else:
            messagebox.showerror(
                tr("common.error"),
                "Impossibile salvare settings.json nella cartella dell'applicazione."
            )

    # delineo tutte le variabili Tkinter
    def _create_variables(self):
        
        return {
            # Connessione
            'conn_type': tk.StringVar(value="serial"),
            'port': tk.StringVar(value="COM3"),
            'host': tk.StringVar(value="192.168.1.1"),
            'status': tk.StringVar(value=tr("connection.disconnected")),
            
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
            'channel_psk': tk.StringVar(value=tr("primary_channel.not_managed")),
            'channel_write_name': tk.BooleanVar(value=True),
            'channel_write_flags': tk.BooleanVar(value=True),
            
            # Mesh
            'mesh_include_self': tk.BooleanVar(value=False),
            'mesh_only_recent': tk.BooleanVar(value=False),
            'mesh_recent_secs': tk.StringVar(value="86400"),
            'mesh_selected': tk.StringVar(value=tr("mesh.no_node")),
            
            # UI Options
            'auto_scroll': tk.BooleanVar(value=True),
            'language': tk.StringVar(value=self._language_label(current_language())),
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
        ttk.Label(parent, text=tr("connection.label")).pack(side=tk.LEFT)
        ttk.Radiobutton(parent, text=tr("connection.serial"), variable=self.vars['conn_type'], 
                       value="serial").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(parent, text=tr("connection.tcp"), variable=self.vars['conn_type'],
                       value="tcp").pack(side=tk.LEFT)
        
        self.port_combo = ttk.Combobox(parent, textvariable=self.vars['port'],
                                      values=UI.PORTS, width=12)
        self.port_combo.pack(side=tk.LEFT, padx=5)
        
        self.host_entry = ttk.Entry(parent, textvariable=self.vars['host'], width=15)
        
        # Scelta lingua in toolbar.
        # La ComboBox mostra etichette leggibili, ma salva solo codici interni it/en.
        self.language_label = ttk.Label(parent, text=tr("settings.language") + ":")
        self.language_label.pack(side=tk.LEFT, padx=(10, 2))

        self.language_combo = ttk.Combobox(
            parent,
            textvariable=self.vars['language'],
            values=self._language_labels(),
            width=10,
            state="readonly"
        )
        self.language_combo.pack(side=tk.LEFT, padx=5)
        self.language_combo.bind("<<ComboboxSelected>>", self.on_language_change)

        self._update_conn_fields()
        self.vars['conn_type'].trace('w', lambda *a: self._update_conn_fields())
        
        self.connect_btn = ttk.Button(parent, text=tr("connection.connect"), command=self.connect)
        self.connect_btn.pack(side=tk.LEFT, padx=2)
        
        self.disconnect_btn = ttk.Button(parent, text=tr("connection.disconnect"), command=self.disconnect)
        self.disconnect_btn.pack(side=tk.LEFT, padx=2)
        
        # Separatore
        ttk.Separator(parent, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Comandi configurazione
        ttk.Button(parent, text=tr("toolbar.read_config"), command=self.read_config).pack(side=tk.LEFT, padx=2)
        ttk.Button(parent, text=tr("toolbar.update"), command=self.apply_config).pack(side=tk.LEFT, padx=2)
        
        # Separatore
        ttk.Separator(parent, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Backup/Restore
        ttk.Button(parent, text=tr("toolbar.backup"), command=self.export_snapshot).pack(side=tk.LEFT, padx=2)
        ttk.Button(parent, text=tr("toolbar.restore"), command=self.import_snapshot).pack(side=tk.LEFT, padx=2)
        
        # Separatore
        ttk.Separator(parent, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Utilità
        ttk.Button(parent, text=tr("toolbar.clear_log"), command=self.clear_log).pack(side=tk.LEFT, padx=2)
        ttk.Button(parent, text=tr("toolbar.statistics"), command=self.show_stats).pack(side=tk.LEFT, padx=2)
        ttk.Button(parent, text=tr("toolbar.reboot"), command=self.confirm_reboot,
                  style='Danger.TButton').pack(side=tk.LEFT, padx=2)
        
        # Checkbox
        ttk.Checkbutton(parent, text=tr("toolbar.only_my_messages"), 
                    variable=self.vars['only_my_msgs']).pack(side=tk.LEFT, padx=5)
    
    # pannello log
    def _build_log_panel(self, parent):
        
        header = ttk.Frame(parent)
        header.pack(fill=tk.X)
        ttk.Label(header, text=tr("log_panel.title"), font=('',10,'bold')).pack(side=tk.LEFT)
        
        self.parse_error_label = ttk.Label(header, text="", foreground='orange')
        self.parse_error_label.pack(side=tk.RIGHT, padx=10)
        
        ttk.Checkbutton(header, text=tr("log_panel.auto_scroll"), 
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
        self.notebook.add(self.tab_identity, text=tr("tabs.identity"))
        
        # Green tab
        self.tab_green = ttk.Frame(self.notebook)
        self._build_green_tab()
        self.notebook.add(self.tab_green, text=tr("tabs.green"))
        
        # Radio tab - MODIFICATO (rimosso colore)
        self.tab_radio = ttk.Frame(self.notebook)
        self._build_radio_tab()
        self.notebook.add(self.tab_radio, text=tr("tabs.radio"))
        
        # WiFi tab - MODIFICATO (rimossi colori)
        self.tab_wifi = ttk.Frame(self.notebook)
        self._build_wifi_tab()
        self.notebook.add(self.tab_wifi, text=tr("tabs.wifi"))
        
        # Primary Channel tab
        self.tab_primary = ttk.Frame(self.notebook)
        self._build_primary_tab()
        self.notebook.add(self.tab_primary, text=tr("tabs.primary_channel"))
        
        # Channels tab
        self.tab_channels = ttk.Frame(self.notebook)
        self._build_channels_tab()
        self.notebook.add(self.tab_channels, text=tr("tabs.channels"))
        
        # Mesh tab
        self.tab_mesh = ttk.Frame(self.notebook)
        self._build_mesh_tab()
        self.notebook.add(self.tab_mesh, text=tr("tabs.mesh"))
        
        # Nodes tab
        self.tab_nodes = ttk.Frame(self.notebook)
        self._build_nodes_tab()
        self.notebook.add(self.tab_nodes, text=tr("tabs.nodes"))
        
        # Chat tab
        self.tab_chat = ttk.Frame(self.notebook)
        self._build_chat_tab()
        self.notebook.add(self.tab_chat, text=tr("tabs.chat"))
        
        # Direct tab con ACK
        self.tab_direct = ttk.Frame(self.notebook)
        self._build_direct_tab()
        self.notebook.add(self.tab_direct, text=tr("tabs.direct_messages"))
        
        # Tab Stato Messaggi
        self.tab_messages = ttk.Frame(self.notebook)
        self._build_messages_tab()
        self.notebook.add(self.tab_messages, text=tr("tabs.message_status"))
        
        # Stats tab
        self.tab_stats = ttk.Frame(self.notebook)
        self._build_stats_tab()
        self.notebook.add(self.tab_stats, text=tr("toolbar.statistics"))
        
        # Settings tab con impostazioni ACK
        self.tab_settings = ttk.Frame(self.notebook)
        self._build_settings_tab()
        self.notebook.add(self.tab_settings, text=tr("tabs.settings"))
    
    def _build_identity_tab(self):
        frame = self.tab_identity
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        ttk.Label(frame, text=tr("identity.long_name")).grid(row=0, column=0, sticky="w", pady=8)
        ttk.Entry(frame, textvariable=self.vars['long_name'], width=40).grid(row=0, column=1, padx=5)
        
        ttk.Label(frame, text=tr("identity.short_name")).grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(frame, textvariable=self.vars['short_name'], width=20).grid(row=1, column=1, padx=5)
    
    def _build_green_tab(self):
        outer = self.tab_green
        outer.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Posizione
        pos = ttk.LabelFrame(outer, text=tr("green.position"))
        pos.pack(fill=tk.X, pady=5)
        
        ttk.Label(pos, text=tr("green.gps_mode")).grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(pos, textvariable=self.vars['gps_mode'], width=20).grid(row=0, column=1, padx=5)
        
        ttk.Label(pos, text=tr("green.gps_update")).grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(pos, textvariable=self.vars['gps_update'], width=15).grid(row=1, column=1, padx=5)
        
        ttk.Label(pos, text=tr("green.broadcast_secs")).grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(pos, textvariable=self.vars['pos_broadcast'], width=15).grid(row=2, column=1, padx=5)
        
        ttk.Checkbutton(pos, text=tr("green.smart_broadcast"), variable=self.vars['smart_broadcast']).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(pos, text=tr("green.fixed_position"), variable=self.vars['fixed_position']).grid(row=4, column=0, columnspan=2, sticky="w")
        
        # Range Test
        range_f = ttk.LabelFrame(outer, text=tr("green.range_test"))
        range_f.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(range_f, text=tr("green.enabled"), variable=self.vars['range_enabled']).pack(anchor="w")
        ttk.Checkbutton(range_f, text=tr("green.sender"), variable=self.vars['range_sender']).pack(anchor="w")
        ttk.Label(range_f, text=tr("green.interval")).pack(anchor="w")
        ttk.Entry(range_f, textvariable=self.vars['range_interval'], width=15).pack(anchor="w", padx=10)
        
        # MQTT
        mqtt = ttk.LabelFrame(outer, text=tr("green.mqtt"))
        mqtt.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(mqtt, text=tr("green.enabled"), variable=self.vars['mqtt_enabled']).pack(anchor="w")
        ttk.Checkbutton(mqtt, text=tr("green.proxy_to_client"), variable=self.vars['mqtt_proxy']).pack(anchor="w")
        ttk.Checkbutton(mqtt, text=tr("green.tls"), variable=self.vars['mqtt_tls']).pack(anchor="w")
        ttk.Checkbutton(mqtt, text=tr("green.encryption"), variable=self.vars['mqtt_encryption']).pack(anchor="w")
        ttk.Checkbutton(mqtt, text=tr("green.json"), variable=self.vars['mqtt_json']).pack(anchor="w")
        
        ttk.Label(mqtt, text=tr("green.broker")).pack(anchor="w")
        ttk.Entry(mqtt, textvariable=self.vars['mqtt_address'], width=40).pack(fill=tk.X, padx=5)
        
        ttk.Label(mqtt, text=tr("green.username")).pack(anchor="w")
        ttk.Entry(mqtt, textvariable=self.vars['mqtt_username'], width=30).pack(fill=tk.X, padx=5)
        
        ttk.Label(mqtt, text=tr("green.password")).pack(anchor="w")
        ttk.Entry(mqtt, textvariable=self.vars['mqtt_password'], width=30, show="*").pack(fill=tk.X, padx=5)
        
        ttk.Label(mqtt, text=tr("green.root_topic")).pack(anchor="w")
        ttk.Entry(mqtt, textvariable=self.vars['mqtt_root'], width=40).pack(fill=tk.X, padx=5)
        
        # Display
        disp = ttk.LabelFrame(outer, text=tr("green.display"))
        disp.pack(fill=tk.X, pady=5)
        
        ttk.Label(disp, text=tr("green.screen_on_secs")).pack(anchor="w")
        ttk.Entry(disp, textvariable=self.vars['display_screen'], width=15).pack(anchor="w", padx=10)
        
        ttk.Label(disp, text=tr("green.gps_format")).pack(anchor="w")
        ttk.Combobox(disp, textvariable=self.vars['display_gps'], 
                    values=UI.GPS_FORMATS, width=20).pack(anchor="w", padx=10)
        
        ttk.Checkbutton(disp, text=tr("green.compass_north_top"), variable=self.vars['display_compass']).pack(anchor="w")
        ttk.Checkbutton(disp, text=tr("green.format_24h"), variable=self.vars['display_24h']).pack(anchor="w")
    
    
    def _build_radio_tab(self):
        # Tab Radio 
        frame = self.tab_radio
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # RIMOSSO foreground=UI.WARN - ora solo grassetto per leggibilità
        ttk.Label(frame, text=tr("radio.warning"), 
                  font=('', 10, 'bold')).grid(row=0, column=0, columnspan=2, 
                                              sticky="w", pady=(5,15))

        ttk.Label(frame, text=tr("radio.node_role")).grid(row=1, column=0, sticky="w", pady=5)
        ttk.Combobox(frame, textvariable=self.vars['role'], 
                     values=UI.ROLES, width=25).grid(row=1, column=1, padx=5)
        
        ttk.Label(frame, text=tr("radio.region")).grid(row=2, column=0, sticky="w", pady=5)
        ttk.Combobox(frame, textvariable=self.vars['region'], 
                     values=UI.REGIONS, width=25).grid(row=2, column=1, padx=5)
        
        ttk.Label(frame, text=tr("radio.modem_preset")).grid(row=3, column=0, sticky="w", pady=5)
        ttk.Combobox(frame, textvariable=self.vars['modem'], 
                     values=UI.MODEM_PRESETS, width=25).grid(row=3, column=1, padx=5)
        
        ttk.Label(frame, text=tr("radio.hop_limit")).grid(row=4, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.vars['hop_limit'], width=10).grid(row=4, column=1, sticky="w", padx=5)
        
        ttk.Checkbutton(frame, text=tr("radio.tx_enabled"), 
                        variable=self.vars['tx_enabled']).grid(row=5, column=0, columnspan=2, 
                                                               sticky="w", pady=5)
    
    def _build_wifi_tab(self):
        #Tab WiFi 
        frame = self.tab_wifi
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Abilitazione WiFi
        enabled_frame = ttk.LabelFrame(frame, text=tr("wifi.enable_title"))
        enabled_frame.pack(fill=tk.X, pady=10)
        
        ttk.Checkbutton(enabled_frame, text=tr("wifi.enable_device"), 
                       variable=self.vars['wifi_enabled']).pack(anchor="w", padx=10, pady=5)
        ttk.Label(enabled_frame, 
                 text=tr("wifi.device_support_note")).pack(anchor="w", padx=10, pady=(0,5))

        # Configurazione rete
        network_frame = ttk.LabelFrame(frame, text=tr("wifi.network_config"))
        network_frame.pack(fill=tk.X, pady=10)

        # SSID
        ssid_frame = ttk.Frame(network_frame)
        ssid_frame.pack(fill=tk.X, pady=5, padx=10)
        ttk.Label(ssid_frame, text=tr("wifi.ssid"), width=15).pack(side=tk.LEFT)
        ttk.Entry(ssid_frame, textvariable=self.vars['wifi_ssid'], 
                  width=40).pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        # Password
        psk_frame = ttk.Frame(network_frame)
        psk_frame.pack(fill=tk.X, pady=5, padx=10)
        ttk.Label(psk_frame, text=tr("green.password"), width=15).pack(side=tk.LEFT)
        psk_entry = ttk.Entry(psk_frame, textvariable=self.vars['wifi_psk'], 
                              width=40, show="*")
        psk_entry.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        def toggle_password():
            if psk_entry.cget('show') == '*':
                psk_entry.config(show='')
                show_btn.config(text=tr("wifi.hide"))
            else:
                psk_entry.config(show='*')
                show_btn.config(text=tr("wifi.show"))
        
        show_btn = ttk.Button(psk_frame, text=tr("wifi.show"), command=toggle_password, width=8)
        show_btn.pack(side=tk.LEFT)

        # Nota sulla sicurezza -
        note = ttk.LabelFrame(frame, text=tr("wifi.security_note_title"))
        note.pack(fill=tk.X, pady=20)
        ttk.Label(note, 
                 text=tr("wifi.security_note"),
                 justify=tk.LEFT).pack(anchor="w", padx=10, pady=10)
        
        # Informazioni 
        info_frame = ttk.LabelFrame(frame, text=tr("wifi.info_title"))
        info_frame.pack(fill=tk.X, pady=10)
        ttk.Label(info_frame, 
                 text=tr("wifi.info_text"),
                 justify=tk.LEFT).pack(anchor="w", padx=10, pady=10)
    
    def _build_primary_tab(self):
        outer = self.tab_primary
        outer.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        head = ttk.LabelFrame(outer, text=tr("tabs.primary_channel"))
        head.pack(fill=tk.X, pady=5)
        
        ttk.Label(head, text=tr("primary_channel.index")).grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(head, textvariable=self.vars['channel_index'], width=10, state="readonly").grid(row=0, column=1, padx=5)
        
        ttk.Label(head, text=tr("primary_channel.role")).grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(head, textvariable=self.vars['channel_role'], width=20, state="readonly").grid(row=1, column=1, padx=5)
        
        ttk.Label(head, text=tr("primary_channel.name")).grid(row=2, column=0, sticky="w", pady=5)
        name_entry = ttk.Entry(head, textvariable=self.vars['channel_name'], width=30)
        name_entry.grid(row=2, column=1, padx=5)
        name_entry.bind("<FocusOut>", lambda e: self._validate_channel_name())
        
        ttk.Checkbutton(head, text=tr("primary_channel.uplink"), variable=self.vars['channel_uplink']).grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(head, text=tr("primary_channel.downlink"), variable=self.vars['channel_downlink']).grid(row=3, column=1, sticky="w")
        
        ttk.Label(head, text=tr("primary_channel.psk")).grid(row=4, column=0, sticky="w", pady=5)
        ttk.Entry(head, textvariable=self.vars['channel_psk'], width=40, state="readonly").grid(row=4, column=1, padx=5)
        
        write_frame = ttk.LabelFrame(outer, text=tr("primary_channel.write_options"))
        write_frame.pack(fill=tk.X, pady=10)
        
        ttk.Checkbutton(write_frame, text=tr("primary_channel.allow_write_name"), 
                       variable=self.vars['channel_write_name']).pack(anchor="w")
        ttk.Checkbutton(write_frame, text=tr("primary_channel.allow_write_flags"), 
                       variable=self.vars['channel_write_flags']).pack(anchor="w")
        
        ttk.Button(outer, text=tr("primary_channel.reread"), command=self.read_primary_channel).pack(pady=10)
    
    def _build_channels_tab(self):
        frame = self.tab_channels
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        ttk.Button(frame, text=tr("channels.update_channels"), command=self.read_channels).pack(anchor="w", pady=5)
        
        self.channels_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD,
            bg=UI.PANEL, fg=UI.FG, font=('Consolas',10))
        self.channels_text.pack(fill=tk.BOTH, expand=True)
    
    def _build_mesh_tab(self):
        outer = self.tab_mesh
        outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=5)
        
        ttk.Button(controls, text=tr("common.refresh"), command=self.refresh_mesh).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(controls, text=tr("mesh.include_self"), variable=self.vars['mesh_include_self']).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(controls, text=tr("mesh.only_recent"), variable=self.vars['mesh_only_recent']).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(controls, text=tr("mesh.seconds")).pack(side=tk.LEFT, padx=(10,2))
        ttk.Entry(controls, textvariable=self.vars['mesh_recent_secs'], width=8).pack(side=tk.LEFT)
        
        ttk.Label(controls, textvariable=self.vars['mesh_selected']).pack(side=tk.RIGHT, padx=5)
        
        columns = ("id", "short", "long", "hw", "role", "hops", "snr", "distance", "lastheard")
        self.mesh_tree = ttk.Treeview(outer, columns=columns, show="headings", height=15)
        
        col_widths = {"id":120, "short":80, "long":150, "hw":100, "role":80, 
                     "hops":50, "snr":60, "distance":90, "lastheard":120}
        for col in columns:
            self.mesh_tree.heading(col, text=tr(f"columns.{col}"))
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
        
        ttk.Label(toolbar, text=tr("nodes.filter")).pack(side=tk.LEFT)
        ttk.Entry(toolbar, textvariable=self.vars['filter_text'], width=20).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(toolbar, text=tr("nodes.refresh_nodes"), command=self.refresh_nodes).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(toolbar, text=tr("nodes.favorites"), command=self.manage_favorites).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text=tr("nodes.clean"), command=self.confirm_clean_nodes,
                  style='Danger.TButton').pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(toolbar, text=tr("nodes.preserve_mqtt"), variable=self.vars['preserve_mqtt']).pack(side=tk.LEFT, padx=5)
        
        columns = ("id", "nome", "tipo", "fav", "hops", "snr", "rssi", "qual", "last")
        self.nodes_tree = ttk.Treeview(frame, columns=columns, show="headings", height=20)
        
        col_widths = {"id":120, "nome":150, "tipo":60, "fav":40, "hops":50, "snr":60, "rssi":60, "qual":70, "last":120}
        for col in columns:
            self.nodes_tree.heading(col, text=tr(f"columns.{col}"))
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
        
        ttk.Label(frame, text=tr("chat.channel_message")).pack(anchor="w")
        
        self.chat_text = tk.Text(frame, height=6, wrap=tk.WORD,
            bg=UI.PANEL, fg=UI.FG, font=('',11))
        self.chat_text.pack(fill=tk.X, pady=10)
        
        ttk.Button(frame, text=tr("common.send"), command=self.send_chat).pack()
    
    def _build_direct_tab(self):
        frame = self.tab_direct
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Destinatario
        ttk.Label(frame, text=tr("direct.recipient")).pack(anchor="w")
        dest_frame = ttk.Frame(frame)
        dest_frame.pack(fill=tk.X, pady=5)
        ttk.Entry(dest_frame, textvariable=self.vars['dest'], width=30).pack(side=tk.LEFT)
        ttk.Button(dest_frame, text=tr("direct.node_list"), command=self.show_node_list).pack(side=tk.LEFT, padx=5)
        
        # Opzioni ACK
        ack_frame = ttk.LabelFrame(frame, text=tr("direct.delivery_options"))
        ack_frame.pack(fill=tk.X, pady=10)
        
        ack_check_frame = ttk.Frame(ack_frame)
        ack_check_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Checkbutton(ack_check_frame, text=tr("direct.request_ack"), 
                       variable=self.vars['use_ack']).pack(side=tk.LEFT)
        
        timeout_frame = ttk.Frame(ack_frame)
        timeout_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(timeout_frame, text=tr("direct.timeout_seconds")).pack(side=tk.LEFT)
        ttk.Spinbox(timeout_frame, from_=5, to=120, textvariable=self.vars['ack_timeout'],
                   width=5).pack(side=tk.LEFT, padx=10)
        
        notif_frame = ttk.Frame(ack_frame)
        notif_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Checkbutton(notif_frame, text=tr("direct.show_delivery_notifications"), 
                       variable=self.vars['show_ack_notifications']).pack(side=tk.LEFT)
        
        retry_frame = ttk.Frame(ack_frame)
        retry_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Checkbutton(retry_frame, text=tr("direct.auto_retry_timeout"), 
                       variable=self.vars['auto_retry_on_timeout']).pack(side=tk.LEFT)
        ttk.Label(retry_frame, text=tr("direct.max_attempts")).pack(side=tk.LEFT, padx=(20,5))
        ttk.Spinbox(retry_frame, from_=1, to=10, textvariable=self.vars['max_retries'],
                   width=3).pack(side=tk.LEFT)
        
        # Messaggio
        ttk.Label(frame, text=tr("direct.message")).pack(anchor="w", pady=(10,0))
        self.direct_text = tk.Text(frame, height=5, wrap=tk.WORD,
            bg=UI.PANEL, fg=UI.FG, font=('',11))
        self.direct_text.pack(fill=tk.X, pady=5)
        
        # Pulsanti invio
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text=tr("common.send"), command=self.send_direct).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text=tr("direct.send_with_ack"), 
                  command=self.send_direct_with_ack).pack(side=tk.LEFT, padx=2)
        
        # Cronologia
        ttk.Label(frame, text=tr("direct.message_history")).pack(anchor="w", pady=(15,5))
        
        columns = ("ora", "dest", "msg", "stato", "tempo", "id")
        self.history_tree = ttk.Treeview(frame, columns=columns, show="headings", height=8)
        
        self.history_tree.heading("ora", text=tr("columns.time"))
        self.history_tree.heading("dest", text=tr("columns.recipient"))
        self.history_tree.heading("msg", text=tr("columns.message"))
        self.history_tree.heading("stato", text=tr("columns.status"))
        self.history_tree.heading("tempo", text=tr("columns.delivery_time"))
        self.history_tree.heading("id", text=tr("columns.id"))
        
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
        
        ttk.Button(toolbar, text=tr("common.refresh"), command=self.refresh_message_stats).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text=tr("messages.clear_history"), command=self.clear_message_history).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text=tr("messages.export_csv"), command=self.export_message_history).pack(side=tk.LEFT, padx=2)
        
        stats_frame = ttk.LabelFrame(frame, text=tr("messages.delivery_stats"))
        stats_frame.pack(fill=tk.X, pady=10, padx=5)
        
        self.stats_text = tk.Text(stats_frame, height=5, bg=UI.PANEL, fg=UI.FG, wrap=tk.WORD)
        self.stats_text.pack(fill=tk.X, padx=5, pady=5)
        
        filter_frame = ttk.Frame(frame)
        filter_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(filter_frame, text=tr("messages.filter_by_status")).pack(side=tk.LEFT)
        self.filter_state = tk.StringVar(value=tr("messages.all"))
        state_combo = ttk.Combobox(filter_frame, textvariable=self.filter_state,
                                   values=[tr("messages.all"), tr("messages.delivered"), tr("messages.pending"), tr("messages.timeout"), tr("messages.sent")],
                                   width=15, state="readonly")
        state_combo.pack(side=tk.LEFT, padx=5)
        state_combo.bind('<<ComboboxSelected>>', lambda e: self.filter_messages())
        
        ttk.Label(filter_frame, text=tr("messages.search")).pack(side=tk.LEFT, padx=(20,5))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(filter_frame, textvariable=self.search_var, width=20)
        search_entry.pack(side=tk.LEFT)
        self.search_var.trace('w', lambda *a: self.filter_messages())
        
        columns = ("ora", "dest", "msg", "stato", "tempo", "tentativi", "id")
        self.messages_tree = ttk.Treeview(frame, columns=columns, show="headings", height=15)
        
        self.messages_tree.heading("ora", text=tr("columns.sent_time"))
        self.messages_tree.heading("dest", text=tr("columns.recipient"))
        self.messages_tree.heading("msg", text=tr("columns.message"))
        self.messages_tree.heading("stato", text=tr("columns.status"))
        self.messages_tree.heading("tempo", text=tr("columns.delivery_time"))
        self.messages_tree.heading("tentativi", text=tr("columns.attempts"))
        self.messages_tree.heading("id", text=tr("columns.id"))
        
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
        
        ttk.Button(frame, text=tr("common.refresh"), command=self.update_stats).pack(pady=5)
    
    def _build_settings_tab(self):
        frame = self.tab_settings
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Lingua interfaccia
        lang_frame = ttk.LabelFrame(frame, text=tr("settings.language"))
        lang_frame.pack(fill=tk.X, pady=10)

        lang_row = ttk.Frame(lang_frame)
        lang_row.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(lang_row, text=tr("settings.language")).pack(side=tk.LEFT)
        lang_combo = ttk.Combobox(
            lang_row,
            textvariable=self.vars['language'],
            values=self._language_labels(),
            width=10,
            state="readonly"
        )
        lang_combo.pack(side=tk.LEFT, padx=10)
        lang_combo.bind("<<ComboboxSelected>>", self.on_language_change)

        ttk.Label(
            lang_frame,
            text=tr("settings.language_restart_note"),
            justify=tk.LEFT
        ).pack(anchor="w", padx=10, pady=(0, 8))

        # Impostazioni ACK
        ack_settings = ttk.LabelFrame(frame, text=tr("settings.ack_settings"))
        ack_settings.pack(fill=tk.X, pady=10)
        
        ttk.Checkbutton(ack_settings, text=tr("settings.enable_desktop_notifications"),
                       variable=self.vars['show_ack_notifications']).pack(anchor="w", padx=10, pady=2)
        
        ttk.Checkbutton(ack_settings, text=tr("settings.auto_retry"),
                       variable=self.vars['auto_retry_on_timeout']).pack(anchor="w", padx=10, pady=2)
        
        timeout_frame = ttk.Frame(ack_settings)
        timeout_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(timeout_frame, text=tr("settings.default_timeout")).pack(side=tk.LEFT)
        ttk.Spinbox(timeout_frame, from_=5, to=120, textvariable=self.vars['ack_timeout'],
                   width=5).pack(side=tk.LEFT, padx=10)
        
        retry_frame = ttk.Frame(ack_settings)
        retry_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(retry_frame, text=tr("settings.max_retries")).pack(side=tk.LEFT)
        ttk.Spinbox(retry_frame, from_=1, to=10, textvariable=self.vars['max_retries'],
                   width=5).pack(side=tk.LEFT, padx=10)
        
        # RSSI
        rssi_f = ttk.Frame(frame)
        rssi_f.pack(fill=tk.X, pady=5)
        ttk.Label(rssi_f, text=tr("settings.rssi_threshold")).pack(side=tk.LEFT)
        ttk.Scale(rssi_f, from_=-100, to=-50, variable=self.vars['rssi_threshold'],
                 orient=tk.HORIZONTAL, length=200).pack(side=tk.LEFT, padx=10)
        ttk.Label(rssi_f, textvariable=self.vars['rssi_threshold']).pack(side=tk.LEFT)
        
        ref_f = ttk.Frame(frame)
        ref_f.pack(fill=tk.X, pady=5)
        ttk.Checkbutton(ref_f, text=tr("settings.auto_refresh_every"), variable=self.vars['auto_refresh']).pack(side=tk.LEFT)
        ttk.Spinbox(ref_f, from_=10, to=300, textvariable=self.vars['refresh_interval'],
                   width=5).pack(side=tk.LEFT, padx=5)
        ttk.Label(ref_f, text="secondi").pack(side=tk.LEFT)
        
        debug_f = ttk.LabelFrame(frame, text="Debug")
        debug_f.pack(fill=tk.X, pady=10)
        ttk.Checkbutton(debug_f, text=tr("settings.show_channel_debug"), 
                       variable=self.vars['show_channel_debug']).pack(anchor="w", padx=5)
        
        info_f = ttk.LabelFrame(frame, text="Info")
        info_f.pack(fill=tk.X, pady=10)
        ttk.Label(info_f, 
                 text=tr("settings.persistence_note"),
                 foreground='orange').pack(padx=5, pady=5)
        
        ttk.Button(frame, text=tr("settings.save_settings"), command=self.save_settings).pack(pady=20)
    
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
        before_widget = getattr(self, "language_label", None)

        if self.vars['conn_type'].get() == "serial":
            self.host_entry.pack_forget()
            if before_widget:
                self.port_combo.pack(side=tk.LEFT, padx=5, before=before_widget)
            else:
                self.port_combo.pack(side=tk.LEFT, padx=5)
        else:
            self.port_combo.pack_forget()
            if before_widget:
                self.host_entry.pack(side=tk.LEFT, padx=5, before=before_widget)
            else:
                self.host_entry.pack(side=tk.LEFT, padx=5)
    
    def _update_clock(self):
        self.clock_label.config(text=datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        self.root.after(1000, self._update_clock)
    
    def _validate_channel_name(self, event=None):
        name = self.vars['channel_name'].get().strip()
        if name and len(name.encode('utf-8')) > 11:
            self.log(tr("channel.name_too_long"), "warn")
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
                    messagebox.showwarning(tr("common.warning"), tr("connection.insert_port"))
                    return
                ok = self.device.connect_serial(port)
                conn_str = port
            else:
                host = self.vars['host'].get().strip()
                if not host:
                    messagebox.showwarning(tr("common.warning"), tr("connection.insert_host"))
                    return
                ok = self.device.connect_tcp(host)
                conn_str = host
            
            if ok:
                self.vars['status'].set(tr("connection.connected_to", target=conn_str))
                self.log(tr("connection.connected_to", target=conn_str), "success")
                self.refresh_nodes()
                self.root.after(2000, self.read_config)
            else:
                self.log(tr("connection.connection_failed"), "error")
        except Exception as e:
            self.log(tr("connection.connection_error_detail", error=e), "error")
            messagebox.showerror(tr("common.error"), str(e))
    
    def disconnect(self):
        self.device.disconnect()
        self.vars['status'].set(tr("connection.disconnected"))
        self.log(tr("connection.disconnected"), "success")
        self.nodes_tree.delete(*self.nodes_tree.get_children())
        self.pending_messages.clear()
        self._update_pending_count()
    
    def clear_log(self):
        self.log_text.delete(1.0, tk.END)
    
    def refresh_nodes(self):
        if not self.device.connected:
            self.log(tr("connection.not_connected"), "warn")
            return
        nodes = self.device.get_nodes()
        self.ui_queue.put(('update_nodes', nodes))
    
    def read_config(self):
        if not self.device.connected:
            messagebox.showwarning(tr("common.warning"), tr("connection.not_connected"))
            return
        
        self.log(tr("config.reading"), "info")
        
        try:
            self.device.wait_for_config(timeout=3.0)
            
            local_cfg, module_cfg = self.device.read_config()
            
            if not local_cfg:
                self.log(tr("config.local_config_missing"), "warn")
                return
            
            long_name, short_name = self.device.read_local_identity()
            self.vars['long_name'].set(long_name)
            self.vars['short_name'].set(short_name)
            self.log(tr("config.identity_read", long_name=long_name, short_name=short_name), "info")
            
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
                self.log(tr("config.wifi_read"), "wifi")
            
            self.read_primary_channel()
            self.read_channels()
            
            self.log(tr("config.read_success"), "success")
            
        except Exception as e:
            self.log(tr("config.read_error", error=e), "error")
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
                self.log(tr("channel.primary_not_found"), "warn")
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
                self.vars['channel_psk'].set(tr("channel.psk_present") if psk else tr("channel.psk_empty"))
            
            self.log(tr("channel.primary_index", index=idx), "info")
        except Exception as e:
            self.log(tr("channel.read_error", error=e), "error")
    
    def read_channels(self):
        try:
            channels = self.device.read_channels()
            primary_idx, _ = self.device.find_primary_channel()
            
            lines = [tr("channel.node_channels"), "="*60, ""]
            
            for ch in channels:
                idx = getattr(ch, 'index', 0)
                role = self.device._get_channel_role_name(ch)
                marker = tr("channel.primary_marker") if primary_idx == idx else ""
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
            self.log(tr("channel.read_channels_error", error=e), "error")
    
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
            
            self.vars['mesh_selected'].set(tr("logs.nodes_count", count=len(rows)))
            
        except Exception as e:
            self.log(tr("logs.mesh_error", error=e), "error")
    
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
            self.mesh_detail.insert(tk.END, tr("mesh.detail_title", node_id=vals[0]) + "\n")
            self.mesh_detail.insert(tk.END, f"Short: {vals[1]}\nLong: {vals[2]}\nHW: {vals[3]}\nRole: {vals[4]}")
    
    def send_chat(self):
        msg = self.chat_text.get(1.0, tk.END).strip()
        if not msg:
            messagebox.showwarning(tr("common.warning"), tr("chat.empty_message"))
            return
        
        if self.device.send_text(msg):
            self.log(tr("chat.channel_log", message=msg), "channel")
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
            messagebox.showwarning(tr("common.warning"), tr("direct.recipient_required") + " / " + tr("direct.message_required"))
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
                status_text = tr("messages.pending")
                status_tag = 'pending'
            else:
                msg_id = self.device.send_text(msg, dest)
                status_text = tr("messages.sent")
                status_tag = 'sent'
            
            if msg_id:
                log_msg = tr("logs.sent_to", dest=dest, msg_id=msg_id, ack=(tr("logs.with_ack") if use_ack else ""))
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
                self.log(tr("logs.send_failed_no_id"), "error")
                messagebox.showerror(tr("common.error"), tr("notifications.failed_body"))
                
        except Exception as e:
            self.log(tr("logs.send_error", error=e), "error")
            messagebox.showerror(tr("common.error"), tr("logs.send_failed", error=e))

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
                        values[3] = f"{tr('messages.delivered')} ({delivery_time:.1f}s)"
                        values[4] = f"{delivery_time:.1f}"
                        self.history_tree.item(item_id, values=values, tags=('delivered',))
                        self.log(tr("logs.message_delivered", msg_id=msg_id, seconds=delivery_time), "ack_delivered")
                        if self.vars['show_ack_notifications'].get():
                            self._show_notification(tr("notifications.delivered_title"), tr("notifications.delivered_body_short", dest=dest, seconds=delivery_time))
                    else:
                        values[3] = tr("messages.timeout")
                        values[4] = "-"
                        self.history_tree.item(item_id, values=values, tags=('timeout',))
                        self.log(tr("logs.message_timeout", msg_id=msg_id), "ack_timeout")
                        if self.vars['auto_retry_on_timeout'].get() and pending['retries'] < self.vars['max_retries'].get():
                            pending['retries'] += 1
                            self.root.after(2000, lambda: self._retry_message(pending))
                    
                    del self.pending_messages[msg_id]
            
            self._update_pending_count()
            self.refresh_message_stats()
        except Exception as e:
            self.log(tr("logs.ack_update_error", error=e), "error")    
        
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
            self.root.title(tr("notifications.window_title", title=title, message=message))
            self.root.after(3000, lambda: self.root.title(tr("app.title")))
    
    # Menu contestuale per la cronologia
    def show_history_menu(self, event):
        
        sel = self.history_tree.selection()
        if not sel: return
        
        item = self.history_tree.item(sel[0])
        values = item['values']
        
        menu = tk.Menu(self.root, tearoff=0, bg=UI.PANEL, fg=UI.FG)
        menu.add_command(label=tr("message_menu.retry"), command=lambda: self._retry_selected(values))
        menu.add_command(label=tr("message_menu.copy_id"), command=lambda: self.root.clipboard_append(str(values[5])))
        menu.add_command(label=tr("message_menu.copy_message"), command=lambda: self.root.clipboard_append(str(values[2])))
        menu.add_separator()
        menu.add_command(label=tr("message_menu.delete"), command=lambda: self.history_tree.delete(sel[0]))
        
        menu.post(event.x_root, event.y_root)
    
    # Ritenta di inviare il messaggio
    def _retry_selected(self, values):
         
        if len(values) >= 5:
            dest = values[1]
            msg = values[2].replace('...', '')
            
            dialog = tk.Toplevel(self.root)
            dialog.title(tr("retry_dialog.title"))
            dialog.geometry("400x200")
            dialog.configure(bg=UI.BG)
            
            ttk.Label(dialog, text=tr("direct.recipient")).pack(anchor="w", padx=10, pady=5)
            dest_var = tk.StringVar(value=dest)
            ttk.Entry(dialog, textvariable=dest_var, width=40).pack(fill=tk.X, padx=10)
            
            ttk.Label(dialog, text=tr("direct.message")).pack(anchor="w", padx=10, pady=5)
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
            
            ttk.Button(dialog, text=tr("retry_dialog.send_with_ack"), command=do_retry).pack(pady=10)
    

    def refresh_message_stats(self):
    
        if not hasattr(self.device, 'get_message_stats'):
            return
        
        try:
            stats = self.device.get_message_stats()
            history = self.device.get_message_history(limit=200)
            
            stats_text = "\n".join([
                tr("messages.stats_title"),
                "=" * 50,
                "",
                tr("messages.total_messages", count=stats['total']),
                tr("messages.delivered_count", count=stats['delivered'], rate=stats['success_rate']),
                tr("messages.pending_count", count=stats['pending']),
                tr("messages.timeout_count", count=stats['timeout']),
                tr("messages.received_count", count=stats.get('received', 0)),
                tr("messages.average_delivery_time", seconds=stats['avg_delivery_time'])
            ])
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
                    self.log(tr("logs.message_without_timestamp", message=msg), "debug")
                    continue
                
                sent_time = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S %d/%m")
                
                if msg.get('direction') == 'received':
                    destinatario = f"{tr('messages.from')}: {msg['from']}"
                    stato = tr("messages.received")
                    tempo = "-"
                    tag = 'received'
                    tentativi = 0
                else:
                    destinatario = msg.get('dest', 'Broadcast')
                    if msg['status'] == MessageState.DELIVERED:
                        stato = tr("messages.delivered")
                        tempo = f"{msg.get('delivery_time', 0):.1f}"
                        tag = 'delivered'
                    elif msg['status'] == MessageState.PENDING:
                        stato = tr("messages.pending")
                        tempo = "-"
                        tag = 'pending'
                    elif msg['status'] == MessageState.TIMEOUT:
                        stato = tr("messages.timeout")
                        tempo = "-"
                        tag = 'timeout'
                    else:
                        stato = tr("messages.sent")
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
            self.log(tr("logs.refresh_message_stats_error", error=e), "error")
            import traceback
            self.log(traceback.format_exc(), "debug")

    # Pulisce storico messaggi
    def clear_message_history(self):
        
        if messagebox.askyesno(tr("common.confirm"), tr("dialogs.clear_history_confirm")):
            self.device._message_history = []
            self.pending_messages.clear()
            self.refresh_message_stats()
            self.history_tree.delete(*self.history_tree.get_children())
            self.log(tr("logs.history_cleared"), "info")
    
 
    def export_message_history(self):
        
        if not hasattr(self.device, '_message_history') or not self.device._message_history:
            messagebox.showinfo(tr("common.info"), tr("dialogs.no_messages_export"))
            return
        
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[(tr("dialogs.csv_files"), "*.csv"), (tr("dialogs.all_files"), "*.*")],
            title=tr("dialogs.export_history_title")
        )
        if not path:
            return
        
        try:
            with open(path, 'w', encoding='utf-8') as f:
                # Intestazione CSV
                f.write(",".join([tr("csv.datetime"), tr("csv.type"), tr("csv.peer"), tr("csv.message"), tr("csv.status"), tr("csv.time_seconds"), tr("csv.attempts"), tr("csv.id")]) + "\n")
                
                for msg in self.device._message_history:
                    # Determina il timestamp
                    if 'sent' in msg:
                        timestamp = msg['sent']
                        data_ora = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                    elif 'received' in msg:
                        timestamp = msg['received']
                        data_ora = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        data_ora = tr("common.not_available")
                    
                    # Determina il tipo e destinazione/mittente
                    if msg.get('direction') == 'received':
                        tipo = tr("messages.received")
                        destinazione = msg.get('from', tr("common.unknown"))
                        stato = tr("messages.received")
                        tempo = ""
                        tentativi = ""
                    else:
                        tipo = tr("messages.sent")
                        destinazione = msg.get('dest', tr("common.broadcast"))
                        
                        # Stato del messaggio
                        if msg['status'] == MessageState.DELIVERED:
                            stato = tr("messages.delivered")
                            tempo = f"{msg.get('delivery_time', 0):.1f}"
                        elif msg['status'] == MessageState.PENDING:
                            stato = tr("messages.pending")
                            tempo = ""
                        elif msg['status'] == MessageState.TIMEOUT:
                            stato = tr("messages.timeout")
                            tempo = ""
                        else:
                            stato = tr("messages.sent")
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
                
            self.log(tr("logs.history_exported", path=path), "success")
            messagebox.showinfo(tr("dialogs.export_done_title"), tr("dialogs.export_done_body", path=path))
            
        except Exception as e:
            self.log(tr("logs.export_error", error=e), "error")
            import traceback
            self.log(traceback.format_exc(), "debug")
            messagebox.showerror(tr("common.error"), tr("dialogs.export_failed_body", error=str(e)))
    
    def filter_messages(self):
        """Filtra messaggi per stato e testo"""
        filter_state = self.filter_state.get()
        search_text = self.search_var.get().lower()
        
        for item in self.messages_tree.get_children():
            values = self.messages_tree.item(item, 'values')
            stato = values[3]
            msg_text = values[2].lower()
            
            state_match = True
            if filter_state != tr("messages.all"):
                if filter_state == tr("messages.delivered"):
                    if not stato.startswith(tr("messages.delivered")):
                        state_match = False
                elif filter_state == tr("messages.pending"):
                    if stato != tr("messages.pending"):
                        state_match = False
                elif filter_state == tr("messages.timeout"):
                    if stato != tr("messages.timeout"):
                        state_match = False
                elif filter_state == tr("messages.sent"):
                    if stato != tr("messages.sent"):
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
        msg = f"{tr('node_info.id')}: {node_id}\n"
        msg += f"{tr('node_info.name')}: {user.get('longName', tr('common.not_available'))}\n"
        msg += f"{tr('node_info.short')}: {user.get('shortName', tr('common.not_available'))}\n"
        msg += f"{tr('node_info.hw')}: {user.get('hwModel', tr('common.not_available'))}\n"
        msg += f"{tr('node_info.snr')}: {data.get('snr', tr('common.not_available'))}\n"
        msg += f"{tr('node_info.rssi')}: {data.get('rssi', tr('common.not_available'))}\n"
        msg += f"{tr('node_info.battery')}: {data.get('deviceMetrics', {}).get('batteryLevel', tr('common.not_available'))}%\n"
        msg += f"{tr('node_info.mqtt')}: {tr('common.yes_short') if data.get('viaMqtt') else tr('common.no')}\n"
        msg += f"{tr('node_info.favorite')}: {tr('common.yes_short') if node_id in self.favorite_nodes else tr('common.no')}"
        
        messagebox.showinfo(tr("dialogs.node_info_title", node_id=node_id), msg)
    
    def show_node_menu(self, event):
        sel = self.nodes_tree.selection()
        if not sel: return
        
        vals = self.nodes_tree.item(sel[0])['values']
        node_id = vals[0]
        is_mqtt = "MQTT" in vals[2] if len(vals) > 2 else False
        
        menu = tk.Menu(self.root, tearoff=0, bg=UI.PANEL, fg=UI.FG)
        
        if node_id in self.favorite_nodes:
            menu.add_command(label=tr("node_menu.remove_favorite"), command=lambda: self.toggle_fav(node_id))
        else:
            menu.add_command(label=tr("node_menu.add_favorite"), command=lambda: self.toggle_fav(node_id))
        
        menu.add_separator()
        menu.add_command(label=tr("node_menu.info"), command=lambda: self.show_node_info(node_id))
        menu.add_command(label=tr("node_menu.message"), command=lambda: self.set_dest(node_id))
        
        if is_mqtt:
            menu.add_separator()
            menu.add_command(label=tr("node_menu.delete_mqtt"), command=lambda: self.delete_node(node_id),
                           foreground=UI.ERR)
        else:
            menu.add_command(label=tr("node_menu.delete"), command=lambda: self.delete_node(node_id))
        
        menu.post(event.x_root, event.y_root)
    
    def toggle_fav(self, node_id):
        if node_id in self.favorite_nodes:
            self.favorite_nodes.remove(node_id)
            self.log(tr("logs.favorite_removed", node_id=node_id), "info")
        else:
            self.favorite_nodes.add(node_id)
            self.log(tr("logs.favorite_added", node_id=node_id), "info")
        self.refresh_nodes()
    
    def set_dest(self, node_id):
        self.vars['dest'].set(node_id)
        self.notebook.select(self.tab_direct)
    
    def delete_node(self, node_id):
        if node_id == self.device.local_node_id:
            messagebox.showwarning(tr("common.warning"), tr("dialogs.cannot_delete_local_node"))
            return
        
        if messagebox.askyesno(tr("common.confirm"), tr("dialogs.delete_node_confirm", node_id=node_id)):
            if self.device.remove_node(node_id):
                self.log(tr("logs.node_deleted", node_id=node_id), "success")
                self.refresh_nodes()
            else:
                self.log(tr("logs.node_delete_error", node_id=node_id), "error")
    
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
            messagebox.showinfo(tr("common.info"), tr("dialogs.no_nodes_available"))
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title(tr("dialogs.select_node_title"))
        dialog.geometry("400x300")
        dialog.configure(bg=UI.BG)
        
        listbox = tk.Listbox(dialog, bg=UI.PANEL, fg=UI.FG)
        listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        node_map = {}
        for nid, data in nodes.items():
            name = data.get('user', {}).get('longName', tr('common.not_available'))
            tipo = "MQTT" if data.get('viaMqtt') else tr("common.radio")
            display = f"{nid} - {name} [{tipo}]"
            listbox.insert(tk.END, display)
            node_map[display] = nid
        
        def select():
            sel = listbox.curselection()
            if sel:
                display = listbox.get(sel[0])
                self.vars['dest'].set(node_map[display])
                dialog.destroy()
        
        ttk.Button(dialog, text=tr("common.selected"), command=select).pack(pady=5)
    
    def manage_favorites(self):
        messagebox.showinfo(tr("common.info"), tr("dialogs.favorites_help"))
    
    def confirm_clean_nodes(self):
        if not self.device.connected:
            messagebox.showwarning(tr("common.warning"), tr("connection.not_connected"))
            return
        
        mqtt_count = sum(1 for d in self.device.get_nodes().values() if d.get('viaMqtt'))
        msg = tr("dialogs.clean_nodes_confirm_body", mqtt_count=mqtt_count, radio_count=len(self.device.get_nodes()) - mqtt_count - 1)
        
        if messagebox.askyesno(tr("common.confirm"), msg, icon='warning'):
            self._clean_nodes()
    
    def _clean_nodes(self):
        if not self.device.connected:
            self.log(tr("logs.clean_nodes_not_connected"), "warn")
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
                    self.log(tr("logs.node_deleted", node_id=node_id), "info")
                else:
                    self.log(tr("logs.node_delete_error", node_id=node_id), "error")
            except Exception as e:
                self.log(tr("logs.node_delete_exception", node_id=node_id, error=e), "error")

            self.root.update()

        self.root.config(cursor="")
        self.log(tr("logs.clean_completed", removed=removed, skipped=skipped), "success")
        self.refresh_nodes()
    
    def update_stats(self):
        if not self.device.connected:
            self.stats_display.delete(1.0, tk.END)
            self.stats_display.insert(tk.END, tr("connection.not_connected"))
            return
        
        nodes = self.device.get_nodes()
        mqtt = sum(1 for d in nodes.values() if d.get('viaMqtt'))
        
        msg_stats = self.device.get_message_stats() if hasattr(self.device, 'get_message_stats') else {}
        
        stats = "\n".join([
            tr("stats.mesh_title"),
            "=" * 40,
            "",
            tr("stats.nodes"),
            tr("stats.total_nodes", count=len(nodes)),
            tr("stats.radio_nodes", count=len(nodes)-mqtt),
            tr("stats.mqtt_nodes", count=mqtt),
            tr("stats.favorites", count=len(self.favorite_nodes)),
            "",
            tr("stats.messages"),
            tr("stats.total", count=msg_stats.get('total', 0)),
            tr("stats.delivered", count=msg_stats.get('delivered', 0)),
            tr("stats.pending", count=msg_stats.get('pending', 0)),
            tr("stats.timeout", count=msg_stats.get('timeout', 0)),
            tr("stats.success_rate", rate=msg_stats.get('success_rate', 0)),
            "",
            tr("stats.errors"),
            tr("stats.parse_errors", count=self.parse_errors),
            "",
            tr("stats.local_node", node_id=self.device.local_node_id)
        ])
        self.stats_display.delete(1.0, tk.END)
        self.stats_display.insert(tk.END, stats)
    
    def show_stats(self):
        self.update_stats()
        self.notebook.select(self.tab_stats)
    
    def apply_config(self):
        """Applica la configurazione al dispositivo (Update)"""
        if not self.device.connected:
            messagebox.showwarning(tr("common.warning"), tr("dialogs.not_connected_body"))
            return
        
        advanced_changes = any([
            self.vars['role'].get().strip(),
            self.vars['region'].get().strip(),
            self.vars['modem'].get().strip(),
            self.vars['hop_limit'].get().strip()
        ])
        
        if advanced_changes:
            proceed = messagebox.askyesno(
                tr("config.radio_confirm_title"),
                tr("config.radio_confirm_body"),
                icon='warning'
            )
            if not proceed:
                self.log(tr("config.changes_cancelled"), "info")
                return
        
        try:
            self.root.config(cursor="watch")
            self.root.update()
            
            self.log(tr("config.apply_running"), "info")
            
            if self.vars['channel_write_name'].get():
                name = self.vars['channel_name'].get().strip()
                if name and len(name.encode('utf-8')) > 11:
                    messagebox.showerror(tr("common.error"), tr("channel.name_too_long_body"))
                    self.root.config(cursor="")
                    return
            
            changes = self.device.apply_all_config(self.vars, self._validate_channel_name)
            
            if changes:
                self.log(tr("config.changes_applied", count=len(changes)), "success")
                for change in changes[:10]:
                    self.log(f"  - {change}", "info")
                
                messagebox.showinfo(tr("common.success"), tr("config.apply_success", count=len(changes)))
                
                self.root.after(2000, self.read_config)
            else:
                self.log(tr("config.no_changes"), "info")
                messagebox.showinfo(tr("common.info"), tr("config.no_changes_body"))
        
        except Exception as e:
            self.log(tr("config.apply_error", error=e), "error")
            import traceback
            self.log(traceback.format_exc(), "muted")
            messagebox.showerror(tr("common.error"), str(e))
        
        finally:
            self.root.config(cursor="")
    
    def confirm_reboot(self):
        if not self.device.connected:
            messagebox.showwarning(tr("common.warning"), tr("connection.not_connected"))
            return
        
        if messagebox.askyesno(tr("common.confirm"), tr("dialogs.reboot_confirm_body")):
            self.device.reboot()
            self.disconnect()
            self._show_reboot_countdown()
    
    def _show_reboot_countdown(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Reboot")
        dialog.geometry("300x150")
        dialog.configure(bg=UI.BG)
        
        ttk.Label(dialog, text=tr("logs.reboot_running"), font=('',12,'bold')).pack(pady=20)
        
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
            messagebox.showwarning(tr("common.warning"), tr("dialogs.not_connected_body"))
            return

        try:
            self.root.config(cursor="watch")
            self.root.update()

            self.log(tr("logs.reading_backup_config"), "info")
            config = self.device.get_full_config()

            path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[(tr("dialogs.json_files"), "*.json"), (tr("dialogs.all_files"), "*.*")],
                title=tr("dialogs.backup_save_title")
            )
            if not path:
                return

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            self.log(tr("logs.backup_saved", path=path), "success")
            messagebox.showinfo(tr("dialogs.backup_done_title"), tr("dialogs.backup_done_body", path=path))

        except Exception as e:
            self.log(tr("logs.backup_error", error=e), "error")
            import traceback
            self.log(traceback.format_exc(), "muted")
            messagebox.showerror(tr("dialogs.backup_error_title"), str(e))
        finally:
            self.root.config(cursor="")

    def import_snapshot(self):
        if not self.device.connected:
            messagebox.showwarning(tr("common.warning"), tr("dialogs.not_connected_body"))
            return

        path = filedialog.askopenfilename(
            filetypes=[(tr("dialogs.json_files"), "*.json"), (tr("dialogs.all_files"), "*.*")],
            title=tr("dialogs.restore_select_title")
        )
        if not path:
            return

        if not messagebox.askyesno(
            tr("dialogs.restore_confirm_title"),
            tr("dialogs.restore_confirm_body"),
            icon='warning'
        ):
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            self.root.config(cursor="watch")
            self.root.update()

            self.log(tr("logs.restore_running"), "info")
            self.device.set_full_config(config)

            self.log(tr("logs.restore_reread"), "info")
            self.root.after(2000, self.read_config)
            messagebox.showinfo(tr("dialogs.restore_done_title"), tr("dialogs.restore_done_body"))

        except Exception as e:
            self.log(tr("logs.restore_error", error=e), "error")
            import traceback
            self.log(traceback.format_exc(), "muted")
            messagebox.showerror(tr("dialogs.restore_error_title"), str(e))
        finally:
            self.root.config(cursor="")
    
    def save_settings(self):
        lang_code = self._language_code(self.vars["language"].get())

        if save_language(lang_code):
            self.vars["language"].set(self._language_label(lang_code))
            self.log(tr("logs.settings_saved"), "info")
            messagebox.showinfo(tr("dialogs.settings_saved_title"), tr("dialogs.settings_saved_body_memory"))
        else:
            messagebox.showerror(
                tr("common.error"),
                "Impossibile salvare settings.json nella cartella dell'applicazione."
            )
    
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
            return f"{abs_time} | {rel_time} {tr('time.ago')}" if rel_time else abs_time
        except:
            return ""

    def _populate_nodes(self, nodes):
        self.nodes_tree.delete(*self.nodes_tree.get_children())
        
        for node_id, data in nodes.items():
            if not isinstance(data, dict): continue
            
            user = data.get('user', {})
            name = user.get('longName', '') or user.get('shortName', '') or '-'
            is_mqtt = data.get('viaMqtt', False)
            tipo = "MQTT" if is_mqtt else tr("common.radio")
            fav = "*" if node_id in self.favorite_nodes else ""
            hops = data.get('hopsAway', '-')
            snr = data.get('snr', '-')
            rssi = data.get('rssi', '-')
            
            qual = tr("quality.good")
            try:
                rssi_val = float(rssi) if rssi != '-' else -100
                if rssi_val > self.vars['rssi_threshold'].get():
                    qual = tr("quality.excellent")
                elif rssi_val > self.vars['rssi_threshold'].get() - 20:
                    qual = tr("quality.good")
                else:
                    qual = tr("quality.weak")
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
            
            msg_type = tr("message_types.direct") if to_id == self.device.local_node_id else tr("message_types.channel")
            self.log(tr("logs.message_from", msg_type=msg_type, from_id=from_id, text=text), "info" if to_id == self.device.local_node_id else None)
            
        except Exception as e:
            self.parse_errors += 1
    
    def on_close(self):
        self.disconnect()
        self.root.destroy()
