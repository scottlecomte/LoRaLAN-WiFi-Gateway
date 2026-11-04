# main.py - LoRaLAN WiFi Gateway (LoRa -> Wi-Fi -> MQTT)
# Seeed XIAO ESP32-S3 + Wio-SX1262, MicroPython, USB-C powered.
#
#   node --(to=GATEWAY_ADDRESS, from=N, id=I)--> gateway     ACK to N sent at once
#   gateway --MQTT--> <TOPIC_PREFIX>/gateway<GATEWAY_ADDRESS>/rx
#       {"payload": {<same fields the Ethernet bridge sends>, "gw": GATEWAY_ADDRESS}, "rcv_ts": t}
#   This is the same JSON the Lora-to-Ethernet-Bridge hands Node-RED on its
#   WebSocket, so a Node-RED "mqtt in" node can feed the same parsing flow.
#
# Radio side works like the bridge: poll -> address filter -> deferred ACK sent
# from the main loop, 30 s (from, id) duplicate filter, ping ACK (0x10, counted,
# not published), no prints after the boot banner unless VERBOSE.
# The gateway does not relay LoRa packets; the only thing it transmits is ACKs.
#
# Network work never blocks the radio for long: Wi-Fi connect is non-blocking,
# MQTT connect has a short socket timeout and backoff, one publish per loop pass,
# and only when no radio payload is waiting.
#
# Site settings (Wi-Fi, broker, gateway address, topic prefix) live in secrets.py
# on the board. Copy secrets.example.py to secrets.py and fill it in.

import time, machine, ujson as json, gc
try:
    import ubinascii as binascii
except ImportError:
    import binascii
try:
    from urandom import getrandbits
except ImportError:
    from random import getrandbits
from sx1262_ulora import LoRa, FLAGS_ACK

try:
    import secrets as _S          # WIFI_SSID, WIFI_PASS, MQTT_*, GATEWAY_ADDRESS (never printed)
except ImportError:
    _S = None

def _cfg(name, default=None):
    return getattr(_S, name, default) if _S is not None else default

# config
BOARD = "b2b"                    # XIAO ESP32-S3 + Wio-SX1262 kit
RF_FREQ = 915.0
# RadioHead address of this gateway. Pick one no other node or gateway uses; a
# sensor node sends to this gateway by setting its SERVER_ADDRESS to the same number.
GATEWAY_ADDRESS = int(_cfg("GATEWAY_ADDRESS", 5))
RF_POW = 20                      # only ACKs go out; 20 dBm = SX1262 HP PA, driver max 22
FLAGS_HOP_SET = 0x08             # bridge counts 0x08 copies as rpt_src
FLAGS_PING = 0x10                # path probe: ACK it, never publish
FLAGS_RELAYED = 0x20             # repeater-relayed frame: not for us
FORWARD_BROADCAST = False        # True: also publish to=255 frames (no ACK); the bridge
                                 # forwards those too, so Node-RED dedupe drops one copy

GW_ID = GATEWAY_ADDRESS
TOPIC_PREFIX = _cfg("TOPIC_PREFIX", "homemade/loralan")
TOPIC_BASE = TOPIC_PREFIX + "/gateway%d" % GW_ID
TOPIC_RX = TOPIC_BASE + "/rx"            # node frames, not retained
TOPIC_STATUS = TOPIC_BASE + "/status"    # retained JSON, every STATUS_EVERY_MS
TOPIC_AVAIL = TOPIC_BASE + "/availability"   # retained "online"; LWT "offline"
MQTT_CLIENT_ID = "loralan-gw%d" % GW_ID
MQTT_KEEPALIVE_S = 60
MQTT_PING_MS = 30000
MQTT_DEAD_MS = 2 * MQTT_KEEPALIVE_S * 1000 + 10000   # no bytes from broker this long -> reconnect
MQTT_SOCK_TIMEOUT_S = 2          # connect / publish worst case blocks the radio this long
MQTT_BACKOFF_MS = (2000, 60000)  # first retry, max (doubles)
WIFI_BACKOFF_MS = (5000, 60000)
WIFI_CONNECT_WAIT_MS = 15000     # let an in-progress association finish before retrying
HOSTNAME = "loralan-gw%d" % GW_ID
NTP_EVERY_MS = 6 * 3600 * 1000   # ntptime blocks <= 1 s; retried hourly if it fails
NTP_RETRY_MS = 3600 * 1000

PUBQ_MAX = 64                    # frames held while MQTT is down; oldest dropped
STATUS_EVERY_MS = 60000
STATUS_FIRST_MS = 10000
STATUS_FILE = "/gateway_status.txt"    # overwritten; None = off
STATUS_FILE_EVERY_MS = 1800000
LAST_MAX = 12                    # per-src last RSSI/SNR kept for status

VERBOSE = False
LED_PIN = 21                     # XIAO user LED, active LOW; None = off
BOOT_GRACE_S = 8
WDT_ENABLE = False               # True = hardware watchdog (recommended once installed)
WDT_TIMEOUT_MS = 30000

_boot_ms = time.ticks_ms()
_rxq_drop = 0
_dup_total = 0
_dup_by_src = {}
_rpt_by_src = {}
_DUP_SRC_MAX = 12
_rx_by_src = {}                  # src -> first copies queued for MQTT
_ping_total = 0
_ign_relayed = 0
_bcast = 0
_last = {}                       # src -> (rssi, snr, ticks_ms)
_pub_ok = 0; _pub_err = 0; _pubq_drop = 0
_status_seq = 0
try:
    _reset_cause = machine.reset_cause()
except Exception:
    _reset_cause = -1

def _log(*a):
    if VERBOSE:
        try:
            print(*a)
        except Exception:
            pass

def _bump(d, k):
    # str keys: MicroPython json.dumps writes int dict keys unquoted (invalid JSON)
    k = str(k)
    if k in d:
        d[k] += 1
    elif len(d) < _DUP_SRC_MAX:
        d[k] = 1
    else:
        d["other"] = d.get("other", 0) + 1

def _dumps(o):
    try:
        return json.dumps(o, separators=(',', ':'))
    except TypeError:
        return json.dumps(o)

# LED
_led = None
_led_off_at = None
if LED_PIN is not None:
    _led = machine.Pin(LED_PIN, machine.Pin.OUT, value=1)

def _blink(ms=20):
    global _led_off_at
    if _led is not None:
        _led.value(0)
        _led_off_at = time.ticks_add(time.ticks_ms(), ms)

def _led_service():
    global _led_off_at
    if _led_off_at is not None and time.ticks_diff(time.ticks_ms(), _led_off_at) >= 0:
        _led.value(1)
        _led_off_at = None

# RX payload queue (frames for us, ACK already queued)
_payload_queue = []
_QUEUE_MAX = 32

# Dedupe, same as the bridge: (header_from, header_id) for 30 s. ACKs not suppressed.
_seen_keys = []
_SEEN_MAX = 32
_SEEN_MS = 30000

def _drop_dup(payload):
    try:
        src = int(payload.header_from) & 0xff
        pid = int(payload.header_id) & 0xff
    except Exception:
        return False
    now = time.ticks_ms()
    fresh = []
    dup = False
    for item in _seen_keys:
        if time.ticks_diff(now, item[2]) > _SEEN_MS:
            continue
        fresh.append(item)
        if item[0] == src and item[1] == pid:
            dup = True
    if not dup:
        fresh.append((src, pid, now))
        if len(fresh) > _SEEN_MAX:
            fresh = fresh[-_SEEN_MAX:]
    _seen_keys[:] = fresh
    return dup

def _enqueue_payload(payload):
    global _rxq_drop
    try:
        if len(_payload_queue) >= _QUEUE_MAX:
            _payload_queue.pop(0)
            _rxq_drop += 1
        _payload_queue.append(payload)
    except Exception:
        pass

# Publish queue: encoded frame bytes, bounded, drop oldest.
_pubq = []

def _pubq_add(b):
    global _pubq_drop
    if len(_pubq) >= PUBQ_MAX:
        _pubq.pop(0)
        _pubq_drop += 1
    _pubq.append(b)

def _on_rx(lora, p):
    global _ign_relayed, _bcast
    flags = p.header_flags
    if flags & FLAGS_ACK:
        return                     # nobody ACKs us now (no relay); ignore
    if p.header_to != GATEWAY_ADDRESS:
        if FORWARD_BROADCAST and p.header_to == 255 and p.header_from != GATEWAY_ADDRESS:
            _bcast += 1
            _enqueue_payload(p)    # no ACK for broadcasts (bridge ulora rule)
        return
    if p.header_from == GATEWAY_ADDRESS:
        return
    if flags & FLAGS_RELAYED:
        _ign_relayed += 1
        return
    lora.queue_ack(p.header_from, p.header_id, FLAGS_PING if flags & FLAGS_PING else 0)
    _enqueue_payload(p)

def _frame_obj(p):
    # Same keys/types as the Ethernet bridge, plus gw. ts: epoch s once NTP set.
    try:
        msg_str = p.message.decode('utf-8')
    except Exception:
        msg_str = binascii.b2a_base64(p.message).decode().strip()
    return {
        "message": msg_str,
        "header_to": int(p.header_to),
        "header_from": int(p.header_from),
        "header_id": int(p.header_id),
        "header_flags": int(p.header_flags),
        "rssi": float(p.rssi),
        "snr": float(p.snr),
        "ts": time.time(),
        "gw": GW_ID,
    }

def _handle_payload(p):
    global _dup_total, _ping_total
    flags = int(p.header_flags)
    src = int(p.header_from) & 0xff
    if flags & FLAGS_PING:
        _ping_total += 1
        return
    if _drop_dup(p):
        _dup_total += 1
        _bump(_rpt_by_src if flags & FLAGS_HOP_SET else _dup_by_src, src)
        return
    _bump(_rx_by_src, src)
    k = str(src)
    if k in _last or len(_last) < LAST_MAX:
        _last[k] = (p.rssi, p.snr, time.ticks_ms())
    try:
        obj = _frame_obj(p)
    except Exception:
        obj = {"error": "serialize_failed", "raw": str(getattr(p, "message", b"")), "gw": GW_ID}
    # Bridge envelope: {"payload": <frame>, "rcv_ts": t}
    _pubq_add(_dumps({"payload": obj, "rcv_ts": time.time()}).encode('utf-8'))

# ---------------- network ----------------
def _mqtt_mod():
    try:
        from umqtt.simple import MQTTClient
        return MQTTClient
    except ImportError:
        return None

class Net:
    def __init__(self):
        import network
        self.network = network
        self.wlan = network.WLAN(network.STA_IF)
        self.ssid = _cfg("WIFI_SSID")
        self.pw = _cfg("WIFI_PASS")
        self.host = _cfg("MQTT_HOST")
        self.port = int(_cfg("MQTT_PORT", 1883))
        self.user = _cfg("MQTT_USER") or None
        self.mpw = _cfg("MQTT_PASS") or None
        self.ntp_host = _cfg("NTP_HOST")
        self.Client = _mqtt_mod()
        self.wifi_up = False
        self.wifi_try = 0            # connect() calls
        self.wifi_drops = 0          # lost after being up
        self.wifi_next = time.ticks_ms()
        self.wifi_backoff = WIFI_BACKOFF_MS[0]
        self.wifi_t0 = None
        self.mq = None
        self.mq_try = 0; self.mq_ok = 0; self.mq_drops = 0
        self.mq_next = time.ticks_ms()
        self.mq_backoff = MQTT_BACKOFF_MS[0]
        self.mq_last_rx = 0; self.mq_last_ping = 0
        self.ntp_ok = False
        self.ntp_next = time.ticks_ms()
        self.err = None              # last error class name (no secrets)
        self.status_pending = None   # newest status that could not be published
        try:
            network.hostname(HOSTNAME)
        except Exception:
            pass
        self.wlan.active(True)
        self._pm_off()

    def _pm_off(self):
        # Wi-Fi power save off: keeps the link and the MQTT socket steady. PM_NONE = 0.
        try:
            self.wlan.config(pm=getattr(self.wlan, "PM_NONE", 0))
        except Exception:
            pass

    def rssi(self):
        try:
            return self.wlan.status('rssi') if self.wifi_up else None
        except Exception:
            return None

    def ip(self):
        try:
            return self.wlan.ifconfig()[0] if self.wifi_up else None
        except Exception:
            return None

    def _drop_mqtt(self, why):
        if self.mq is not None:
            try:
                self.mq.sock.close()
            except Exception:
                pass
            self.mq = None
            self.mq_drops += 1
            self.err = why
            self.mq_next = time.ticks_add(time.ticks_ms(), self.mq_backoff)
            self.mq_backoff = min(self.mq_backoff * 2, MQTT_BACKOFF_MS[1])

    def _wifi(self, now):
        if self.wlan.isconnected():
            if not self.wifi_up:
                self.wifi_up = True
                self.wifi_backoff = WIFI_BACKOFF_MS[0]
                self.wifi_t0 = None
                self._pm_off()
                self.mq_next = now
                _log("WIFI up", self.ip())
            return True
        if self.wifi_up:
            self.wifi_up = False
            self.wifi_drops += 1
            self.wifi_next = now
            self._drop_mqtt("wifi")
            _log("WIFI lost")
        if not self.ssid:
            return False
        if self.wifi_t0 is not None and time.ticks_diff(now, self.wifi_t0) < WIFI_CONNECT_WAIT_MS:
            return False             # association in progress
        if time.ticks_diff(now, self.wifi_next) < 0:
            return False
        try:
            try:
                self.wlan.disconnect()
            except Exception:
                pass
            self.wlan.connect(self.ssid, self.pw)   # returns at once
            self.wifi_try += 1
        except Exception as e:
            self.err = "wifi:" + type(e).__name__
        self.wifi_t0 = now
        self.wifi_next = time.ticks_add(now, self.wifi_backoff)
        self.wifi_backoff = min(self.wifi_backoff * 2, WIFI_BACKOFF_MS[1])
        return False

    def _ntp(self, now):
        if time.ticks_diff(now, self.ntp_next) < 0:
            return
        try:
            import ntptime
            if self.ntp_host:
                ntptime.host = self.ntp_host
            ntptime.settime()
            self.ntp_ok = True
            self.ntp_next = time.ticks_add(now, NTP_EVERY_MS)
        except Exception:
            self.ntp_next = time.ticks_add(now, NTP_RETRY_MS)

    def _mqtt_connect(self, now):
        if self.Client is None or time.ticks_diff(now, self.mq_next) < 0:
            return False
        if not self.host:
            self.err = "no MQTT_HOST in secrets.py"
            return False
        self.mq_try += 1
        c = None
        try:
            c = self.Client(MQTT_CLIENT_ID, self.host, port=self.port, user=self.user,
                            password=self.mpw, keepalive=MQTT_KEEPALIVE_S)
            c.set_last_will(TOPIC_AVAIL, b"offline", retain=True)
            try:
                c.connect(timeout=MQTT_SOCK_TIMEOUT_S)
            except TypeError:        # older umqtt.simple without timeout kwarg
                c.connect()
            c.sock.settimeout(MQTT_SOCK_TIMEOUT_S)
            c.publish(TOPIC_AVAIL, b"online", retain=True)
        except Exception as e:
            try:
                if c is not None and c.sock:
                    c.sock.close()
            except Exception:
                pass
            # MQTTException(5) = not authorised; never log creds
            self.err = "mqtt:" + type(e).__name__ + (":" + str(e.args[0]) if getattr(e, "args", None) else "")
            self.mq_next = time.ticks_add(now, self.mq_backoff)
            self.mq_backoff = min(self.mq_backoff * 2, MQTT_BACKOFF_MS[1])
            _log("MQTT connect failed", self.err)
            return False
        self.mq = c
        self.mq_ok += 1
        self.mq_backoff = MQTT_BACKOFF_MS[0]
        self.mq_last_rx = now
        self.mq_last_ping = now
        _log("MQTT up")
        return True

    def _drain(self, now):
        # Only CONNACK/PINGRESP ever arrive (no subscriptions). Read what is there.
        s = self.mq.sock
        try:
            s.setblocking(False)
            while True:
                b = s.read(64)
                if not b:
                    break
                self.mq_last_rx = now
        except OSError:
            pass
        finally:
            try:
                s.settimeout(MQTT_SOCK_TIMEOUT_S)
            except Exception:
                pass

    def publish(self, topic, b, retain=False):
        global _pub_ok, _pub_err
        if self.mq is None:
            return False
        try:
            self.mq.publish(topic, b, retain=retain)
            _pub_ok += 1
            return True
        except Exception as e:
            _pub_err += 1
            self._drop_mqtt("pub:" + type(e).__name__)
            return False

    def service(self, now):
        """One step of WiFi / MQTT upkeep plus at most one queued publish."""
        if not self._wifi(now):
            return
        if time.ticks_diff(now, self.ntp_next) >= 0:
            self._ntp(now)           # once at WiFi up, then every 6 h (1 h after a miss)
            return
        if self.mq is None:
            if self._mqtt_connect(now) and self.status_pending is not None:
                if self.publish(TOPIC_STATUS, self.status_pending, retain=True):
                    self.status_pending = None
            return
        self._drain(now)
        if time.ticks_diff(now, self.mq_last_rx) > MQTT_DEAD_MS:
            self._drop_mqtt("dead")
            return
        if time.ticks_diff(now, self.mq_last_ping) >= MQTT_PING_MS:
            try:
                self.mq.ping()
                self.mq_last_ping = now
            except Exception as e:
                self._drop_mqtt("ping:" + type(e).__name__)
            return
        if _pubq:
            if self.publish(TOPIC_RX, _pubq[0]):
                _pubq.pop(0)

def _status_obj(lora, net):
    now = time.ticks_ms()
    last = {}
    for k, v in _last.items():
        last[k] = [v[0], v[1], time.ticks_diff(now, v[2]) // 1000]
    s = {
        "gw": GW_ID, "seq": _status_seq,
        "up_s": time.ticks_diff(now, _boot_ms) // 1000,
        "rst": _reset_cause,
        "rx": _rx_by_src, "dup": _dup_total, "dup_src": _dup_by_src, "rpt_src": _rpt_by_src,
        "ping": _ping_total, "ign": _ign_relayed, "bcast": _bcast, "rxq_drop": _rxq_drop,
        "last": last,
        "pub": _pub_ok, "pub_err": _pub_err, "q": len(_pubq), "qdrop": _pubq_drop,
        "aq": lora.ack_q, "aok": lora.ack_ok, "ato": lora.ack_to, "aerr": lora.ack_err,
        "adrop": lora.ack_drop, "alate": lora.ack_late, "alat_max": lora.ack_lat_max,
        "alat": lora.ack_lat_last, "txto": lora.tx_to, "crc": lora.crc_errors,
        "wifi_rssi": net.rssi() if net else None,
        "wifi_try": net.wifi_try if net else 0, "wifi_drops": net.wifi_drops if net else 0,
        "mqtt_try": net.mq_try if net else 0, "mqtt_conn": net.mq_ok if net else 0,
        "mqtt_drops": net.mq_drops if net else 0,
        "ntp": net.ntp_ok if net else False, "err": net.err if net else "no_net",
        "ip": net.ip() if net else None,
        "pow": RF_POW, "mf": gc.mem_free(),
    }
    return s

def _send_status(lora, net, to_file):
    global _status_seq
    try:
        _status_seq += 1
        b = _dumps(_status_obj(lora, net)).encode('utf-8')
        if net is not None:
            # not queued: if MQTT is down, the newest one goes out right after reconnect
            net.status_pending = None if net.publish(TOPIC_STATUS, b, retain=True) else b
        if to_file and STATUS_FILE:
            try:
                with open(STATUS_FILE, "wb") as f:
                    f.write(b)
            except Exception:
                pass
    except Exception:
        pass

def run():
    lora = LoRa(GATEWAY_ADDRESS, freq=RF_FREQ, tx_power=RF_POW, board=BOARD)
    lora._last_header_id = getrandbits(8)
    lora.listen()
    try:
        net = Net()
    except Exception as e:
        net = None                   # radio side keeps working without WiFi
        _log("net init failed", e)
    try:
        print("LoRaLAN WiFi gateway addr {} {} MHz pow={} board={} mqtt={} secrets={}".format(
            GATEWAY_ADDRESS, RF_FREQ, RF_POW, BOARD,
            "ok" if _mqtt_mod() else "MISSING", "ok" if _S is not None else "MISSING"))
    except Exception:
        pass
    wdt = machine.WDT(timeout=WDT_TIMEOUT_MS) if WDT_ENABLE else None
    next_status = time.ticks_add(time.ticks_ms(), STATUS_FIRST_MS)
    next_file = time.ticks_add(time.ticks_ms(), STATUS_FIRST_MS)
    try:
        while True:
            try:
                lora.process_pending_acks()
            except Exception as e:
                _log("ACK drain err", e)
            p = None
            try:
                p = lora.poll()
            except Exception as e:
                _log("poll err", e)
            if p is not None:
                _on_rx(lora, p)
                try:
                    lora.process_pending_acks()   # node ACK before anything else
                except Exception as e:
                    _log("ACK drain err", e)
                if p.header_flags & FLAGS_ACK == 0 and p.header_to == GATEWAY_ADDRESS:
                    _blink()
            if _payload_queue:
                try:
                    _handle_payload(_payload_queue.pop(0))
                except Exception as e:
                    _log("payload err", e)
            elif p is None and net is not None:
                # network only when the radio had nothing this pass
                try:
                    net.service(time.ticks_ms())
                except Exception as e:
                    _log("net err", e)
            now = time.ticks_ms()
            if time.ticks_diff(now, next_status) >= 0:
                to_file = time.ticks_diff(now, next_file) >= 0
                if to_file:
                    next_file = time.ticks_add(now, STATUS_FILE_EVERY_MS)
                next_status = time.ticks_add(now, STATUS_EVERY_MS)
                _send_status(lora, net, to_file)
            _led_service()
            if wdt is not None:
                wdt.feed()
            if p is None and not _payload_queue:
                time.sleep_ms(1)
    finally:
        try:
            lora.close()
        except Exception:
            pass

if __name__ == "__main__":
    try:
        if BOOT_GRACE_S:
            print("LoRaLAN gateway: starting in {} s (Ctrl-C for REPL)".format(BOOT_GRACE_S))
            time.sleep(BOOT_GRACE_S)
        run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        try:
            import sys
            sys.print_exception(e)
        except Exception:
            pass
        time.sleep(10)
        machine.reset()
