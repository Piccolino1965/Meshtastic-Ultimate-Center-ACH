
# Costanti UI e configurazione
# aiutocomputerhelp.it
# Giovanni Popolizio - anon@m00n
###################################

class UI:
    # Sfondo principale - molto scuro per massimo contrasto
    BG = "#1e1e1e"        
    FG = "#f0f0f0"        
    
    # Pannelli secondari - leggermente più chiari dello sfondo
    PANEL = "#2b2b2b"     
    
    # Colori funzionali - tutti verificati per contrasto
    OK = "#2f9141"        
    INFO = "#4dabf7"      
    WARN = "#ffd43b"      
    ERR = "#ff6b6b"       
    ALLERT = "#ff2600"    
    
    # Colori specifici per funzionalità
    MQTT = "#9370db"      
    CHANNEL = "#00f7ff"   
    WIFI = "#67B9D4"      
    DEBUG = "#808080"     #
    
    # Colori per stato messaggi (ACK)
    ACK_PENDING = "#b18d0d"   
    ACK_DELIVERED = "#2ecc71" 
    ACK_TIMEOUT = "#ff6b6b"   
    
    PORTS = ["COM1", "COM2", "COM3", "COM4", "COM5", "/dev/ttyUSB0", "/dev/ttyACM0"]
    ROLES = ["", "CLIENT", "CLIENT_MUTE", "ROUTER", "ROUTER_CLIENT", "REPEATER"]
    REGIONS = ["", "UNSET", "US", "EU_868", "EU_433", "CN", "JP"]
    MODEM_PRESETS = ["", "SHORT_FAST", "SHORT_SLOW", "MEDIUM_FAST", "LONG_FAST"]
    GPS_FORMATS = ["", "GpsFormat_DMS", "GpsFormat_DEC", "GpsFormat_UTM"]

class ConnectionState:
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    
class MessageState:
    PENDING = "pending"
    DELIVERED = "delivered"
    TIMEOUT = "timeout"
    FAILED = "failed"
    SENT = "sent"