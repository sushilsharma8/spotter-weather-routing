from django.urls import path

from routing import views

urlpatterns = [
    path("health", views.health),
    path("suggest", views.suggest),
    path("plan", views.plan),
    path("assess", views.assess),
    path("corridor", views.corridor),
]
