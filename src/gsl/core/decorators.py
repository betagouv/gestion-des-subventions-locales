from django.http import HttpResponseBadRequest


def htmx_only(view_func):
    def wrapper_func(request, *args, **kwargs):
        if not request.htmx:
            return HttpResponseBadRequest()
        return view_func(request, *args, **kwargs)

    return wrapper_func
