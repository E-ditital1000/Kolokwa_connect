# nl_interact/urls.py
from django.urls import path
from .views import NLQueryView

app_name = 'nl_interact'

urlpatterns = [
    path('query/', NLQueryView.as_view(), name='nl-query'),
]