**Title:** Player timecode always starts at 00:00:00:00 instead of the file's embedded start timecode

**What happens**

In timecode mode, the review player labels the first frame of every video `00:00:00:00`. The same applies to the scrub/hover tooltip, the timeline comment-marker tooltip, the attached-timecode chip in the comment box, and the audio player.

Most delivery masters and review renders carry their own start timecode in the container (`timecode` tag on the format or video stream). A common post convention is a 5-second slate/pre-roll before the program, so the file starts at `00:59:55:00` and the program starts at `01:00:00:00`. Slateless masters usually start at `01:00:00:00`.

So a reviewer's note "at 00:00:12:00" lands on a frame the editor's NLE calls `01:00:07:00` (slated render) or `01:00:12:00` (slateless master). Reviewers and editors end up converting by hand, and they get it wrong.

The marker export (EDL) has the same root cause. It assumes `01:00:00:00` unless `?start_tc=` is passed, and the web UI never passes it.

**Expected**

Frame 0 in the player should read as the file's embedded start timecode, the frame number an NLE shows for that same frame. If the file has no timecode tag, keep counting from `00:00:00:00` as now.

**Suggested approach** (we've built this in a fork and can send a PR)

- API: read the start TC once per version with `ffprobe -show_entries format_tags=timecode:stream_tags=timecode` against the original upload (header only, no decode). Cache it per version, including a "no timecode" result so it isn't probed again. Expose it as `GET /assets/{id}/versions/{vid}/source-tc` and as a share-link equivalent that follows the same version-visibility rules as the share stream endpoint. Response: `{start_tc, fps, start_frames}`, with `start_frames` computed using SMPTE drop-frame math when the separator is `;`.
- Web: hold `{startFrames, fps}` for the current version in the review store. Format displayed timecode as `startFrames + floor(seconds * fps)` in the nominal base (24/25/30/60). Stored comment times stay seconds-from-0, so this changes display only, with no migration.
- The EDL export should default to the same probed start TC when `start_tc` isn't given.

**Notes / open points**

- Drop-frame sources: the client-side label can use non-drop arithmetic for simplicity, which drifts a few frames over long 29.97 DF clips. Exact DF labelling in the client is a possible follow-up.
- Compare view: a pane showing a non-current version would need its own start TC. Counting from 0 there is an acceptable first step.
