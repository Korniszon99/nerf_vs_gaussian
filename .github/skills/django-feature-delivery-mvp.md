# Skill: django-feature-delivery-mvp

Powtarzalny workflow wdrażania funkcji end-to-end w Django + Nerfstudio MVP.

---

## Delivery checklist

### 1. Model & Database
- [ ] Update `experiments/models.py` if needed (new model or fields)
- [ ] Create and commit migration: `python manage.py makemigrations`
- [ ] Add type hints on new model methods
- [ ] Add docstring on `__str__` and public methods

### 2. Form
- [ ] Create `ModelForm` in `experiments/forms.py` (if form is needed)
- [ ] Add validators for business logic (e.g., `clean_*()` methods)
- [ ] Write docstring on custom validators
- [ ] Test form in unit tests

### 3. View & URL
- [ ] Implement class-based view (CBV) in `experiments/views.py`
- [ ] Use `get_object_or_404()` for detail/edit/delete views
- [ ] Implement `get_queryset()` with `select_related()` / `prefetch_related()`
- [ ] Add docstring on view class
- [ ] Wire URL in `experiments/urls.py`
- [ ] Use descriptive `name` parameter for `reverse()` calls

### 4. Template
- [ ] Create/update template in `experiments/templates/experiments/`
- [ ] Use Bootstrap 5 utility classes only (no custom CSS unless in `static/css/main.css`)
- [ ] Display validation errors gracefully
- [ ] Use Django template tags (`{% url %}`, `{% if %}`, etc.) safely
- [ ] Never expose raw exception text

### 5. Service logic
- [ ] Move complex business logic to `experiments/services/*.py`
- [ ] Add type hints on function signatures
- [ ] Add docstring on public functions
- [ ] Avoid importing `subprocess` in services meant for views

### 6. Tests
- [ ] Add view tests in `experiments/tests/test_views.py`
  - Test GET rendering
  - Test POST create/update
  - Test permission checks (if any)
  - Test error rendering
- [ ] Add service tests in `experiments/tests/test_services.py` (if new service)
  - Test success case
  - Test error cases
  - Test state persistence
- [ ] Run: `python manage.py test`

### 7. Documentation (optional)
- [ ] Update `README.md` if user-facing
- [ ] Add inline comments for non-obvious logic

---

## N+1 query avoidance

When querying lists or related objects:

```python
# ❌ Bad (N+1 queries)
runs = ExperimentRun.objects.all()
for run in runs:
    metrics = run.metrics.all()  # extra query per run

# ✅ Good (prefetch_related)
runs = ExperimentRun.objects.prefetch_related("metrics")
for run in runs:
    metrics = run.metrics.all()  # no extra query

# ✅ Also good (select_related for ForeignKey)
runs = ExperimentRun.objects.select_related("dataset")
for run in runs:
    name = run.dataset.name  # no extra query
```

---

## Error handling patterns

### In views
```python
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages

def some_view(request, pk):
    run = get_object_or_404(ExperimentRun, pk=pk)  # ✅
    
    try:
        run.start()
    except ValidationError as e:
        messages.error(request, f"Cannot start: {e}")  # ✅ user-friendly
        return redirect("run_detail", pk=run.pk)
    
    messages.success(request, "Run started!")
    return redirect("run_detail", pk=run.pk)
```

### In templates
```html
{% if messages %}
  <div class="alert alert-danger">
    {% for message in messages %}
      <p>{{ message }}</p>
    {% endfor %}
  </div>
{% endif %}
```

---

## Bootstrap 5 only

```html
<!-- ✅ Bootstrap utilities -->
<div class="container mt-4">
  <div class="row">
    <div class="col-md-8">
      <h1 class="mb-3">Title</h1>
      <button class="btn btn-primary">Action</button>
    </div>
  </div>
</div>

<!-- ❌ Custom CSS (unless in static/css/main.css) -->
<style>
  .my-custom-class { color: red; }
</style>
```

---

## Before merging

- [ ] All tests pass: `python manage.py test`
- [ ] Type hints on public functions: `mypy experiments/`
- [ ] No `print()` calls, logging used
- [ ] No raw exceptions in views/templates
- [ ] Follow `.github/copilot-instructions.md` rules
- [ ] Migration committed if DB changes
- [ ] Docstrings on public methods


