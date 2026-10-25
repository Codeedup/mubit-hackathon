# Robo Medic — two-minute product video brief

Use this brief with the Remotion Skills in this project. Create a polished 16:9, 1920×1080, 30 fps video that runs about two minutes. The result is a short project demo, not a promise of an adapter improvement that did not happen.

## Story and timing

| Time | Beat | Picture / on-screen text |
| --- | --- | --- |
| 0:00–0:10 | The problem | Title: “ROBO MEDIC”. A robot fault needs a useful diagnosis, not another opaque alert. |
| 0:10–0:30 | The input | Show the real app incident view. Label the example accurately as synthetic, measured, or operator-observed. Bring the incident readings into focus. |
| 0:30–0:55 | The diagnosis | Show the actual diagnosis screen: likely cause, evidence, alternative, next check, uncertainty. Do not invent interface features or results. |
| 0:55–1:12 | Human verification | Show the technician outcome/feedback flow. Explain that the technician records the verified cause and repair. |
| 1:12–1:35 | Hardware cutaway | Use the team's real N20 motor and servo clip if supplied. Treat it as a tabletop demonstration and only claim the measurements the board actually captures. |
| 1:35–1:52 | Mubit status | Show the dated dashboard and task captures. Requests were recorded, but the task was still reviewing examples and had not reached the 25-example first-training threshold. Keep the wording neutral. |
| 1:52–2:00 | Close | “Robo Medic: evidence-based diagnosis, technician feedback, and a learning loop ready to continue.” Add a small caption: “Any adapter benefit still needs to be tested.” |

## Narration draft

“Robot faults are often ambiguous. Robo Medic is designed to help a technician turn a fault report into a practical next step.

Here, the incident includes [accurately name the readings and source]. Robo Medic presents a likely cause, the evidence behind it, an alternative explanation, and a next check. The technician can then record what inspection confirmed and what repair was performed.

Our tabletop rig gives the project a physical example. This clip shows [describe only what the footage actually shows]. The software workflow is designed to accept incident information from synthetic cases or real observations, with each source labelled.

We built the Mubit path because repeated diagnosis is the kind of task that could benefit from adaptation. The console recorded requests, but review had not reached the first training threshold within the event window. An adapter was not ready for this demo. Once training can complete, we hope to test whether the adapter makes future triage more useful; we have not measured a benefit yet.

Robo Medic demonstrates the diagnosis and technician feedback workflow, with adapter learning as the next step once the service is available.”

Replace bracketed text with what is actually visible in the recorded app and hardware clips. Keep spoken delivery conversational and leave a little breathing room between sections.

## Accuracy rules

- Never fabricate telemetry, diagnosis results, Mubit status, request IDs, adapter versions, or evaluation improvements.
- Clearly label synthetic data. Distinguish a planned workflow from a feature that is implemented and shown.
- Only say a Mubit request succeeded when the console/backend evidence supports it. Say adapter creation or improvement was not verified.
- The hardware footage is supporting evidence of the physical tabletop demo. Do not imply that the LLM controls the motors or that an unmeasured sensor was read.
- Do not infer an outage from task progress screenshots. State the observed review and adapter status plainly and briefly.

## Edit direction

- Use the app and real tabletop footage as the main visuals; use motion graphics for labels, transitions, and evidence callouts.
- Keep captions readable on a phone, use high contrast, and avoid tiny console text. Crop or zoom into evidence rather than showing a full desktop at once.
- Use restrained technical styling: dark navy background, warm white text, teal for confirmed evidence, amber for uncertainty, and red only for fault indicators.
- Avoid stock footage that could be mistaken for the team's robot or test setup.
- Leave the hardware segment as a replaceable clip. The app section should still make sense if the hardware clip is removed.

## When footage is ready

1. Put the app recording, hardware clip, and any approved Mubit evidence image/video under `public/assets/`.
2. Tell Codex: “Use `/remotion-create` and follow `VIDEO_BRIEF.md`. Inspect the assets in `public/assets/`, assemble the two-minute Robo Medic video, add readable captions, and keep the hardware clip replaceable. Do not invent any facts or status.”
3. Preview with `npm run dev`; render the final MP4 with `npx remotion render <composition-id> out/robo-medic-demo.mp4`.
