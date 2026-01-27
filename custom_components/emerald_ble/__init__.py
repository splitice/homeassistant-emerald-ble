"""The Emerald Energy Monitor integration."""
import logging

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import async_discovered_service_info
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_MAC_ADDRESS,
    CONF_DEVICE_NAME,
    CONF_PIN,
    CONF_PULSES_PER_KW,
    DEVICE_NAME_PREFIX,
    DOMAIN,
)
from .emerald_ble import EmeraldBLEDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


def extract_serial_from_name(device_name: str | None) -> str | None:
    """Extract serial number from Emerald device name.
    
    Expected format: "ElAdv <SERIAL>" e.g. "ElAdv 210800000000"
    Returns the serial number or None if the name doesn't match.
    """
    if not device_name:
        return None
    
    if device_name.startswith(DEVICE_NAME_PREFIX):
        serial = device_name[len(DEVICE_NAME_PREFIX):].strip()
        if serial:
            return serial
    
    return None


def find_emerald_device_by_name(hass: HomeAssistant, device_name: str):
    """Find an Emerald BLE device by its name across all discovered devices."""
    _LOGGER.debug("Searching for Emerald device with name: %s", device_name)
    
    for discovery_info in async_discovered_service_info(hass, connectable=True):
        # Check both the name and advertisement name
        discovered_name = discovery_info.name
        _LOGGER.debug("Checking discovered device: %s (address: %s)", 
                     discovered_name, discovery_info.address)
        
        if discovered_name == device_name:
            _LOGGER.info("Found Emerald device by name: %s at address %s", 
                        device_name, discovery_info.address)
            return discovery_info.device
    
    return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Emerald Energy Monitor from a config entry."""
    mac_address = entry.data[CONF_MAC_ADDRESS]
    pin = entry.data[CONF_PIN]
    pulses_per_kw = entry.data[CONF_PULSES_PER_KW]
    device_name = entry.data.get(CONF_DEVICE_NAME)

    _LOGGER.debug("Setting up Emerald device at %s (name: %s)", mac_address, device_name)

    # Try to get the BLE device by MAC address first
    ble_device = bluetooth.async_ble_device_from_address(
        hass, mac_address.upper(), connectable=True
    )
    
    # If not found by MAC and we have a device name, try finding by name
    if not ble_device and device_name:
        _LOGGER.info(
            "Device not found by MAC address %s, searching by name: %s", 
            mac_address, device_name
        )
        ble_device = find_emerald_device_by_name(hass, device_name)
        
        if ble_device:
            _LOGGER.info(
                "Found device by name %s at new address: %s (old address was %s)",
                device_name, ble_device.address, mac_address
            )
    
    if not ble_device:
        error_msg = f"Could not find Emerald device with address {mac_address}"
        if device_name:
            error_msg += f" or name {device_name}"
        raise ConfigEntryNotReady(error_msg)

    # Create the device instance
    device = EmeraldBLEDevice(ble_device, pin, pulses_per_kw)
    
    # Try to connect
    if not await device.connect():
        raise ConfigEntryNotReady(f"Failed to connect to device {mac_address}")

    # Store the device in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = device

    # Forward the setup to the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        device: EmeraldBLEDevice = hass.data[DOMAIN].pop(entry.entry_id)
        await device.disconnect()

    return unload_ok
