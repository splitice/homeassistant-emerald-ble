# Emerald Energy Monitor - Home Assistant Integration

A Home Assistant custom integration for the Emerald Energy Monitor BLE device. This integration allows you to connect to your Emerald device directly from Home Assistant without needing an ESP32 bridge.

## Features

- **Direct BLE Connection**: Connects to the Emerald device via Bluetooth Low Energy
- **Real-time Power Monitoring**: Displays current power consumption in kilowatts (kW)
- **Battery Monitoring**: Shows the battery level of your Emerald device
- **Auto-discovery**: Supports Home Assistant's Bluetooth discovery
- **Easy Setup**: Simple configuration through the Home Assistant UI

## Requirements

- Home Assistant with Bluetooth support (built-in Bluetooth adapter or ESPHome Bluetooth Proxy)
- Emerald Energy Monitor BLE device
- Pairing PIN from your Emerald device

## Installation

### HACS (Recommended)

1. Add this repository as a custom repository in HACS
2. Search for "Emerald Energy Monitor" in HACS
3. Install the integration
4. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/emerald_ble` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "Emerald Energy Monitor"
4. Enter the following information:
   - **MAC Address**: The Bluetooth MAC address of your Emerald device (e.g., `30:1B:97:00:00:00`)
   - **Pairing PIN**: The 6-digit PIN from your Emerald device (default: `123123`)
   - **Pulses per kW**: Number of pulses per kilowatt-hour (default: `1000`)

## Entities

After successful setup, the integration will create the following entities:

- **Power Sensor**: Current power consumption (kW)
  - Device Class: Power
  - Unit: kW
  - Updates every 30 seconds (standard for Emerald)

- **Energy Sensor**: Cumulative energy consumption (kWh)
  - Device Class: Energy
  - Unit: kWh
  - Calculated by integrating power over time using Riemann sum approximation
  - Resets when the integration is reloaded or Home Assistant restarts

- **Battery Sensor**: Battery level of the Emerald device
  - Device Class: Battery
  - Unit: %

## Troubleshooting

### Device Not Found

- Ensure your Emerald device is in range and powered on
- Check that Bluetooth is enabled on your Home Assistant host
- Verify the MAC address is correct (use uppercase or lowercase consistently)

### Connection Failed

- Verify the pairing PIN is correct
- Try restarting the Emerald device
- Check Home Assistant logs for detailed error messages

### No Data Updates

- Ensure the device is connected (check entity availability)
- Verify the "pulses per kW" value matches your meter configuration
- Check that auto-upload is enabled on the device

## Technical Details

This integration is based on the [Emerald Electricity Advisor ESP32 reference code](https://github.com/WeekendWarrior1/emerald_electricity_advisor/blob/main/esp32_ble_print_data.ino) and implements the following:

- BLE Service UUIDs:
  - Device Info: `0000180a-0000-1000-8000-00805f9b34fb`
  - Time Service: `00001910-0000-1000-8000-00805f9b34fb`
  - Battery Service: `0000180f-0000-1000-8000-00805f9b34fb`

- Power calculation: Based on 30-second pulse data packets
- Default pulse multiplier: `120 / pulses_per_kw` (for 30s intervals)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.

## Credits

Based on research and reference code from [WeekendWarrior1's Emerald Electricity Advisor](https://github.com/WeekendWarrior1/emerald_electricity_advisor).
