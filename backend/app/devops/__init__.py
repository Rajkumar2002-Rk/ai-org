"""DevOps agent (Week 7, agent #11).

Takes a project that has passed QA + the Opus security review and deploys its
generated code — silently. It never talks to the user; the API layer exposes a
live URL and status only.

The whole agent is built on two structural guarantees taken from this project's
standing principle ("absence of evidence is not evidence of success"):

* **Per-user isolation is enforced by construction, not intention.** Every
  resource name is a pure function of `project_id` (see `naming.py`); there is no
  code path that mixes two projects' containers, networks, or databases.
* **A deployment can never ship code the security review never saw.** The
  orchestrator re-checks certificate drift at deploy time and fails closed.
"""
