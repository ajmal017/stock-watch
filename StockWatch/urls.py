from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from StockWatch.main import views

urlpatterns = [
    path('', views.search, name='search'),
    path('login/', views.login, name='login'),
    path('logout/', auth_views.LogoutView.as_view(template_name='base.jinja'), name='logout'),
    path('search/symbols/', views.search_company_symbols, name='symbol-search'),
    path('price-data/', views.get_historical_price, name='historical-price'),
    path('archive', views.archive, name='archive'),
    path('archive/export/', views.archive_export, name='archive-export'),
    path('admin/', admin.site.urls),
]
