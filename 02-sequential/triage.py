import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import asyncio
import logging
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.genai import types
from blaxel.core import DriveInstance, SandboxInstance, settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
for _noisy in ("mcp", "google_genai", "LiteLLM", "litellm", "google.adk", "httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
log = logging.getLogger(__name__)

async def main():

    log.info("Support ticket triage pipeline")
    log.info("Creating agent sandbox...")
    agent_sandbox = await SandboxInstance.create_if_not_exists({
      "name": "agent-sandbox",
      "image": "blaxel/base-image:latest",
      "memory": 4096,
      "region": "us-was-1"
    })
    log.info("Agent sandbox ready: %s", agent_sandbox.metadata.name)

    log.info("Mounting drive in agent sandbox at /data...")
    await agent_sandbox.drives.mount(
        drive_name="my-drive",
        mount_path="/data",
    )

    log.info("Connecting to sandbox MCP toolset...")
    agent_sandbox_toolset = McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=agent_sandbox.metadata.url + "/mcp",
            headers=settings.headers,
        )
    )
    tools = await agent_sandbox_toolset.get_tools()
    log.info("MCP tools loaded: %d tool(s) available.", len(tools))

    model = "openai/gpt-4o"

    log.info("Configuring agents (model: %s) for triage...", model)
    analyst_agent = LlmAgent(
        name="analyst",
        model=model,
        instruction="Read the file /data/support_tickets.md. Analyze and classify the support tickets into categories. Write the report to /data/analyst_report.md",
        tools=tools,
        output_key="analyst_report",
    )
    log.info("  analyst  : /data/support_tickets.md → /data/analyst_report.md")

    manager_agent = LlmAgent(
        name="manager",
        model=model,
        instruction="Read the file /data/analyst_report.md. Consolidate any duplicate or similar issues into a single task. Create a deduplicated list of tasks for the developer team. Classify the tasks by priority P0, P1 and P2. Write the list of tasks to /data/tasks.md",
        tools=tools,
        output_key="manager_report"
    )
    log.info("  manager  : /data/analyst_report.md → /data/tasks.md")

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

    log.info("Starting ticket triage pipeline...")

    current_agent = None
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=types.Content(parts=[types.Part(text=task)])
    ):
        if event.author != current_agent:
            if event.author == "analyst":
                log.info("[analyst] Reading /data/support_tickets.md from drive...")
                log.info("[analyst] Analyzing and writing /data/analyst_report.md to drive...")
            elif event.author == "manager":
                log.info("[manager] Reading /data/analyst_report.md from drive...")
                log.info("[manager] Analyzing and writing /data/tasks.md to drive...")
            current_agent = event.author
        # if event.content and event.content.parts:
        #     for part in event.content.parts:
        #         if hasattr(part, 'text') and part.text:
        #             print(part.text, end="", flush=True)
        #             print()

    log.info("Pipeline finished.")

    log.info("Reading /data/tasks.md from drive...")
    tasks = await agent_sandbox.fs.read("/data/tasks.md")

    log.info("Deleting agent sandbox...")
    await agent_sandbox.delete()
    log.info("Agent sandbox deleted.")

    #print("\nDEVELOPER TASK LIST (from drive: /data/tasks.md)")
    #print("-------------------------------------------------")
    #print(tasks)

asyncio.run(main())
