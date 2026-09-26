"""Заглушки провайдеров модуля assessment (связываются в aiskra.bootstrap.wire)."""

from aiskra.shared.di import provider_stub

provide_assess = provider_stub("assessment.AssessCardHandler")
provide_get = provider_stub("assessment.GetAssessmentHandler")
provide_insights = provider_stub("assessment.GroupInsightsHandler")
