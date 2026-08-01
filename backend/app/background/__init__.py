"""Week 9 post-launch background agents.

Three agents that run silently after deployment; the user sees them only through
the post-launch dashboard:

  * monitor.py       — Monitoring (#13): ping the live app, record health /
                       response time / errors, and write a plain-English weekly
                       summary from the REAL logs.
  * autofix.py       — Auto-fix (#14): on a detected problem, snapshot first
                       (Safe Mode), then self-heal by REUSING the DevOps restart
                       primitive; notify or escalate honestly; roll back if worse.
  * cost_tracker.py  — Cost Tracker (#15): daily actual + projected cost vs the
                       user's budget, with a budget alert. Real AWS Cost Explorer
                       is gated off by default; the math is proven synthetically.
  * dashboard.py     — aggregates the four post-launch dashboard sections.

Like every agent in this project they are deterministic-first and never fabricate
a number: metrics/costs come from stored data, and a missing source reads as "not
available yet".
"""
