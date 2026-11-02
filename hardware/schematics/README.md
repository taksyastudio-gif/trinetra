# TRINETRA Hardware Schematics & Wiring

This directory contains wiring diagrams, pinout configurations, power distribution schematics, and mechanical mounting specifications for the chest-mounted TRINETRA prototype.

## Modules & Peripherals
1. **Camera Module:** ESP32-CAM (AI-Thinker) / OV2640
2. **Power Supply:** 3.7V 18650 Li-Ion battery with TP4056 charging module and 5V step-up boost converter (or protected power bank)
3. **FTDI / Programmer:** USB-to-TTL UART programmer (GND, 5V, TX->U0R, RX->U0T, IO0 to GND during flash mode)
4. **Rangefinding / Sensors (Planned):** HC-SR04 / VL53L0X ToF sensor
5. **Physical Enclosure:** Chest-mounted harness / 3D-printed enclosure with thermal dissipation venting for ESP32-CAM
