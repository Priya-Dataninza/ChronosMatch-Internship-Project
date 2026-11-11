from django.urls import path

from webdashboard import views


app_name = "webdashboard"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("api/status/", views.status, name="status"),
    path("orders/submit/", views.submit_order, name="submit_order"),
]
