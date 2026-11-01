# Publication audit

Decision recorded on 1 Nov 2026: option B, audit the existing repository for eventual publication. Visibility remains private. No release assets or history were deleted, and publication is not cleared.

## Findings

| Check | Result |
| --- | --- |
| GitHub visibility | Private, verified with `gh repo view` and the repository API. |
| Remote history | A fresh private clone passed `scripts/check_history.sh`: no prohibited media/data/model filenames and no blob above the scanner's size limit. This scan does not inspect release attachments or prove that historical text is suitable for publication. |
| Local all-ref history | Failed: local checkpoint refs contain test media, frame dumps and large executable archives. They are absent from the fresh remote clone. Do not push checkpoint refs or use a mirror push. No refs were removed. |
| Tracked working tree | The session scan inspected 127 tracked files: none above 5 MiB; no matches for the checked token patterns or non-author email addresses. These pattern checks are not a complete credential audit. |
| Internal metadata | The same scan flagged 17 tracked files for private paths, recording identifiers or restricted-release references. Generic example paths also trigger this scan; each match needs review. Details stay in the ignored local audit output. |
| Releases | Both published releases were inspected by metadata. The handoff release contains the source-video archive, processed-data archive and interactive-replay archive. These must remain private. Its asset manifest, planning PDF and checksums also need review. The separate model release contains model archives and is outside the source-only submission. |
| Other repository surfaces | The API returned 3 PR/issue descriptions with no issue comments; 1 description contains a recording reference. Inline review text has not received a full privacy review. Wiki is enabled but its Git endpoint returned not found, so its contents are unverified. Repository discussions and Pages are disabled. |

## Before visibility can change

1. Review every release attachment and its release description. Removing the source-video archive alone is insufficient. Preserve authorized private copies before a person decides whether to remove attachments.
2. Review internal documentation, launch scripts, issue/PR text and the wiki. Historical commits retain earlier recording identifiers and internal notes even after a later deletion commit.
3. Resolve the conflict between retaining this repository's existing history and the requirement that public material contain no internal notes. The current instructions forbid rewriting history. This audit does not authorize a rewrite, release deletion or a visibility change.
4. Repeat the remote-history scan and perform a fresh source-only clone/setup/test after the cleanup decision. Recheck all submission links from the intended judge account.

The earlier source-only-copy route remains available if the existing historical material cannot be approved for public release. No new repository was created.
