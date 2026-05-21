from pathlib import Path
from praisonaiagents import Agent

ROOT = Path(__file__).resolve().parent
plan = (ROOT / 'PLAN_技术指标Dashboard.md').read_text(encoding='utf-8')
handoff = (ROOT / 'references' / '任务交接指南.md').read_text(encoding='utf-8')

prompt = f"""
You are an autonomous senior full-stack developer. Build a complete local project for a Crypto Technical Indicators Dashboard according to the provided Chinese implementation plan and handoff guide.

Hard requirements:
- Create/modify files only under {ROOT / 'crypto-tech-dashboard'}.
- Produce FastAPI backend, native JS frontend, local CSV data cache, indicators, scoring, tests, README, .env.example, run.sh, and zip-ready structure.
- Preserve formulas and architecture from the plan.
- Record progress in {ROOT / 'PROGRESS.md'}.
- If the referenced notebook is missing, implement from the formulas embedded in the plan and explicitly note the limitation.

HANDOFF GUIDE:
{handoff[:12000]}

CORE PLAN:
{plan[:24000]}
"""

agent = Agent(
    instructions="You are a careful autonomous software engineer. Implement production-quality code, tests, and documentation.",
    name="crypto-dashboard-builder",
)
agent.start(prompt)
