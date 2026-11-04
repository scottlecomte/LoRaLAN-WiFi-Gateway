# ulora-style LoRa API on the official MicroPython lora-sx126x driver (lib/lora).
# Radio: Wio-SX1262 on a Seeed XIAO ESP32-S3.
#
# Frame format and constants match the Lora-to-Ethernet-Bridge ulora: RadioHead
# header [to, from, id, flags] + payload, ACK = FLAGS_ACK 0x80, same id, body b'!',
# BROADCAST_ADDRESS 255. Radio settings match the bridge RFM95 defaults
# (915 MHz, Bw125 Cr4/5 SF7, preamble 8, CRC on, explicit header, sync 0x12).
#
#   - deferred ACKs: queue_ack() only appends (to, id, t_rx) to _pending_acks
#     (max 8, oldest dropped); process_pending_acks() sends them from the main
#     loop and returns the radio to RX.
#   - ACK/TX counters, no print() anywhere: ack_q ack_ok ack_to ack_err
#     ack_drop ack_late (> ack_late_ms = 800 after RX) ack_lat_max ack_lat_last
#     tx_to (any TX that did not finish within wait_packet_sent_timeout).
#   - bounded TX wait (wait_packet_sent_timeout = 1.0 s on top of time on air).
#   - send(..., header_from=x) so a relayed frame can keep the original sender.
#   - listen() + poll(): continuous RX, never blocks, NO address filter and NO
#     auto-ACK. main.py decides what to ACK.
#
# Driver install (once per board), or copy lib/lora from this folder:
#   import mip; mip.install("lora-sync"); mip.install("lora-sx126x")

from ucollections import namedtuple
import time
from machine import Pin, SPI
from lora import SX1262

# Constants (same values as the bridge ulora)
FLAGS_ACK = 0x80
BROADCAST_ADDRESS = 255
ACK_BODY = b'!'

Payload = namedtuple(
    "Payload",
    ['message', 'header_to', 'header_from', 'header_id', 'header_flags', 'rssi', 'snr'],
)

# ESP32-S3 GPIO numbers (same table as the moisture nodes).
#   "b2b"    = XIAO ESP32-S3 + Wio-SX1262 kit (module on the B2B connector)
#   "header" = Wio-SX1262 for XIAO stacked on D0-D5
PINS = {
    "b2b": dict(sck=7, mosi=9, miso=8, cs=41, reset=42, busy=40, dio1=39, rf_sw=38),
    "header": dict(sck=7, mosi=9, miso=8, cs=5, reset=3, busy=4, dio1=2, rf_sw=6),
}


class WioRfSwitch:
    def __init__(self, pin):
        self.rf_sw = Pin(pin, Pin.OUT, value=0)

    def tx(self, _hp):
        self.rf_sw(0)

    def rx(self):
        self.rf_sw(1)

    def idle(self):
        self.rf_sw(0)


class LoRa:
    def __init__(self, this_address, freq=915.0, tx_power=20, board="b2b"):
        self._this_address = this_address & 0xff
        self._last_header_id = 0
        self._tx_power = tx_power
        self._pending_acks = []
        self._pending_acks_max = 8
        # ACK / TX counters (same names as the bridge ulora). Read from the main loop.
        self.ack_q = 0        # ACKs queued
        self.ack_ok = 0       # ACK TX finished
        self.ack_to = 0       # ACK TX did not finish within wait_packet_sent_timeout
        self.ack_err = 0      # exception while sending an ACK
        self.ack_drop = 0     # ACK queue overflow (oldest dropped)
        self.ack_late = 0     # ACK finished > ack_late_ms after RX
        self.ack_late_ms = 800
        self.ack_lat_max = 0  # max RX -> ACK TX done, ms
        self.ack_lat_last = -1
        self.tx_to = 0        # any TX that did not finish in time
        self.wait_packet_sent_timeout = 1.0
        self.crc_errors = 0   # mirrored from the driver by poll()

        p = PINS[board]
        spi = SPI(1, baudrate=2_000_000, polarity=0, phase=0,
                  sck=Pin(p["sck"]), mosi=Pin(p["mosi"]), miso=Pin(p["miso"]))
        lora_cfg = {
            "freq_khz": int(freq * 1000),
            "sf": 7,
            "bw": "125",
            "coding_rate": 5,
            "preamble_len": 8,
            "output_power": tx_power,
            "implicit_header": False,
            "crc_en": True,
            "syncword": 0x12,
            "invert_iq_tx": False,
            "invert_iq_rx": False,
        }
        self.modem = SX1262(
            spi,
            Pin(p["cs"], Pin.OUT),
            busy=Pin(p["busy"], Pin.IN),
            dio1=Pin(p["dio1"], Pin.IN),
            reset=Pin(p["reset"], Pin.OUT),
            dio2_rf_sw=True,
            dio3_tcxo_millivolts=1800,
            ant_sw=WioRfSwitch(p["rf_sw"]),
            lora_cfg=lora_cfg,
        )
        self._listening = False

    @property
    def address(self):
        return self._this_address

    def next_id(self):
        """Next header id for frames this radio originates (status). Skips 0."""
        self._last_header_id = (self._last_header_id + 1) & 0xff
        if self._last_header_id == 0:
            self._last_header_id = 1
        return self._last_header_id

    # --- TX ------------------------------------------------------------------
    def send(self, data, header_to, header_id=0, header_flags=0, header_from=None):
        """One frame, bounded wait (time on air + wait_packet_sent_timeout).
        Returns True if TX finished. RX resumes afterwards when listen() is on."""
        if header_from is None:
            header_from = self._this_address
        if isinstance(data, str):
            data = data.encode()
        header = bytes((header_to & 0xff, header_from & 0xff, header_id & 0xff, header_flags & 0xff))
        return self._tx(header + bytes(data))

    def _tx(self, packet):
        m = self.modem
        m.prepare_send(packet)
        m.start_send()
        toa_ms = m.get_time_on_air_us(len(packet)) // 1000
        deadline = time.ticks_add(time.ticks_ms(), toa_ms + int(self.wait_packet_sent_timeout * 1000))
        time.sleep_ms(toa_ms)
        while True:
            r = m.poll_send()           # resumes continuous RX when the TX is done
            if r is not True:
                return True
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                self.tx_to += 1
                try:
                    m.standby()         # cancel the stuck TX
                except Exception:
                    pass
                if self._listening:
                    self.listen()
                return False
            time.sleep_ms(1)

    def send_ack(self, header_to, header_id, header_flags=0):
        header_to = int(header_to) & 0xff
        header_id = int(header_id) & 0xff
        # Extra flag bits (FLAGS_PING on a ping reply) ride with 0x80.
        return self.send(ACK_BODY, header_to, header_id, FLAGS_ACK | (header_flags & 0x7f))

    # --- Deferred ACKs (bridge ulora style) -----------------------------------
    def queue_ack(self, header_to, header_id, header_flags=0, t_rx=None):
        try:
            if len(self._pending_acks) >= self._pending_acks_max:
                self._pending_acks.pop(0)
                self.ack_drop += 1
            self._pending_acks.append((header_to, header_id,
                                       t_rx if t_rx is not None else time.ticks_ms(), header_flags))
            self.ack_q += 1
        except Exception:
            pass

    def process_pending_acks(self):
        """Send queued ACKs. Call from the main loop only. Counters, no print()."""
        while self._pending_acks:
            try:
                item = self._pending_acks.pop(0)
                header_to = item[0]
                header_id = item[1]
                t_rx = item[2]
                flags = item[3]
            except Exception:
                break
            try:
                ok = self.send_ack(header_to, header_id, flags)
                if ok:
                    self.ack_ok += 1
                else:
                    self.ack_to += 1
                lat = time.ticks_diff(time.ticks_ms(), t_rx)
                self.ack_lat_last = lat
                if lat > self.ack_lat_max:
                    self.ack_lat_max = lat
                if lat > self.ack_late_ms:
                    self.ack_late += 1
            except Exception:
                self.ack_err += 1
                try:
                    if self._listening:
                        self.listen()
                except Exception:
                    pass

    # --- RX (non-blocking) ---------------------------------------------------
    def listen(self):
        """Start continuous receive. Call once; send() keeps it running."""
        self._listening = True
        self.modem.start_recv(continuous=True)

    def poll(self):
        """One Payload if a valid frame arrived since the last call, else None.
        Never blocks. Does NOT filter on address and does NOT auto-ACK."""
        rx = self.modem.poll_recv()
        try:
            self.crc_errors = self.modem.crc_errors
        except AttributeError:
            pass
        if rx is True or rx is False or rx is None:
            if rx is False and self._listening:
                self.listen()   # receive stopped (should not happen in continuous mode)
            return None
        if len(rx) < 4:
            return None
        return Payload(bytes(rx[4:]), rx[0], rx[1], rx[2], rx[3], rx.rssi, rx.snr / 4)

    def close(self):
        try:
            self.modem.standby()
        except Exception:
            pass
