from django.urls import path

from . import views

urlpatterns = [
    path("health", views.health),
    path("presets", views.presets),
    path("videos", views.videos),
    path("videos/upload", views.upload_video),
    path("videos/scan", views.videos_scan),
    path("videos/<int:video_id>", views.video_detail),
    path("videos/<int:video_id>/frames/<int:frame_index>.jpg", views.video_frame),
    path("runs", views.runs),
    path("runs/<uuid:run_id>", views.run_detail),
    path("runs/<uuid:run_id>/cancel", views.run_cancel),
    path("runs/<uuid:run_id>/manifest", views.run_manifest),
    path("runs/<uuid:run_id>/frames", views.run_frames),
    path("runs/<uuid:run_id>/frames/<int:frame_index>", views.run_frame),
    path("runs/<uuid:run_id>/tracks", views.run_tracks),
    path("runs/<uuid:run_id>/events", views.run_events),
    path("runs/<uuid:run_id>/quality", views.run_quality),
    path("runs/<uuid:run_id>/review-queue", views.run_review_queue),
    path("runs/<uuid:run_id>/review-queue/<str:item_id>/decisions", views.review_decision),
    path("runs/<uuid:run_id>/review-stats", views.review_stats),
    path("runs/<uuid:run_id>/preview.mp4", views.run_preview),
    path("runs/<uuid:run_id>/proxy.mp4", views.run_proxy),
    path("runs/<uuid:run_id>/compare.jpg", views.run_compare),
    path("runs/<uuid:run_id>/artifacts/<path:name>", views.run_artifact),
]
