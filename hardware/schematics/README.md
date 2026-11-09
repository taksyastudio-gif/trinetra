# TRINETRA Hardware Schematics & Electrical Wiring

This document provides electrical wiring schematics, flashing steps, power distribution calculations, and pinout tables for the AI-Thinker ESP32-CAM wearable assistive vision rig.

---

## 1. AI-Thinker ESP32-CAM Pinout Map

```
                     +-------------------+
                     |   [OV2640 LENS]   |
                     |                   |
               GND  -| 1               16|- 5V (Power Input)
              IO23  -| 2  ESP32-CAM    15|- GND
              IO22  -| 3  AI-THINKER   14|- IO12 (MTDI)
              IO16  -| 4  MODULE       13|- IO13 (MTCK)
               IO0  -| 5  (PSRAM 4MB)  12|- IO15 (MTDO)
               GND  -| 6               11|- IO14 (MTMS)
              VCC   -| 7 (3.3V out)    10|- IO2  (HS2_DATA0)
              U0R   -| 8 (RX / IO3)     9|- IO4  (Flash LED / HS2_DATA1)
                     +-------------------+
```

> [!CAUTION]
> Power the module with clean **5V DC** on pin 16. Powering with 3.3V directly often causes WiFi brownouts during high radio transmission bursts.

---

## 2. Flashing Circuit (USB-to-TTL FTDI Programmer)

ESP32-CAM lacks an onboard USB-to-UART chip. Use a standard CP2102, FT232RL, or CH340G adapter to flash firmware.

```
+--------------------+                       +--------------------+
|  FTDI Programmer   |                       | ESP32-CAM Board    |
|                    |                       |                    |
|                VCC |====== (5V DC) =======>| 5V (Pin 16)        |
|                GND |====== (Ground) =======| GND (Pin 1 or 15)  |
|                 TX |====== (Data) =========>| U0R (Pin 8)        |
|                 RX |<===== (Data) =========| U0T (Pin 14 / IO1) |
+--------------------+                       +--------------------+
                                                        |
                                          [Jumper during Flash]
                                          IO0 (Pin 5) --------> GND
```

### Flashing Procedure
1. Jumper **IO0 to GND**.
2. Connect FTDI to PC USB port.
3. Open Arduino IDE:
   - Board: `AI Thinker ESP32-CAM`
   - CPU Frequency: `240MHz (WiFi/BT)`
   - Flash Frequency: `80MHz`
   - Flash Mode: `QIO`
   - Partition Scheme: `Huge APP (3MB No OTA/1MB SPIFFS)`
   - PSRAM: `Enabled`
4. Click **Upload**. Press the onboard `RST` button if prompted with `Connecting.....___`.
5. Once `Leaving... Hard resetting via RTS pin...` appears:
   - **Remove the IO0 to GND jumper**.
   - Press `RST` once to boot into live streaming mode.

---

## 3. Battery Power Distribution Circuit

```
+-----------------------+
| 3.7V 18650 Li-Ion     |
| (2600mAh / 3.7V Nom.) |
+-----------+-----------+
            |
            v
+-----------------------+      5V DC
| TP4056 Charger &      |================> [5V Pin] ESP32-CAM
| 5V Boost Step-Up Mod. |----------------> [GND Pin] ESP32-CAM
+-----------------------+
```

### Power & Battery Life Budget
- Active WiFi + MJPEG Streaming (VGA 640x480 @ 15 FPS): **180mA to 220mA @ 5V** (~1.0W)
- Flash LED Active (Night navigation): **+80mA** (~1.4W total)
- **Runtime on 2600mAh 18650 Cell**:
  $$\text{Runtime} \approx \frac{2600 \text{ mAh} \times 3.7\text{V} \times 0.85 \text{ (efficiency)}}{5\text{V} \times 200 \text{ mA}} \approx 8.1 \text{ hours}$$

---

## 4. Optional Sensor Add-ons (White Cane Rig)

### VL53L0X Time-of-Flight (ToF) Distance Sensor
For ground hazard detection (sub-millimeter precision for potholes up to 2 meters):
- **VCC** -> 3.3V (Pin 7)
- **GND** -> GND
- **SCL** -> IO14 (Pin 11)
- **SDA** -> IO13 (Pin 13)

### HC-SR04 Ultrasonic Distance Sensor
For obstacle echo detection in rain or foggy conditions:
- **VCC** -> 5V
- **GND** -> GND
- **Trig** -> IO15 (Pin 12)
- **Echo** -> Voltage Divider (1k / 2k resistor) -> IO12 (Pin 14) *(protects 3.3V logic)*
