from django.contrib.auth.models import Permission, User

import rules


# called by boss-oidc to process JWT user roles
def load_oidc_roles(user, roles):
    """Default implementation of the LOAD_USER_ROLES callback
    Args:
        user (UserModel): Django user object for the user logging in
        roles (list[str]): List of Keycloak roles assigned to the user
                           Note: Contains both realm roles and client roles
    """
    for role in roles:
        perm = Permission.objects.get_or_create(codename=role + "-admin")
        user.user_permissions.add(perm)

# Delegate to keycloak in future iteration

# Predicates
@rules.predicate
def is_project_owner(user, project):
    if not project:
        return False
    return project.owner == user or user.has_perm(f'projman-{project.namespace}-admin')


@rules.predicate
def is_chart_owner(user, proj_chart):
    # Should have update rights on the parent project
    if not proj_chart:
        return False
    return user.has_perm('projman.change_project', proj_chart.project)


# Permissions
rules.add_perm('projman.view_project', is_project_owner | rules.is_staff)
rules.add_perm('projman.add_project', is_project_owner | rules.is_staff)
rules.add_perm('projman.change_project', is_project_owner | rules.is_staff)
rules.add_perm('projman.delete_project', is_project_owner | rules.is_staff)

rules.add_perm('projman.view_chart', is_chart_owner | rules.is_staff)
rules.add_perm('projman.add_chart', is_chart_owner | rules.is_staff)
rules.add_perm('projman.change_chart', is_chart_owner | rules.is_staff)
rules.add_perm('projman.delete_chart', is_chart_owner | rules.is_staff)
