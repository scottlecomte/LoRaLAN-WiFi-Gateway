# secrets.example.py - copy to secrets.py ON THE BOARD and fill it in.
# Never commit secrets.py (it is in .gitignore).
# main.py reads these names; anything missing falls back to the default shown.

# Wi-Fi (2.4 GHz). The Node-RED server and MQTT broker must be reachable on this network.
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASS = "YOUR_WIFI_PASSWORD"

# MQTT broker. An IP address avoids a blocking DNS lookup on the board.
MQTT_HOST = "xxx.xxx.xxx.xxx"
MQTT_PORT = 1883
MQTT_USER = None                 # set both if your broker needs a login
MQTT_PASS = None

NTP_HOST = None                  # None = pool.ntp.org; a local NTP server works too

# RadioHead address of this gateway. Every gateway needs its own address, different
# from every sensor node. A node uses this gateway when its SERVER_ADDRESS matches.
GATEWAY_ADDRESS = x # Change this to whatever address you would like ot give your gateway (1-255)

# Topics become <TOPIC_PREFIX>/gateway<GATEWAY_ADDRESS>/rx, /status and /availability.
TOPIC_PREFIX = "loralan"
