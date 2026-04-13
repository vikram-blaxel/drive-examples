import asyncio
from blaxel.core import DriveInstance, SandboxInstance


async def main():

    # create drive
    drive = await DriveInstance.create_if_not_exists(
        {
            "name": "my-drive",
            "region": "us-was-1",
        }
    )

    # create sandbox #1
    sandbox_writer = await SandboxInstance.create_if_not_exists({
      "name": "my-sandbox-writer",
      "image": "blaxel/base-image:latest",   # public or custom image
      "memory": 4096,   # in MB
      "region": "us-was-1"   # deployment region
    })

    # mount drive in sandbox #1 at /mnt/shared
    await sandbox_writer.drives.mount(
        drive_name="my-drive",
        mount_path="/mnt/shared",
    )

    # write file to drive
    await sandbox_writer.fs.write("/mnt/shared/answer.txt", "42")

    # delete sandbox #1
    await sandbox_writer.delete()

    # create sandbox #2
    sandbox_reader = await SandboxInstance.create_if_not_exists({
      "name": "my-sandbox-reader",
      "image": "blaxel/base-image:latest",   # public or custom image
      "memory": 4096,   # in MB
      "region": "us-was-1"   # deployment region
    })

    # mount drive in sandbox #2
    await sandbox_reader.drives.mount(
        drive_name="my-drive",
        mount_path="/mnt/shared",
    )

    # read previously saved file from drive
    data = await sandbox_reader.fs.read("/mnt/shared/answer.txt")
    print(data)

    # delete sandbox #2
    # file remains on drive
    await sandbox_reader.delete()

asyncio.run(main())
