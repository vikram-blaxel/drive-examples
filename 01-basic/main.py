import asyncio
import logging
from blaxel.core import DriveInstance, SandboxInstance

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


async def main():

    # create drive
    log.info("Creating shared drive 'my-drive'...")
    drive = await DriveInstance.create_if_not_exists(
        {
            "name": "my-drive",
            "region": "us-was-1",
        }
    )
    log.info("Drive ready: %s", drive.metadata.name)

    # create sandbox #1
    log.info("Creating writer sandbox...")
    sandbox_writer = await SandboxInstance.create_if_not_exists({
      "name": "my-sandbox-writer",
      "image": "blaxel/base-image:latest",   # public or custom image
      "memory": 4096,   # in MB
      "region": "us-was-1"   # deployment region
    })
    log.info("Writer sandbox ready: %s", sandbox_writer.metadata.name)

    # mount drive in sandbox #1 at /mnt/shared
    log.info("Mounting drive in writer sandbox at /mnt/shared...")
    await sandbox_writer.drives.mount(
        drive_name="my-drive",
        mount_path="/mnt/shared",
    )

    # write file to drive
    log.info("Writing /mnt/shared/answer.txt...")
    await sandbox_writer.fs.write("/mnt/shared/answer.txt", "42")
    log.info("File written successfully.")

    # delete sandbox #1
    log.info("Deleting writer sandbox...")
    await sandbox_writer.delete()
    log.info("Writer sandbox deleted. File persists on drive.")

    # create sandbox #2
    log.info("Creating reader sandbox...")
    sandbox_reader = await SandboxInstance.create_if_not_exists({
      "name": "my-sandbox-reader",
      "image": "blaxel/base-image:latest",   # public or custom image
      "memory": 4096,   # in MB
      "region": "us-was-1"   # deployment region
    })
    log.info("Reader sandbox ready: %s", sandbox_reader.metadata.name)

    # mount drive in sandbox #2
    log.info("Mounting drive in reader sandbox at /mnt/shared...")
    await sandbox_reader.drives.mount(
        drive_name="my-drive",
        mount_path="/mnt/shared",
    )

    # read previously saved file from drive
    log.info("Reading /mnt/shared/answer.txt from drive...")
    data = await sandbox_reader.fs.read("/mnt/shared/answer.txt")
    log.info("File contents: %s", data)

    # delete sandbox #2
    # file remains on drive
    log.info("Deleting reader sandbox...")
    await sandbox_reader.delete()
    log.info("Done. File remains on drive for future sandboxes.")

asyncio.run(main())
