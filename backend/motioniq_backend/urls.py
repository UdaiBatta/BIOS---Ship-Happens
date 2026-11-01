from django.urls import include, path

from api import views

urlpatterns = [
    path("api/", include("api.urls")),
    path("", views.frontend),
    path("backend-connector.js", views.frontend, {"name": "backend-connector.js"}),
    path("hand-mesh.js", views.frontend, {"name": "hand-mesh.js"}),
]
