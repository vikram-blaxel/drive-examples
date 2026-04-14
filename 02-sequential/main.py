import asyncio
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.genai import types
from blaxel.core import DriveInstance, SandboxInstance, settings

async def main():

    drive = await DriveInstance.create_if_not_exists(
        {
            "name": "my-drive",
            "region": "us-was-1",
        }
    )

    setup_sandbox = await SandboxInstance.create_if_not_exists({
      "name": "setup-sandbox",
      "image": "blaxel/base-image:latest",
      "memory": 4096,
      "region": "us-was-1"
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

    await setup_sandbox.delete()

    agent_sandbox = await SandboxInstance.create_if_not_exists({
      "name": "agent-sandbox",
      "image": "blaxel/base-image:latest",
      "memory": 4096,
      "region": "us-was-1"
    })

    await agent_sandbox.drives.mount(
        drive_name="my-drive",
        mount_path="/data",
    )

    agent_sandbox_toolset = McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=agent_sandbox.metadata.url + "/mcp",
            headers=settings.headers,
        )
    )
    tools = await agent_sandbox_toolset.get_tools()

    model = "openai/gpt-4o"

    analyst_agent = LlmAgent(
        name="analyst",
        model=model,
        instruction="Read the file /data/support_tickets.md. Analyze and classify the support tickets into categories. Write the report to /data/analyst_report.md",
        tools=tools,
        output_key="analyst_report",
    )

    manager_agent = LlmAgent(
        name="manager",
        model=model,
        instruction="Read the file /data/analyst_report.md. Consolidate any duplicate or similar issues into a single task. Create a deduplicated list of tasks for the developer team. Classify the tasks by priority P0, P1 and P2. Write the list of tasks to /data/tasks.md",
        tools=tools,
        output_key="manager_report"
    )

    root_agent = SequentialAgent(
        name='ticket_triage_pipeline',
        sub_agents=[analyst_agent, manager_agent],
        description="Executes a sequence of agents"
    )

    app = App(
        name="ticket_triage",
        root_agent=root_agent,
    )

    runner = InMemoryRunner(app=app)

    user_id = "user"
    task = "Analyze support tickets and create a list of tasks from it."
    session = await runner.session_service.create_session(
        app_name="ticket_triage",
        user_id=user_id
    )

    print("Starting agent...")

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=types.Content(parts=[types.Part(text=task)])
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, 'text') and part.text:
                    print(part.text, end="", flush=True)
                    print()

    print("Agent finished!")

    tasks = await agent_sandbox.fs.read("/data/tasks.md")

    await agent_sandbox.delete()

    print("DEVELOPER TASK LIST")
    print("-----------------")
    print(tasks)

asyncio.run(main())
