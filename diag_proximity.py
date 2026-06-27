"""Quick diagnostic: test proximity sensor + buzzer interaction."""
import asyncio
import logging
import sys
sys.path.insert(0, ".")

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")

from proximity import AsyncProximity
from buzzer import AsyncBuzzer


async def main():
    p = AsyncProximity(threshold_mm=100)
    b = AsyncBuzzer()
    await p.init()
    await b.init()

    await p.enable()
    print("=== Reading proximity for 3 seconds (no buzzer) ===")
    for i in range(30):
        dist = await p.read_distance()
        wave = await p.is_wave()
        print(f"  t={i*0.1:.1f}s  dist={dist}mm  wave={wave}")
        await asyncio.sleep(0.1)

    print("\n=== Now with buzzer chirps ===")
    for i in range(30):
        dist = await p.read_distance()
        wave = await p.is_wave()
        print(f"  t={i*0.1:.1f}s  dist={dist}mm  wave={wave}")
        if i == 5:
            print("  → buzzing notify...")
            await b.chime_notify()
        if i == 15:
            print("  → buzzing escalate...")
            await b.chime_escalate_2()
        await asyncio.sleep(0.1)

    await p.disable()
    print("\nDone. No false waves should appear above.")


asyncio.run(main())
