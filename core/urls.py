from django.urls import path
from . import views

urlpatterns = [
    path("", views.homepage, name="home"),
    path("about/", views.about_us, name="about"),
]
