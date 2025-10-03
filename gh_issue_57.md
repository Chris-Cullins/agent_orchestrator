# GitHub Issue #57: Create systemd install scripts for some workflows

**State:** OPEN
**Created:** 2025-10-03T21:17:50Z
**Updated:** 2025-10-03T21:17:50Z

## Labels
- None

## Assignees
- None

## Milestone
None

## Description
Setup some basic bash install scripts for some systemd timers so a user can setup a workflow to run on a timer, or at certain times, etc. Here is more info from gpt-5 about how we'd set this up. Again, this issue is to setup a bash install script for the setup below, and make it where it takes a workflow*.yaml file as an arg to the bash script. But use the below information as a general idea of what we're talking about. 


Option A — systemd user timers (best for desktops/laptops)
1) Put your script somewhere sane
mkdir -p ~/bin
nano ~/bin/wiki_full.sh
chmod +x ~/bin/wiki_full.sh

#!/usr/bin/env bash
set -euo pipefail
# …your workflow…

2) Create a service unit

~/.config/systemd/user/wiki-full.service

[Unit]
Description=Run wiki full build

[Service]
Type=oneshot
WorkingDirectory=%h/projects/repo
# Prevent overlap if a run is still going:
ExecStart=/usr/bin/flock -n %t/wiki-full.lock %h/bin/wiki_full.sh
# (optional) Bounds & niceness
TimeoutStartSec=1h
Nice=10

3) Create a timer unit

~/.config/systemd/user/wiki-full.timer

[Unit]
Description=Run wiki full build daily at 02:00

[Timer]
OnCalendar=02:00            # runs daily at 02:00 (local time)
Persistent=true             # catch up after missed runs (sleep/off)
RandomizedDelaySec=10m      # spread start a bit
AccuracySec=1m

[Install]
WantedBy=timers.target

4) Enable it
systemctl --user daemon-reload
systemctl --user enable --now wiki-full.timer
systemctl --user list-timers --all
journalctl --user -u wiki-full.service -n 200 --no-pager


Want intervals instead of a time of day? Use an interval timer:
~/.config/systemd/user/wiki-delta.timer

[Timer]
OnBootSec=5m
OnUnitActiveSec=15m   # run every 15 minutes after each completion
Persistent=true


(Bind it to wiki-delta.service the same way.)

Run when not logged in:

loginctl enable-linger "$USER"


---

_Planning completed by dev_architect on 2025-10-03T21:26:35Z (UTC)._
