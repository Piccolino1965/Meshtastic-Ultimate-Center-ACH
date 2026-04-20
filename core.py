# core.py - Gestione dispositivo Meshtastic 
# -----------------------------------------
# aiutocomputerhelp.it
# Giovanni Popolizio - anon@m00n
###################################

import time
import gc
import json
import base64
from pubsub import pub
from constants import ConnectionState, MessageState
import utils
#------------------------------------------------------------

try:
    import meshtastic
    import meshtastic.serial_interface
    import meshtastic.tcp_interface
    from meshtastic.protobuf import channel_pb2
    from meshtastic.protobuf import config_pb2
    from google.protobuf.json_format import MessageToDict, ParseDict
except ImportError:
    meshtastic = None
    channel_pb2 = None
    config_pb2 = None
    MessageToDict = None
    ParseDict = None

class MeshtasticDevice:
    def __init__(self, logger=None):
        self.interface = None
        self.connected = False
        self.local_node = None
        self.local_node_id = None
        self.state = ConnectionState.DISCONNECTED
        self.log = logger or (lambda msg, tag: None)
        self._nodes_cache = {}
        self._subscriptions = []
        
        # Gestione ACK e messaggi
        self._pending_acks = {}  # {local_id: {'dest': dest, 'timestamp': time, 'text': text, 'callback': callback, 'status': status}}
        self._ack_timeout = 30   # secondi da attendere per ACK
        self._message_history = []  # Storico messaggi (inviati e ricevuti)
        self._last_local_id = 0  # Contatore per ID locali
        self._message_callbacks = []  # Callback per notificare nuovi messaggi

    # ==================== METODI DI CONNESSIONE ====================

    def connect_serial(self, port):
        if self.state != ConnectionState.DISCONNECTED:
            return False
        self.state = ConnectionState.CONNECTING
        try:
            self.interface = meshtastic.serial_interface.SerialInterface(devPath=port)
            self._post_connect()
            # Subscribe unico per tutti i pacchetti
            self.subscribe("meshtastic.receive", self.on_packet_received)
            return True
        except Exception as e:
            self.state = ConnectionState.ERROR
            self.log(f"Errore connessione seriale: {e}", "error")
            return False

    def connect_tcp(self, host):
        if self.state != ConnectionState.DISCONNECTED:
            return False
        self.state = ConnectionState.CONNECTING
        try:
            self.interface = meshtastic.tcp_interface.TCPInterface(hostname=host)
            self._post_connect()
            self.subscribe("meshtastic.receive", self.on_packet_received)
            return True
        except Exception as e:
            self.state = ConnectionState.ERROR
            self.log(f"Errore connessione TCP: {e}", "error")
            return False

    def _post_connect(self):
        for _ in range(10):
            self.local_node = getattr(self.interface, "localNode", None)
            if self.local_node:
                break
            time.sleep(0.3)

        self.local_node_id = self._get_local_id()
        self.connected = True
        self.state = ConnectionState.CONNECTED
        self.log(f"Connesso, ID locale: {self.local_node_id}", "success")

    def disconnect(self):
        try:
            for topic, cb in self._subscriptions:
                try:
                    pub.unsubscribe(cb, topic)
                except:
                    pass
            if self.interface:
                self.interface.close()
        except Exception as e:
            self.log(f"Errore in disconnessione: {e}", "warn")
        finally:
            self.interface = None
            self.local_node = None
            self.local_node_id = None
            self.connected = False
            self.state = ConnectionState.DISCONNECTED
            self._pending_acks.clear()
            gc.collect()
            self.log("Disconnessione completata", "info")

    def subscribe(self, topic, callback):
        try:
            pub.subscribe(callback, topic)
            self._subscriptions.append((topic, callback))
        except Exception as e:
            self.log(f"Errore subscribe {topic}: {e}", "warn")

    def add_message_callback(self, callback):
        """Aggiunge un callback da chiamare quando arriva un nuovo messaggio"""
        self._message_callbacks.append(callback)

    # ==================== METODI DI LETTURA ====================

    def get_nodes(self):
        if not self.connected:
            return {}
        nodes = getattr(self.interface, "nodes", {})
        if isinstance(nodes, dict):
            self._nodes_cache = nodes
        return self._nodes_cache

    def wait_for_config(self, timeout=3.0):
        if not self.local_node:
            return False
        start = time.time()
        while time.time() - start < timeout:
            try:
                if getattr(self.local_node, "localConfig", None) is not None:
                    return True
            except:
                pass
            time.sleep(0.1)
        return False

    def read_local_identity(self):
        long_name = ""
        short_name = ""

        if not self.local_node:
            return long_name, short_name

        try:
            user = getattr(self.local_node, "user", None)
            if user:
                long_name = str(getattr(user, "longName", "") or "")
                short_name = str(getattr(user, "shortName", "") or "")
                if long_name or short_name:
                    return long_name, short_name
        except:
            pass

        try:
            nodes = self.get_nodes()
            if self.local_node_id and self.local_node_id in nodes:
                user = nodes[self.local_node_id].get("user", {})
                long_name = str(user.get("longName", "") or "")
                short_name = str(user.get("shortName", "") or "")
        except:
            pass

        return long_name, short_name

    def read_channels(self):
        if not self.local_node:
            return []
        return getattr(self.local_node, "channels", []) or []

    def find_primary_channel(self):
        channels = self.read_channels()
        if not channels:
            return None, None

        for ch in channels:
            try:
                role_name = self._get_channel_role_name(ch)
                if role_name == "PRIMARY":
                    return getattr(ch, "index", None), ch
            except:
                pass

        for ch in channels:
            try:
                role_name = self._get_channel_role_name(ch)
                if role_name != "DISABLED":
                    return getattr(ch, "index", 0), ch
            except:
                pass

        return None, None

    def _get_channel_role_name(self, ch):
        try:
            if channel_pb2:
                return channel_pb2.Channel.Role.Name(getattr(ch, "role", 0))
        except:
            pass
        return str(getattr(ch, "role", ""))

    def get_channel_settings(self, ch):
        return getattr(ch, "settings", None)

    def read_config(self):
        if not self.local_node:
            return None, None
        return (
            getattr(self.local_node, "localConfig", None),
            getattr(self.local_node, "moduleConfig", None),
        )

    def is_mqtt_node(self, node_data):
        return node_data.get("viaMqtt", False)

    def _get_local_id(self):
        if self.local_node and hasattr(self.local_node, "nodeNum"):
            return f"!{self.local_node.nodeNum:08x}"

        try:
            my_info = self.interface.getMyNodeInfo()
            if isinstance(my_info, dict):
                user = my_info.get("user", {})
                if user.get("id"):
                    return user.get("id")
                if user.get("num"):
                    return f"!{int(user.get('num')):08x}"
        except:
            pass

        return None

    
    # ==================== METODI DI SCRITTURA ====================

    def set_config_value(self, config_obj, attr, value):
        """Imposta un valore di configurazione se diverso"""
        if not config_obj:
            return False
        try:
            if hasattr(config_obj, attr):
                current = getattr(config_obj, attr, None)
                if current != value:
                    setattr(config_obj, attr, value)
                    return True
            else:
                self.log(f"Attributo {attr} non trovato in {type(config_obj).__name__}", "warn")
        except Exception as e:
            self.log(f"Errore impostazione {attr}: {e}", "warn")
        return False

    def set_enum_value(self, config_obj, attr, value_name):
        """Imposta un valore enum tramite nome"""
        if not config_obj or not value_name:
            return False

        try:
            value_name = value_name.strip().upper()
            desc = getattr(config_obj, "DESCRIPTOR", None)
            if desc:
                field = desc.fields_by_name.get(attr)
                if field and field.enum_type:
                    enum_val = field.enum_type.values_by_name.get(value_name)
                    if enum_val:
                        current = getattr(config_obj, attr, None)
                        if current != enum_val.number:
                            setattr(config_obj, attr, enum_val.number)
                            return True
        except Exception as e:
            self.log(f"Errore impostazione enum {attr}: {e}", "warn")
        return False

    def write_channel(self, index):
        if not self.local_node or not hasattr(self.local_node, "writeChannel"):
            return False
        try:
            self.local_node.writeChannel(index)
            return True
        except:
            return False

    def write_config(self, section):
        if not self.local_node or not hasattr(self.local_node, "writeConfig"):
            return False
        try:
            self.local_node.writeConfig(section)
            return True
        except:
            return False

    def begin_transaction(self):
        if not self.local_node or not hasattr(self.local_node, "beginSettingsTransaction"):
            return False
        try:
            self.local_node.beginSettingsTransaction()
            return True
        except:
            return False

    def commit_transaction(self):
        if not self.local_node or not hasattr(self.local_node, "commitSettingsTransaction"):
            return False
        try:
            self.local_node.commitSettingsTransaction()
            return True
        except:
            return False

    def set_owner(self, long_name=None, short_name=None):
        if not self.local_node:
            return False
        try:
            if hasattr(self.local_node, "setOwner"):
                self.local_node.setOwner(
                    long_name=long_name if long_name else None,
                    short_name=short_name if short_name else None,
                )
                return True
        except Exception as e:
            self.log(f"setOwner fallito: {e}", "warn")
            # Fallback
            try:
                user = getattr(self.local_node, "user", None)
                if user:
                    if long_name is not None:
                        setattr(user, "longName", long_name)
                    if short_name is not None:
                        setattr(user, "shortName", short_name)
                    return True
            except:
                pass
        return False


    # Rimuove un nodo dal NodeDB del dispositivo locale.
    def remove_node(self, node_id):
         
        if not self.connected or not self.interface:
            self.log("Non connesso, impossibile rimuovere il nodo", "warn")
            return False

        node_id = utils.normalize_id(node_id)
        if not node_id:
            self.log("ID nodo non valido", "warn")
            return False

        if node_id == self.local_node_id:
            self.log("Tentativo di rimozione del nodo locale bloccato", "warn")
            return False

        try:
            target = None

            if self.local_node and hasattr(self.local_node, "removeNode"):
                target = self.local_node
            elif hasattr(self.interface, "getNode") and self.local_node_id:
                try:
                    target = self.interface.getNode(self.local_node_id, False)
                except TypeError:
                    target = self.interface.getNode(self.local_node_id)

            if not target or not hasattr(target, "removeNode"):
                self.log("API removeNode non disponibile su questo dispositivo/interfaccia", "warn")
                return False

            target.removeNode(node_id)

            try:
                nodes = getattr(self.interface, "nodes", None)
                if isinstance(nodes, dict):
                    nodes.pop(node_id, None)
            except Exception:
                pass

            self._nodes_cache.pop(node_id, None)
            self.log(f"Richiesta rimozione nodo inviata: {node_id}", "info")
            return True

        except Exception as e:
            self.log(f"Errore remove_node {node_id}: {e}", "error")
            return False

    # ==================== METODI INVIO MESSAGGI CON ACK ====================

    #Invio semplice senza ACK 
    def send_text(self, text, dest=None):
        
        return self.send_text_with_ack(text, dest, want_ack=False)

    # Genera un ID locale univoco
    def _generate_local_id(self):
        
        self._last_local_id += 1
        return int(time.time() * 1000) & 0xFFFFFFFF

    def send_text_with_ack(self, text, dest=None, want_ack=True, callback=None, timeout=None):
        """
        Invia un messaggio con possibilità di richiedere conferma
        
        Args:
            text: Testo del messaggio
            dest: ID destinatario (None per broadcast)
            want_ack: Se True, richiede conferma
            callback: Funzione da chiamare quando arriva conferma (opzionale)
            timeout: Timeout personalizzato (opzionale)
            
        Returns:
            local_id: ID locale del messaggio se inviato, None altrimenti
        """
        if not self.interface:
            self.log("Impossibile inviare: non connesso", "error")
            return None
        
        try:
            # Genera un ID locale per il tracciamento
            local_id = self._generate_local_id()
            
            # Prepara i parametri
            if dest:
                # Invia a destinatario specifico
                if want_ack:
                    self.interface.sendText(text, destinationId=dest, wantAck=True)
                else:
                    self.interface.sendText(text, destinationId=dest)
            else:
                # Broadcast
                if want_ack:
                    self.interface.sendText(text, wantAck=True)
                else:
                    self.interface.sendText(text)
            
            # Se richiediamo ACK, registra il messaggio in attesa
            if want_ack:
                self._pending_acks[local_id] = {
                    'dest': dest,
                    'text': text,
                    'timestamp': time.time(),
                    'callback': callback,
                    'status': MessageState.PENDING,
                    'timeout': timeout if timeout is not None else self._ack_timeout,
                    'local_id': local_id,
                    'retries': 0
                }
                self.log(f"Messaggio inviato con ACK (ID locale: {local_id})", "info")
            else:
                # Messaggio senza ACK, registra come inviato
                self._message_history.append({
                    'id': local_id,
                    'dest': dest,
                    'text': text,
                    'sent': time.time(),
                    'delivered': None,
                    'direction': 'sent',
                    'status': MessageState.SENT
                })
                self.log(f"Messaggio inviato (ID locale: {local_id})", "info")
            
            return local_id
            
        except Exception as e:
            self.log(f"Invio messaggio fallito: {e}", "error")
            return None

    # ==================== GESTIONE PACCHETTI RICEVUTI ====================

    
    def on_packet_received(self, packet, interface):
        
        try:
            decoded = packet.get('decoded', {})
            # Se c'è requestId, è un ACK
            if decoded.get('requestId'):
                self._handle_ack_packet(packet)
            # Se c'è testo, è un messaggio
            if decoded.get('text'):
                self._handle_text_packet(packet)
        except Exception as e:
            self.log(f"Errore in on_packet_received: {e}", "error")

    def _handle_ack_packet(self, packet):
        
        try:
            from_id = utils.normalize_id(packet.get('fromId', packet.get('from')))
            decoded = packet.get('decoded', {})
            request_id = decoded.get('requestId')  # ID del messaggio originale (generato dalla libreria)
            self.log(f"ACK ricevuto da {from_id} per requestId: {request_id}", "debug")
            
            # Cerchiamo il messaggio pending per questo destinatario
            now = time.time()
            best_match = None
            best_diff = float('inf')
            
            for lid, pending in list(self._pending_acks.items()):
                if pending['dest'] == from_id:
                    # Calcola quanto tempo è passato dall'invio
                    diff = now - pending['timestamp']
                    if diff < pending['timeout'] + 5:  # entro il timeout più un margine
                        if diff < best_diff:
                            best_diff = diff
                            best_match = (lid, pending)
            
            if best_match:
                local_id, pending = best_match
                self._confirm_ack(local_id, pending)
            else:
                self.log(f"ACK da {from_id} non associato ad alcun pending", "debug")
                
        except Exception as e:
            self.log(f"Errore in _handle_ack_packet: {e}", "error")

    # Gestisce un messaggio di testo ricevuto e lo memorizza nello storico
    def _handle_text_packet(self, packet):
         
        try:
            from_id = utils.normalize_id(packet.get('fromId', packet.get('from')))
            to_id = utils.normalize_id(packet.get('toId', packet.get('to')))
            text = packet.get('decoded', {}).get('text', '')
            
            if not text:
                return
                
            self.log(f"Messaggio da {from_id}: {text}", "info")
            
            # Determina il tipo di messaggio
            if to_id == self.local_node_id:
                msg_type = "Diretto"
            else:
                msg_type = "Canale"
            
            # Aggiungi ai messaggi ricevuti
            self._message_history.append({
                'id': self._generate_local_id(),
                'from': from_id,
                'to': to_id,
                'type': msg_type,
                'text': text,
                'received': time.time(),
                'direction': 'received',
                'status': 'received'
            })
            
            # Notifica i callback che un nuovo messaggio è arrivato
            for callback in self._message_callbacks:
                try:
                    callback()
                except Exception as e:
                    self.log(f"Errore nel callback messaggio: {e}", "warn")
            
        except Exception as e:
            self.log(f"Errore in _handle_text_packet: {e}", "error")

    def _confirm_ack(self, local_id, pending):
        """Conferma la consegna di un messaggio"""
        try:
            delivery_time = time.time() - pending['timestamp']
            pending['status'] = MessageState.DELIVERED
            pending['delivery_time'] = delivery_time
            self.log(f"Conferma ricevuta per messaggio {local_id} in {delivery_time:.1f}s", "success")
            
            # Chiama il callback se presente
            if pending['callback']:
                try:
                    pending['callback'](True, delivery_time, pending)
                except Exception as e:
                    self.log(f"Errore nel callback ACK: {e}", "warn")
            
            # Sposta nello storico
            self._message_history.append({
                'id': local_id,
                'dest': pending['dest'],
                'text': pending['text'],
                'sent': pending['timestamp'],
                'delivered': time.time(),
                'delivery_time': delivery_time,
                'direction': 'sent',
                'status': MessageState.DELIVERED,
                'retries': pending.get('retries', 0)
            })
            
            # Rimuovi dai pending
            del self._pending_acks[local_id]
            
            # Notifica i callback che lo storico è cambiato
            for callback in self._message_callbacks:
                try:
                    callback()
                except Exception as e:
                    self.log(f"Errore nel callback storico: {e}", "warn")
            
        except Exception as e:
            self.log(f"Errore in _confirm_ack: {e}", "error")

    def check_ack_timeouts(self):
        """
        Verifica se qualche ACK è scaduto
        Da chiamare periodicamente (es. ogni 5 secondi)
        
        Returns:
            Numero di timeout rilevati
        """
        now = time.time()
        timed_out = []
        
        for local_id, pending in list(self._pending_acks.items()):
            timeout_value = pending.get('timeout', self._ack_timeout)
            if now - pending['timestamp'] > timeout_value:
                timed_out.append(local_id)
                pending['status'] = MessageState.TIMEOUT
                
                self.log(f"Timeout per messaggio {local_id}", "warn")
                
                # Chiama il callback con fallimento
                if pending['callback']:
                    try:
                        pending['callback'](False, None, pending)
                    except Exception as e:
                        self.log(f"Errore nel callback timeout: {e}", "warn")
                
                # Sposta nello storico
                self._message_history.append({
                    'id': local_id,
                    'dest': pending['dest'],
                    'text': pending['text'],
                    'sent': pending['timestamp'],
                    'delivered': None,
                    'direction': 'sent',
                    'status': MessageState.TIMEOUT,
                    'retries': pending.get('retries', 0)
                })
                
                # Notifica i callback che lo storico è cambiato
                for callback in self._message_callbacks:
                    try:
                        callback()
                    except Exception as e:
                        self.log(f"Errore nel callback storico: {e}", "warn")
        
        # Rimuovi quelli scaduti
        for local_id in timed_out:
            del self._pending_acks[local_id]
        
        return len(timed_out)

    def retry_message(self, local_id):
        """Ritenta un messaggio scaduto"""
        if local_id not in self._pending_acks:
            return False
        
        pending = self._pending_acks[local_id]
        pending['retries'] = pending.get('retries', 0) + 1
        pending['timestamp'] = time.time()  # Reset timestamp
        pending['status'] = MessageState.PENDING
        
        # Reinvia il messaggio
        try:
            if pending['dest']:
                self.interface.sendText(pending['text'], destinationId=pending['dest'], wantAck=True)
            else:
                self.interface.sendText(pending['text'], wantAck=True)
            
            self.log(f"Ritentato invio messaggio {local_id} (tentativo {pending['retries']})", "info")
            return True
        except Exception as e:
            self.log(f"Ritentativo fallito: {e}", "error")
            return False

    def get_message_history(self, limit=100):
        """
        Restituisce lo storico dei messaggi (inviati e ricevuti)
        
        Args:
            limit: Numero massimo di messaggi da restituire
            
        Returns:
            Lista degli ultimi messaggi
        """
        # Ordina per timestamp (sent o received)
        sorted_history = sorted(
            self._message_history, 
            key=lambda x: x.get('sent', x.get('received', 0)), 
            reverse=True
        )
        return sorted_history[:limit]

    def get_pending_acks(self):
        """
        Restituisce i messaggi in attesa di conferma
        """
        return self._pending_acks.copy()

    def get_message_stats(self):
        """
        Calcola statistiche sui messaggi
        
        Returns:
            Dizionario con statistiche
        """
        total = len(self._message_history)
        delivered = sum(1 for m in self._message_history if m.get('status') == MessageState.DELIVERED)
        timeout = sum(1 for m in self._message_history if m.get('status') == MessageState.TIMEOUT)
        pending = len(self._pending_acks)
        received = sum(1 for m in self._message_history if m.get('direction') == 'received')
        
        # Calcolo tempi medi di consegna
        delivery_times = [m.get('delivery_time', 0) for m in self._message_history 
                         if m.get('status') == MessageState.DELIVERED and m.get('delivery_time')]
        avg_delivery = sum(delivery_times) / len(delivery_times) if delivery_times else 0
        
        # Calcolo tasso di successo (solo sui messaggi inviati)
        sent_total = total - received
        success_rate = (delivered / sent_total * 100) if sent_total > 0 else 0
        
        return {
            'total': total,
            'delivered': delivered,
            'timeout': timeout,
            'pending': pending,
            'received': received,
            'avg_delivery_time': avg_delivery,
            'success_rate': success_rate
        }

    def clear_message_history(self):
        """Pulisce lo storico dei messaggi"""
        self._message_history = []
        self._pending_acks.clear()
        self.log("Storico messaggi cancellato", "info")

    # ==================== METODI DI SCRITTURA CONFIG (PER SINGOLE SEZIONI) ====================

    def write_position_config(self, position_cfg, vars_dict):
        changes = []

        # GPS Mode
        if vars_dict["gps_mode"].get().strip():
            if self.set_enum_value(position_cfg, "gps_mode", vars_dict["gps_mode"].get()):
                changes.append("gps_mode")

        # GPS Update Interval
        val = utils.to_int_or_none(vars_dict["gps_update"].get())
        if val is not None:
            if self.set_config_value(position_cfg, "gps_update_interval", val):
                changes.append("gps_update_interval")

        # Position Broadcast
        val = utils.to_int_or_none(vars_dict["pos_broadcast"].get())
        if val is not None:
            if self.set_config_value(position_cfg, "position_broadcast_secs", val):
                changes.append("position_broadcast_secs")

        # Smart Broadcast
        if self.set_config_value(
            position_cfg,
            "position_broadcast_smart_enabled",
            vars_dict["smart_broadcast"].get(),
        ):
            changes.append("position_broadcast_smart_enabled")

        # Fixed Position
        if self.set_config_value(
            position_cfg, "fixed_position", vars_dict["fixed_position"].get()
        ):
            changes.append("fixed_position")

        return changes

    def write_range_config(self, range_cfg, vars_dict):
        changes = []

        if range_cfg:
            if self.set_config_value(range_cfg, "enabled", vars_dict["range_enabled"].get()):
                changes.append("range_test.enabled")

            if self.set_config_value(range_cfg, "sender", vars_dict["range_sender"].get()):
                changes.append("range_test.sender")

            val = utils.to_int_or_none(vars_dict["range_interval"].get())
            if val is not None:
                if self.set_config_value(range_cfg, "sender_interval", val):
                    changes.append("range_test.sender_interval")

        return changes

    def write_mqtt_config(self, mqtt_cfg, vars_dict):
        changes = []

        if not mqtt_cfg:
            return changes

        # Boolean flags
        for var, attr in [
            (vars_dict["mqtt_enabled"], "enabled"),
            (vars_dict["mqtt_proxy"], "proxy_to_client_enabled"),
            (vars_dict["mqtt_tls"], "tls_enabled"),
            (vars_dict["mqtt_encryption"], "encryption_enabled"),
            (vars_dict["mqtt_json"], "json_enabled"),
        ]:
            if self.set_config_value(mqtt_cfg, attr, var.get()):
                changes.append(f"mqtt.{attr}")

        # String values
        for var, attr in [
            (vars_dict["mqtt_address"], "address"),
            (vars_dict["mqtt_username"], "username"),
            (vars_dict["mqtt_root"], "root"),
        ]:
            val = var.get().strip()
            if val and self.set_config_value(mqtt_cfg, attr, val):
                changes.append(f"mqtt.{attr}")

        # Password (only if not empty)
        pwd = vars_dict["mqtt_password"].get()
        if pwd:
            if self.set_config_value(mqtt_cfg, "password", pwd):
                changes.append("mqtt.password")

        return changes

    def write_display_config(self, display_cfg, vars_dict):
        changes = []

        if not display_cfg:
            return changes

        # Screen on seconds
        val = utils.to_int_or_none(vars_dict["display_screen"].get())
        if val is not None:
            if self.set_config_value(display_cfg, "screen_on_secs", val):
                changes.append("screen_on_secs")

        # GPS Format
        if vars_dict["display_gps"].get().strip():
            if self.set_enum_value(display_cfg, "gps_format", vars_dict["display_gps"].get()):
                changes.append("gps_format")

        # Compass
        if self.set_config_value(
            display_cfg, "compass_north_top", vars_dict["display_compass"].get()
        ):
            changes.append("compass_north_top")

        # 24h format
        use_12h = not vars_dict["display_24h"].get()
        if self.set_config_value(display_cfg, "use_12h_clock", use_12h):
            changes.append("use_12h_clock (24h mode)")

        return changes

    def write_device_config(self, device_cfg, vars_dict):
        changes = []

        if not device_cfg:
            return changes

        if vars_dict["role"].get().strip():
            if self.set_enum_value(device_cfg, "role", vars_dict["role"].get()):
                changes.append("device.role")

        return changes

    def write_lora_config(self, lora_cfg, vars_dict):
        changes = []

        if not lora_cfg:
            return changes

        # Region
        if vars_dict["region"].get().strip():
            if self.set_enum_value(lora_cfg, "region", vars_dict["region"].get()):
                changes.append("lora.region")

        # Modem Preset
        if vars_dict["modem"].get().strip():
            if self.set_enum_value(lora_cfg, "modem_preset", vars_dict["modem"].get()):
                changes.append("lora.modem_preset")

        # Hop Limit
        val = utils.to_int_or_none(vars_dict["hop_limit"].get())
        if val is not None:
            if self.set_config_value(lora_cfg, "hop_limit", val):
                changes.append("lora.hop_limit")

        # TX Enabled
        if self.set_config_value(lora_cfg, "tx_enabled", vars_dict["tx_enabled"].get()):
            changes.append("lora.tx_enabled")

        return changes

    def write_network_config(self, network_cfg, vars_dict):
        """
        Scrive la configurazione di rete (WiFi) sul dispositivo.
        """
        changes = []

        if not network_cfg:
            return changes

        # wifi_enabled (bool)
        if self.set_config_value(network_cfg, "wifi_enabled", vars_dict["wifi_enabled"].get()):
            changes.append("network.wifi_enabled")

        # wifi_ssid (stringa) - solo se non vuota
        ssid = vars_dict["wifi_ssid"].get().strip()
        if ssid:
            if self.set_config_value(network_cfg, "wifi_ssid", ssid):
                changes.append("network.wifi_ssid")

        # wifi_password (stringa) - solo se non vuota
        psk = vars_dict["wifi_psk"].get()
        if psk:
            if self.set_config_value(network_cfg, "wifi_psk", psk):
                changes.append("network.wifi_psk")

        return changes

    def write_primary_channel_safe(self, vars_dict, validate_callback=None):
        if not self.local_node:
            raise RuntimeError("localNode non disponibile")

        idx, ch = self.find_primary_channel()
        if ch is None:
            raise RuntimeError("Canale primario non trovato")

        settings = self.get_channel_settings(ch)
        if settings is None:
            raise RuntimeError("settings del canale primario non disponibili")

        changes = []

        # Scrittura nome (se consentito)
        if vars_dict["channel_write_name"].get():
            new_name = vars_dict["channel_name"].get().strip()
            old_name = str(getattr(settings, "name", "") or "")

            if new_name != old_name:
                if validate_callback and not validate_callback(new_name):
                    raise ValueError("Nome canale non valido (troppo lungo)")
                if self.set_config_value(settings, "name", new_name):
                    changes.append(f"channel.name: '{old_name}' -> '{new_name}'")

        # Scrittura uplink/downlink (se consentito)
        if vars_dict["channel_write_flags"].get():
            old_uplink = bool(getattr(settings, "uplink_enabled", False))
            new_uplink = bool(vars_dict["channel_uplink"].get())
            if old_uplink != new_uplink:
                if self.set_config_value(settings, "uplink_enabled", new_uplink):
                    changes.append(f"channel.uplink: {old_uplink} -> {new_uplink}")

            old_downlink = bool(getattr(settings, "downlink_enabled", False))
            new_downlink = bool(vars_dict["channel_downlink"].get())
            if old_downlink != new_downlink:
                if self.set_config_value(settings, "downlink_enabled", new_downlink):
                    changes.append(f"channel.downlink: {old_downlink} -> {new_downlink}")

        if changes:
            if not self.write_channel(idx):
                raise RuntimeError(f"writeChannel({idx}) fallito")

        return changes

    def apply_all_config(self, vars_dict, validate_callback=None):
        if not self.local_node:
            raise RuntimeError("localNode non disponibile")

        local_cfg, module_cfg = self.read_config()
        if not local_cfg:
            raise RuntimeError("localConfig non disponibile")

        all_changes = []
        sections_to_write = set()

        # 1. Identità (owner)
        long_name = vars_dict["long_name"].get().strip()
        short_name = vars_dict["short_name"].get().strip()
        if long_name or short_name:
            if self.set_owner(long_name or None, short_name or None):
                all_changes.append("owner updated")

        # 2. Posizione
        if hasattr(local_cfg, "position"):
            pos_changes = self.write_position_config(local_cfg.position, vars_dict)
            if pos_changes:
                all_changes.extend([f"position.{c}" for c in pos_changes])
                sections_to_write.add("position")

        # 3. Range Test
        if module_cfg and hasattr(module_cfg, "range_test"):
            range_changes = self.write_range_config(module_cfg.range_test, vars_dict)
            if range_changes:
                all_changes.extend(range_changes)
                sections_to_write.add("range_test")

        # 4. MQTT
        if module_cfg and hasattr(module_cfg, "mqtt"):
            mqtt_changes = self.write_mqtt_config(module_cfg.mqtt, vars_dict)
            if mqtt_changes:
                all_changes.extend(mqtt_changes)
                sections_to_write.add("mqtt")

        # 5. Display
        if hasattr(local_cfg, "display"):
            disp_changes = self.write_display_config(local_cfg.display, vars_dict)
            if disp_changes:
                all_changes.extend([f"display.{c}" for c in disp_changes])
                sections_to_write.add("display")

        # 6. Device (role)
        if hasattr(local_cfg, "device"):
            dev_changes = self.write_device_config(local_cfg.device, vars_dict)
            if dev_changes:
                all_changes.extend(dev_changes)
                sections_to_write.add("device")

        # 7. LoRa (radio)
        if hasattr(local_cfg, "lora"):
            lora_changes = self.write_lora_config(local_cfg.lora, vars_dict)
            if lora_changes:
                all_changes.extend(lora_changes)
                sections_to_write.add("lora")

        # 8. Network (WiFi)
        if hasattr(local_cfg, 'network'):
            net_changes = self.write_network_config(local_cfg.network, vars_dict)
            if net_changes:
                all_changes.extend([f"network.{c}" for c in net_changes])
                sections_to_write.add("network")

        # 9. Canale primario
        try:
            channel_changes = self.write_primary_channel_safe(vars_dict, validate_callback)
            if channel_changes:
                all_changes.extend(channel_changes)
        except Exception as e:
            self.log(f"Errore scrittura canale: {e}", "warn")

        # Scrivi le sezioni modificate
        if sections_to_write:
            tx_started = False
            if len(sections_to_write) > 1:
                tx_started = self.begin_transaction()
                if tx_started:
                    self.log("Transazione iniziata", "info")

            for section in sections_to_write:
                if self.write_config(section):
                    self.log(f"Sezione {section} scritta", "info")
                else:
                    self.log(f"Errore scrittura sezione {section}", "warn")

            if tx_started:
                self.commit_transaction()
                self.log("Transazione completata", "info")

        return all_changes

    # ==================== METODI DI BACKUP/RESTORE COMPLETI ====================

    def get_full_config(self):
        """
        Restituisce un dizionario con tutta la configurazione del dispositivo
        """
        if not self.local_node:
            raise RuntimeError("Dispositivo non connesso")

        self.wait_for_config(timeout=3.0)

        local_cfg, module_cfg = self.read_config()
        if not local_cfg:
            raise RuntimeError("Impossibile leggere localConfig")

        # Converti i protobuf in dizionari (con enum come stringhe)
        local_dict = MessageToDict(local_cfg, preserving_proto_field_name=True)
        module_dict = MessageToDict(module_cfg, preserving_proto_field_name=True) if module_cfg else {}

        # Ottieni i canali
        channels = self.read_channels()
        channels_list = []
        for ch in channels:
            ch_dict = MessageToDict(ch, preserving_proto_field_name=True)
            channels_list.append(ch_dict)

        # Ottieni l'owner
        long_name, short_name = self.read_local_identity()
        owner = {"long_name": long_name, "short_name": short_name}

        config_snapshot = {
            "version": "1.0",
            "owner": owner,
            "localConfig": local_dict,
            "moduleConfig": module_dict,
            "channels": channels_list,
        }

        return config_snapshot

    def set_full_config(self, config_dict):
        """
        Ripristina la configurazione da un dizionario (caricato da JSON).
        """
        if not self.local_node:
            raise RuntimeError("Dispositivo non connesso")

        if config_dict.get("version") != "1.0":
            self.log("Versione backup non riconosciuta, tenta comunque", "warn")

        # 1. Imposta owner
        owner = config_dict.get("owner", {})
        long_name = owner.get("long_name", "")
        short_name = owner.get("short_name", "")
        if long_name or short_name:
            self.set_owner(long_name or None, short_name or None)

        # 2. Ripristina localConfig
        local_dict = config_dict.get("localConfig")
        if local_dict:
            local_cfg, _ = self.read_config()
            if local_cfg:
                try:
                    ParseDict(local_dict, local_cfg, ignore_unknown_fields=True)
                    sections_to_write = []
                    for field in local_cfg.DESCRIPTOR.fields:
                        section_name = field.name
                        sections_to_write.append(section_name)
                    for section in set(sections_to_write):
                        try:
                            self.write_config(section)
                        except Exception as e:
                            self.log(f"Errore scrittura sezione {section}: {e}", "warn")
                except Exception as e:
                    self.log(f"Errore ripristino localConfig: {e}", "error")

        # 3. Ripristina moduleConfig
        module_dict = config_dict.get("moduleConfig")
        if module_dict:
            _, module_cfg = self.read_config()
            if module_cfg:
                try:
                    ParseDict(module_dict, module_cfg, ignore_unknown_fields=True)
                    module_sections = []
                    for field in module_cfg.DESCRIPTOR.fields:
                        module_sections.append(field.name)
                    for section in set(module_sections):
                        try:
                            self.write_config(section)
                        except Exception as e:
                            self.log(f"Errore scrittura modulo {section}: {e}", "warn")
                except Exception as e:
                    self.log(f"Errore ripristino moduleConfig: {e}", "error")

        # 4. Ripristina canali
        channels_list = config_dict.get("channels", [])
        if channels_list:
            current_channels = self.read_channels()
            current_by_index = {getattr(ch, "index", None): ch for ch in current_channels}

            for ch_dict in channels_list:
                idx = ch_dict.get("index")
                if idx is None:
                    continue
                if idx in current_by_index:
                    ch = current_by_index[idx]
                    try:
                        ParseDict(ch_dict, ch, ignore_unknown_fields=True)
                        self.write_channel(idx)
                    except Exception as e:
                        self.log(f"Errore ripristino canale {idx}: {e}", "error")
                else:
                    self.log(f"Canale indice {idx} non trovato, impossibile ripristinare", "warn")

        self.log("Ripristino configurazione completato", "success")