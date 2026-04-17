import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import asyncio
import logging
import re
import time
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
  Step 2 of 2: Manager                       (manager.py)
  ---
  Waits for the analyst report, then deduplicates
  issues and produces a prioritized task list.

  [drive: my-drive @ /shared]
  INPUT : /shared/ANALYSIS.md   (written by analyst.py)
  OUTPUT: /shared/P0_TASKS.md, /shared/P1_TASKS.md, /shared/P2_TASKS.md
  ---
  This script polls the drive every 1s until
  ANALYSIS.md appears, then starts automatically.
============================================================
"""

POLL_FILE = "/shared/ANALYSIS.md"
POLL_INTERVAL = 1  # seconds

async def main():
    print(BANNER)

    log.info("[manager] Creating sandbox...")
    sandbox = await SandboxInstance.create_if_not_exists({
        "name": "manager-sandbox-1",
        "image": "blaxel/base-image:latest",
        "memory": 4096,
        "region": "us-was-1"
    })
    log.info("[manager] Sandbox ready: %s", "manager-sandbox")

    log.info("[manager] Mounting drive my-drive at /shared...")
    await sandbox.drives.mount(
        drive_name="my-drive",
        mount_path="/shared",
    )

    # Poll for ANALYSIS.md
    log.info("[poll] Waiting for analyst to write %s...", POLL_FILE)
    start = time.monotonic()
    while True:
        try:
            content = await sandbox.fs.read(POLL_FILE)
            if content:
                elapsed = int(time.monotonic() - start)
                log.info("[poll] ANALYSIS.md found after %ds. Starting manager agent.", elapsed)
                break
        except Exception:
            pass
        elapsed = int(time.monotonic() - start)
        log.info("[poll] Waiting for ANALYSIS.md... (%ds elapsed)", elapsed)
        await asyncio.sleep(POLL_INTERVAL)

    log.info("[manager] Connecting to MCP toolset...")
    toolset = McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=sandbox.metadata.url + "/mcp",
            headers=settings.headers,
        )
    )
    tools = await toolset.get_tools()
    log.info("[manager] MCP tools loaded: %d tool(s) available.", len(tools))

    model = "openai/gpt-4o"
    log.info("[manager] Configuring manager agent (model: %s)...", model)

    manager_agent = LlmAgent(
        name="manager",
        model=model,
        instruction=(
            "Read the file /shared/ANALYSIS.md. "
            "Consolidate any duplicate or similar issues into a single task. "
            "Create a deduplicated list of tasks for the developer team. "
            "Classify the tasks by priority: P0 (critical), P1 (high), P2 (medium/low). "
            "Write P0 tasks to /shared/P0_TASKS.md, P1 tasks to /shared/P1_TASKS.md, and P2 tasks to /shared/P2_TASKS.md. "
            "Each file must start with a one-line summary stating the priority level and total task count for that file."
        ),
        tools=tools,
        output_key="manager_report",
    )

    app = App(name="manager_app", root_agent=manager_agent)
    runner = InMemoryRunner(app=app)

    session = await runner.session_service.create_session(
        app_name="manager_app",
        user_id="user"
    )

    log.info("[manager] Reading /shared/ANALYSIS.md from drive...")
    log.info("[manager] Deduplicating and prioritizing tasks, writing P0/P1/P2 task files to drive...")

    async for _ in runner.run_async(
        user_id="user",
        session_id=session.id,
        new_message=types.Content(parts=[types.Part(text="Create the deduplicated, prioritized developer task list.")])
    ):
        pass

    log.info("[manager] Done. P0/P1/P2 task files written to drive.")

    p0_tasks = await sandbox.fs.read("/shared/P0_TASKS.md")
    p1_tasks = await sandbox.fs.read("/shared/P1_TASKS.md")
    p2_tasks = await sandbox.fs.read("/shared/P2_TASKS.md")

    log.info("[manager] Deleting sandbox...")
    await sandbox.delete()
    log.info("[manager] Sandbox deleted. Manager step complete.")

    def count_tasks(content):
        for line in content.splitlines():
            m = re.search(r'Total Tasks:\s*(\d+)', line)
            if m:
                return int(m.group(1))
        return sum(1 for line in content.splitlines() if re.match(r'^\d+\.', line))

    print("\n============================================================")
    print("  PIPELINE COMPLETE — Developer Task List")
    print("============================================================")
    print(f"  {'Priority':<12} {'Tasks':>6}  {'File'}")
    print(f"  {'-'*12} {'-'*6}  {'-'*20}")
    print(f"  {'P0 (critical)':<12} {count_tasks(p0_tasks):>6}  /shared/P0_TASKS.md")
    print(f"  {'P1 (high)':<12} {count_tasks(p1_tasks):>6}  /shared/P1_TASKS.md")
    print(f"  {'P2 (medium)':<12} {count_tasks(p2_tasks):>6}  /shared/P2_TASKS.md")
    print("============================================================\n")

asyncio.run(main())
