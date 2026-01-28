"""The Emerald Energy Monitor integration."""
import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_MAC_ADDRESS, CONF_PIN, CONF_PULSES_PER_KW, DOMAIN
from .emerald_ble import EmeraldBLEDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Emerald Energy Monitor from a config entry."""
    mac_address = entry.data[CONF_MAC_ADDRESS]
    pin = entry.data[CONF_PIN]
    pulses_per_kw = entry.data[CONF_PULSES_PER_KW]

    _LOGGER.debug("Setting up Emerald device at %s", mac_address)

    # Get the BLE device
    ble_device = bluetooth.async_ble_device_from_address(
        hass, mac_address.upper(), connectable=True
    )
    
    if not ble_device:
        raise ConfigEntryNotReady(
            f"Could not find Emerald device with address {mac_address}"
        )

    # Create the device instance
    device = EmeraldBLEDevice(hass, ble_device, pin, pulses_per_kw)
    
    # Store the device in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = device

    # Start the device (will register advertisement callback and wait for connection opportunity)
    await device.start()

    # Forward the setup to the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        device: EmeraldBLEDevice = hass.data[DOMAIN].pop(entry.entry_id)
        await device.stop()

    return unload_ok
