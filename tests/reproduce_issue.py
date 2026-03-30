
import asyncio
from dataclasses import dataclass
from app.services.counter import LineCounter
from app.core.config import CameraConfig, CountingLineConfig

@dataclass
class MockTrackedPerson:
    track_id: int
    centroid: tuple[int, int]

async def reproduce():
    # Config: Vertical line at 0.5 (320 in 640px)
    # Dead zone: 8px (312 to 328)
    line_cfg = CountingLineConfig(
        orientation="vertical",
        position=0.5,
        direction_in="right"
    )
    cam_cfg = CameraConfig(
        id="test",
        name="Test Camera",
        type="usb",
        source="0",
        counting_line=line_cfg
    )
    
    counter = LineCounter(cam_cfg, dead_zone_px=8)
    
    # Simulation: Person moves from 300 to 340, but stops at 320 (inside dead zone)
    steps = [300, 320, 340]
    
    print(f"Starting simulation with steps: {steps}")
    print(f"Line position: 320, Dead zone: [312, 328]")
    
    for i, x in enumerate(steps):
        person = MockTrackedPerson(track_id=1, centroid=(x, 240))
        # LineCounter.update expects TrackedPerson but only uses tid and centroid
        # We'll pass our mock person (it has track_id and centroid property/attribute)
        crossings = await counter.update([person], 640, 480)
        print(f"Step {i+1}: x={x}, crossings={crossings}, count_in={counter.state.count_in}")

    if counter.state.count_in == 1:
        print("\nSUCCESS: Crossing detected!")
    else:
        print("\nFAILURE: Crossing NOT detected (Current Bug confirmed)")

if __name__ == "__main__":
    asyncio.run(reproduce())
