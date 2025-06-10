# arretes/views.py
import json

from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from weasyprint import HTML  # pip install weasyprint !!

from .forms import ArreteForm


def create_arrete(request):
    if request.method == "POST":
        form = ArreteForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect("arrete_success")
        else:
            print("Form errors:", form.errors)
            render(request, "gsl_programmation/create_arrete.html", {"form": form})
    else:
        form = ArreteForm()
    return render(request, "gsl_programmation/create_arrete.html", {"form": form})


@require_POST
def export_pdf(request):
    data = json.loads(request.body)
    html_content = data.get("html", "")

    pdf_file = HTML(string=html_content).write_pdf()

    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="export.pdf"'
    return response
