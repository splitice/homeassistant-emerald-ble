# Quick Installation Guide

## Option 1: Manual Installation

1. Download or clone this repository
2. Copy the entire `custom_components/emerald_ble` folder to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant
4. Go to **Settings** → **Devices & Services** → **Add Integration**
5. Search for "Emerald Energy Monitor"
6. Follow the configuration wizard

## Option 2: HACS Installation (Future)

When this integration is published to HACS:

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots menu and select "Custom repositories"
4. Add this repository URL
5. Search for "Emerald Energy Monitor"
6. Click "Install"
7. Restart Home Assistant
8. Add the integration via Settings → Devices & Services

## Configuration Parameters

- **MAC Address**: Your Emerald device's Bluetooth MAC address (format: `30:1B:97:00:00:00`)
  - Find this by scanning for Bluetooth devices or checking your device documentation
  
- **Pairing PIN**: 6-digit PIN code (default: `123123`)
  - If your PIN starts with 0, enter it without the leading zero (e.g., `024024` → `24024`)
  
- **Pulses per kW**: Meter pulse rate (default: `1000`)
  - Consult your electricity meter documentation for the correct value

## Troubleshooting

### Cannot find the device
- Ensure your Emerald device is powered on and in range
- Check that Bluetooth is enabled on your Home Assistant host
- Verify the MAC address is correct

### Connection timeout
- Try moving the device closer to your Home Assistant host
- Verify the pairing PIN is correct
- Restart both the Emerald device and Home Assistant

### No data updates
- Check that the device shows as "Connected" in the entity attributes
- Verify the "pulses per kW" setting matches your meter
- Review Home Assistant logs for any error messages

## Getting the MAC Address

### Method 1: Home Assistant Bluetooth Scanner
1. Go to **Settings** → **Devices & Services** → **Bluetooth**
2. Look for your Emerald device in the discovered devices list
3. Note the MAC address

### Method 2: Using bluetoothctl (Linux)
```bash
sudo bluetoothctl
scan on
# Look for your Emerald device in the list
# Note the MAC address
scan off
exit
```

### Method 3: Mobile App
Use a Bluetooth scanning app on your phone to find nearby BLE devices and locate your Emerald device.
