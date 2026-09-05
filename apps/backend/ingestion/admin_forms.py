from django import forms
from django.core.exceptions import ValidationError
from pydantic import ValidationError as PydanticValidationError

from ingestion.contracts import CanonicalizationProposal, EventCandidatePayload
from ingestion.models import CanonicalizationPlan, EventCandidate


class EventCandidateAdminForm(forms.ModelForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)

    class Meta:
        model = EventCandidate
        fields = ("effective_payload", "reviewer_notes")
        widgets = {"effective_payload": forms.Textarea(attrs={"rows": 32, "cols": 120})}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["expected_version"].initial = self.instance.edit_version

    def clean_effective_payload(self) -> dict:
        value = self.cleaned_data["effective_payload"]
        try:
            EventCandidatePayload.model_validate(value)
        except PydanticValidationError as exc:
            raise forms.ValidationError(
                "The payload does not match the event-candidate schema: "
                f"{exc.errors(include_url=False)}"
            ) from exc
        return value

    def clean(self) -> dict:
        cleaned_data = super().clean()
        if not self.instance.pk or "expected_version" not in cleaned_data:
            return cleaned_data
        current_version = (
            EventCandidate.objects.filter(pk=self.instance.pk)
            .values_list("edit_version", flat=True)
            .first()
        )
        if current_version != cleaned_data["expected_version"]:
            raise ValidationError(
                "This candidate changed after the page was loaded. Reload and retry."
            )
        return cleaned_data


class CanonicalizationPlanAdminForm(forms.ModelForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)

    class Meta:
        model = CanonicalizationPlan
        fields = ("effective_proposal",)
        widgets = {"effective_proposal": forms.Textarea(attrs={"rows": 36, "cols": 120})}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["expected_version"].initial = self.instance.plan_version

    def clean_effective_proposal(self) -> dict:
        value = self.cleaned_data["effective_proposal"]
        try:
            CanonicalizationProposal.model_validate(value)
        except PydanticValidationError as exc:
            raise forms.ValidationError(
                "The proposal does not match the canonicalization schema: "
                f"{exc.errors(include_url=False)}"
            ) from exc
        return value

    def clean(self) -> dict:
        cleaned_data = super().clean()
        if not self.instance.pk or "expected_version" not in cleaned_data:
            return cleaned_data
        current = (
            CanonicalizationPlan.objects.filter(pk=self.instance.pk)
            .values_list("plan_version", flat=True)
            .first()
        )
        if current != cleaned_data["expected_version"]:
            raise ValidationError("This plan changed after the page was loaded. Reload and retry.")
        return cleaned_data
