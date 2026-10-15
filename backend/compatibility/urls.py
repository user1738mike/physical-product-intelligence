from django.urls import path

from . import views

urlpatterns = [
    path("equipment/", views.EquipmentList.as_view()),
    path("equipment/<uuid:equipment_id>/", views.EquipmentDetail.as_view()),
    path("equipment/<uuid:equipment_id>/state/", views.StateView.as_view()),
    path("equipment/<uuid:equipment_id>/revisions/", views.RevisionsView.as_view()),
    path("equipment/<uuid:equipment_id>/rule-sets/", views.RulesView.as_view()),
    path("equipment/<uuid:equipment_id>/rule-sets/<uuid:rule_id>/", views.RuleDetail.as_view()),
    path(
        "equipment/<uuid:equipment_id>/rule-sets/<uuid:rule_id>/activate/",
        views.ActivateView.as_view(),
    ),
    path("assessments/", views.AssessmentsView.as_view()),
    path("assessments/<uuid:assessment_id>/", views.AssessmentDetail.as_view()),
    path("assessments/<uuid:assessment_id>/compare/", views.CompareView.as_view()),
]
