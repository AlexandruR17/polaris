# PlatformIO extra script: quiet third-party warnings we cannot fix upstream.
# LiquidCrystal_I2C 1.1.3 uses the deprecated Arduino Bxxxxxxx macros.
Import("env")

for lb in env.GetLibBuilders():
    if lb.name == "LiquidCrystal_I2C":
        lb.env.Append(CCFLAGS=["-Wno-deprecated-declarations"])
