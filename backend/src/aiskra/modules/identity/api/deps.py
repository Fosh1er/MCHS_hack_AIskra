"""Заглушки провайдеров модуля identity (связываются в aiskra.bootstrap.wire)."""

from aiskra.shared.di import provider_stub

provide_session_cookie = provider_stub("identity.SessionCookie")
provide_login = provider_stub("identity.LoginHandler")
provide_logout = provider_stub("identity.LogoutHandler")
provide_list_users = provider_stub("identity.ListUsersHandler")
provide_create_user = provider_stub("identity.CreateUserHandler")
provide_update_user = provider_stub("identity.UpdateUserHandler")
provide_set_user_blocked = provider_stub("identity.SetUserBlockedHandler")
provide_reset_password = provider_stub("identity.ResetPasswordHandler")
provide_save_group = provider_stub("identity.SaveGroupHandler")
provide_delete_group = provider_stub("identity.DeleteGroupHandler")
provide_list_groups = provider_stub("identity.ListGroupsHandler")
provide_login_throttle = provider_stub("identity.LoginThrottle")
provide_get_onboarding = provider_stub("identity.GetOnboardingHandler")
provide_update_onboarding = provider_stub("identity.UpdateOnboardingHandler")
