# AGENTS.md

Last updated: 2026-05-18

This file provides shared, project-wide guidance for any coding agent (Claude Code, Codex, Cursor, etc.) working in this repository.

> **For Claude Code users:** create a personal `CLAUDE.local.md` at the repo root (it is gitignored) and start it with `@AGENTS.md` on the first line so this file is imported. Add your personal preferences (branch prefix, dev-server habits, local credentials, etc.) below that line.

## Quick Commands

### Setup & Dependencies
```bash
# Initial setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
npm install && just install-js
cp .env.example .env
pre-commit install
python manage.py migrate
python manage.py createsuperuser

# Run development server
python manage.py runserver

# Interactive Django shell
python manage.py shell_plus --ipython
```

### Development Commands

**Using `just` (recommended):**
```bash
just runserver              # Start development server
just test                   # Run all tests
just test-watching <path>   # Watch and re-run tests on file changes
just shell                  # Django interactive shell
just migrate                # Apply migrations
just makemigrations         # Create migrations (auto-formats with ruff)
just run-celery             # Start Celery worker with beat scheduler
just install-js             # Install/update JS dependencies and vendorize them
```

**Using Django directly:**
```bash
python manage.py runserver
python -m pytest [file_or_path]
python manage.py migrate
python manage.py makemigrations
python -m celery --app gsl worker --beat --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

### Linting & Formatting

```bash
# Python
ruff format                         # Format all Python files
ruff check --fix                    # Fix linting errors
ruff check gsl_core/                # Check specific app

# JavaScript
npm run format:js                   # Check JS style (Standard)
npm run format-fix:js               # Fix JS style

# CSS
npm run lint:css                    # Check CSS
npm run lint-fix:css                # Fix CSS

# Django Templates
djlint --reformat .                 # Format Django templates
djlint --lint .                     # Lint Django templates

# Build JS bundles
npm run build                       # Build TipTap bundle to static/vendor/
```

### Database

```bash
# PostgreSQL setup (first time only)
psql
CREATE USER gsl_team WITH PASSWORD 'gsl_pass';
CREATE DATABASE gsl OWNER gsl_team;
ALTER USER gsl_team CREATEDB;

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Reset database (dev only)
python manage.py flush
python manage.py migrate
```

### Testing

```bash
# All tests
python -m pytest

# Specific test file
python -m pytest gsl_projet/tests/test_models.py

# Specific test function
python -m pytest gsl_projet/tests/test_models.py::test_projet_state_machine

# With verbose output
python -m pytest -vv gsl_projet/

# Watch and re-run on changes
git ls-files | entr -c pytest -vv gsl_projet/
```

**Running tests in a sandboxed environment (no PostgreSQL):**
PostgreSQL is not reachable in the Claude Code sandbox), so DATABASE_URL='sqlite://:memory:' is configured in the
environment.

This matches what CI does on pull requests (see `.github/workflows/django.yml`).

### Deployment

**Production deployment** is automated via GitHub Actions (`.github/workflows/deploy-prod.yml`):
1. Push a version tag matching `vYY.MM.DD` (e.g., `v26.04.08`) to `main`
2. The workflow runs tests, creates a GitHub Release with auto-generated notes (PRs since last tag), and deploys to Scalingo production via the Sources API
3. Requires `SCALINGO_API_TOKEN` secret in the GitHub `production` environment

Scalingo utilities via `just`:
```bash
just scalingo-django-command <env> <command>      # Run Django command
just scalingo-django-shell <env>                  # Open Django shell
just scalingo-django-ssh <env>                    # SSH access
```

### Git Workflow

**Branch naming:**
- `main` is the development and default branch, target PRs to it

**Commit messages:**
- Write commit messages in **English**
- Use [Conventional Commits](https://www.conventionalcommits.org/) format: `type(scope): description`
- Common types: `feat`, `fix`, `refacto`, `core`, `test`, `docs`
- Example: `feat(simulation): prevent modification of notified project dotations`
- Keep commit messages short and descriptive, and proportional to the change being made

**Pull Requests:**
- Write PR title and content in **French**
- Follow the PR template structure:

```markdown
## 🌮 Objectif

_Résumé de l'objectif de la PR en 1 ligne_

Fix #x #y #z _issues à clôturer automatiquement_

## 🔍 Liste des modifications

- _Liste des modifications_

## ⚠️ Informations supplémentaires

_(optionnel) Documentation, commandes à lancer, variables d'environment, etc_

## 🖼️ Images

_(optionnel) Une ou plusieurs captures d'écran_
```

## Application Overview

**Gestion des Subventions Locales** (Local Subsidies Management) is a government platform for managing two major French subsidy programs:
- **DETR** (Dotation d'Équipement des Territoires Ruraux) - Rural territory equipment grants
- **DSIL** (Dotation de Soutien à l'Investissement Local) - Local investment support grants

### Main Workflow

```
1. Project Submission
   ├─ Applicants (municipalities) submit projects via Démarches Simplifiées (DS)
   └─ System imports dossiers from DS into Turgot (this app)

2. Project Evaluation
   ├─ Staff review project eligibility (DETR/DSIL/both)
   ├─ Calculate eligible expenses (assiette), approved amount (montant), subsidy rate (taux)
   └─ Push decision back to DS for applicant visibility

3. Budget Planning (Simulation)
   ├─ Create multiple simulation scenarios
   ├─ Test different budget allocations across projects
   ├─ Compare scenarios to optimize allocation
   └─ Confirm final allocation scenario

4. Formal Approval
   ├─ Authorized user formally approves the allocation
   ├─ ProgrammationProjet records the decision
   └─ Status: accepted/refused/dismissed

5. Document Generation & Notification
   ├─ Accepted projects: system generates legal document templates (arrêté,
   │  notification letter); user signs externally and uploads the signed version
   ├─ Refused/dismissed projects: notification is decoupled from the status
   │  change — user explicitly triggers it from the "À notifier" action
   └─ All notifications to Démarches Numériques are manually triggered
```

### Key Concepts

**Double Dotation:** A single project can be eligible for **both DETR and DSIL simultaneously**
- Requires meeting criteria for both programs
- Each program contributes its own funding (combined funding)
- Tracked separately: assiette_detr/assiette_dsil, montant_detr/montant_dsil, taux_detr/taux_dsil

**Eligibility Criteria:** Complex rules based on:
- Project type/category (infrastructure vs equipment)
- Location (arrondissement/department)
- Applicant type (municipality type)
- Project costs and characteristics
- Program-specific requirements

**Perimeter-Based Authorization:**
- Regional staff see all projects in their region
- Departmental staff see only their department
- Arrondissement staff see only their arrondissement
- Budget delegation: regions can delegate envelopes to departments/arrondissements

**Simulation & Planning:**
- Create multiple "what-if" scenarios
- Test different allocations without committing
- Compare scenarios side-by-side
- Once satisfied, confirm one scenario as the official allocation

## Codebase Architecture

### Django Apps & Responsibilities

| App | Purpose |
|-----|---------|
| **gsl_core** | Base infrastructure, user model (`Collegue`), geographic data (Region/Departement/Arrondissement), perimeter/access control |
| **gsl_demarches_simplifiees** | Integration with French "Démarches Simplifiées" (DS) API for form submissions, dossier sync, field mapping |
| **gsl_projet** | Project management, dotation eligibility (DETR/DSIL), state machine on `DotationProjet` (PROCESSING → ACCEPTED/REFUSED/DISMISSED) |
| **gsl_programmation** | Budget allocation & programming, `Enveloppe` (budget envelope), approval decision recording |
| **gsl_simulation** | "What-if" scenario modeling for subsidy allocations (`views/` directory) |
| **gsl_notification** | Document generation (arrêtés, notification letters), template management, file uploads (`views/` directory) |
| **gsl_oidc** | OIDC/ProConnect authentication integration |
| **gsl_pages** | Static/public pages (accessibility, coming features) |
| **ui** | Reusable template components and assets |

### URL Structure

```
/admin/                    → Django admin panel
/                          → Login/logout (gsl_oidc), static pages (gsl_pages)
/ds/                       → Demarches Simplifiées dossier list/detail
/oidc/                     → OIDC provider routes
/projets/                  → Project CRUD and detail views
/simulation/               → Simulation management
/programmation/            → Budget envelopes and programming
/notification/             → Document templates and generation
```

### Key Models & Relationships

```
Collegue (user)
  └─ Perimetre (Region/Departement/Arrondissement level)
      └─ Geographic hierarchy (Region → Departement → Arrondissement)

Dossier (from Démarches Simplifiées)
  ├─ PersonneMorale (applicant organization)
  └─ Perimetre (derived from address/arrondissement)

Projet
  ├─ Dossier
  └─ DotationProjet (DETR/DSIL eligibility)
      └─ State machine (FSM: PROCESSING → ACCEPTED/REFUSED/DISMISSED)

Enveloppe (budget envelope for DETR/DSIL per territory/year)
  └─ ProgrammationProjet (project allocations, OneToOne with DotationProjet)

Simulation
  └─ SimulationProjet (scenario-based allocations)

Arrete / LettreNotification (generated documents)
  └─ ModeleArrete / ModeleLettreNotification (templates)
```

### Perimeter-Based Access Control

- Each user (`Collegue`) is assigned a `Perimetre` (geographic scope: Region, Departement, or Arrondissement)
- Projects, envelopes, and programming visible only within user's perimeter
- Staff/superusers bypass perimeter filtering
- Departement+ level required for DETR/DSIL envelopes (Regions not allowed)
- Middleware checks: `CheckPerimeterMiddleware` redirects users without perimeter assignment

### Double Dotation Support

Projects can be eligible for **both DETR and DSIL simultaneously**. This is a complex feature that requires separate tracking at multiple levels:

**Financial Data (Separate per Dotation):**
- `DotationProjet.montant_demande_detr` / `montant_demande_dsil`
- `Dossier.annotations_assiette_detr` / `annotations_assiette_dsil`
- `Dossier.annotations_montant_accorde_detr` / `annotations_montant_accorde_dsil`
- `Dossier.annotations_taux_detr` / `annotations_taux_dsil`

**Status Tracking (Key Implementation Detail):**
- `DotationProjet` has a `status` field that tracks DETR and DSIL **independently**
- Each dotation can transition through states (PROCESSING → ACCEPTED | REFUSED | DISMISSED) **separately**
- `Projet.status` is **read-only** and derived from `DotationProjet` statuses (future implementation)
- **Mixed outcomes possible:** Project can be ACCEPTED for DETR but REFUSED for DSIL (and vice versa)

**Synchronization with DS:**
- DS has only a **single status field** per dossier
- When Turgot statuses differ, DS status shows the **overall optimistic outcome** (ACCEPTED if ANY dotation accepted)
- Annotations (`assiette`, `montant`, `taux`) are pushed **separately** for each dotation type

**Programming & Simulation:**
- `ProgrammationProjet`: **Two records per double-dotation project** (one per subsidy with separate identifiers)
- `SimulationProjet`: **Two simulation entries** tested independently for each dotation type
  - **IMPORTANT:** Each `Simulation` is linked to exactly ONE `Enveloppe` (which has a single dotation type)
  - A project with both DETR and DSIL dotations requires **two separate simulations**: one with DETR envelope and one with DSIL envelope
  - `SimulationProjet` validates that its `dotation_projet.dotation` matches the `simulation.enveloppe.dotation`
- `Arrete`: Generated separately with **different identifiers per dotation** (two documents for DETR vs DSIL)

**UI Presentation:**
- Project detail view shows **separate tabs or sections per dotation**
- Users can approve/refuse each dotation independently before finalizing

**When Updating DS Annotations:**
Always push DETR and DSIL updates **separately** via `DsService` (instantiated, not static):
```python
from gsl_demarches_simplifiees.services import DsService

service = DsService()
service.update_ds_annotations_for_one_dotation(
    dossier=dossier_obj,
    user=user,
    dotations_to_be_checked=["detr", "dsil"],
    annotations_dotation_to_update="detr",
)
```

**When Transitioning States:**
Each dotation state can transition independently:
```python
# DETR can move to ACCEPTED
dossier.dossier_dotation_detr.status = "accepted"

# While DSIL stays in PROCESSING or moves to REFUSED
dossier.dossier_dotation_dsil.status = "refused"

# No constraint prevents these different states
```

### Data Integration with Démarches Simplifiées (DS)

1. **Dossiers** are imported from DS via GraphQL API (pull-based sync)
2. **Field mapping** translates DS form fields to Django model fields
3. **Annotations** (internal decisions) are pushed back to DS:
   - `assiette` (eligible expenses)
   - `montant` (approved amount)
   - `taux` (subsidy rate percentage)
4. **Services:**
   - `DsService` handles annotation updates
   - `DsMutator` executes GraphQL mutations
   - Importer loads dossier data

### Frontend Technology Stack

- **Framework:** Django templates (DTL - Django Template Language)
- **Interactivity:** HTMX (v2) for dynamic content + Stimulus (v3) for JS components
- **Rich text:** TipTap editor (v3.7.2) for document templates
- **UI system:** DSFR (Design System of the French Republic) via `django-dsfr`
- **Build tools:** esbuild (bundler/minifier), stylelint (CSS linting)
- **CSS approach:** DSFR classes + custom CSS

> **Prefer DSFR utility classes over custom CSS.** Reach for DSFR's grid
> classes (`fr-grid-row`, `fr-col-*`) and spacing utilities
> (`fr-mt-*`, `fr-mb-*`, `fr-p-*`, etc.) before writing custom CSS. Only add
> custom CSS when no DSFR utility covers the need.

**Key patterns:**
- Server-side HTML rendering with HTMX for AJAX updates
- Stimulus controllers for modal/tab interactions
- TipTap editor for rich text in template fields
- DSFR template tags for consistent component styling

### View Architecture Patterns

- **CBVs (Class-Based Views)** are the standard pattern, with `DsfrBaseForm` for DSFR-compliant forms
- **HTMX-specific mixins** in `gsl_core/view_mixins.py`:
  - `OpenHtmxModalMixin` - Auto-opens DSFR modal after HTMX swap
  - `NoFeedbackHtmxFormViewMixin` - Handles HTMX form submissions (204 on success, 400 on error)
- **Business logic placement:** `Form.save()` for complex mutations, `Model.clean()`/`clean_fields()` for validation

### Admin Permissions

- To reserve a `ModelAdmin` to super-users only (e.g. background-plumbing models like `BulkStatusJob`), inherit directly from `admin.ModelAdmin` and **don't** override `has_*_permission`, and **don't** mix in `AllPermsForStaffUser`. Django's default behavior is enough: a user only sees the module if they have the explicit Django permissions (`add`, `change`, `view`, `delete`) on the model — which by default no one has, so only super-users (who bypass all permissions) get access.
- Use `AllPermsForStaffUser` only when the admin is intended for the business team (`is_staff` users) and the model is part of the day-to-day workflow.

### State Machines & Workflows

**Dotation workflow (django-fsm):**
- FSM is on `DotationProjet.status`: PROCESSING → (ACCEPTED | REFUSED | DISMISSED)
- Each dotation (DETR/DSIL) transitions independently
- `Projet.status` is a **read-only computed property** derived from its `DotationProjet` statuses
- Permissions controlled per state transition

**Enveloppe delegation:**
- Parent/child relationship for budget delegation across perimeters
- `parent_enveloppe` field tracks hierarchy

### Async Tasks & Celery

Tasks are spread across multiple apps:
- `gsl_core/tasks.py`: `associate_or_update_ds_profile_to_users()` - Link DS profiles to user accounts
- `gsl_demarches_simplifiees/tasks.py`: DS dossier import/refresh (fetch, save, refresh dossiers and démarches)
- `gsl_projet/tasks.py`: Project and dotation creation/update from imported dossiers

Run with: `python -m celery --app gsl worker --beat --scheduler django_celery_beat.schedulers:DatabaseScheduler`

Or use `just run-celery`.

#### Task priorities

Priority is decided **at the dispatch site**, not baked into the task — the same
task can be high or low depending on context. Constants and helper live in
`gsl/celery.py` (Redis: lower number = served first): `TASK_PRIORITY_HIGH = 0`,
`TASK_PRIORITY_NORMAL = 5` (= `CELERY_TASK_DEFAULT_PRIORITY`),
`TASK_PRIORITY_LOW = 9`, `TASK_BULK_DISPATCH_THRESHOLD = 10`.

- **High (0)** — short non-blocking task, including a small interactive batch
  (count < 10), admin or not.
- **Normal (5, default)** — long task that blocks the agent waiting on it, or a
  moderate count. Use plain `.delay()` (no override).
- **Low (9)** — long admin task, or a high count (≥ 10: batch wrappers and their
  children, sync fan-out).

Sites dispatched both per-unit and en masse: use `priority_for_dispatch_count(count)`
(high if `< 10` else low). If the dispatch lives in a shared helper reached by
several contexts, thread the priority down as a parameter per entry point instead
of hardcoding it (see `_save_dossier_data_and_refresh_dossier_and_projet_and_co`'s
`refresh_priority`).

## Coding Conventions

### General

- When asked to handle a specific error type, handle only that one. Let
  unexpected errors propagate so they trigger alerts and native logging
  (stack traces) instead of being swallowed.
- Keep `try` blocks small with narrow exception types. Lines not expected to
  fail stay outside `try` blocks.
- Run the project's existing linters/formatters on files you modified (see
  `## Code Style & Quality`). Don't introduce tools the project doesn't use.

### Frontend Accessibility

- Use ARIA attributes (`aria-controls`, `aria-expanded`, etc.) and ensure
  keyboard navigation/interaction works.

### Django

- Stay pythonic and djangoesque.
- **Don't use service classes for database or form mutations.** Use native
  Django patterns instead: `QuerySet`, `Model`, `Manager`, `Form`,
  `Validator`, `Admin`, `Filter`, `Resource`. Service classes that exist for
  DB/form logic are legacy — prefer refactoring toward native patterns rather
  than extending them.
  - Services **are** appropriate for interfacing with real external
    third-party systems (e.g. `DsService` wrapping the Démarches
    Numériques API). The rule targets DB/form mutation logic, not genuine
    integration boundaries.
  - Complex data mutations belong in the `save()` method of a `Form`
    subclass (keeps logic in context, not in a detached helper).
  - Complex POST-data transformation belongs in `Form` subclasses, not views.
  - Validate POST data in `Form`s; reading `request.POST` directly in a view
    is almost always an antipattern.
  - Simple model mutations (the building blocks) are `QuerySet`/`Model`
    methods.
- Prefer end-to-end tests (test client → send request → assert response)
  over complex combinations of unit tests.
- Set field `label`, `help_text`, and `validators` at the **Model** level
  rather than per-`Form`, so they apply everywhere (other forms + Django
  admin) and form code stays concise.
- Minimize context keys passed to templates:
  - Use the `{% url %}` tag instead of calling `reverse()` for URLs.
  - Use the `|length` filter instead of passing a precomputed `len()`.

### JavaScript / NPM

- For security, don't use `npx` outside of project bootstrapping. A JS tool
  used regularly inside the project must be a dev dependency run via an
  `npm run <command>` script.

## Common Development Tasks

### Adding a New Field to a Model

1. Add field to model in `gsl_*/models.py`
2. Create migration: `just makemigrations` (auto-formats migrations)
3. Apply migration: `just migrate`
4. Add to admin if needed in `gsl_*/admin.py`
5. Add to views/serializers if needed

### Creating a New View

1. Add view class to `gsl_*/views.py` or `gsl_*/views/` directory (depends on the app; `gsl_simulation` and `gsl_notification` use a `views/` directory)
2. Add URL pattern to `gsl_*/urls.py`
3. Create template in `gsl_*/templates/gsl_*/`
4. Add to main `gsl/urls.py` if a new app
5. Test with `pytest gsl_*/tests/`

### Updating DS Annotations

Use `DsService` in `gsl_demarches_simplifiees/services.py` (instantiated):

```python
from gsl_demarches_simplifiees.services import DsService

service = DsService()
service.update_ds_annotations_for_one_dotation(
    dossier=dossier_obj,
    user=user,
    dotations_to_be_checked=["detr"],
    annotations_dotation_to_update="detr",
)
```

### Document Generation & Notification Workflow

Notification of Démarches Numériques is now **decoupled from the status
change** and always manually triggered.

**For refused/dismissed projects (two steps):**
1. In programmation, `ProgrammationStatusUpdateView`
   (`gsl_simulation/views/simulation_projet_views.py`) only changes the status
   via `SimulationProjetStatusForm`, using the unified modal
   `gsl_simulation/templates/htmx/programmation_status_change_modal.html`
   (no justification, no DS call). The project is marked "À notifier".
2. The user later clicks the "À notifier" action, handled by
   `RefusedDismissedNotificationModalView` (`gsl_notification/views/views.py`)
   with `RefusedDismissedNotificationForm` (`gsl_notification/forms.py`),
   modal `gsl_notification/templates/gsl_notification/modal/notify_refused_dismissed.html`,
   route `notify-refused-dismissed`
   (`/notification/<projet_id>/notifier/refus-ou-classement/`). The user enters
   the justification and explicitly sends the notification to DS.

Table cells and the project-detail card route the "À notifier" action based on
`Projet.has_accepted_dotation`: accepted → documents flow; otherwise → the
`notify-refused-dismissed` endpoint.

**For accepted projects:**
- System generates template documents (arrêté, notification letter)
- User downloads template, signs externally, uploads signed copy
- User manually triggers notification to send documents to applicant

**Adding a new document template:**
1. Create model class in `gsl_notification/models.py` (e.g., `ModeleMonDocument`)
2. Add admin inline to configure templates
3. Create template file in `gsl_notification/templates/`
4. Add generation method in views to render template
5. Implement file upload for signed documents via `ArreteEtLettreSignes` or `Annexe`

### Filtering by Perimeter

Use `EnveloppeService` or query filters:

```python
from gsl_programmation.services import EnveloppeService

# Get envelopes visible to a user
envelopes = EnveloppeService.get_enveloppes_visible_for_a_user(user=request.user)
```

Or directly filter by user's perimeter:
```python
user_perimetre = request.user.collegue.perimetre
projects = Projet.objects.filter(perimetre=user_perimetre)
```

### Recording Project Actions (ProjetAction)

`ProjetAction` (`gsl_historique/models.py`) is the audit log for significant events on a project: status changes, montant/assiette updates, dotation changes, document generation/upload, notifications, etc.

**Rule: call `ProjetAction.objects.create(...)` directly at the semantic site of the change.**

Place the call in the method or form `save()` that owns the business logic — not in a wrapper, not in a service layer, not in a view. This keeps the audit trail co-located with the mutation that triggers it.

```python
# Good: inside the FSM transition method that changes the status
def refuse(self, enveloppe, actor=None):
    ...
    ProjetAction.objects.create(
        projet=self.projet,
        action_type=ProjetAction.TYPE_STATUS_CHANGE,
        source=ProjetAction.SOURCE_TURGOT if actor else ProjetAction.SOURCE_DS,
        actor=actor,
        dotation=self.dotation,
        status=PROJET_STATUS_REFUSED,
        enveloppe=enveloppe,
    )

# Good: inside Form.save() for a manual update
if "assiette" in self.changed_data:
    ProjetAction.objects.create(
        projet=self.instance.projet,
        action_type=ProjetAction.TYPE_ASSIETTE_MODIFIED,
        source=ProjetAction.SOURCE_TURGOT,
        actor=self.user,
        ...
    )
```

**Key fields:**
- `source`: `SOURCE_TURGOT` when an agent acts via the UI, `SOURCE_DS` when the change comes from a DN/DS sync (no `actor`)
- `actor`: the logged-in `Collegue`, or `None` for automated DN updates
- `enveloppe`: set for final-status changes (accepted/refused/dismissed) only

**Idempotency:** only log when something actually changes. Check `self.changed_data` in forms, compare old vs new values in model methods before creating the action.

**Do not** create a helper function or service method that wraps `ProjetAction.objects.create` — the directness is intentional.

## Testing

### Test Structure

Tests are in `gsl_*/tests/` directories:
- `test_models.py` - Model logic and constraints
- `test_views.py` - View responses and permissions
- `test_services.py` - Business logic services
- `test_forms.py` - Form validation
- `test_double_dotation_display.py` - Double dotation UI display on programming/simulation pages

### Double Dotation Display Tests

#### Programmation Page Tests (`gsl_programmation/tests/test_double_dotation_display.py`)

Tests that ensure when viewing DETR/DSIL programming pages, the other dotation information is displayed under each project line for user reference:

- `TestDoubleDotationDisplayOnDetrProgrammation`:
  - `test_detr_programming_page_displays_dsil_information` - DSIL info shown below DETR projects
  - `test_detr_programming_page_shows_dsil_amount` - DSIL amount displayed
  - `test_detr_programming_page_shows_dsil_rate` - DSIL subsidy rate displayed
  - `test_detr_programming_page_shows_dsil_status` - DSIL status displayed
  - `test_detr_programming_page_shows_dsil_categories` - DSIL operation categories displayed
  - `test_single_dotation_projects_dont_show_other_row` - Single-dotation projects don't show secondary row

- `TestDoubleDotationDisplayOnDsilProgrammation`:
  - `test_dsil_programming_page_displays_detr_information` - DETR info shown below DSIL projects
  - `test_dsil_programming_page_shows_detr_amount` - DETR amount displayed on DSIL page

**Template Structure:** The programmation list uses `other-dotation-row` class for secondary rows displaying complementary dotation info.

**Implementation Reference:** See `gsl_programmation/templates/gsl_programmation/programmation_projet_list.html` lines 244-282 for the existing template structure that renders other-dotation rows.

#### Simulation Page Tests (`gsl_simulation/tests/test_double_dotation_display.py`)

Tests that ensure when viewing DETR/DSIL simulation pages, the other dotation information is displayed for user reference:

- `TestDoubleDotationDisplayOnDetrSimulation`:
  - `test_detr_simulation_page_displays_dsil_information` - DSIL info shown in DETR simulation
  - `test_detr_simulation_table_row_structure` - Proper row structure for DETR/DSIL split
  - `test_detr_simulation_shows_both_dotation_amounts` - DETR + DSIL amounts visible
  - `test_detr_simulation_shows_both_dotation_rates` - DETR + DSIL rates visible
  - `test_single_dotation_projet_no_secondary_row` - Single-dotation projects have no secondary row

- `TestDoubleDotationDisplayOnDsilSimulation`:
  - `test_dsil_simulation_page_displays_detr_information` - DETR info shown in DSIL simulation
  - `test_dsil_simulation_shows_detr_amount_in_secondary_row` - DETR amount in secondary row
  - `test_dsil_simulation_shows_detr_rate_in_secondary_row` - DETR rate in secondary row

- `TestOtherDotationAccessibility`:
  - `test_other_dotation_info_clearly_labeled` - Other dotation is clearly labeled
  - `test_other_dotation_visible_to_all_users_in_perimetre` - All users with perimeter see it

### Pytest Configuration

- `conftest.py` sets Celery to eager mode for tests
- Default storage uses FileSystemStorage (not S3)
- Automatic fixtures available from pytest plugins

### Running Tests

```bash
# All tests
pytest

# Watch mode (re-run on file changes)
git ls-files | entr -c pytest -vv gsl_projet/

# Specific test
pytest gsl_projet/tests/test_models.py::test_projet_state_machine -vv
```

### Test Database

Uses a test database with auto-rollback per test. No manual cleanup needed.

## Code Style & Quality

### Python

- **Formatter:** `ruff format` (must-have)
- **Linter:** `ruff check --fix` (auto-fixable issues)
- **Pre-commit hooks** installed via `pre-commit install`
- Line length: 88 characters (Black default)

### JavaScript

- **Linter:** Standard (JavaScript Style Guide)
- Use: `npm run format-fix:js`
- Global variables: `dsfr`, `htmx` (predefined in package.json)

### CSS

- **Linter:** stylelint with standard config
- Use: `npm run lint-fix:css`
- Follow DSFR component patterns

### Django Templates

- **Formatter/Linter:** djLint (profile: django)
- Pre-commit hook auto-reformats templates on commit
- Line length: 120 characters

### Migrations

- Auto-formatted by `just makemigrations` (runs `ruff format` on them)
- Never edit migration files manually
- Always review migration diffs before committing

## Environment Variables

See `.env.example` for required variables:
- `SECRET_KEY` - Django secret key
- `DEBUG` - Debug mode (dev/test only)
- `ENV` - Environment: dev|test|staging|prod
- `ALLOWED_HOSTS` - Comma-separated list
- `DATABASE_URL` - PostgreSQL connection
- `SENTRY_DSN` - Error tracking (optional)
- `CELERY_BROKER_URL` - Redis connection for tasks
- `AWS_*` - S3 storage credentials (production)
- `OIDC_RP_CLIENT_*` - ProConnect OIDC credentials
- `OTP_ENABLED` - Enable TOTP two-factor authentication for staff users (default: true)

## Key Files Reference

| Path | Purpose |
|------|---------|
| `gsl/settings.py` | Django configuration |
| `gsl/urls.py` | Main URL routing |
| `manage.py` | Django CLI entry point |
| `justfile` | Task automation (build, test, deploy) |
| `conftest.py` | pytest configuration and fixtures |
| `gsl_core/models.py` | User, Perimetre, Geography models |
| `gsl_demarches_simplifiees/models.py` | Dossier, DS integration models |
| `gsl_projet/models.py` | Project, DotationProjet models |
| `gsl_programmation/models.py` | Enveloppe, ProgrammationProjet models |
| `gsl_notification/models.py` | Template and document models |
| `package.json` | JS dependencies and build scripts |
| `requirements.txt` | Python production dependencies |
| `requirements-dev.txt` | Development dependencies (pytest, ruff, etc.) |
| `gsl_core/view_mixins.py` | Reusable HTMX/DSFR view mixins (`OpenHtmxModalMixin`, `NoFeedbackHtmxFormViewMixin`) |
| `gsl_core/middlewares.py` | OTP verification and Perimeter check middlewares |

## Architecture Diagrams

### Data Flow: Complete Project Lifecycle

```
1. SUBMISSION & IMPORT
   Démarches Simplifiées (applicant submits)
       ↓ (GraphQL API pull)
   Dossier imported with form fields
       ↓ (Field mapping)
   Projet + DotationProjet created

2. EVALUATION
   Manual Review: Determine eligible expenses, amount, rate
       ↓ (DsService.update_ds_assiette/montant/taux)
   Démarches Simplifiées updated (applicant sees decision)
       ↓ (Projet state: PROCESSING)
   Eligible for DETR, DSIL, or both?

3. SIMULATION & ALLOCATION
   Create Simulation scenarios
       ↓ (test different allocations)
   Compare scenarios
       ↓ (confirm best allocation)
   Create Enveloppe per territory/year
       ↓
   ProgrammationProjet: Allocate projects to envelope

4. APPROVAL & DOCUMENTS
   Authorized user approves allocation
       ↓ (ProgrammationProjet records decision)
   Projet state → ACCEPTED | REFUSED | DISMISSED
       ↓
   IF REFUSED/DISMISSED: marked "À notifier"; user later triggers
       notification via notify-refused-dismissed (gsl_notification)
   IF ACCEPTED: Generate templates (arrêté, letter)
       ↓
   User signs externally → uploads signed version
       ↓ (Manual notification trigger)
   Applicant notified in DS + receives documents
```

### User Access Control Flow

```
Collegue (logged-in user)
    ↓ (has assigned)
Perimetre (Region|Departement|Arrondissement)
    ↓
OTPVerificationMiddleware (enforces TOTP for staff, configurable via OTP_ENABLED)
    ↓
CheckPerimeterMiddleware (redirect if missing)
    ↓
View filtering (Projet.objects.filter(perimetre=user.perimetre))
    ↓
Only visible data shown
```

## Debugging Tips

### Database Queries

Use Django's query debugger in development:
```python
from django.db import connection
from django.test.utils import CaptureQueriesContext

with CaptureQueriesContext(connection) as ctx:
    # ... your code
    print(f"Queries: {len(ctx)}")
    for q in ctx:
        print(q['sql'])
```

### Celery Tasks

Tasks run immediately in tests (eager mode set in conftest.py). In dev, check Redis:
```bash
redis-cli
> KEYS *
> GET celery-task-key
```

### DS API Integration

Check `gsl_demarches_simplifiees/importer/` for dossier import logic.
Logs from `DsService` and `DsMutator` show API calls and responses.

### Perimeter Filtering

Enable SQL logging to debug perimeter filters:
```python
# In settings.py dev section
LOGGING = {
    'version': 1,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'loggers': {
        'django.db.backends': {'level': 'DEBUG', 'handlers': ['console']},
    }
}
```

## Deployment Notes

- **Scalingo** platform (Heroku-like)
- **Production deploy:** push a `vYY.MM.DD` tag to `main` → GitHub Actions runs tests, creates a release, and deploys via Scalingo Sources API
- Environment-based config
- Static files served by Whitenoise
- Database: PostgreSQL managed service
- Task queue: Celery + Redis
- File storage: S3
- SSL/TLS: Auto-managed by platform

See `justfile` for Scalingo commands.
