from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.templatetags.static import static as static_url
from django.urls import include, path, re_path
from django.views.static import serve
from django.views.generic import RedirectView

admin.site.site_header = 'Teffaha Casual Wear'
admin.site.site_title = 'Teffaha Admin'
admin.site.index_title = 'Store management'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('favicon.ico', RedirectView.as_view(url=static_url('img/favicon.svg'), permanent=True)),
    path('manage/', include('manager.urls')),
    path('account/', include('accounts.urls')),
    path('', include('store.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # Small shop, one server: let Django serve uploaded photos too.
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
