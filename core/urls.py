from django.urls import path
from . import views

urlpatterns = [
    path("", views.homepage, name="home"),
    path("about/", views.about_us, name="about"),
    path("privacy/", views.privacy_policy, name="privacy_policy"),
    path("terms/", views.terms_of_use, name="terms_of_use"),
]
