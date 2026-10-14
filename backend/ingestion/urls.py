from django.urls import path

from . import views

urlpatterns = [
    path("", views.JobsView.as_view()),
    path("limits/", views.LimitsView.as_view()),
    path("<uuid:job_id>/", views.JobView.as_view()),
    path("<uuid:job_id>/validate/", views.ValidateView.as_view()),
    path("<uuid:job_id>/mapping/", views.MappingView.as_view()),
    path("<uuid:job_id>/process/", views.ProcessView.as_view()),
    path("<uuid:job_id>/apply/", views.ApplyView.as_view()),
    path("<uuid:job_id>/cancel/", views.CancelView.as_view()),
    path("<uuid:job_id>/refresh/", views.RefreshView.as_view()),
    path("<uuid:job_id>/rows/", views.RowsView.as_view()),
    path("<uuid:job_id>/rows/<uuid:row_id>/creation/", views.CreationView.as_view()),
    path("<uuid:job_id>/candidates/", views.CandidatesView.as_view()),
    path("<uuid:job_id>/candidates/<uuid:candidate_id>/review/", views.DecisionView.as_view()),
    path("<uuid:job_id>/history/", views.HistoryView.as_view()),
    path("<uuid:job_id>/file/", views.FileView.as_view()),
    path("<uuid:job_id>/errors/", views.ErrorsView.as_view()),
]
