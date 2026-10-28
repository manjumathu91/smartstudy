"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""



from pathlib import Path

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.http import FileResponse, Http404
from django.conf.urls.static import static

from . import frontend_views


def frontend_component(request, component):
    allowed_components = {
        "sidebar.html": "assets/components/sidebar.html",
    }

    relative_path = allowed_components.get(component)

    if not relative_path:
        raise Http404("Component not found")

    file_path = Path(settings.FRONTEND_DIR) / relative_path

    if not file_path.is_file():
        raise Http404("Component file not found")

    return FileResponse(
        open(file_path, "rb"),
        content_type="text/html; charset=utf-8",
    )


urlpatterns = [
    path("", frontend_views.frontend_page, name="home"),

    # Shared frontend components
    path(
        "components/<str:component>",
        frontend_component,
        name="frontend-component",
    ),

    path("admin/", admin.site.urls),

    # Existing API routes
    path("api/documents/", include("documents.urls")),
    path("api/learning/", include("learning.urls")),
    path("api/auth/", include("accounts.urls")),

    # Frontend pages
    path("<str:page>", frontend_views.frontend_page, name="frontend-page"),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
