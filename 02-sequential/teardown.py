import asyncio
from blaxel.core import DriveInstance, SandboxInstance


async def main():

    drive = await DriveInstance.get("my-drive")
    watcher_sandbox = await SandboxInstance.get("watcher")
    setup_sandbox = await SandboxInstance.get("setup")

    await setup_sandbox.delete()
    await watcher_sandbox.delete()
    await drive.delete()

asyncio.run(main())
