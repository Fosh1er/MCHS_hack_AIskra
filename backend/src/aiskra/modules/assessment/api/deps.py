"""Заглушки провайдеров модуля assessment (связываются в aiskra.bootstrap.wire)."""

from aiskra.shared.di import provider_stub

provide_assess = provider_stub("assessment.AssessCardHandler")
provide_get = provider_stub("assessment.GetAssessmentHandler")
provide_insights = provider_stub("assessment.GroupInsightsHandler")
provide_override = provider_stub("assessment.OverrideAssessmentHandler")
provide_report = provider_stub("assessment.GetSessionReportHandler")
provide_evaluate_session = provider_stub("assessment.EvaluateSessionHandler")
provide_progress = provider_stub("assessment.MyProgressHandler")
provide_my_report = provider_stub("assessment.GetMySessionReportHandler")
provide_norm_report = provider_stub("assessment.NormReportHandler")
provide_student_profile = provider_stub("assessment.StudentProfileHandler")
provide_debrief = provider_stub("assessment.SessionDebriefHandler")
provide_suggest = provider_stub("assessment.SuggestAssignmentHandler")
provide_readiness = provider_stub("assessment.ReadinessHandler")
provide_validation = provider_stub("assessment.ValidationHandler")
