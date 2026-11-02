from django.contrib import admin
from django.urls import include, path
from core.views import admin_dashboard

urlpatterns = [
    path("gestion/", admin.site.admin_view(admin_dashboard), name="admin_dashboard"),
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]
