---
name: alert-policy
description: When and how to send an alert to the on-call team. Load it only when an event might need an alert.
---

# Alert policy

Send an alert with `send_alert` only for:

- A `reviewed` event of magnitude 7.0 or higher.
- An `automatic` event of magnitude 7.5 or higher (it may be revised, so say so in the message).

Do not alert for revisions, deletions, or feed problems; flag those instead.

The message must include the event id, magnitude, status, place, and time in UTC. One alert per event. Alerts need human approval; if the alert is queued instead of sent, say so in your summary and do not retry it.
