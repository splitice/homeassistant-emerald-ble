"""Constants for the Emerald Energy Monitor integration."""

DOMAIN = "emerald_ble"

# BLE Service UUIDs
SERVICE_TIME_UUID = "00001910-0000-1000-8000-00805f9b34fb"
CHAR_TIME_READ_UUID = "00002b10-0000-1000-8000-00805f9b34fb"
CHAR_TIME_WRITE_UUID = "00002b11-0000-1000-8000-00805f9b34fb"

SERVICE_BATTERY_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
CHAR_BATTERY_READ_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

# BLE Command Response Headers (used in notification handlers)
RESPONSE_30S_POWER = 0x0001020a06
RESPONSE_UPDATED_POWER = 0x0001020204
RESPONSE_EVERY_30S_POWER = 0x000102050e

# Default configuration values
DEFAULT_PULSES_PER_KW = 1000
DEFAULT_PIN = 123123

# Assuming 30s data packets (standard for Emerald)
# pulse_multiplier = (2 * 60.0) / pulses_per_kw = 0.12 for 1000 pulses/kW
PULSE_MULTIPLIER_BASE = 2 * 60.0  # 120.0

# Config keys
CONF_MAC_ADDRESS = "mac_address"
CONF_PIN = "pin"
CONF_PULSES_PER_KW = "pulses_per_kw"
CONF_DEVICE_NAME = "device_name"

# Device name pattern for Emerald devices
DEVICE_NAME_PREFIX = "ElAdv "

