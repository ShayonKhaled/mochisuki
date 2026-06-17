import spidev
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 4000000
spi.mode = 0b00

resp = spi.xfer2([0x71, 0x00])
print("SPI response:", resp)
spi.close()
print("SPI test done")
