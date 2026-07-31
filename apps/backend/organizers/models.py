from common.models import TimestampedModel
from django.db import models


class OrganizationType(models.TextChoices):
    NTU_CENTRAL_UNIT = "NTU_CENTRAL_UNIT", "NTU central unit"
    NTU_SCHOOL_COLLEGE = "NTU_SCHOOL_COLLEGE", "NTU school or college"
    NTU_RESEARCH_CENTRE_INSTITUTE = (
        "NTU_RESEARCH_CENTRE_INSTITUTE",
        "NTU research centre or institute",
    )
    NTU_STUDENT_ORGANISATION = (
        "NTU_STUDENT_ORGANISATION",
        "NTU student organisation",
    )
    NTU_RESIDENTIAL_HALL = "NTU_RESIDENTIAL_HALL", "NTU residential hall"
    EXTERNAL_COMPANY = "EXTERNAL_COMPANY", "External company"
    GOVERNMENT_PUBLIC_AGENCY = "GOVERNMENT_PUBLIC_AGENCY", "Government or public agency"
    NONPROFIT_COMMUNITY = "NONPROFIT_COMMUNITY", "Nonprofit or community"
    INDIVIDUAL_INFORMAL = "INDIVIDUAL_INFORMAL", "Individual or informal group"
    OTHER = "OTHER", "Other"


class Organizer(TimestampedModel):
    name = models.CharField(max_length=255)
    normalized_name = models.CharField(max_length=255, db_index=True)
    organization_type = models.CharField(
        max_length=50,
        choices=OrganizationType.choices,
        null=True,
        blank=True,
    )
    school_or_unit = models.CharField(max_length=255, blank=True)
    website_url = models.URLField(max_length=1000, blank=True)
    social_urls = models.JSONField(default=list, blank=True)
    is_official = models.BooleanField(default=False)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name
