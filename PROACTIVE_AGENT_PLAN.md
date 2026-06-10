# ClawOS v2.1 — Proactive Agent + Approval Fix Plan

## Goal
Build 3 interconnected features:
1. Fix approval gate → executor resume (async/await)
2. Add `/yolo` slash command to bypass all approvals
3. Proactive background agent: cron automation, scheduled tasks, app monitoring

---

## Architecture

### Before (current)
```
main.py thread → run() → executor.execute() [BLOCKING]
                                      ↓
                              approval_request.emit() [blocks until UI responds]
                                      ↓
                              [UI shows dialog — waits indefinitely]
```

### After (target)
```
main.py thread → run() → executor.execute() [ASYNC/AWAIT]
                                      ↓
                              approval_request.emit() [non-blocking]
                                      ↓
                              executor._resume_event.wait() [pause, don't block UI]
                                      ↓
                              [UI shows dialog]
                                      ↓
                              [user approves/rejects]
                                      ↓
                              executor._resume_event.set() [resumes]
```

---

## Component Changes

### 1. streaming_executor.py — Async Refactor
- Change `execute()` from sync to async using `asyncio`
- Replace blocking `on_approval()` callback with `asyncio.Event` pause/resume
- Add `self._yolo_mode = False` — when True, auto-approve everything
- Add `_yolo()` method to enable yolo mode
- `_should_ask()` → check yolo flag first

### 2. clawos_ui.py — YOLO + Approval Wire
- Detect `/yolo` prefix in input → set `executor._yolo_mode = True`
- Strip `/yolo` from message before sending
- Approval dialog: use `QTimer.singleShot` to show on main thread
- After approval: set `executor._resume_event.set()` via signal
- Add "⚡ YOLO" indicator in UI when active

### 3. proactive/ directory — NEW
```
proactive/
  __init__.py
  scheduler_agent.py   # Reads natural language scheduling requests
  app_monitor.py      # Monitor URLs, files, processes, APIs
  alert_dispatcher.py # Send alerts when conditions trigger
  background_loop.py  # Persistent loop that runs when OS is active
```

### 4. cron_manager.py — Add proactive capabilities
- `create_from_natural_language(text)` → parses "every 5 minutes check X"
- `create_app_monitor(url, check_interval, alert_condition)` → URL/API monitor
- `create_process_watcher(process_name, on_down)` → process monitoring

### 5. main.py — Wire proactive agent
- Start background loop when app starts
- On voice orb activation → agent goes "proactive mode"
- During streaming → agent can call `schedule_task()` or `create_monitor()`

---

## File Changes Summary

| File | Change | Lines |
|------|--------|-------|
| agent/streaming_executor.py | Async refactor + yolo mode | ~50 new |
| clawos_ui.py | YOLO detection, approval resume signal | ~30 new |
| proactive/__init__.py | NEW | 10 |
| proactive/scheduler_agent.py | NEW — natural language → cron | 120 |
| proactive/app_monitor.py | NEW — URL/API/process monitor | 150 |
| proactive/alert_dispatcher.py | NEW — alert routing | 60 |
| proactive/background_loop.py | NEW — persistent loop | 80 |
| scheduler/cron_manager.py | Add proactive methods | ~50 new |
| main.py | Wire proactive agent | ~20 changed |

---

## Slash Commands (Phase 1)

| Command | Effect |
|---------|--------|
| `/yolo` | Skip all approvals for this session |
| `/cron <text>` | Create a cron job from natural language |
| `/monitor <text>` | Create a background monitor |
| `/status` | Show all active schedules/monitors |
| `/cancel <id>` | Cancel a scheduled task |

---

## Testing Checklist
- [ ] `/yolo` skips approval for shell command
- [ ] `/yolo` skips approval for python execution
- [ ] Regular approval flow still works (block → approve → resume)
- [ ] `/cron every 5 minutes check google.com` creates a monitor
- [ ] Background monitor fires and alerts correctly
- [ ] Voice orb proactive mode activates background agent
- [ ] No UI freezing during approval dialog
