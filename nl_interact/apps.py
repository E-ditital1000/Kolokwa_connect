from django.apps import AppConfig
import os


class NlInteractConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'nl_interact'
    
    # Explicitly set the path to resolve the duplicate location issue
    path = os.path.dirname(os.path.abspath(__file__))