from django.urls import path

from webdashboard import views


app_name = "webdashboard"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("api/status/", views.status, name="status"),
    path("api/engine/on/", views.engine_on, name="engine_on"),
    path("api/engine/off/", views.engine_off, name="engine_off"),
    path("api/orders/simulate/", views.simulate_bulk, name="simulate_bulk"),
    path("orders/submit/", views.submit_order, name="submit_order"),
]
