import rules

# Delegate to keycloak in future iteration

# Predicates
@rules.predicate
def is_project_owner(user, project):
    if not project:
        return False
    return project.owner == user


@rules.predicate
def is_chart_owner(user, proj_chart):
    # Should have update rights on the parent project
    if not proj_chart:
        return False
    return user.has_perm('projects.change_project', proj_chart.project)


# Permissions
rules.add_perm('projects.view_project', rules.is_authenticated)
rules.add_perm('projects.add_project', is_project_owner | rules.is_staff)
rules.add_perm('projects.change_project', is_project_owner | rules.is_staff)
rules.add_perm('projects.delete_project', is_project_owner | rules.is_staff)

rules.add_perm('charts.view_chart', rules.is_authenticated)
rules.add_perm('charts.add_chart', is_chart_owner | rules.is_staff)
rules.add_perm('charts.change_chart', is_chart_owner | rules.is_staff)
rules.add_perm('charts.delete_chart', is_chart_owner | rules.is_staff)
