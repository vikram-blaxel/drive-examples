import asyncio
from blaxel.core import DriveInstance, SandboxInstance


async def main():

    drive = await DriveInstance.create_if_not_exists(
        {
            "name": "my-drive",
            "region": "us-was-1",
        }
    )

    sandbox = await SandboxInstance.create_if_not_exists({
      "name": "my-sandbox",
      "image": "blaxel/base-image:latest",   # public or custom image
      "memory": 4096,   # in MB
      "region": "us-was-1"   # deployment region
    })

    await sandbox.drives.mount(
        drive_name="my-drive",
        mount_path="/data",
    )

    await sandbox.fs.write("/data/support_tickets.txt", """1. User cannot reset password — reset link expires immediately after clicking.
2. Multiple users report payment failures on credit cards, especially Visa.
3. App logs out users randomly after a few minutes of inactivity.
4. Feature request: ability to export reports to CSV format.
5. Mobile app crashes when uploading profile pictures.
6. Users are not receiving email notifications for important updates.
7. Dashboard takes too long to load, especially with large datasets.
8. Feature request: add dark mode for better night-time usability.
9. Some users are being charged twice for the same transaction.
10. Search functionality is returning irrelevant results for common queries.""")

    support_agent = LlmAgent(
        name="support",
        model=MODEL,
        instruction="Analyze and classify the support tickets in /data/support_tickets.txt. Write the report to /data/support_report.txt",
        output_key="support_ticket_report",
    )

    manager_agent = LlmAgent(
        model=MODEL,
        instruction="Read the support ticket analysis at /data/support_report.txt. Create a list of tasks for the developer team. Return the list with the tasks classified by priority P0, P1 and P2.",
        output_key="task_report"
    )

    root_agent = SequentialAgent(
        name='feedback_pipeline_agent',
        sub_agents=[support_agent, manager_agent],
        description="Executes a sequence of agents"
    )

    sandbox_reader = await SandboxInstance.create_if_not_exists({
      "name": "my-sandbox-reader",
      "image": "blaxel/base-image:latest",   # public or custom image
      "memory": 4096,   # in MB
      "region": "us-was-1"   # deployment region
    })

    await sandbox_reader.drives.mount(
        drive_name="my-drive",
        mount_path="/mnt/shared",
    )

    data = await sandbox_reader.fs.read("/mnt/shared/answer.txt")
    print(data)

asyncio.run(main())
