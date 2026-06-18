"""Deploy run_all_routes flow to Prefect server.

Usage:
    PREFECT_API_URL=http://localhost:4200/api python scheduler/deploy.py

POLL_INTERVAL_MINUTES env var sets the cron schedule (default: 60).
"""
import os
from dotenv import load_dotenv

from scheduler.flow import run_all_routes

load_dotenv()


def main():
    poll_interval = int(os.getenv("POLL_INTERVAL_MINUTES", "60"))
    cron = f"*/{poll_interval} * * * *"

    run_all_routes.deploy(
        name="flight-monitor-schedule",
        work_pool_name="default-agent-pool",
        cron=cron,
        tags=["flight-monitor"],
        description=f"Runs all enabled routes every {poll_interval} minutes",
    )
    print(f"Deployed 'run-all-routes' with cron='{cron}'")


if __name__ == "__main__":
    main()
