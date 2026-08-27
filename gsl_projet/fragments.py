from gsl_core.fragments import Fragment


class ProjetFragment(Fragment):
    context_object_name = "projet"


class ProjetActionsFragment(ProjetFragment):
    name = "projet_actions"
    template_name = "includes/projet_detail/_projet_actions.html"

    def get_context(self):
        return {
            **super().get_context(),
            "next_url": self.request.htmx.current_url or self.request.path,
        }
