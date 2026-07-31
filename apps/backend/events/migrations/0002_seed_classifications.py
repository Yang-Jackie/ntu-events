from django.db import migrations

CLASSIFICATIONS = {
    "EventFormat": [
        ("TALK_SEMINAR", "Talk or seminar"),
        ("WORKSHOP_CLASS", "Workshop or class"),
        ("CONFERENCE", "Conference"),
        ("COMPETITION_HACKATHON", "Competition or hackathon"),
        ("FAIR_EXHIBITION", "Fair or exhibition"),
        ("NETWORKING_MEETUP", "Networking or meetup"),
        ("PERFORMANCE", "Performance"),
        ("CEREMONY", "Ceremony"),
        ("SOCIAL_GATHERING", "Social gathering"),
        ("SPORTS_RECREATION", "Sports or recreation"),
        ("SERVICE_ACTIVITY", "Service activity"),
        ("TOUR_OPEN_HOUSE", "Tour or open house"),
        ("INFORMATION_SESSION", "Information session"),
        ("OTHER", "Other"),
    ],
    "EventTopic": [
        ("COMPUTING_TECHNOLOGY", "Computing and technology"),
        ("SCIENCE_ENGINEERING", "Science and engineering"),
        ("BUSINESS_FINANCE", "Business and finance"),
        ("ARTS_CULTURE", "Arts and culture"),
        ("SOCIAL_SCIENCES_HUMANITIES", "Social sciences and humanities"),
        ("HEALTH_WELLBEING", "Health and wellbeing"),
        ("SPORTS_RECREATION", "Sports and recreation"),
        ("SUSTAINABILITY_ENVIRONMENT", "Sustainability and environment"),
        ("COMMUNITY_STUDENT_LIFE", "Community and student life"),
        ("INTERNATIONAL_EXCHANGE", "International exchange"),
        ("OTHER", "Other"),
    ],
    "EventPurpose": [
        ("LEARNING_RESEARCH", "Learning and research"),
        ("CAREER_RECRUITMENT", "Career and recruitment"),
        ("NETWORKING_COMMUNITY", "Networking and community"),
        ("COMPETITION_ACHIEVEMENT", "Competition and achievement"),
        ("SERVICE_VOLUNTEERING", "Service and volunteering"),
        ("SOCIAL_RECREATION", "Social and recreation"),
        ("ORIENTATION_OUTREACH", "Orientation and outreach"),
        ("SHOWCASE_CELEBRATION", "Showcase and celebration"),
        ("INFORMATION_SUPPORT", "Information and support"),
        ("OTHER", "Other"),
    ],
    "EventAudience": [
        ("ALL_CURRENT_STUDENTS", "All current students"),
        ("UNDERGRADUATES", "Undergraduates"),
        ("POSTGRADUATES", "Postgraduates"),
        ("STAFF_FACULTY", "Staff and faculty"),
        ("ALUMNI", "Alumni"),
        ("PROSPECTIVE_STUDENTS", "Prospective students"),
        ("INDUSTRY_ACADEMIC_PARTNERS", "Industry and academic partners"),
        ("PUBLIC", "Public"),
        ("RESTRICTED_NTU_COMMUNITY", "Restricted NTU community"),
        ("OTHER", "Other"),
    ],
}


def seed_classifications(apps, schema_editor):
    del schema_editor
    for model_name, values in CLASSIFICATIONS.items():
        model = apps.get_model("events", model_name)
        for sort_order, (code, label) in enumerate(values):
            model.objects.update_or_create(
                code=code,
                defaults={
                    "label": label,
                    "sort_order": sort_order,
                    "is_active": True,
                },
            )


def remove_classifications(apps, schema_editor):
    del schema_editor
    for model_name, values in CLASSIFICATIONS.items():
        model = apps.get_model("events", model_name)
        model.objects.filter(code__in=[code for code, _label in values]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_classifications, remove_classifications),
    ]
