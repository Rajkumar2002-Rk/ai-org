# Safety & Prohibited-Use Policy — BA Agent Guardrail

This is the source-of-truth for what the platform will and will not build.
The BA Agent screens the user's idea **and every free-text answer**, plus a
final re-screen of the confirmed summary, before anything is locked in.

## Why this exists
A public "describe any app" box is an open door. Without a guardrail, users
could try to commission illegal or harmful software, which creates legal,
financial, and reputational risk for the platform. Security is the platform's
stated #1 principle, so this gate runs at the very first stage (the BA) — the
only agent that talks to users.

## Screening approach (defense in depth)
1. **OpenAI Moderation API** — hard categories (sexual content, minors,
   violence, self-harm). Free and purpose-built; safe to call on every input.
2. **LLM policy classifier (GPT-4o mini, temp 0)** — nuanced, category-aware
   judgement against the policy below. Crucially, it *allows* legitimate ideas
   that merely mention a sensitive topic (e.g. "an app to help people quit
   gambling", "a phishing-awareness training tool").
3. **Keyword fallback** — deterministic regex so the guardrail still works
   with no LLM configured (mock mode).

Decision rule: a hard moderation flag (minors/sexual) blocks outright; the
classifier is the primary authority for everything else; keyword hits block
when no classifier is available.

## Prohibited categories

### 1. Gambling & betting (real money)
Sportsbooks, casinos, betting apps, lotteries, real-money poker/slots.
*Allowed:* play-money games, gambling-addiction help, age-gated fantasy stats
with no wagering.

### 2. Synthetic media abuse
Deepfakes, face-swapping, voice cloning to deceive, "nudify"/undress apps,
non-consensual intimate imagery, impersonation to defraud.

### 3. Child safety (zero tolerance)
Any sexual content involving minors. Never built, no exceptions.

### 4. Illegal goods & services
Drug marketplaces, weapons/firearms/explosives sales or manufacture,
endangered wildlife, stolen goods, fake IDs/documents, human trafficking.

### 5. Fraud, scams & deception
Phishing kits, carding, counterfeit goods, money laundering, fake-review
generators, pyramid/Ponzi schemes, pump-and-dump, fake-charity scams,
academic-cheating/essay-mill services.

### 6. Malware & unauthorized access
Ransomware, keyloggers, botnets, DDoS tools, credential stuffing,
account-takeover tooling, exploit kits, software to hack/bypass security.

### 7. Surveillance & privacy violations
Stalkerware, secretly tracking a person, covert recording, doxxing,
scraping/selling personal data without consent, mass-surveillance of
individuals.

### 8. Violence & extremism
Terrorism, violent extremist content/recruitment, instructions for weapons or
attacks, incitement to violence.

### 9. Self-harm
Apps that promote, encourage, or facilitate suicide, self-harm, or eating
disorders. *Allowed:* mental-health support and crisis-resource apps.

### 10. Hate & harassment
Platforms whose purpose is harassment, bullying, or hateful targeting of
people based on protected characteristics.

### 11. Spam & platform abuse
Bulk unsolicited messaging tools, engagement/follower fraud, CAPTCHA-solving
for abuse, large-scale disinformation/coordinated-inauthentic-behavior tools.

## Regulated-but-allowed (build with care, do not auto-block)
Legitimate fintech/lending, crypto, healthcare, alcohol/cannabis (where
legal), and dating apps are **allowed** — these are normal businesses. They
may carry compliance requirements that later agents surface, but the BA does
not reject them.

## User experience on a block
- BA declines in plain English, no technical words, no lecturing.
- Project is marked `rejected`; nothing is built.
- The block is terminal for that conversation — the user starts over with a
  new idea. Follow-up messages cannot talk past the block.

## Known limitation / future hardening
This gate screens the idea, every free-text answer, and the final summary.
A determined user could still phrase intent very obliquely. Future passes
should add: per-account abuse-rate limiting, logging of blocked attempts for
review, and a human-review queue for edge cases.
