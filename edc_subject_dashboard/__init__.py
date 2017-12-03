from django.core.exceptions import ImproperlyConfigured
from django.conf import settings

from .model_wrappers import CrfModelWrapper, AppointmentModelWrapper, AppointmentModelWrapperError
from .model_wrappers import SubjectVisitModelWrapper
from .url_config import UrlConfig

name = 'edc_subject_dashboard.middleware.DashboardMiddleware'
if name not in settings.MIDDLEWARE:
    raise ImproperlyConfigured(f'Missing middleware. Expected {name}.')
