# Video loading diagnosis

**Reproduced (cloud copy of the app; two extra videos made from the official clip in the git-ignored `media/Sample/`: H.264 720p and HEVC stream-copy, plus an unreadable file):**

- **Processing worked.** Both new videos registered and processed through the API (`POST /api/runs`): 240-frame proxies with correct time offsets. Nothing in the backend rejected them.
- **Root cause 1: discovery.** Videos added to `media/` while the app runs were never registered, because the launcher only registers at start-up and the viewer had no rescan.
- **Root cause 2: mismatch.** "Load run" loaded whatever was selected in the *run* list, independent of the *video* chosen for Process. In the team recording, `Sample/…-015.mp4` was selected while a run of `…-016.mp4` was loaded. Nothing tied the two together.
- **Also found:** a raw FFprobe command line as the error for an unreadable file; a deleted file still listed as usable; the backend upload endpoint had no button; and a server started before a code change keeps serving old routes (`--noreload`, fixed earlier by the launcher stopping old servers).

**Fixes:**
- **Scan.** `POST /api/videos/scan` registers new files in the media folders; registered files are not re-hashed. The viewer scans on load and on "↻ scan".
- **Video first.** The video selector comes first, the run list shows only that video's runs ("no completed runs for this video: Process it" when empty), and loading a run moves the selector to its video.
- **Upload.** "Upload…" button with a progress display, using the existing private upload folder.
- **Clear errors.** "not a readable video (FFprobe could not open it)"; "file missing" shown for moved or deleted files; the source duration ("180 s source") is shown separately from the run segment ("60–150 s").

**Path safety (unchanged):** only files under `EGOHAND_MEDIA_ROOTS` or the upload folder can be registered; `..` escapes are refused (403).

**Tests:** `backend/api/tests/test_multi_video.py` covers two distinct MP4 files, discovery while running, repeated processing of one video, invalid paths, unsupported uploads, failure recovery, a moved file, and segment validation. Chromium end to end: scan picked up a file added while the page was open, the run list filtered per video, and the run of the selected video loaded.
