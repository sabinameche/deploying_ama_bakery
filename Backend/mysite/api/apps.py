from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'
    
    def ready(self):
        # Import signals to connect them
        from api.views_dir import signals
        logger = logging.getLogger(__name__)
        logger.info("✅ Dashboard signals loaded - SSE will update automatically")
