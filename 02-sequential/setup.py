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
        mount_path="/data",
    )

    setup_sandbox = await SandboxInstance.create_if_not_exists({
      "name": "setup",
      "image": "blaxel/base-image:latest",   # public or custom image
      "memory": 4096,   # in MB
      "region": "us-was-1"   # deployment region
    })

    await setup_sandbox.drives.mount(
        drive_name="my-drive",
        mount_path="/data",
    )

    support_tickets = "\n".join([
        "1. User cannot reset password, reset link expires immediately after clicking.",
        "2. Multiple users report payment failures on credit cards, especially Visa.",
        "3. App logs out users randomly after a few minutes of inactivity.",
        "4. Feature request: ability to export reports to CSV format.",
        "5. Mobile app crashes when uploading profile pictures.",
        "6. Users are not receiving email notifications for important updates.",
        "7. Dashboard takes too long to load, especially with large datasets.",
        "8. Feature request: add dark mode for better night-time usability.",
        "9. Some users are being charged twice for the same transaction.",
        "10. Search functionality is returning irrelevant results for common queries.",
        "11. Password reset emails are broken - the link in the email doesn't work.",
        "12. Customer was billed twice for a single purchase.",
    ])

    await setup_sandbox.fs.write("/data/support_tickets.md", support_tickets)
    log.info("Support tickets written to drive.")

asyncio.run(main())
