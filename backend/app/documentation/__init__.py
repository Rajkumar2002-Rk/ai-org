"""Documentation agent (Week 8, agent #12).

Generates four documents for a project — a plain-English user guide, a demo
recording script, a maintenance guide, and a one-page handoff summary — from REAL
stored data only. It is strictly READ-ONLY over the rest of the system: it never
modifies code, security certificates, or deployment state, and it writes ONLY to
the `documents` table.

The governing rule (this project's standing principle): it never generates a
plausible-sounding number or status. Every fact traces to a real row; a missing
source reads as "not available yet", never an invented value. The set of features
and screens it describes comes from the project's OWN blueprint + generated files,
so it can only ever describe things that actually exist.
"""
