"use client";

/**
 * BuildCharacter — a simple, swappable CSS-only mascot for the build dashboard.
 *
 * Deliberately NOT Lottie yet (Week 10 Part 1): every pose is a plain CSS class
 * on `.mascot` (see globals.css, section "Build mascot"). To add or change a
 * pose, edit the POSES map here and the matching `.mascot--<pose>` rules — no
 * new dependencies, no animation runtime. This keeps it easy to iterate on
 * before deciding how elaborate the character should become.
 *
 * The pose follows the current pipeline stage:
 *   thinking    — BA + Architect (understanding / designing)
 *   typing      — Developer agents (writing the app)
 *   inspecting  — Code Review + QA (checking everything)
 *   launching   — DevOps (putting it online)
 *   celebrating — complete (live)
 */

export type Pose =
  | "thinking"
  | "typing"
  | "inspecting"
  | "launching"
  | "celebrating";

const CAPTIONS: Record<Pose, string> = {
  thinking: "Thinking it through…",
  typing: "Writing your app…",
  inspecting: "Checking every detail…",
  launching: "Putting it online…",
  celebrating: "All done!",
};

export function BuildCharacter({
  pose,
  caption,
}: {
  pose: Pose;
  caption?: string;
}) {
  return (
    <div className="mascotWrap">
      <div className={`mascot mascot--${pose}`} aria-hidden="true">
        {/* Thought dots (thinking) */}
        <div className="mascot__thought">
          <span />
          <span />
          <span />
        </div>
        {/* Confetti (celebrating) */}
        <div className="mascot__confetti">
          <i />
          <i />
          <i />
          <i />
          <i />
        </div>
        <div className="mascot__antenna" />
        <div className="mascot__head">
          <div className="mascot__eye mascot__eye--l" />
          <div className="mascot__eye mascot__eye--r" />
        </div>
        <div className="mascot__body">
          <div className="mascot__arm mascot__arm--l" />
          <div className="mascot__arm mascot__arm--r" />
          {/* Magnifier (inspecting) */}
          <div className="mascot__lens" />
          {/* Rocket flame (launching) */}
          <div className="mascot__flame" />
          {/* Keyboard (typing) */}
          <div className="mascot__keys">
            <i />
            <i />
            <i />
          </div>
        </div>
      </div>
      <div className="mascotCaption">{caption ?? CAPTIONS[pose]}</div>
    </div>
  );
}
