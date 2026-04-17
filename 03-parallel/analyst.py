import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import asyncio
import logging
from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.genai import types
from blaxel.core import SandboxInstance, settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
for _noisy in ("mcp", "google_genai", "LiteLLM", "litellm", "google.adk", "httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
log = logging.getLogger(__name__)

BANNER = """
============================================================
  SUPPORT TICKET TRIAGE PIPELINE
  Step 1 of 2: Analyst                       (analyst.py)
  ---
  Reads raw support tickets and classifies them
  into categories, producing an analyst report.

  [drive: my-drive @ /shared]
  INPUT : /shared/support_tickets_raw.md
  OUTPUT: /shared/ANALYSIS.md
  ---
  Run manager.py in parallel — it will wait for
  this script to finish writing ANALYSIS.md
  before starting.
============================================================
"""

async def main():
    print(BANNER)

    log.info("[analyst] Creating sandbox...")
    sandbox = await SandboxInstance.create_if_not_exists({
        "name": "analyst-sandbox",
        "image": "blaxel/base-image:latest",
        "memory": 4096,
        "region": "us-was-1"
    })
    log.info("[analyst] Sandbox ready: %s", sandbox.metadata.name)

    log.info("[analyst] Mounting drive my-drive at /shared...")
    await sandbox.drives.mount(
        drive_name="my-drive",
        mount_path="/shared",
    )

    log.info("[analyst] Connecting to MCP toolset...")
    toolset = McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=sandbox.metadata.url + "/mcp",
            headers=settings.headers,
        )
    )
    tools = await toolset.get_tools()
    log.info("[analyst] MCP tools loaded: %d tool(s) available.", len(tools))

    model = "openai/gpt-4o"
    log.info("[analyst] Configuring analyst agent (model: %s)...", model)

    analyst_agent = LlmAgent(
        name="analyst",
        model=model,
        instruction=(
            "Read the file /shared/support_tickets_raw.md. "
            "Analyze and classify the support tickets into categories. "
            "Write the report to /shared/ANALYSIS.md. "
            "Include a 'Summary' section at the end of the report listing the total number of tickets and the count per category."
        ),
        tools=tools,
        output_key="analyst_report",
    )

    app = App(name="analyst_app", root_agent=analyst_agent)
    runner = InMemoryRunner(app=app)

    session = await runner.session_service.create_session(
        app_name="analyst_app",
        user_id="user"
    )

    log.info("[analyst] Reading /shared/support_tickets_raw.md from drive...")
    log.info("[analyst] Analyzing tickets and writing /shared/ANALYSIS.md to drive...")

    async for _ in runner.run_async(
        user_id="user",
        session_id=session.id,
        new_message=types.Content(parts=[types.Part(text="Analyze support tickets and write the analyst report.")])
    ):
        pass

    log.info("[analyst] Done. /shared/ANALYSIS.md written to drive.")

    analysis = await sandbox.fs.read("/shared/ANALYSIS.md")

    log.info("[analyst] Deleting sandbox...")
    await sandbox.delete()
    log.info("[analyst] Sandbox deleted. Analyst step complete.")

    print("[analyst] Step 1 of 2 complete. Manager can now proceed.\n")

asyncio.run(main())
