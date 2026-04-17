import asyncio
import os
import logging
import uuid
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request
from github import Github, Auth
from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.genai import types
from blaxel.core import SandboxInstance, DriveInstance
import uvicorn

from prompts import (
    SECURITY_REVIEWER_INSTRUCTION,
    CODE_REVIEWER_INSTRUCTION,
    TEST_REVIEWER_INSTRUCTION,
    DEVELOPER_INSTRUCTION,
    TRIGGER_MESSAGE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

host = os.getenv("HOST", "0.0.0.0")
port = int(os.getenv("PORT", "8000"))

BOT_COMMENT_MARKER = "<!-- AI_REVIEW_COMMENT -->"
MODEL = "anthropic/claude-sonnet-4-5-20250929"
SANDBOX_IMAGE = "sandbox/review-swarm-sandbox:latest"
SHARED_MOUNT_PATH = "/shared"

app = FastAPI()


async def setup_sandbox(
    role: str,
    job_id: str,
    drive_name: str,
    repository: str,
    pr_number: int,
    github_token: str,
    api_key: str,
) -> tuple:
    project = repository.split("/")[-1]
    sandbox_name = f"{role}-sandbox-{job_id}"
    logger.info(f"Creating sandbox: {sandbox_name}")

    sandbox = await SandboxInstance.create_if_not_exists({
        "name": sandbox_name,
        "image": SANDBOX_IMAGE,
        "memory": 4096,
        "region": "us-was-1",
    })
    await sandbox.drives.mount(
        drive_name=drive_name,
        mount_path=SHARED_MOUNT_PATH,
        drive_path="/",
    )
    logger.info(f"Sandbox ready: {sandbox_name}")

    await sandbox.process.exec({
        "name": f"{role}-clone",
        "command": f"git clone https://{github_token}@github.com/{repository}.git /root/{project}",
        "wait_for_completion": True,
        "timeout": 120000,
    })
    await sandbox.process.exec({
        "name": f"{role}-fetch",
        "working_dir": f"/root/{project}",
        "command": f"git fetch origin pull/{pr_number}/head:pr-{pr_number}",
        "wait_for_completion": True,
        "timeout": 120000,
    })
    await sandbox.process.exec({
        "name": f"{role}-checkout",
        "working_dir": f"/root/{project}",
        "command": f"git checkout pr-{pr_number}",
        "wait_for_completion": True,
        "timeout": 120000,
    })
    logger.info(f"Repository ready in sandbox: {sandbox_name}")

    toolset = McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=sandbox.metadata.url + "/mcp",
            headers={"Authorization": f"Bearer {api_key}"},
        ),
    )
    await toolset.get_tools()
    logger.info(f"MCP toolset ready for: {sandbox_name}")

    return sandbox, toolset


@app.post("/review")
async def review_endpoint(request: Request):
    body = await request.json()
    logger.info(f"Received review request: {body}")

    repository = body.get("repository")
    pr_number = body.get("pr_number")
    open_pr = body.get("open_pr", True)
    api_key = os.getenv("BLAXEL_API_KEY")
    github_token = os.getenv("GITHUB_TOKEN")

    if not repository:
        raise HTTPException(status_code=400, detail="repository is required")
    if "/" not in repository:
        raise HTTPException(status_code=400, detail="repository must be owner/name")
    if pr_number is None:
        raise HTTPException(status_code=400, detail="pr_number is required")
    try:
        pr_number = int(pr_number)
    except ValueError:
        raise HTTPException(status_code=400, detail="pr_number must be an integer")
    if not api_key:
        raise HTTPException(status_code=400, detail="BLAXEL_API_KEY env var is required")
    if not github_token:
        raise HTTPException(status_code=400, detail="GITHUB_TOKEN env var is required")

    project = repository.split("/")[-1]
    job_id = uuid.uuid4().hex[:12]
    drive_name = f"review-drive-{job_id}"

    logger.info(f"Starting review job {job_id} for {repository} PR #{pr_number}")

    auth = Auth.Token(github_token)
    g = Github(auth=auth)
    repo = g.get_repo(repository)
    pr = repo.get_pull(pr_number)
    base_branch = pr.base.ref
    pr_title = pr.title
    logger.info(f"PR: {pr_title!r}, base branch: {base_branch}")

    drive = None
    sandboxes = []
    toolsets = []

    try:
        logger.info(f"Creating shared drive: {drive_name}")
        drive = await DriveInstance.create_if_not_exists({
            "name": drive_name,
            "region": "us-was-1",
        })
        logger.info(f"Drive ready: {drive_name}")

        logger.info("Creating all sandboxes in parallel")
        results = await asyncio.gather(
            setup_sandbox("security-reviewer", job_id, drive_name, repository, pr_number, github_token, api_key),
            setup_sandbox("code-reviewer", job_id, drive_name, repository, pr_number, github_token, api_key),
            setup_sandbox("test-reviewer", job_id, drive_name, repository, pr_number, github_token, api_key),
            setup_sandbox("developer", job_id, drive_name, repository, pr_number, github_token, api_key),
        )
        security_review_sandbox, sec_review_toolset = results[0]
        code_review_sandbox, code_review_toolset = results[1]
        test_review_sandbox, test_review_toolset = results[2]
        dev_sandbox, dev_toolset = results[3]
        sandboxes = [security_review_sandbox, code_review_sandbox, test_review_sandbox, dev_sandbox]
        toolsets = [sec_review_toolset, code_review_toolset, test_review_toolset, dev_toolset]
        logger.info("All sandboxes and toolsets ready")

        security_agent = LlmAgent(
            name="security_reviewer",
            model=MODEL,
            instruction=SECURITY_REVIEWER_INSTRUCTION.format(
                project=project,
                base_branch=base_branch,
            ),
            tools=[sec_review_toolset],
            output_key="security_summary",
        )
        code_agent = LlmAgent(
            name="code_reviewer",
            model=MODEL,
            instruction=CODE_REVIEWER_INSTRUCTION.format(
                project=project,
                base_branch=base_branch,
            ),
            tools=[code_review_toolset],
            output_key="code_summary",
        )
        test_agent = LlmAgent(
            name="test_reviewer",
            model=MODEL,
            instruction=TEST_REVIEWER_INSTRUCTION.format(
                project=project,
                base_branch=base_branch,
            ),
            tools=[test_review_toolset],
            output_key="test_summary",
        )
        developer_agent = LlmAgent(
            name="developer",
            model=MODEL,
            instruction=DEVELOPER_INSTRUCTION.format(project=project),
            tools=[dev_toolset],
            output_key="developer_summary",
        )

        parallel_reviewers = ParallelAgent(
            name="parallel_reviewers",
            sub_agents=[security_agent, code_agent, test_agent],
        )
        pipeline = SequentialAgent(
            name="review_pipeline",
            sub_agents=[parallel_reviewers, developer_agent],
        )

        adk_app = App(name="review_app", root_agent=pipeline)
        runner = InMemoryRunner(app=adk_app)
        session = await runner.session_service.create_session(
            app_name="review_app",
            user_id="user",
        )

        trigger = types.Content(
            role="user",
            parts=[types.Part(text=TRIGGER_MESSAGE.format(
                pr_number=pr_number,
                pr_title=pr_title,
                repository=repository,
                base_branch=base_branch,
                project=project,
            ))],
        )

        logger.info("Running review pipeline (parallel reviewers + developer)")
        async for event in runner.run_async(
            user_id="user",
            session_id=session.id,
            new_message=trigger,
        ):
            if event.author and event.is_final_response():
                logger.info(f"Agent {event.author!r} completed")

        final_session = await runner.session_service.get_session(
            app_name="review_app",
            user_id="user",
            session_id=session.id,
        )
        state = final_session.state if final_session else {}
        security_summary = state.get("security_summary", "Review not available")
        code_summary = state.get("code_summary", "Review not available")
        test_summary = state.get("test_summary", "Review not available")
        developer_summary = state.get("developer_summary", "No developer actions recorded")
        logger.info("Pipeline complete")

        fix_pr = None
        if open_pr:
            fix_branch = f"review-fix/pr-{pr_number}-{job_id[:8]}"
            logger.info(f"Committing and pushing fix branch: {fix_branch}")

            await dev_sandbox.process.exec({
                "name": "git-config-email",
                "working_dir": f"/root/{project}",
                "command": 'git config user.email "review-swarm@example.com"',
                "wait_for_completion": True,
                "timeout": 30000,
            })
            await dev_sandbox.process.exec({
                "name": "git-config-name",
                "working_dir": f"/root/{project}",
                "command": 'git config user.name "ReviewSwarm"',
                "wait_for_completion": True,
                "timeout": 30000,
            })
            await dev_sandbox.process.exec({
                "name": "git-checkout-fix",
                "working_dir": f"/root/{project}",
                "command": f"git checkout -B {fix_branch}",
                "wait_for_completion": True,
                "timeout": 30000,
            })
            await dev_sandbox.process.exec({
                "name": "git-add",
                "working_dir": f"/root/{project}",
                "command": "git add -A",
                "wait_for_completion": True,
                "timeout": 30000,
            })
            await dev_sandbox.process.exec({
                "name": "git-commit",
                "working_dir": f"/root/{project}",
                "command": f'git commit -m "review-fix: automated review fixes for PR #{pr_number}"',
                "wait_for_completion": True,
                "timeout": 30000,
            })
            await dev_sandbox.process.exec({
                "name": "git-push",
                "working_dir": f"/root/{project}",
                "command": f"git push --force https://{github_token}@github.com/{repository}.git {fix_branch}",
                "wait_for_completion": True,
                "timeout": 120000,
            })
            logger.info("Fix branch pushed")

            pr_body = (
                f"Automated review fixes for PR #{pr_number}.\n\n"
                f"**Developer actions:**\n\n{developer_summary}"
            )
            fix_pr = repo.create_pull(
                title=f"review-fix: automated review of PR #{pr_number}",
                body=pr_body,
                head=fix_branch,
                base=base_branch,
            )
            logger.info(f"Fix PR created: {fix_pr.html_url}")

        OUTDATED_MARKER = "> **This comment is outdated and has been superseded.**"
        for comment in pr.get_issue_comments():
            if BOT_COMMENT_MARKER in comment.body and OUTDATED_MARKER not in comment.body:
                logger.info(f"Marking previous comment {comment.id} as outdated")
                comment.edit(f"{OUTDATED_MARKER}\n\n{comment.body}")

        timestamp = datetime.now(timezone.utc).strftime("%d-%m-%Y %H:%M:%S UTC")
        fix_pr_section = f"\n**Fix PR:** {fix_pr.html_url}\n" if fix_pr else ""

        comment_text = (
            f"{BOT_COMMENT_MARKER}\n"
            f"## Automated Code Review — PR #{pr_number}\n\n"
            f"**Repository:** {repository} | **Reviewed at:** {timestamp}\n\n"
            f"---\n\n"
            f"### Security Review\n{security_summary}\n\n"
            f"### Code Quality Review\n{code_summary}\n\n"
            f"### Test Coverage Review\n{test_summary}\n\n"
            f"---\n\n"
            f"### Developer Actions\n\n{developer_summary}\n"
            f"{fix_pr_section}\n"
            f"---\n*Generated by review-swarm (job: {job_id})*"
        )

        comment = pr.create_issue_comment(comment_text)
        logger.info(f"Comment posted: {comment.html_url}")

        result = {
            "status": "success",
            "repository": repository,
            "pr_number": pr_number,
            "job_id": job_id,
            "comment_url": comment.html_url,
            "reviewer_summaries": {
                "security": security_summary,
                "code": code_summary,
                "test": test_summary,
            },
        }
        if fix_pr:
            result["fix_pr_url"] = fix_pr.html_url
        return result

    finally:
        logger.info("Cleaning up sandboxes and drive")
        for sandbox in sandboxes:
            await sandbox.delete()
        for toolset in toolsets:
            await toolset.close()
        if drive is not None:
            await drive.delete()
        logger.info("Cleanup complete")


if __name__ == "__main__":
    print(f"Server listening on {host}:{port}")
    uvicorn.run(app, host=host, port=port)

"""
curl -X POST "http://localhost:8000/review" \
  -H "Content-Type: application/json" \
  -d '{
    "repository": "owner/repo-name",
    "pr_number": 1
  }'
"""
