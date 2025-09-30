
import argparse, json, os, subprocess, time, uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
import yaml
from datetime import datetime

REPORTS_DIR = ".agents/run_reports"

@dataclass
class Step:
    id: str
    agent: str
    prompt: str
    needs: List[str] = field(default_factory=list)
    next_on_success: List[str] = field(default_factory=list)
    gates: List[str] = field(default_factory=list)
    human_in_the_loop: bool = False

@dataclass
class StepRuntime:
    status: str = "PENDING"  # PENDING | RUNNING | COMPLETED | FAILED | SKIPPED
    attempts: int = 0
    report_path: Optional[str] = None

class Orchestrator:
    def __init__(self, repo_dir: str, workflow_path: str):
        self.repo_dir = os.path.abspath(repo_dir)
        self.workflow = self._load_workflow(workflow_path)
        self.run_id = str(uuid.uuid4())[:8]
        self.state: Dict[str, StepRuntime] = {s.id: StepRuntime() for s in self.workflow["steps"]}
        os.makedirs(os.path.join(self.repo_dir, REPORTS_DIR), exist_ok=True)
        print(f"[orchestrator] run_id={self.run_id} repo={self.repo_dir}")

    def _load_workflow(self, path: str) -> Dict:
        with open(path, "r", encoding="utf-8") as f:
            wf = yaml.safe_load(f)
        steps: List[Step] = []
        for s in wf.get("steps", []):
            steps.append(Step(
                id=s["id"],
                agent=s["agent"],
                prompt=s["prompt"],
                needs=s.get("needs", []),
                next_on_success=s.get("next_on_success", []),
                gates=s.get("gates", []),
                human_in_the_loop=s.get("human_in_the_loop", False),
            ))
        wf["steps"] = steps
        self.step_index: Dict[str, Step] = {s.id: s for s in steps}
        return wf

    def _deps_satisfied(self, step_id: str) -> bool:
        deps = self.step_index[step_id].needs
        return all(self.state[d].status == "COMPLETED" for d in deps)

    def _gates_open(self, step_id: str) -> bool:
        # Placeholder: always open in PoC. Wire to CI/PR checks later.
        return True

    def _runnable_steps(self) -> List[str]:
        runnable = []
        for s in self.workflow["steps"]:
            st = self.state[s.id].status
            if st == "PENDING" and self._deps_satisfied(s.id) and self._gates_open(s.id):
                runnable.append(s.id)
        return runnable

    def _launch(self, step_id: str):
        step = self.step_index[step_id]
        self.state[step_id].status = "RUNNING"
        self.state[step_id].attempts += 1
        report_path = os.path.join(self.repo_dir, REPORTS_DIR, f"{self.run_id}__{step_id}.json")
        self.state[step_id].report_path = report_path

        wrapper = os.path.join(os.path.dirname(__file__), "scripts", "codex_exec_wrapper.py")
        prompt_path = os.path.join(os.path.dirname(__file__), step.prompt)
        cmd = [
            "python", wrapper,
            "--run-id", self.run_id,
            "--step-id", step_id,
            "--agent", step.agent,
            "--prompt", prompt_path,
            "--repo", self.repo_dir,
            "--report", report_path,
        ]
        print(f"[orchestrator] launching step={step_id} agent={step.agent}")
        subprocess.Popen(cmd)  # fire and forget; the wrapper writes the report file

    def _collect_reports(self) -> None:
        # Any new/updated reports?
        for s in self.workflow["steps"]:
            st = self.state[s.id]
            if st.status != "RUNNING":
                continue
            if st.report_path and os.path.exists(st.report_path):
                try:
                    with open(st.report_path, "r", encoding="utf-8") as f:
                        report = json.load(f)
                    status = report.get("status", "").upper()
                    if status in {"COMPLETED", "FAILED"}:
                        st.status = status
                        print(f"[orchestrator] step={s.id} finished status={status}")
                        if status == "FAILED" and st.attempts < 2:
                            print(f"[orchestrator] retrying step={s.id} attempt={st.attempts+1}")
                            st.status = "PENDING"  # queue for retry
                except Exception as e:
                    print(f"[orchestrator] failed reading report for step={s.id}: {e}")

    def run(self):
        # Seed initial runnable steps (no dependencies)
        print("[orchestrator] starting workflow")
        while True:
            # Launch any runnable steps
            for step_id in self._runnable_steps():
                self._launch(step_id)

            # Collect run reports and update state
            self._collect_reports()

            # Fan-out: schedule downstream of completed steps
            progressed = False
            for s in self.workflow["steps"]:
                if self.state[s.id].status == "COMPLETED":
                    for nxt in s.next_on_success:
                        if self.state[nxt].status == "PENDING" and self._deps_satisfied(nxt):
                            # Will be picked up next loop as runnable
                            progressed = True

            # Check for done
            if all(self.state[s.id].status in {"COMPLETED", "SKIPPED"} for s in self.workflow["steps"]):
                print("[orchestrator] workflow completed")
                break

            # If nothing is running or pending, and nothing progressed, prevent a tight loop
            time.sleep(0.5)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="Path to local repo (working tree)")
    ap.add_argument("--workflow", default="workflow.yaml", help="Workflow YAML path")
    args = ap.parse_args()

    orch = Orchestrator(args.repo, args.workflow)
    orch.run()

if __name__ == "__main__":
    main()
