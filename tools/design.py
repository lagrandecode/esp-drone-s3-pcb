"""ESP32-S3 micro brushed quadcopter: parts, nets and placement.

Coordinates are millimetres relative to the frame centre, x to the right and
y towards the rear (KiCad convention). The front of the drone is -y.
Pin assignments follow espressif/esp-drone target TARGET_ESP32_S2_DRONE_V1_2,
which is also the default for ESP32-S3 builds.
"""

BOARD_ORIGIN = (100.0, 100.0)

MOTORS = {1: (35.0, -35.0), 2: (35.0, 35.0), 3: (-35.0, 35.0), 4: (-35.0, -35.0)}
MOTOR_SPIN = {1: "CCW", 2: "CW", 3: "CCW", 4: "CW"}
ARM_ROOTS = {1: (14.0, -8.0), 2: (14.0, 24.0), 3: (-14.0, 24.0), 4: (-14.0, -8.0)}
ARM_WIDTH = 6.5
RING_OUTER_D = 16.5
MOTOR_HOLE_D = 11.0  # 7 mm motor + rubber motor ring, same as ESP-Drone reference frame
SLOT_WIDTH = 1.5
BODY = (-19.0, -21.5, 19.0, 30.0)  # x0, y0, x1, y1
BODY_CORNER_R = 3.0
FILLET_R = 2.0
MOTOR_PAD_DIST = {"+": 11.0, "-": 14.0}  # distance from motor centre along the arm

FP_LIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"

R0603 = ("Resistor_SMD", "R_0603_1608Metric")
C0603 = ("Capacitor_SMD", "C_0603_1608Metric")
C0805 = ("Capacitor_SMD", "C_0805_2012Metric")
C1206 = ("Capacitor_SMD", "C_1206_3216Metric")
LED0603 = ("LED_SMD", "LED_0603_1608Metric")
SOT23 = ("Package_TO_SOT_SMD", "SOT-23")
SMA = ("Diode_SMD", "D_SMA")

# ref: (footprint, value, lcsc, x, y, rot, {pad: net})
PARTS = {
    # --- MCU -------------------------------------------------------------
    "U1": (("RF_Module", "ESP32-S3-WROOM-1"), "ESP32-S3-WROOM-1-N8", "C2913198", 0.0, -15.0, 0, {
        "1": "GND", "2": "3V3", "3": "EN", "4": "MOT4_PWM", "5": "MOT1_PWM", "6": "MOT2_PWM",
        "7": "LED_B", "12": "LED_R", "13": "USB_DN", "14": "USB_DP", "15": "MOT3_PWM",
        "17": "LED_G", "18": "I2C_SCL", "19": "I2C_SDA", "20": "IMU_INT", "27": "BOOT",
        "38": "VBAT_ADC", "40": "GND", "41": "GND"}),
    "C2": (C0805, "22uF", "C45783", -13.6, -19.0, 90, {"1": "3V3", "2": "GND"}),
    "C3": (C0603, "100nF", "C14663", -11.4, -19.0, 90, {"1": "3V3", "2": "GND"}),
    "R9": (R0603, "10k", "C25804", -11.4, -15.6, 90, {"1": "3V3", "2": "EN"}),
    "C1": (C0603, "1uF", "C15849", -13.6, -15.6, 90, {"1": "EN", "2": "GND"}),
    "SW2": (("Button_Switch_SMD", "SW_Push_1P1T_XKB_TS-1187A"), "RESET", "C318884", -14.4, -5.0, 0,
            {"1": "EN", "2": "GND"}),
    "R10": (R0603, "10k", "C25804", 13.4, -15.6, 90, {"1": "3V3", "2": "BOOT"}),
    "SW1": (("Button_Switch_SMD", "SW_Push_1P1T_XKB_TS-1187A"), "BOOT", "C318884", 14.4, -5.0, 0,
            {"1": "BOOT", "2": "GND"}),
    # --- battery voltage sense (1:2 divider, ADC on GPIO2) -----------------
    "R13": (R0603, "100k", "C25803", 11.4, -19.0, 90, {"1": "VBAT", "2": "VBAT_ADC"}),
    "R14": (R0603, "100k", "C25803", 13.4, -19.0, 90, {"1": "VBAT_ADC", "2": "GND"}),
    "C14": (C0603, "100nF", "C14663", 11.4, -15.6, 90, {"1": "VBAT_ADC", "2": "GND"}),
    # --- IMU ---------------------------------------------------------------
    "U2": (("Sensor_Motion", "InvenSense_QFN-24_4x4mm_P0.5mm"), "MPU-6050", "C24112", 0.0, 4.0, 180, {
        "1": "GND", "8": "3V3", "9": "GND", "10": "MPU_REGOUT", "11": "GND", "12": "IMU_INT",
        "13": "3V3", "18": "GND", "20": "MPU_CPOUT", "23": "I2C_SCL", "24": "I2C_SDA"}),
    "C10": (C0603, "100nF", "C14663", -3.9, 2.9, 90, {"1": "3V3", "2": "GND"}),
    "C11": (C0603, "10nF", "C57112", 3.9, 2.9, 90, {"1": "3V3", "2": "GND"}),
    "C12": (C0603, "100nF", "C14663", -3.9, 6.2, 90, {"1": "MPU_REGOUT", "2": "GND"}),
    "C13": (C0603, "2.2nF", "C1604", -1.0, 8.0, 0, {"1": "MPU_CPOUT", "2": "GND"}),
    "R11": (R0603, "4.7k", "C23162", 3.9, 6.2, 90, {"1": "3V3", "2": "I2C_SDA"}),
    "R12": (R0603, "4.7k", "C23162", 2.1, 9.6, 0, {"1": "3V3", "2": "I2C_SCL"}),
    # --- status LEDs (active high, as in esp-drone led.h) -----------------
    "R6": (R0603, "470R", "C23179", -11.5, 1.0, 0, {"1": "LED_R", "2": "LED_R_A"}),
    "R7": (R0603, "100R", "C22775", -11.5, 3.0, 0, {"1": "LED_G", "2": "LED_G_A"}),
    "R8": (R0603, "100R", "C22775", -11.5, 5.0, 0, {"1": "LED_B", "2": "LED_B_A"}),
    "LED1": (LED0603, "RED", "C2286", -8.0, 1.0, 180, {"1": "GND", "2": "LED_R_A"}),
    "LED2": (LED0603, "GREEN", "C12624", -8.0, 3.0, 180, {"1": "GND", "2": "LED_G_A"}),
    "LED3": (LED0603, "BLUE", "C2288", -8.0, 5.0, 180, {"1": "GND", "2": "LED_B_A"}),
    # --- USB-C + Li-ion charger -------------------------------------------
    "J1": (("Connector_USB", "USB_C_Receptacle_HRO_TYPE-C-31-M-12"), "USB-C", "C165948", 0.0, 26.3, 0, {
        "A1": "GND", "B12": "GND", "A12": "GND", "B1": "GND", "A4": "VBUS", "B9": "VBUS",
        "A9": "VBUS", "B4": "VBUS", "A5": "CC1", "B5": "CC2", "A6": "USB_DP", "B6": "USB_DP",
        "A7": "USB_DN", "B7": "USB_DN", "SH": "GND"}),
    "R1": (R0603, "5.1k", "C23186", -7.0, 20.0, 90, {"1": "CC1", "2": "GND"}),
    "R2": (R0603, "5.1k", "C23186", 7.0, 20.0, 90, {"1": "CC2", "2": "GND"}),
    "U3": (("Package_SO", "SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.3mm"), "TP4056", "C16581", -10.5, 10.5, 0, {
        "1": "GND", "2": "TP_PROG", "3": "GND", "4": "VBUS", "5": "VBAT", "6": "CHG_STDBY",
        "7": "CHG_CHRG", "8": "VBUS", "9": "GND"}),
    "R3": (R0603, "3k", "C4211", -16.5, 9.9, 90, {"1": "TP_PROG", "2": "GND"}),  # 400 mA charge
    "C6": (C0805, "10uF", "C15850", -16.5, 13.6, 90, {"1": "VBUS", "2": "GND"}),
    "C7": (C0805, "10uF", "C15850", -5.5, 11.5, 90, {"1": "VBAT", "2": "GND"}),
    "LED4": (LED0603, "RED", "C2286", -16.3, 0.5, 180, {"1": "CHG_CHRG", "2": "LED4_A"}),
    "LED5": (LED0603, "GREEN", "C12624", -16.3, 2.5, 180, {"1": "CHG_STDBY", "2": "LED5_A"}),
    "R4": (R0603, "1k", "C21190", -16.3, 4.5, 0, {"1": "LED4_A", "2": "VBUS"}),
    "R5": (R0603, "1k", "C21190", -16.3, 6.5, 0, {"1": "LED5_A", "2": "VBUS"}),
    # --- power path (USB or battery -> VSYS) + 3.3 V LDO ------------------
    "D5": (("Diode_SMD", "D_SOD-123"), "B5819W", "C8598", 9.5, 13.0, 0, {"1": "VSYS", "2": "VBUS"}),
    "Q5": (SOT23, "AO3401A", "C15127", 10.0, 9.4, 0, {"1": "VBUS", "2": "VSYS", "3": "VBAT"}),
    "R15": (R0603, "100k", "C25803", 6.0, 9.0, 90, {"1": "VBUS", "2": "GND"}),
    "U4": (("Package_TO_SOT_SMD", "SOT-23-5"), "AP2112K-3.3", "C51118", 9.0, 3.0, 0, {
        "1": "VSYS", "2": "GND", "3": "LDO_EN", "5": "3V3"}),
    "C4": (C0805, "10uF", "C15850", 9.0, 6.3, 0, {"1": "VSYS", "2": "GND"}),
    "C5": (C0805, "10uF", "C15850", 9.5, -0.3, 0, {"1": "3V3", "2": "GND"}),
    "R20": (R0603, "100k", "C25803", 6.0, 5.0, 90, {"1": "LDO_EN", "2": "GND"}),
    "SW3": (("Button_Switch_SMD", "SW_SPDT_Shouhan_MSK12C02"), "POWER", "C431540", 16.1, 5.8, 270, {
        "1": "VSYS", "2": "LDO_EN", "SH": "GND"}),
    # --- battery bulk capacitance ------------------------------------------
    "C8": (C1206, "47uF", "C96123", 1.5, 16.9, 0, {"1": "VBAT", "2": "GND"}),
    "C9": (C1206, "47uF", "C96123", 1.5, 19.4, 0, {"1": "VBAT", "2": "GND"}),
}

# Brushed motor low-side drivers: (mosfet pos, diode pos, pulldown pos)
DRIVERS = {
    1: ((12.8, -11.0, 0), (16.9, -16.0, 90), (17.0, -10.2, 90)),
    2: ((12.8, 17.5, 0), (16.9, 14.0, 90), (12.8, 21.0, 0)),
    3: ((-12.5, 17.5, 0), (-16.9, 19.5, 90), (-12.5, 21.2, 0)),
    4: ((-12.8, -11.0, 0), (-16.9, -16.0, 90), (-17.0, -10.2, 90)),
}
for n, (q, d, r) in DRIVERS.items():
    PARTS[f"Q{n}"] = (SOT23, "AO3400A", "C20917", q[0], q[1], q[2],
                      {"1": f"MOT{n}_PWM", "2": "GND", "3": f"MOT{n}_N"})
    PARTS[f"D{n}"] = (SMA, "SS34", "C8678", d[0], d[1], d[2], {"1": "VBAT", "2": f"MOT{n}_N"})
    PARTS[f"R{15 + n}"] = (R0603, "10k", "C25804", r[0], r[1], r[2], {"1": f"MOT{n}_PWM", "2": "GND"})

BAT_PADS = {"+": (4.5, 13.0), "-": (-1.5, 13.0)}

# Pad mapping KiCad -> EasyEDA for polarised two-terminal parts whose EasyEDA
# pad numbers do not follow KiCad's cathode = pad 1 convention.
EASYEDA_PAD_MAP = {
    "C2286": {"1": "2", "2": "1"},
}

NETCLASSES = {
    # name: (track width, clearance, nets)
    "PLANE": (0.5, 0.2, ["GND", "VBAT"]),
    "MOTOR": (0.8, 0.25, [f"MOT{n}_N" for n in range(1, 5)]),
    "POWER": (0.4, 0.2, ["VSYS", "VBUS"]),
    "LOGIC_PWR": (0.25, 0.2, ["3V3"]),
}
