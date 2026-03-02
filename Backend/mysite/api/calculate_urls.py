from django.urls import path
from . import views

urlpatterns =[
    path('dashboard-details/',views.DashboardView.as_view(),name="today-sales"),
    path('dashboard-details/<int:branch_id>/',views.DashboardView.as_view(),name="today-sales"),
    path('report-dashboard/',views.ReportDashboardView.as_view(),name="report-dashboard"),
    path('report-dashboard/<int:branch_id>/',views.ReportDashboardView.as_view(),name="report-dashboard"),
    path('staff-report/',views.StaffReportView.as_view(),name="staff-report"),
    path('staff-report/<int:branch_id>/',views.StaffReportView.as_view(),name="staff-report-branch"),
]
