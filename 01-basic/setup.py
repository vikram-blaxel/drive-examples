import asyncio
import logging
from blaxel.core import DriveInstance, SandboxInstance

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


async def main():

    drive = await DriveInstance.create_if_not_exists(
        {
            "name": "my-drive",
            "region": "us-was-1",
        }
    )

    watcher_sandbox = await SandboxInstance.create_if_not_exists({
      "name": "watcher",
      "image": "blaxel/base-image:latest",   # public or custom image
      "memory": 4096,   # in MB
      "region": "us-was-1"   # deployment region
    })

    await watcher_sandbox.drives.mount(
        drive_name="my-drive",
        mount_path="/mnt/shared",
    )


asyncio.run(main())
