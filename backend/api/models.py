"""Database records for the EgoHand Twin backend.

The database stores metadata and human decisions only. Hand data stays in the run
directories written by ``egohand_twin`` (JSONL/CSV/NPZ/manifest), which remain the
source of truth; the API reads them through indexed, cached accessors.
"""
from __future__ import annotations

import uuid

from django.db import models


class Video(models.Model):
    """A source video registered from an allowed local folder (never copied elsewhere)."""
    name = models.CharField(max_length=255)
    path = models.CharField(max_length=1024, unique=True)
    sha256 = models.CharField(max_length=64, db_index=True)
    width = models.IntegerField()
    height = models.IntegerField()
    fps = models.FloatField()
    frame_count = models.IntegerField()
    duration_s = models.FloatField()
    timestamp_source = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "sha256": self.sha256, "width": self.width,
                "height": self.height, "fps": self.fps, "frame_count": self.frame_count,
                "duration_s": self.duration_s, "timestamp_source": self.timestamp_source,
                "created_at": self.created_at.isoformat()}


class Run(models.Model):
    """One processing job; doubles as the job-queue entry (status column)."""
    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        COMPLETE = "complete"
        FAILED = "failed"
        CANCELLED = "cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video = models.ForeignKey(Video, on_delete=models.PROTECT, related_name="runs")
    preset = models.CharField(max_length=16, default="recall")
    start_s = models.FloatField(default=0.)
    duration_s = models.FloatField(null=True, blank=True)
    render_preview = models.BooleanField(default=False)
    write_rrd = models.BooleanField(default=False)
    workers = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    stage = models.CharField(max_length=32, default="queued")
    progress = models.FloatField(default=0.)
    out_dir = models.CharField(max_length=1024, blank=True)
    error = models.TextField(blank=True)
    worker_id = models.CharField(max_length=128, blank=True)  # "hostname:pid" of the worker processing it
    metrics = models.JSONField(null=True, blank=True)
    quality_summary = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def as_dict(self, detail: bool = False) -> dict:
        data = {"id": str(self.id), "video_id": self.video_id, "preset": self.preset, "start_s": self.start_s,
                "duration_s": self.duration_s, "render_preview": self.render_preview, "write_rrd": self.write_rrd,
                "workers": self.workers, "status": self.status, "stage": self.stage,
                "progress": round(self.progress, 4), "error": self.error or None,
                "created_at": self.created_at.isoformat(),
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "finished_at": self.finished_at.isoformat() if self.finished_at else None}
        if detail:
            data["metrics"] = self.metrics
            data["quality_summary"] = self.quality_summary
        return data


class ReviewDecision(models.Model):
    """A person's verdict on one review-queue item. Feeds measurement of flag precision."""
    class Verdict(models.TextChoices):
        CONFIRMED_ISSUE = "confirmed_issue"   # the flagged problem is real
        FALSE_ALARM = "false_alarm"           # flagged, but the reconstruction is fine
        EXCLUDE = "exclude"                   # exclude this interval from a downstream export
        NEEDS_MORE_REVIEW = "needs_more_review"

    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="decisions")
    item_id = models.CharField(max_length=16)
    verdict = models.CharField(max_length=24, choices=Verdict.choices)
    reviewer = models.CharField(max_length=64)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def as_dict(self) -> dict:
        return {"id": self.id, "item_id": self.item_id, "verdict": self.verdict, "reviewer": self.reviewer,
                "note": self.note, "created_at": self.created_at.isoformat()}
