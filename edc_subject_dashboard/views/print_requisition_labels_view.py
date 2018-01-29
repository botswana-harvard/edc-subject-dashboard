from django.apps import apps as django_apps
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.edit import ProcessFormView
from django.contrib import messages
from django.urls.base import reverse
from django.http.response import HttpResponseRedirect
from django.conf import settings
from edc_label.job_result import JobResult
from edc_label.printers_mixin import PrintersMixin
from edc_metadata.models import RequisitionMetadata
from edc_appointment.models.appointment import Appointment
from edc_metadata.constants import REQUIRED, KEYED
from edc_lab.labels import RequisitionLabel
from django.core.exceptions import ObjectDoesNotExist
from edc_constants.constants import NO


class RequisitionLabels:

    label_cls = RequisitionLabel
    label_template_name = 'requisition'

    def __init__(self, requisition_metadata=None, panel_names=None,
                 appointment=None, user=None):
        zpl_datas = []
        self.appointment = appointment
        for metadata in requisition_metadata.filter(
                panel_name__in=panel_names):
            panel = [
                r for r in appointment.visit.visit.all_requisitions
                if r.panel.name == metadata.panel_name][0].panel
            requisition = self.get_or_create_requisition(
                panel=panel, user=user)
            if requisition.is_drawn != NO:
                item_count = requisition.item_count or 1
                for item in range(1, item_count + 1):
                    label = self.label_cls(
                        requisition=requisition, user=user, item=item)
                    zpl_datas.append(label.render_as_zpl_data(copies=1))
        self.zpl_data = b''.join(zpl_datas)

    def get_or_create_requisition(self, panel=None, user=None):
        """Gets or creates a requisition.

        If created, the requisition created is incomplete; that is,
        is_drawn and drawn_datetime are None.
        """
        requisition_model_cls = django_apps.get_model(panel.requisition_model)
        visit_model_attr = requisition_model_cls.visit_model_attr()
        try:
            requisition_model_obj = requisition_model_cls.objects.get(
                panel=panel.panel_model_obj,
                **{f'{visit_model_attr}__appointment': self.appointment})
        except ObjectDoesNotExist:
            requisition_model_obj = requisition_model_cls(
                user_created=user.username,
                panel=panel.panel_model_obj,
                **{visit_model_attr: self.appointment.visit})
            requisition_model_obj.get_requisition_identifier()
            requisition_model_obj.save()
        return requisition_model_obj


class PrintRequisitionLabelsView(LoginRequiredMixin, PrintersMixin, ProcessFormView):

    job_result_cls = JobResult
    success_url = settings.DASHBOARD_URL_NAMES.get('subject_dashboard_url')
    print_selected_button = 'print_selected_labels'
    print_all_button = 'print_all_labels'
    checkbox_name = 'selected_panel_names'

    def __init__(self, **kwargs):
        self._selected_panel_names = []
        self._requisition_metadata = None
        super().__init__(**kwargs)

    @property
    def requisition_metadata(self):
        """Returns a queryset of keyed or required RequisitionMetadata for this
        appointment.
        """
        if not self._requisition_metadata:
            appointment = Appointment.objects.get(
                pk=self.request.POST.get('appointment'))
            subject_identifier = self.request.POST.get('subject_identifier')
            opts = dict(
                subject_identifier=subject_identifier,
                visit_schedule_name=appointment.visit_schedule_name,
                schedule_name=appointment.schedule_name,
                visit_code=appointment.visit_code,
                visit_code_sequence=appointment.visit_code_sequence)
            self._requisition_metadata = RequisitionMetadata.objects.filter(
                entry_status__in=[KEYED, REQUIRED], **opts)
        return self._requisition_metadata

    @property
    def selected_panel_names(self):
        """Returns a list of panel names selected on the page.

        Returns all on the page if "print all" is submitted.
        """
        if not self._selected_panel_names:
            if self.request.POST.get('submit') == self.print_selected_button:
                self._selected_panel_names = self.request.POST.getlist(
                    self.checkbox_name) or []
            elif self.request.POST.get('submit') == self.print_all_button:
                for metadata in self.requisition_metadata:
                    self._selected_panel_names.append(metadata.panel_name)
        return self._selected_panel_names

    def post(self, request, *args, **kwargs):
        appointment = Appointment.objects.get(
            pk=request.POST.get('appointment'))
        subject_identifier = request.POST.get('subject_identifier')
        if self.selected_panel_names:

            labels = RequisitionLabels(
                requisition_metadata=self.requisition_metadata.filter(
                    panel_name__in=self.selected_panel_names),
                panel_names=self.selected_panel_names,
                appointment=appointment,
                user=request.user)

            job_id = self.clinic_label_printer.stream_print(
                zpl_data=labels.zpl_data)
            job_result = self.job_result_cls(
                name=labels.label_template_name, copies=1, job_ids=[job_id],
                printer=self.clinic_label_printer)
            messages.success(request, job_result.message)
        success_url = reverse(self.success_url, kwargs=dict(
            subject_identifier=subject_identifier,
            appointment=str(appointment.pk)))
        return HttpResponseRedirect(redirect_to=f'{success_url}')
