# Archived hackathon demo video (Remotion)

This video records the October 2026 prototype. It is historical material and
does not depict the current 1.0 interface, current Mubit task state, or newly
implemented management feedback. See the root README for the current app.

This is a standalone Remotion project with a rendered 120-second, 1920×1080, 30 fps demo at [`out/robo-medic-demo.mp4`](out/robo-medic-demo.mp4). It follows `VIDEO_BRIEF.md` and keeps the app, hardware, and Mubit evidence slots replaceable.

The current video uses captures from the real app running in **offline rule fixture** mode, a reconstruction of the documented 24 October synthetic simulator outcome, an illustration for the tabletop rig, two dated Mubit console screenshots, and a generated draft narration. It does not present the fixture result as Mubit inference or claim adapter improvement.

The Mubit dashboard capture at 14:33 shows four requests and zero adapters serving; it also shows zero request errors and says first training starts at 25 examples. The task capture at 23:30 shows the intended task still reviewing examples, at 12 of 25, with no adapter serving. These are snapshots of the unfinished review process, not proof of a server outage. An adapter was not ready for the demo. We hope to test whether a trained adapter makes future triage more useful once it is available; no benefit is claimed yet.

## Start Remotion Studio

```bash
npm ci
npm run dev
```

## Source and verification

The editable composition is in `src/RoboMedicDemo.tsx`. `npm run build` verifies
the Remotion bundle. Generated bundles are ignored. Vendored agent-skill caches
are not part of this repository; install the tools you use separately.

[`VIDEO_BRIEF.md`](VIDEO_BRIEF.md) preserves the original event brief. If you
revise the video, replace its app captures and narration and verify every
current integration claim against the actual service state.

## Add footage

To replace the current captures, put the real app recordings, hardware clip, and approved Mubit evidence in [`public/assets/`](public/assets/). See the filename list in [`public/assets/README.md`](public/assets/README.md). Keep original source recordings.

The composition is `RoboMedicDemo`. Once footage is added, review each scene in Studio, trim or split clips to fit the scene boundaries, crop into small app and console details, and revise the on-screen text to match the recordings. A timed `narration.mp3` replaces the generated draft narration.

## Render

Preview in Remotion Studio first. Render the selected composition to MP4 with:

```bash
npx remotion render RoboMedicDemo out/robo-medic-demo.mp4
```

The final MP4 in `out/` is tracked in Git; intermediate previews and render files are ignored. For final assembly with a quick hardware clip, either include the footage directly in Remotion or export this video and combine it in your preferred editor.
