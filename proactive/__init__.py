"""
Proactive Agent — ClawOS background intelligence layer.
Monitors services, creates scheduled tasks from natural language,
and surfaces alerts when conditions are met.
"""
from proactive.background_loop import ProactiveBackgroundLoop
from proactive.scheduler_agent import SchedulerAgent
from proactive.app_monitor import AppMonitor

__all__ = ["ProactiveBackgroundLoop", "SchedulerAgent", "AppMonitor"]
