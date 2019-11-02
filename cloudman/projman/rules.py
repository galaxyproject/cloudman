import rules

# Delegate to keycloak in future iteration

# Predicates
@rules.predicate
def is_project_owner(user, project):
    if not project:
        return False
    return project.owner == user

# Permissions
rules.add_perm('projects.view_project', rules.is_authenticated)
rules.add_perm('projects.create_project', is_project_owner | rules.is_staff)
rules.add_perm('projects.delete_project', is_project_owner | rules.is_staff)
