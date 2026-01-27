"""BLE communication for Emerald Energy Monitor."""
import logging
from datetime import datetime
from typing import Callable

from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from .const import (
    CHAR_BATTERY_READ_UUID,
    CHAR_TIME_READ_UUID,
    CHAR_TIME_WRITE_UUID,
    PULSE_MULTIPLIER_BASE,
    RESPONSE_30S_POWER,
    RESPONSE_EVERY_30S_POWER,
    RESPONSE_UPDATED_POWER,
)

_LOGGER = logging.getLogger(__name__)

# Protocol constants
COMMAND_HEADER_LENGTH = 5
DATE_FIELD_START = 5
TOTAL_HEADER_WITH_DATE_LENGTH = 9
POWER_NOTIFICATION_LENGTH = 11
CMD_AUTO_UPLOAD = bytearray([0x00, 0x01, 0x02, 0x0b, 0x01, 0x01])


def get_command_from_notify(data: bytearray) -> int:
    """Extract command header from BLE notification data."""
    if len(data) < COMMAND_HEADER_LENGTH:
        return 0
    
    command_header = 0
    for i in range(COMMAND_HEADER_LENGTH):
        command_header += data[i] << (8 * (4 - i))
    return command_header


def get_date_from_notify(data: bytearray) -> int:
    """Extract date binary from BLE notification data."""
    if len(data) < TOTAL_HEADER_WITH_DATE_LENGTH:
        return 0
    
    command_date_bin = 0
    for i in range(DATE_FIELD_START, TOTAL_HEADER_WITH_DATE_LENGTH):
        command_date_bin += data[i] << (8 * (8 - i))
    return command_date_bin


def decode_emerald_date(command_date_bin: int) -> datetime | None:
    """Decode Emerald date format to datetime.
    
    Format: (6)year + (4)month + (5)days + (5)hours + (6)minutes + (6)seconds
    """
    try:
        year = 2000 + (command_date_bin >> 26)
        month = (command_date_bin >> 22) & 0b1111
        days = (command_date_bin >> 17) & 0b11111
        hours = (command_date_bin >> 12) & 0b11111
        minutes = (command_date_bin >> 6) & 0b111111
        seconds = command_date_bin & 0b111111
        
        return datetime(year, month, days, hours, minutes, seconds)
    except (ValueError, OverflowError) as err:
        _LOGGER.error("Failed to decode Emerald date: %s", err)
        return None


class EmeraldBLEDevice:
    """Representation of an Emerald Energy Monitor BLE device."""

    def __init__(
        self,
        ble_device: BLEDevice,
        pin: int,
        pulses_per_kw: int,
    ) -> None:
        """Initialize the Emerald BLE device."""
        self._ble_device = ble_device
        self._pin = pin
        self._pulses_per_kw = pulses_per_kw
        self._pulse_multiplier = PULSE_MULTIPLIER_BASE / pulses_per_kw
        
        self._client: BleakClient | None = None
        self._connected = False
        self._authenticated = False
        
        self._power_kw: float | None = None
        self._battery_level: int | None = None
        self._last_update: datetime | None = None
        
        self._callbacks: list[Callable[[], None]] = []

    @property
    def address(self) -> str:
        """Return the MAC address of the device."""
        return self._ble_device.address

    @property
    def is_connected(self) -> bool:
        """Return True if connected to the device."""
        return self._connected

    @property
    def power_kw(self) -> float | None:
        """Return the current power consumption in kW."""
        return self._power_kw

    @property
    def battery_level(self) -> int | None:
        """Return the battery level percentage."""
        return self._battery_level

    @property
    def last_update(self) -> datetime | None:
        """Return the timestamp of the last data update."""
        return self._last_update

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called when data is updated."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove a previously registered callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def connect(self) -> bool:
        """Connect to the Emerald BLE device."""
        try:
            _LOGGER.debug("Connecting to Emerald device at %s", self.address)
            self._client = await establish_connection(
                BleakClient, self._ble_device, self._ble_device.address
            )
            self._connected = True
            _LOGGER.info("Connected to Emerald device at %s", self.address)
            
            # Subscribe to characteristics
            await self._subscribe_to_notifications()
            
            # Enable auto upload
            await self._enable_auto_upload()
            
            return True
        except BleakError as err:
            _LOGGER.error("Failed to connect to device: %s", err)
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from the BLE device."""
        if self._client and self._connected:
            try:
                await self._client.disconnect()
            except BleakError as err:
                _LOGGER.error("Error disconnecting: %s", err)
            finally:
                self._connected = False
                self._authenticated = False

    async def _subscribe_to_notifications(self) -> None:
        """Subscribe to BLE notifications."""
        if not self._client or not self._connected:
            return

        try:
            # Subscribe to time/power characteristic
            await self._client.start_notify(
                CHAR_TIME_READ_UUID, self._handle_power_notification
            )
            
            # Subscribe to battery characteristic
            await self._client.start_notify(
                CHAR_BATTERY_READ_UUID, self._handle_battery_notification
            )
            
            _LOGGER.debug("Subscribed to notifications")
        except BleakError as err:
            _LOGGER.error("Failed to subscribe to notifications: %s", err)

    async def _enable_auto_upload(self) -> None:
        """Enable auto upload mode on the device."""
        if not self._client or not self._connected:
            return

        try:
            # Send auto upload enable command
            await self._client.write_gatt_char(
                CHAR_TIME_WRITE_UUID, CMD_AUTO_UPLOAD, response=False
            )
            _LOGGER.debug("Enabled auto upload")
        except BleakError as err:
            _LOGGER.error("Failed to enable auto upload: %s", err)

    def _handle_power_notification(self, sender: int, data: bytearray) -> None:
        """Handle power consumption notifications."""
        _LOGGER.debug("Power notification: %s", data.hex())
        
        if len(data) < COMMAND_HEADER_LENGTH:
            _LOGGER.warning("Received short notification data")
            return

        command_header = get_command_from_notify(data)
        
        if command_header == RESPONSE_30S_POWER:
            if len(data) == POWER_NOTIFICATION_LENGTH:
                # Extract date
                command_date_bin = get_date_from_notify(data)
                timestamp = decode_emerald_date(command_date_bin)
                
                # Extract power
                msb = data[-2] << 8
                total_pulses = msb + data[-1]
                self._power_kw = total_pulses * self._pulse_multiplier
                self._last_update = timestamp
                
                _LOGGER.debug(
                    "Power update: %.2f kW at %s", self._power_kw, timestamp
                )
                
                # Notify callbacks
                for callback in self._callbacks:
                    callback()
            else:
                _LOGGER.warning("Unexpected data length for 30s power: %d", len(data))
        elif command_header == RESPONSE_UPDATED_POWER:
            _LOGGER.debug("Received updated power command")
        elif command_header == RESPONSE_EVERY_30S_POWER:
            _LOGGER.debug("Received every 30s power command")

    def _handle_battery_notification(self, sender: int, data: bytearray) -> None:
        """Handle battery level notifications."""
        _LOGGER.debug("Battery notification: %s", data.hex())
        
        if len(data) >= 1:
            self._battery_level = data[0]
            _LOGGER.debug("Battery level: %d%%", self._battery_level)
            
            # Notify callbacks
            for callback in self._callbacks:
                callback()
