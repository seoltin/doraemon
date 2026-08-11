import asyncio
import os
from pathlib import Path
from .config import settings

class AgentExecutor:
    def __init__(self):
        self.binary = settings.agent_binary
        self.work_dir = Path(settings.agent_work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    async def run(self, prompt: str) -> str:
        if not prompt or len(prompt.strip()) == 0:
            return "(empty message, nothing to execute)"

        if self.binary.endswith("echo"):
            cmd = [
                self.binary,
                f"[Doraemon-MVP]\nReceived your instruction: {prompt}\nI'm still learning, waiting for Codex installation!"
            ]
        else:
            cmd = [
                self.binary,
                "query",
                "-p", prompt
            ]

        print(f"\n[Agent] Start Executing...")
        print(f"[Agent] CMD: {' '.join(cmd)}")
        print(f"[Agent] CWD: {self.work_dir.resolve()}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.work_dir.resolve()),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=os.environ.copy()
            )

            stdout_data, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=600
            )

            output = stdout_data.decode("utf-8", errors="ignore").strip()

            if process.returncode != 0:
                return f"[Agent Error] Exit Code: {process.returncode}\n{output}"

            print(f"[Agent] Done. Output Len: {len(output)}")
            return output if output else "(Agent produced no output)"

        except asyncio.TimeoutError:
            if process and process.returncode is None:
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
            return "[Agent Timeout] Task exceeded 10 minutes, auto-terminated."
        except FileNotFoundError:
            return f"[Agent Startup Failed] Binary not found: '{self.binary}'. Check .env AGENT_BINARY path."
        except Exception as e:
            return f"[Agent System Error] {type(e).__name__}: {str(e)}"

agent_executor = AgentExecutor()
