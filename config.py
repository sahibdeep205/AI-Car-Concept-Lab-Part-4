<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}AI Car Concept Lab{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
  <script>
  window.HCAPTCHA_SITE_KEY = {{ hcaptcha_site_key|default('', true)|tojson }};
  </script>
  <script src="https://js.hcaptcha.com/1/api.js?render=explicit&onload=hcaptchaReady" async defer></script>
</head>
<body>
  <div class="noise"></div>
  <header class="site-header">
    <a href="{{ url_for('index') }}" class="brand">AI Car Concept Lab</a>
    <nav class="nav-links">
      <a class="{% if request.endpoint == 'index' %}active{% endif %}" href="{{ url_for('index') }}">Home</a>
      <a class="{% if request.endpoint == 'studio' %}active{% endif %}" href="{{ url_for('studio') }}">Studio</a>
      <a class="{% if request.endpoint == 'history' %}active{% endif %}" href="{{ url_for('history') }}">History</a>
    </nav>
    <a href="{{ url_for('studio') }}" class="btn btn-primary small">Design Now</a>
  </header>
 
  <main>
    {% block content %}{% endblock %}
  </main>
 
  <footer class="site-footer">
    <p>Built with Flask, structured prompts, session history, secure CAPTCHA gating, and a futuristic product workflow.</p>
  </footer>
  {% block scripts %}{% endblock %}
</body>
</html>
